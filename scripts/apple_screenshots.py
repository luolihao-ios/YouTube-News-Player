"""校验真实截图来源，向唯一可编辑的平台/语言草稿追加截图并回读状态；不提交审核。"""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

from PIL import Image
import appstore as store
from capture_store_screenshots import GROUPS, LOCALES, TABS, check_raw, digest, normalized_image


def safe_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('截图路径无效')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('截图路径逃逸或文件不存在')
    return path


def validate_manifest(path, platform, locales):
    store.selected_platforms([platform])
    if not locales or len(set(locales)) != len(locales) or any(locale not in LOCALES for locale in locales):
        raise ValueError('语言必须是指定且不重复的三个本地化之一')
    path = Path(path).resolve(); document = json.loads(path.read_text(encoding='utf8'))
    if (document.get('schema') != 1 or document.get('bundle_id') != store.BUNDLE or document.get('platform') != platform or
            not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,2}', document.get('version', '')) or
            document.get('build', {}).get('configuration') != 'Debug' or
            not re.fullmatch(r'[0-9a-f]{64}', document.get('build', {}).get('executable_sha256', ''))):
        raise ValueError('截图来源 Bundle、平台、构建或版本无效')
    items = document.get('screenshots', [])
    if not items: raise ValueError('没有截图')
    counts = {}; identities = set()
    for item in items:
        group = GROUPS.get(item.get('group'))
        identity = (item.get('locale'), item.get('group'), item.get('tab'))
        if (not group or group['platform'] != platform or item.get('platform') != platform or item.get('locale') not in LOCALES or
                item.get('display_type') != group['display_type'] or item.get('tab') not in TABS or identity in identities or
                item.get('transform') != 'aspect-fit-center-rgb'):
            raise ValueError('截图平台、语言、设备、页面重复或来源不匹配')
        identities.add(identity)
        source = item.get('source', {})
        expected = 'screencapture-window' if platform == 'macos' else 'simctl'
        if source.get('method') != expected or not isinstance(source.get('pid'), int) or source['pid'] <= 0:
            raise ValueError('截图没有真实运行进程来源')
        image_path = safe_path(path.parent, item.get('path'))
        raw = safe_path(path.parent, item.get('raw_path'))
        if (digest(image_path) != item.get('sha256') or digest(image_path, 'md5') != item.get('md5') or
                digest(raw) != item.get('raw_sha256')):
            raise ValueError('截图或原图哈希不匹配')
        if check_raw(raw) != item.get('raw_size'): raise ValueError('原图尺寸不匹配')
        with Image.open(image_path) as image:
            image.load()
            if image.mode != 'RGB' or image.size != group['size'] or list(image.size) != item.get('size'):
                raise ValueError('截图必须符合 Apple 像素规格且没有透明通道')
            if image.tobytes() != normalized_image(raw, group['size']).tobytes():
                raise ValueError('截图像素不是由保留原图等比适配而来')
        key = identity[:2]; counts[key] = counts.get(key, 0) + 1
        if counts[key] > 10: raise ValueError('一个语言/设备最多 10 张截图')
    for locale in locales:
        if not any(item['locale'] == locale for item in items): raise ValueError('manifest 缺少指定语言: ' + locale)
    document['screenshots'] = [item for item in items if item['locale'] in locales]
    document['_root'] = path.parent
    return document


def plan_assets(existing, desired):
    """仅构造追加/复用计划，拒绝同名异内容；所有组完成此检查后才能写入。"""
    names = {}
    for old in existing:
        name = old['attributes'].get('fileName')
        if name in names: raise ValueError('商店已有重名截图，无法可靠匹配')
        names[name] = old
    result = []
    for item in desired:
        name = Path(item['path']).name
        old = names.get(name)
        if old and old['attributes'].get('sourceFileChecksum', '').lower() != item['md5'].lower():
            raise ValueError('商店存在同名但不同哈希截图，保留原资产并停止: ' + name)
        result.append({'item': item, 'existing_id': old['id'] if old else None})
    if len(existing) + sum(action['existing_id'] is None for action in result) > 10:
        raise ValueError('保留现有截图后超过 Apple 每设备/语言最多 10 张限制')
    return result


def validate_capture_layout(document, platform, locales):
    """工作流入口要求每个所选语言均具有本平台全部真实设备组和四页面。"""
    groups = [name for name, config in GROUPS.items() if config['platform'] == platform]
    expected = {(locale, group, tab) for locale in locales for group in groups for tab in TABS}
    actual = {(item['locale'], item['group'], item['tab']) for item in document['screenshots']}
    if actual != expected:
        raise ValueError('采集 manifest 不完整：每个所选语言必须包含本平台全部设备组与四个真实页面')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('上传地址发生重定向，停止避免转发上传头')


def upload_chunks(path, operations):
    content = Path(path).read_bytes()
    if not operations: raise ValueError('Apple 没有返回分块上传指令')
    ranges = []
    for operation in operations:
        offset = operation.get('offset'); length = operation.get('length')
        url = urllib.parse.urlparse(operation.get('url', ''))
        if (type(offset) is not int or type(length) is not int or offset < 0 or length <= 0 or offset + length > len(content) or
                url.scheme != 'https' or not url.hostname or url.username or url.password or operation.get('method') != 'PUT'):
            raise ValueError('Apple 分块上传指令无效')
        ranges.append((offset, offset + length))
    cursor = 0
    for start, end in sorted(ranges):
        if start != cursor: raise ValueError('Apple 上传分块有缺口或重叠')
        cursor = end
    if cursor != len(content): raise ValueError('Apple 上传指令没有覆盖完整文件')
    opener = urllib.request.build_opener(NoRedirect())
    for operation in operations:
        headers = {item['name']: item['value'] for item in operation.get('requestHeaders', [])}
        if any(name.lower() == 'authorization' for name in headers):
            raise ValueError('不向资产主机发送 Authorization')
        start = operation['offset']; end = start + operation['length']
        request = urllib.request.Request(operation['url'], data=content[start:end], headers=headers, method='PUT')
        with opener.open(request, timeout=120) as response:
            if response.status < 200 or response.status >= 300: raise RuntimeError('截图分块上传没有成功')


def require_complete(api, identity, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    while True:
        asset = api.call(f'appScreenshots/{identity}')['data']
        state = asset['attributes'].get('assetDeliveryState', {}).get('state')
        if state == 'COMPLETE': return asset
        if state == 'FAILED' or time.monotonic() >= deadline:
            raise RuntimeError(f'Apple 截图 {identity} 状态仍是 {state}；尚未完成，保留现有资产与报告')
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def upload(api, manifest_path, platform, locales, wait_seconds=600, report_path=None):
    document = validate_manifest(manifest_path, platform, locales)
    app = store.find_app(api)
    if not app: raise ValueError('未找到同一 Bundle 的 Apple App 记录')
    version = store.select_editable_version(api.all(f"apps/{app['id']}/appStoreVersions?limit=200"), platform)
    if version['attributes']['versionString'] != document['version']:
        raise ValueError('真实截图构建版本与本平台 Apple 可编辑草稿版本不一致')
    localizations = api.all(f"appStoreVersions/{version['id']}/appStoreVersionLocalizations?limit=200")
    groups = {}
    for item in document['screenshots']:
        groups.setdefault((item['locale'], item['display_type']), []).append(item)
    plans = []
    # 所有平台/语言/容量/同名冲突都只读预检成功后，才开始保留式追加。
    for (locale, display), desired in groups.items():
        matches = [item for item in localizations if item['attributes']['locale'] == locale]
        if len(matches) != 1: raise ValueError('本平台草稿没有唯一指定语言: ' + locale)
        localization = matches[0]
        sets = [item for item in api.all(f"appStoreVersionLocalizations/{localization['id']}/appScreenshotSets?limit=200")
                if item['attributes']['screenshotDisplayType'] == display]
        if len(sets) > 1: raise ValueError('同一设备类型具有多个截图集合，停止')
        screenshot_set = sets[0] if sets else None
        existing = api.all(f"appScreenshotSets/{screenshot_set['id']}/appScreenshots?limit=200") if screenshot_set else []
        plans.append({'locale': locale, 'display': display, 'localization': localization['id'],
                      'set': screenshot_set, 'before': [item['id'] for item in existing], 'actions': plan_assets(existing, desired)})
    report = {'app_id': app['id'], 'platform': platform, 'version_id': version['id'], 'version': document['version'],
              'locales': locales, 'assets': [], 'sets': [], 'complete': False}
    def save():
        if report_path:
            destination = Path(report_path); destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    try:
        for plan in plans:
            screenshot_set = plan['set']
            if not screenshot_set:
                screenshot_set = api.call('appScreenshotSets', 'POST', {'data': {'type': 'appScreenshotSets',
                    'attributes': {'screenshotDisplayType': plan['display']}, 'relationships': {'appStoreVersionLocalization':
                    {'data': {'type': 'appStoreVersionLocalizations', 'id': plan['localization']}}}}})['data']
            set_id = screenshot_set['id']; desired_ids = []
            plan['set_id']=set_id; plan['desired_ids']=desired_ids
            for action in plan['actions']:
                item = action['item']; identity = action['existing_id']
                if not identity:
                    path = safe_path(document['_root'], item['path'])
                    asset = api.call('appScreenshots', 'POST', {'data': {'type': 'appScreenshots',
                        'attributes': {'fileName': path.name, 'fileSize': path.stat().st_size},
                        'relationships': {'appScreenshotSet': {'data': {'type': 'appScreenshotSets', 'id': set_id}}}}})['data']
                    identity = asset['id']
                    report['assets'].append({'id': identity, 'locale': plan['locale'], 'set_id': set_id, 'state': 'RESERVED', 'sha256': item['sha256']})
                    save()
                    upload_chunks(path, asset['attributes'].get('uploadOperations', []))
                    api.call(f'appScreenshots/{identity}', 'PATCH', {'data': {'type': 'appScreenshots', 'id': identity,
                             'attributes': {'uploaded': True, 'sourceFileChecksum': item['md5']}}})
                desired_ids.append(identity)
        # Apple 异步处理。先完整上传本次图片，再等状态，避免第一张排队阻断其余素材。
        for plan in plans:
            set_id=plan['set_id']; desired_ids=plan['desired_ids']
            for action,identity in zip(plan['actions'],desired_ids):
                item=action['item']
                asset = require_complete(api, identity, wait_seconds)
                if asset['attributes'].get('sourceFileChecksum', '').lower() != item['md5'].lower():
                    raise RuntimeError('Apple 回读截图 MD5 不匹配')
                entry = {'id': identity, 'locale': plan['locale'], 'set_id': set_id, 'state': 'COMPLETE', 'sha256': item['sha256']}
                report['assets'] = [old for old in report['assets'] if old['id'] != identity] + [entry]
                save()
            expected = plan['before'] + [identity for identity in desired_ids if identity not in plan['before']]
            current = [item['id'] for item in api.all(f'appScreenshotSets/{set_id}/appScreenshots?limit=200')]
            if set(current) != set(expected) or len(current) != len(expected):
                raise RuntimeError('Apple 截图集合与预检后的追加结果不符；未覆盖并发变更')
            if current != expected:
                api.call(f'appScreenshotSets/{set_id}/relationships/appScreenshots', 'PATCH',
                         {'data': [{'type': 'appScreenshots', 'id': identity} for identity in expected]})
                current = [item['id'] for item in api.all(f'appScreenshotSets/{set_id}/appScreenshots?limit=200')]
            if current != expected: raise RuntimeError('Apple 有序截图关联回读不匹配')
            report['sets'].append({'id': set_id, 'locale': plan['locale'], 'display_type': plan['display'],
                                   'preserved_ids': plan['before'], 'ordered_ids': current})
        report['complete'] = True; save()
        return report
    except Exception as error:
        report['error'] = str(error); save(); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['validate', 'upload'])
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--platform', required=True, choices=list(store.platforms()))
    parser.add_argument('--locale', action='append', choices=list(LOCALES))
    parser.add_argument('--wait-seconds', type=int, default=600)
    parser.add_argument('--report', default='build/apple-report/screenshots.json')
    args = parser.parse_args(); locales = args.locale or list(LOCALES)
    if not 0 <= args.wait_seconds <= 600: raise SystemExit('处理状态等待时间须为 0 至 600 秒')
    document = validate_manifest(args.manifest, args.platform, locales)
    validate_capture_layout(document, args.platform, locales)
    if args.operation == 'validate':
        print(f"已离线校验 {len(document['screenshots'])} 张截图、原图像素与哈希，未访问 Apple。")
    else:
        result = upload(store.AppleAPI(), args.manifest, args.platform, locales, args.wait_seconds, args.report)
        print(f"已追加/复用并回读 {len(result['assets'])} 张 COMPLETE 截图；未提交审核或发布。")


if __name__ == '__main__': main()
