import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('apple_platforms', ROOT/'scripts/appstore.py')
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

class StoreAPI:
    def __init__(self):
        self.calls = []
        self.versions = [{'id': key, 'attributes': {'platform': platform, 'versionString': '1.0', 'appStoreState': 'PREPARE_FOR_SUBMISSION'}} for key, platform in [('ios','IOS'),('mac','MAC_OS'),('vision','VISION_OS'),('tv','TV_OS')]]
        self.infos = [{'id':'info', 'attributes':{'state':'PREPARE_FOR_SUBMISSION'}}]
        self.localizations = {'appInfos/info/appInfoLocalizations': [], **{f'appStoreVersions/{v["id"]}/appStoreVersionLocalizations': [] for v in self.versions}}
        self.corrupt_readback = False
    def all(self, path):
        self.calls.append((path,'GET',None))
        key = path.split('?')[0]
        if key == 'apps/app/appInfos': return copy.deepcopy(self.infos)
        if key == 'apps/app/appStoreVersions': return copy.deepcopy(self.versions)
        if key in {'builds','preReleaseVersions'}: return []
        if key in self.localizations:
            values = copy.deepcopy(self.localizations[key])
            if self.corrupt_readback and values:
                values[0]['attributes']['description'] = 'wrong'
            return values
        raise AssertionError(path)
    def call(self, path, method='GET', data=None):
        self.calls.append((path,method,data))
        if path.startswith('bundleIds?'): return {'data':[{'id':'bundle', 'attributes':{'identifier':store.BUNDLE,'platform':'UNIVERSAL'}}]}
        if path.startswith('apps?'): return {'data':[{'id':'app','attributes':{'bundleId':store.BUNDLE}}]}
        if method == 'POST':
            resource = data['data']; relation = 'appInfo' if resource['type']=='appInfoLocalizations' else 'appStoreVersion'
            parent = resource['relationships'][relation]['data']
            key = f'{parent["type"]}/{parent["id"]}/{resource["type"]}'
            item = {'id':f'{parent["id"]}-{resource["attributes"]["locale"]}', 'attributes':resource['attributes']}
            self.localizations[key].append(copy.deepcopy(item)); return {'data':item}
        if method == 'PATCH':
            for values in self.localizations.values():
                for value in values:
                    if value['id'] == data['data']['id']:
                        value['attributes'].update(data['data']['attributes']); return {'data':value}
        raise AssertionError(path)

class PlatformStoreTests(unittest.TestCase):
    def test_prepare_is_read_only_and_reports_every_platform_including_untouched_tv(self):
        api = StoreAPI()
        with patch.object(store,'report'), patch.object(store,'output'):
            result = store.prepare(api)
        self.assertEqual(result['app_id'], 'app')
        self.assertEqual({v['attributes']['platform'] for v in result['versions']}, {'IOS','MAC_OS','VISION_OS','TV_OS'})
        self.assertTrue(all(method=='GET' for _,method,_ in api.calls))
    def test_missing_bundle_prepare_does_not_register_it(self):
        api = StoreAPI(); original = api.call
        api.call = lambda path, method='GET', data=None: {'data':[]} if path.startswith('bundleIds?') else original(path, method, data)
        with patch.object(store,'report'), patch.object(store,'output'):
            result = store.prepare(api)
        self.assertIsNone(result['apple_bundle_id'])
    def test_metadata_targets_only_selected_platform_and_reads_back(self):
        api = StoreAPI()
        with patch.object(store,'report'):
            result = store.metadata(api, ['visionos'])
        self.assertEqual(result['platforms'], ['visionos'])
        self.assertEqual(len(api.localizations['appStoreVersions/vision/appStoreVersionLocalizations']),3)
        for key in ['ios','mac','tv']:
            self.assertEqual(api.localizations[f'appStoreVersions/{key}/appStoreVersionLocalizations'], [])
        for labels in store.LABELS.values(): self.assertEqual(labels['name'],'YouTubeNewsLive')
        attrs = api.localizations['appStoreVersions/vision/appStoreVersionLocalizations'][0]['attributes']
        self.assertIn('description',attrs); self.assertNotIn('supportUrl',attrs)
    def test_missing_selected_platform_prevents_all_mutations(self):
        api = StoreAPI(); api.versions = [v for v in api.versions if v['id']!='mac']
        with self.assertRaisesRegex(ValueError,'macos'):
            store.metadata(api, ['ios','macos','visionos'])
        self.assertTrue(all(method=='GET' for _,method,_ in api.calls))
    def test_released_and_duplicate_drafts_are_rejected(self):
        for state, duplicate in [('READY_FOR_SALE',False),('PREPARE_FOR_SUBMISSION',True)]:
            api = StoreAPI(); api.versions[0]['attributes']['appStoreState']=state
            if duplicate: api.versions.append(copy.deepcopy(api.versions[0]))
            with self.assertRaises(ValueError): store.metadata(api,['ios'])
            self.assertTrue(all(method=='GET' for _,method,_ in api.calls))
    def test_metadata_readback_failure_is_not_success(self):
        api = StoreAPI(); api.corrupt_readback=True
        with self.assertRaisesRegex(RuntimeError,'回读'):
            store.metadata(api,['ios'])
    def test_provision_reuses_only_profile_bound_to_our_bundle_and_certificate(self):
        import base64
        api = StoreAPI()
        attrs = {'profileType':'MAC_APP_STORE','profileState':'ACTIVE','expirationDate':'2099-01-01T00:00:00Z','profileContent':base64.b64encode(b'profile-content').decode()}
        good = {'id':'our-profile','attributes':attrs,'relationships':{'bundleId':{'data':{'id':'bundle'}},'certificates':{'data':[{'id':'cert'}]}}}
        bad = copy.deepcopy(good); bad['id']='other-profile'; bad['relationships']['bundleId']['data']['id']='other-app'
        original=api.call
        api.all=lambda path: [bad,good] if path.startswith('profiles?') else []
        def call(path,method='GET',data=None):
            if path.startswith('profiles/our-profile?'):
                api.calls.append((path,method,data)); return {'data':copy.deepcopy(good)}
            return original(path,method,data)
        api.call=call
        with tempfile.TemporaryDirectory() as folder,patch.dict(__import__('os').environ,{'SIGNING_CERTIFICATE_PATH':'fake'}),patch.object(store,'certificate_der',return_value=b'certificate'),patch.object(store,'match_certificate',return_value={'id':'cert','attributes':{'certificateType':'DISTRIBUTION'}}),patch.object(store,'output'):
            destination=Path(folder)/'test.profile'
            store.provision(api,str(destination),'macos')
            self.assertEqual(destination.read_bytes(),b'profile-content')
        self.assertTrue(all(method=='GET' for _,method,_ in api.calls))
        self.assertTrue(any(path.startswith('profiles/our-profile?include=') for path,_,_ in api.calls))
    def test_provision_rejects_mismatched_profile_returned_after_selection(self):
        import base64
        api=StoreAPI()
        good={'id':'our-profile','attributes':{'profileType':'IOS_APP_STORE','profileState':'ACTIVE','expirationDate':'2099-01-01T00:00:00Z','profileContent':base64.b64encode(b'profile').decode()},'relationships':{'bundleId':{'data':{'id':'bundle'}},'certificates':{'data':[{'id':'cert'}]}}}
        api.all=lambda path:[good]
        original=api.call
        def call(path,method='GET',data=None):
            if path.startswith('profiles/'):
                bad=copy.deepcopy(good); bad['relationships']['certificates']['data']=[{'id':'other-cert'}]
                return {'data':bad}
            return original(path,method,data)
        api.call=call
        with tempfile.TemporaryDirectory() as folder,patch.dict(__import__('os').environ,{'SIGNING_CERTIFICATE_PATH':'fake'}),patch.object(store,'certificate_der',return_value=b'certificate'),patch.object(store,'match_certificate',return_value={'id':'cert','attributes':{'certificateType':'DISTRIBUTION'}}):
            destination=Path(folder)/'test.profile'
            with self.assertRaises(ValueError): store.provision(api,str(destination),'ios')
            self.assertFalse(destination.exists())
    def test_marketing_version_comes_from_selected_platform_editable_draft(self):
        api=StoreAPI()
        api.versions[0]['attributes']['versionString']='1.0'
        api.versions[1]['attributes']['versionString']='2.3'
        api.versions.append({'id':'released-ios','attributes':{'platform':'IOS','versionString':'0.9','appStoreState':'READY_FOR_SALE'}})
        self.assertEqual(store.select_editable_version(api.versions,'ios')['attributes']['versionString'],'1.0')
        self.assertEqual(store.select_editable_version(api.versions,'macos')['attributes']['versionString'],'2.3')
    def test_marketing_version_selection_rejects_missing_duplicate_or_invalid_drafts(self):
        for versions in [[],[{'id':'a','attributes':{'platform':'IOS','versionString':'1.0','appStoreState':'READY_FOR_SALE'}}],
                         [{'id':key,'attributes':{'platform':'IOS','versionString':'1.0','appStoreState':'PREPARE_FOR_SUBMISSION'}} for key in ['a','b']],
                         [{'id':'a','attributes':{'platform':'IOS','versionString':'1.0;bad','appStoreState':'PREPARE_FOR_SUBMISSION'}}]]:
            with self.subTest(versions=versions),self.assertRaises(ValueError): store.select_editable_version(versions,'ios')
    def test_tvos_is_not_an_allowed_platform(self):
        with self.assertRaises(ValueError): store.selected_platforms(['tvos'])
    def test_certificate_matching_requires_unexpired_exact_der(self):
        import base64
        api = StoreAPI()
        api.all = lambda path: [{'id':'wrong','attributes':{'certificateType':'DISTRIBUTION','certificateContent':base64.b64encode(b'wrong').decode(),'expirationDate':'2099-01-01T00:00:00Z'}}]
        with self.assertRaises(ValueError): store.match_certificate(api,b'correct',{'DISTRIBUTION'})
        api.all = lambda path: [{'id':'expired','attributes':{'certificateType':'DISTRIBUTION','certificateContent':base64.b64encode(b'correct').decode(),'expirationDate':'2000-01-01T00:00:00Z'}}]
        with self.assertRaises(ValueError): store.match_certificate(api,b'correct',{'DISTRIBUTION'})
    def test_tvos_localizations_remain_intact_when_updating_all_three(self):
        api = StoreAPI()
        original = [{'id':'tv-existing','attributes':{'locale':'en-US','description':'unchanged TV draft'}}]
        api.localizations['appStoreVersions/tv/appStoreVersionLocalizations'] = copy.deepcopy(original)
        with patch.object(store,'report'): store.metadata(api,['all'])
        self.assertEqual(api.localizations['appStoreVersions/tv/appStoreVersionLocalizations'],original)
    def test_existing_metadata_is_patched_and_readback_proves_idempotency(self):
        api = StoreAPI()
        with patch.object(store,'report'):
            store.metadata(api,['ios'])
            api.calls.clear()
            store.metadata(api,['ios'])
        writes=[method for _,method,_ in api.calls if method!='GET']
        self.assertEqual(writes,['PATCH']*6)
    def test_macos_requires_separate_installer_secrets(self):
        with self.assertRaisesRegex(ValueError,'MAC_INSTALLER_P12_BASE64.*MAC_INSTALLER_P12_PASSWORD'):
            store.require_signing_secrets('macos', {})
    def test_platform_certificate_types_prevent_legacy_ios_certificate_on_mac(self):
        self.assertEqual(store.certificate_types('visionos'), {'DISTRIBUTION'})
        self.assertIn('DISTRIBUTION',store.certificate_types('macos'))
        self.assertNotIn('IOS_DISTRIBUTION',store.certificate_types('macos'))

if __name__=='__main__': unittest.main()
