"""商店版本构建关联的行为回归；所有远端操作使用内存 API。"""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def module():
    path=ROOT/'scripts/attach_store_builds.py'
    spec=importlib.util.spec_from_file_location('attach_store_builds_test',path)
    value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

class API:
    def __init__(self):
        self.calls=[]; self.polls=0; self.current=None; self.corrupt=False
        self.versions=[{'id':'ios-draft','attributes':{'platform':'IOS','versionString':'1.0','appStoreState':'PREPARE_FOR_SUBMISSION'}}]
        self.builds=[{'id':'build','attributes':{'version':'123','processingState':'VALID','expired':False},'relationships':{'app':{'data':{'id':'app','type':'apps'}}}}]
        self.prereleases={'build':{'id':'pre','attributes':{'platform':'IOS','version':'1.0'}}}
        self.states=[]
    def all(self,path):
        self.calls.append((path,'GET',None))
        if path.startswith('apps/app/appStoreVersions?'): return copy.deepcopy(self.versions)
        if path.startswith('builds?'):
            self.polls+=1
            result=copy.deepcopy(self.builds)
            if self.states:
                state=self.states.pop(0)
                if state=='MISSING': return []
                for item in result: item['attributes']['processingState']=state
            return result
        raise AssertionError(path)
    def call(self,path,method='GET',data=None):
        self.calls.append((path,method,data))
        if path.startswith('apps?'): return {'data':[{'id':'app','attributes':{'bundleId':'com.luolihao.newslive'}}]}
        if path.startswith('builds/') and path.endswith('/preReleaseVersion'):
            return {'data':copy.deepcopy(self.prereleases[path.split('/')[1]])}
        if path=='appStoreVersions/ios-draft/relationships/build':
            if method=='PATCH': self.current=data['data']; return {}
            return {'data':{'id':'wrong','type':'builds'} if self.corrupt else copy.deepcopy(self.current)}
        if path=='appStoreVersions/ios-draft': return {'data':copy.deepcopy(self.versions[0])}
        raise AssertionError(path)

class AttachTests(unittest.TestCase):
    def attach(self,api,**kwargs):
        mod=module()
        with patch.object(mod.store,'report') as report:
            result=mod.attach(api,'app','123','ios',**kwargs)
        return result,report
    def test_valid_exact_build_is_attached_and_read_back(self):
        api=API(); result,_=self.attach(api,timeout=0)
        self.assertEqual(result['build_id'],'build'); self.assertTrue(result['verified'])
        writes=[call for call in api.calls if call[1]!='GET']
        self.assertEqual(len(writes),1); self.assertEqual(writes[0][2],{'data':{'type':'builds','id':'build'}})
    def test_each_native_platform_attaches_its_own_build(self):
        for platform,apple in [('macos','MAC_OS'),('visionos','VISION_OS')]:
            api=API(); api.versions[0]['attributes']['platform']=apple; api.prereleases['build']['attributes']['platform']=apple
            mod=module()
            with self.subTest(platform=platform),patch.object(mod.store,'report'):
                result=mod.attach(api,'app','123',platform,timeout=0)
            self.assertTrue(result['verified']); self.assertEqual(result['platform'],platform)
    def test_draft_submitted_while_waiting_prevents_write(self):
        api=API(); original=api.call
        def call(path,method='GET',data=None):
            if path=='appStoreVersions/ios-draft':
                item=copy.deepcopy(api.versions[0]); item['attributes']['appStoreState']='WAITING_FOR_REVIEW'
                return {'data':item}
            return original(path,method,data)
        api.call=call
        with self.assertRaises(ValueError): self.attach(api,timeout=0)
        self.assertFalse(any(method!='GET' for _,method,_ in api.calls))
    def test_same_build_is_idempotent_without_patch(self):
        api=API(); api.current={'type':'builds','id':'build','meta':{'extra':'ignored'}}
        result,_=self.attach(api,timeout=0)
        self.assertTrue(result['verified']); self.assertFalse(any(method!='GET' for _,method,_ in api.calls))
    def test_platform_marketing_version_and_number_must_all_match(self):
        for field,value in [('platform','MAC_OS'),('version','1.0.0'),('number','122'),('app','other')]:
            api=API()
            if field=='number': api.builds[0]['attributes']['version']=value
            elif field=='app': api.builds[0]['relationships']['app']['data']['id']=value
            else: api.prereleases['build']['attributes'][field]=value
            with self.subTest(field=field), self.assertRaises((ValueError,TimeoutError)): self.attach(api,timeout=0)
            self.assertFalse(any(method!='GET' for _,method,_ in api.calls))
    def test_duplicate_exact_builds_are_rejected(self):
        api=API(); second=copy.deepcopy(api.builds[0]); second['id']='duplicate'; api.builds.append(second); api.prereleases['duplicate']=api.prereleases['build']
        with self.assertRaises(ValueError): self.attach(api,timeout=0)
    def test_processing_polls_and_valid_transition_attaches(self):
        api=API(); api.states=['MISSING','PROCESSING','VALID']; sleeps=[]
        result,_=self.attach(api,timeout=90,sleep=sleeps.append)
        self.assertTrue(result['verified']); self.assertEqual(sleeps,[30,30])
    def test_processing_timeout_is_reported_without_patch(self):
        mod=module(); api=API(); api.states=['PROCESSING']*4
        with patch.object(mod.store,'report') as report:
            with self.assertRaises(TimeoutError): mod.attach(api,'app','123','ios',timeout=30,sleep=lambda _:None)
        self.assertTrue(report.called); self.assertFalse(any(method!='GET' for _,method,_ in api.calls))
    def test_invalid_or_expired_build_fails_without_waiting(self):
        for state,expired in [('INVALID',False),('FAILED',False),('VALID',True)]:
            api=API(); api.builds[0]['attributes'].update(processingState=state,expired=expired); sleeps=[]
            with self.subTest(state=state,expired=expired),self.assertRaises(ValueError): self.attach(api,timeout=90,sleep=sleeps.append)
            self.assertEqual(sleeps,[])
    def test_released_draft_wrong_app_and_tvos_are_rejected(self):
        api=API(); api.versions[0]['attributes']['appStoreState']='READY_FOR_SALE'
        with self.assertRaises(ValueError): self.attach(api,timeout=0)
        mod=module()
        for app,platform in [('other','ios'),('app','tvos')]:
            with patch.object(mod.store,'report'),self.assertRaises(ValueError): mod.attach(API(),app,'123',platform,timeout=0)
    def test_wrong_relationship_readback_is_failure(self):
        api=API(); api.corrupt=True
        with self.assertRaises(RuntimeError): self.attach(api,timeout=0)

if __name__=='__main__': unittest.main()
