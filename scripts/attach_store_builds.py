"""把本次运行中已处理成功的确切构建关联到对应平台商店草稿并回读。"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('apple_attach_store',ROOT/'scripts/appstore.py')
store=importlib.util.module_from_spec(spec); spec.loader.exec_module(store)

def exact_build(api,app_id,build_number,platform,marketing_version):
    apple_platform=store.platforms()[platform]['apple_platform']
    builds=api.all(store.query('builds',**{'filter[app]':app_id,'filter[version]':build_number,
                    'filter[preReleaseVersion.platform]':apple_platform,'filter[preReleaseVersion.version]':marketing_version,
                    'include':'app,preReleaseVersion','limit':'200'}))
    matches=[]
    for build in builds:
        if build['attributes'].get('version')!=build_number: continue
        app=build.get('relationships',{}).get('app',{}).get('data') or {}
        if app.get('type')!='apps' or app.get('id')!=app_id:
            raise ValueError('Apple 返回构建的 App 关系与本应用不匹配，拒绝跨应用操作')
        prerelease=api.call(f"builds/{build['id']}/preReleaseVersion").get('data')
        if not prerelease: continue
        attrs=prerelease['attributes']
        if attrs.get('platform')==apple_platform and attrs.get('version')==marketing_version:
            matches.append(build)
    if len(matches)>1: raise ValueError('本 App、构建号、平台及营销版本不能唯一匹配构建')
    return matches[0] if matches else None

def attach(api,app_id,build_number,platform,*,timeout=900,sleep=time.sleep):
    store.selected_platforms([platform])
    result={'app_id':app_id,'build_number':build_number,'platform':platform,'verified':False,'polls':0,'processing_state':'MISSING'}
    try:
        if not re.fullmatch(r'[0-9]+',str(build_number)): raise ValueError('构建号必须为本次运行的数字构建号')
        if not 0<=timeout<=900: raise ValueError('轮询上限必须在 0 到 900 秒之间')
        app=store.find_app(api)
        if not app or app['id']!=app_id: raise ValueError('App ID 与当前 Bundle 的唯一实际记录不匹配')
        version=store.select_editable_version(api.all(f'apps/{app_id}/appStoreVersions?limit=200'),platform)
        marketing_version=version['attributes']['versionString']
        result.update(app_store_version_id=version['id'],marketing_version=marketing_version)
        started=time.monotonic(); waited=0
        while True:
            build=exact_build(api,app_id,build_number,platform,marketing_version)
            result['polls']+=1
            state=build['attributes'].get('processingState') if build else 'MISSING'
            result['processing_state']=state
            if build:
                result['build_id']=build['id']
                if build['attributes'].get('expired') is not False:
                    raise ValueError('匹配的构建已过期或无法确认有效期，未关联')
                if state in {'FAILED','INVALID'}: raise ValueError('匹配的构建处理失败: '+state)
                if state=='VALID': break
                if state!='PROCESSING': raise ValueError('匹配构建的处理状态未知: '+str(state))
            elapsed=max(time.monotonic()-started,waited)
            if elapsed>=timeout:
                raise TimeoutError(f'等待本次 {platform} 构建 {build_number} 超时，最终状态 {state}；未关联其他构建')
            delay=min(30,timeout-elapsed)
            print(f'{platform} 构建 {build_number}: {state}；等待 Apple 处理。',flush=True)
            sleep(delay); waited+=delay
        # 处理等待期间用户可能提交审核或修改版本，写入前重新校验同一草稿。
        fresh=api.call(f"appStoreVersions/{version['id']}")['data']
        checked=store.select_editable_version([fresh],platform)
        if checked['id']!=version['id'] or checked['attributes']['versionString']!=marketing_version:
            raise ValueError('等待期间商店草稿版本已变化，拒绝关联')
        path=f"appStoreVersions/{version['id']}/relationships/build"
        expected={'type':'builds','id':build['id']}
        current=api.call(path).get('data')
        result['already_attached']=bool(current and current.get('type')=='builds' and current.get('id')==build['id'])
        if not result['already_attached']: api.call(path,'PATCH',{'data':expected})
        after=api.call(path).get('data')
        if not after or after.get('type')!='builds' or after.get('id')!=build['id']:
            raise RuntimeError('商店版本 build 关系回读不匹配，不能确认关联成功')
        result['verified']=True
        print(json.dumps(result,ensure_ascii=False))
        return result
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        store.report('attach-'+platform,result)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',required=True,choices=['ios','macos','visionos'])
    parser.add_argument('--app-id',default=os.environ.get('APP_STORE_ID',''))
    parser.add_argument('--build-number',default=os.environ.get('BUILD_NUMBER',''))
    parser.add_argument('--timeout',type=int,default=900)
    args=parser.parse_args()
    if not args.app_id or not args.build_number: parser.error('需要实际 --app-id 与本次 --build-number')
    attach(store.AppleAPI(),args.app_id,args.build_number,args.platform,timeout=args.timeout)

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('error: '+str(error),file=sys.stderr); sys.exit(1)
