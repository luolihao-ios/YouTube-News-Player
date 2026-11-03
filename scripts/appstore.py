"""YouTubeNewsLive 的 Apple 记录只读检查、限定平台商店资料与签名管理。"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BUNDLE = 'com.luolihao.newslive'
ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    'en-US': {'name': 'YouTubeNewsLive', 'subtitle': 'Live news. More perspectives.'},
    'zh-Hans': {'name': 'YouTubeNewsLive', 'subtitle': '即时新闻，掌握世界每一刻'},
    'zh-Hant': {'name': 'YouTubeNewsLive', 'subtitle': '即時新聞，掌握世界每一刻'},
}
EDITABLE = {'PREPARE_FOR_SUBMISSION', 'DEVELOPER_REJECTED', 'REJECTED', 'METADATA_REJECTED'}

class AppleAPI:
    def __init__(self):
        import jwt
        names = ['APP_STORE_CONNECT_API_KEY_ID', 'APP_STORE_CONNECT_ISSUER_ID', 'APP_STORE_CONNECT_API_KEY_BASE64']
        missing = [name for name in names if not os.environ.get(name)]
        if missing: raise ValueError('缺少仓库 Secret: ' + ', '.join(missing))
        key = base64.b64decode(os.environ[names[2]])
        now = int(time.time())
        self.token = jwt.encode({'iss': os.environ[names[1]], 'iat': now-10, 'exp': now+1100, 'aud': 'appstoreconnect-v1'}, key,
                                algorithm='ES256', headers={'kid': os.environ[names[0]], 'typ': 'JWT'})

    def call(self, path, method='GET', data=None):
        if path.startswith('https://api.appstoreconnect.apple.com/'):
            url = path
        elif '://' in path or path.startswith('//'):
            raise ValueError('拒绝向 Apple 以外的主机发送认证')
        else: url = 'https://api.appstoreconnect.apple.com/v1/' + path
        request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                         headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            try: details = json.load(error).get('errors', [])
            except (ValueError, OSError): details = []
            safe = [{'status': item.get('status'), 'code': item.get('code'), 'detail': item.get('detail')} for item in details]
            raise RuntimeError(f'Apple API HTTP {error.code}: ' + json.dumps(safe, ensure_ascii=False)) from None

    def all(self, path):
        items = []
        while path:
            result = self.call(path); items.extend(result.get('data', [])); path = result.get('links', {}).get('next')
        return items

def platforms():
    return json.loads((ROOT/'Config/platforms.json').read_text(encoding='utf8'))

def selected_platforms(values=None):
    values = list(platforms()) if not values or values == ['all'] else values
    if not values or any(value not in platforms() for value in values) or len(set(values)) != len(values):
        raise ValueError('平台仅支持 ios、macos、visionos，禁止处理 tvOS')
    return values

def query(path, **params):
    return path + '?' + urllib.parse.urlencode(params)

def find_bundle(api):
    matches = api.call(query('bundleIds', **{'filter[identifier]': BUNDLE, 'limit': '10'}))['data']
    if len(matches) > 1 or (matches and matches[0]['attributes']['identifier'] != BUNDLE):
        raise ValueError('不能唯一确认 YouTubeNewsLive 的 Bundle ID')
    return matches[0] if matches else None

def ensure_bundle(api):
    """兼容原入口；只在明确 provision 时才允许注册。prepare 不调用此函数。"""
    bundle = find_bundle(api)
    if bundle: return bundle
    return api.call('bundleIds', 'POST', {'data': {'type': 'bundleIds', 'attributes': {'identifier': BUNDLE, 'name': 'YouTubeNewsLive', 'platform': 'IOS'}}})['data']

def unique_app(items):
    if not items: return None
    if len(items) != 1 or items[0]['attributes']['bundleId'] != BUNDLE:
        raise ValueError('不能唯一确认 YouTubeNewsLive 应用记录，停止操作其他应用')
    return items[0]

def find_app(api):
    return unique_app(api.call(query('apps', **{'filter[bundleId]': BUNDLE, 'limit': '10'}))['data'])

def next_build_number(versions, run_number):
    existing = [int(value) for value in versions if str(value).isdigit()]
    return max(int(run_number), max(existing, default=0) + 1)

def output(name, value):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf8') as handle: handle.write(f'{name}={value}\n')

def report(name, data):
    destination = ROOT/'build/apple-report'
    destination.mkdir(parents=True, exist_ok=True)
    (destination / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')

def prepare(api):
    """仅 GET：同时报告取消范围内的 tvOS，但不改变任何 Apple 资源。"""
    bundle = find_bundle(api)
    app = find_app(api)
    result = {'bundle_id': BUNDLE, 'apple_bundle_id': bundle['id'] if bundle else None,
              'bundle_platform': bundle['attributes'].get('platform') if bundle else None,
              'record_ready': app is not None, 'app_id': app['id'] if app else None,
              'versions': [], 'builds': [], 'app_infos': [], 'pre_release_versions': []}
    output('record_ready', 'true' if app else 'false')
    if bundle: output('bundle_resource_id', bundle['id'])
    if app:
        output('app_id', app['id'])
        result['versions'] = api.all(f"apps/{app['id']}/appStoreVersions?limit=200")
        result['app_infos'] = api.all(f"apps/{app['id']}/appInfos?limit=50")
        result['builds'] = api.all(query('builds', **{'filter[app]': app['id'], 'include': 'preReleaseVersion', 'limit': '200'}))
        result['pre_release_versions'] = api.all(query('preReleaseVersions', **{'filter[app]': app['id'], 'limit': '200'}))
        prerelease = {item['id']:item['attributes'] for item in result['pre_release_versions']}
        for build in result['builds']:
            relation = build.get('relationships',{}).get('preReleaseVersion',{}).get('data') or {}
            build['platform'] = prerelease.get(relation.get('id'),{}).get('platform')
        for item in result['versions']:
            item['localizations'] = api.all(f"appStoreVersions/{item['id']}/appStoreVersionLocalizations?limit=200")
        for item in result['app_infos']:
            item['localizations'] = api.all(f"appInfos/{item['id']}/appInfoLocalizations?limit=200")
        number = next_build_number([item['attributes']['version'] for item in result['builds']], os.environ.get('GITHUB_RUN_NUMBER', '1'))
        output('build_number', number); result['next_build'] = number
    else:
        result['required_action'] = '在 App Store Connect 新建 YouTubeNewsLive，选择 Bundle ID com.luolihao.newslive。脚本不会新建 App。'
    report('prepare', result)
    print(json.dumps(result, ensure_ascii=False))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf8') as handle:
            handle.write('## YouTubeNewsLive Apple 只读报告\n\n' + (f"已找到 App `{app['id']}`，版本/语言/二进制见附件。" if app else result['required_action']) + '\n')
    return result

def state(item):
    attrs = item['attributes']
    return attrs.get('appVersionState') or attrs.get('state') or attrs.get('appStoreState')

def version_labels(platform, locale):
    device = platforms()[platform]['name']
    if locale == 'en-US':
        description = (f'Follow live news on {device} with YouTubeNewsLive. Browse news channels, search for a channel, and keep your favorites close at hand. '
                       'Switch between live broadcasts to explore different perspectives.\n\n'
                       'Videos play through the official YouTube embedded player. Availability depends on the broadcaster, your region, and YouTube. '
                       'An internet connection is required. YouTubeNewsLive is an independent app and is not affiliated with or endorsed by YouTube or the news channels. '
                       'All video content and trademarks belong to their respective owners.')
        if platform != 'ios': description += '\n\nUse a native sidebar and a flexible window to browse channels and watch the news.'
        return {'description':description, 'keywords':'news,live,broadcast,world,channels,headlines,favorites', 'promotionalText':'Explore live news channels and follow the stories that matter to you.'}
    if locale == 'zh-Hans':
        description = (f'使用 YouTubeNewsLive，在 {device} 上关注新闻直播。浏览新闻频道、搜索频道、收藏常看的频道，在不同直播间切换，从不同角度了解正在发生的新闻。\n\n'
                       '视频通过 YouTube 官方嵌入式播放器播放。直播是否可观看取决于频道方、所在地区及 YouTube 服务，需要互联网连接。'
                       'YouTubeNewsLive 为独立应用，与 YouTube 及新闻频道不存在隶属或官方背书关系。视频内容与商标归各自权利人所有。')
        if platform != 'ios': description += '\n\n使用原生侧栏与可调整窗口，方便浏览频道和观看新闻。'
        return {'description':description,'keywords':'新闻,直播,国际,频道,即时,收藏,资讯','promotionalText':'浏览新闻直播频道，收藏常看内容，关注世界正在发生的故事。'}
    description = (f'使用 YouTubeNewsLive，在 {device} 上關注新聞直播。瀏覽新聞頻道、搜尋頻道、收藏常看的頻道，在不同直播間切換，從不同角度了解正在發生的新聞。\n\n'
                   '影片透過 YouTube 官方嵌入式播放器播放。直播是否可觀看取決於頻道方、所在地區及 YouTube 服務，需要網際網路連線。'
                   'YouTubeNewsLive 為獨立應用程式，與 YouTube 及新聞頻道不存在隸屬或官方背書關係。影片內容與商標歸各自權利人所有。')
    if platform != 'ios': description += '\n\n使用原生側邊欄與可調整視窗，方便瀏覽頻道和觀看新聞。'
    return {'description':description,'keywords':'新聞,直播,國際,頻道,即時,收藏,資訊','promotionalText':'瀏覽新聞直播頻道，收藏常看內容，關注世界正在發生的故事。'}

def upsert_localizations(api, resource_type, parent_type, parent_id, desired):
    path = f'{parent_type}/{parent_id}/{resource_type}?limit=200'
    before = {item['attributes']['locale']: item for item in api.all(path)}
    relation = 'appInfo' if parent_type == 'appInfos' else 'appStoreVersion'
    for locale, attrs in desired.items():
        if locale in before:
            identity = before[locale]['id']
            api.call(f'{resource_type}/{identity}', 'PATCH', {'data': {'type':resource_type, 'id':identity, 'attributes':attrs}})
        else:
            api.call(resource_type, 'POST', {'data':{'type':resource_type,'attributes':{'locale':locale,**attrs},
                     'relationships':{relation:{'data':{'type':parent_type,'id':parent_id}}}}})
    after = {item['attributes']['locale']: item['attributes'] for item in api.all(path)}
    for locale, attrs in desired.items():
        if any(after.get(locale,{}).get(key)!=value for key,value in attrs.items()):
            raise RuntimeError('商店资料回读不匹配: '+parent_id+' '+locale)
    return after

def metadata(api, requested=None):
    chosen = selected_platforms(requested)
    app = find_app(api)
    if not app: raise ValueError('尚无 YouTubeNewsLive App Store 应用记录，请先在网页创建')
    infos = [item for item in api.all(f"apps/{app['id']}/appInfos?limit=50") if state(item) in EDITABLE]
    if len(infos)!=1: raise ValueError('没有唯一可编辑的应用共用资料，未改动已发布记录')
    versions = api.all(f"apps/{app['id']}/appStoreVersions?limit=200")
    targets = {}
    # 全部预检成功后才开始写入，避免误改其他平台或遇到缺失草稿后部分写入。
    for platform in chosen:
        matches = [item for item in versions if item['attributes']['platform']==platforms()[platform]['apple_platform'] and state(item) in EDITABLE]
        if len(matches)!=1: raise ValueError('没有唯一可编辑的平台草稿: '+platform)
        targets[platform] = matches[0]
    for values in LABELS.values():
        if any(not value or len(value)>30 for value in values.values()): raise ValueError('名称/副标题超过 Apple 30 字符限制')
    result = {'app_id':app['id'],'platforms':chosen,'shared_app_info':infos[0]['id'], 'versions':{}}
    result['shared_localizations'] = upsert_localizations(api,'appInfoLocalizations','appInfos',infos[0]['id'],LABELS)
    for platform, version in targets.items():
        desired = {locale:version_labels(platform,locale) for locale in LABELS}
        if any(len(attrs['description'])>4000 or len(attrs['keywords'].encode('utf8'))>100 or len(attrs['promotionalText'])>170 for attrs in desired.values()):
            raise ValueError('版本资料超过 Apple 长度限制')
        result['versions'][platform] = {'id':version['id'],'localizations':upsert_localizations(api,'appStoreVersionLocalizations','appStoreVersions',version['id'],desired)}
    report('metadata',result)
    print('已写入并回读所选平台三语言商店资料；未操作 TV_OS 版本、URL、截图、审核或发布。')
    return result

def certificate_types(platform):
    return {'DISTRIBUTION','IOS_DISTRIBUTION'} if platform=='ios' else {'DISTRIBUTION','MAC_APP_DISTRIBUTION'} if platform=='macos' else {'DISTRIBUTION'}

def require_signing_secrets(platform, env):
    selected_platforms([platform])
    names = ['IOS_SIGNING_CERTIFICATE_BASE64','IOS_SIGNING_CERTIFICATE_PASSWORD']
    if platform=='macos': names += ['MAC_INSTALLER_P12_BASE64','MAC_INSTALLER_P12_PASSWORD']
    missing = [name for name in names if not env.get(name)]
    if missing: raise ValueError('缺少仓库 Secret: '+', '.join(missing))

def certificate_der(path, password_variable):
    command = ['openssl','pkcs12','-in',str(path),'-clcerts','-nokeys','-passin','env:'+password_variable]
    cert = subprocess.run(command,capture_output=True)
    if cert.returncode: cert = subprocess.run(command+['-legacy'],capture_output=True)
    if cert.returncode: raise ValueError('无法从现有 P12 读取签名证书，未输出密码')
    return subprocess.run(['openssl','x509','-outform','DER'],input=cert.stdout,capture_output=True,check=True).stdout

def match_certificate(api, der, allowed):
    digest = hashlib.sha256(der).digest()
    now = datetime.now(timezone.utc)
    matches = []
    for item in api.all('certificates?limit=200'):
        attrs = item['attributes']
        expiry = attrs.get('expirationDate')
        if expiry and datetime.fromisoformat(expiry.replace('Z','+00:00'))<=now: continue
        if attrs.get('certificateType') in allowed and hashlib.sha256(base64.b64decode(attrs['certificateContent'])).digest()==digest:
            matches.append(item)
    if len(matches)!=1: raise ValueError('现有 P12 未对应本团队唯一有效的所需发行证书: '+','.join(sorted(allowed)))
    return matches[0]

def provision(api, destination, platform='ios'):
    selected_platforms([platform])
    bundle = find_bundle(api)
    if not bundle: raise ValueError('本应用 Bundle ID 未注册，未自动创建其他平台记录')
    bundle_platform = bundle['attributes'].get('platform')
    permitted = {'UNIVERSAL','MAC_OS'} if platform=='macos' else {'UNIVERSAL','IOS'}
    if bundle_platform not in permitted:
        raise ValueError(f'Bundle 平台 {bundle_platform} 不支持 {platform}，请在开发者后台启用本 App ID 所需平台；未自动修改标识符')
    cert = match_certificate(api,certificate_der(os.environ['SIGNING_CERTIFICATE_PATH'],'IOS_SIGNING_CERTIFICATE_PASSWORD'),certificate_types(platform))
    certificate_id = cert['id']; profile_type = platforms()[platform]['profile_type']
    profiles = api.all(query('profiles',**{'filter[profileType]':profile_type,'filter[profileState]':'ACTIVE','include':'bundleId,certificates','limit':'200'}))
    def compatible(profile):
        attrs = profile['attributes']; rel = profile.get('relationships',{})
        expiration = attrs.get('expirationDate')
        return (attrs.get('profileType')==profile_type and attrs.get('profileState')=='ACTIVE' and
                (not expiration or datetime.fromisoformat(expiration.replace('Z','+00:00'))>datetime.now(timezone.utc)) and
                rel.get('bundleId',{}).get('data',{}).get('id')==bundle['id'] and
                [item['id'] for item in rel.get('certificates',{}).get('data',[])]==[certificate_id])
    matches = [item for item in profiles if compatible(item)]
    if matches: profile = api.call(f"profiles/{matches[0]['id']}?include=bundleId,certificates")['data']
    else:
        profile = api.call('profiles','POST',{'data':{'type':'profiles','attributes':{'name':'YouTubeNewsLive '+platform+' '+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'),'profileType':profile_type},
                  'relationships':{'bundleId':{'data':{'type':'bundleIds','id':bundle['id']}},'certificates':{'data':[{'type':'certificates','id':certificate_id}]}}}})['data']
    if not matches: profile = api.call(f"profiles/{profile['id']}?include=bundleId,certificates")['data']
    if not compatible(profile): raise ValueError('返回的描述文件与本应用、平台或签名证书不匹配')
    Path(destination).write_bytes(base64.b64decode(profile['attributes']['profileContent']))
    output('certificate_type',cert['attributes']['certificateType'])
    print('已准备仅属于 YouTubeNewsLive 的 '+platform+' App Store 描述文件。')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','inspect','metadata','provision'])
    parser.add_argument('--platform',choices=['all','ios','macos','visionos'],default=None)
    parser.add_argument('--profile-output',default='')
    args = parser.parse_args(); api = AppleAPI()
    if args.operation in {'prepare','inspect'}: prepare(api)
    elif args.operation=='metadata': metadata(api,[args.platform] if args.platform else None)
    elif args.operation=='provision':
        if not args.profile_output or args.platform=='all': parser.error('provision 需要 --profile-output 和具体 --platform')
        provision(api,args.profile_output,args.platform or 'ios')

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('error: '+str(error),file=sys.stderr); sys.exit(1)
