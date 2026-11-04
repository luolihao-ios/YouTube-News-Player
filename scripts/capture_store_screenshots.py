"""在 macOS 实际构建、启动三平台 App，采集原图及可审计的商店截图。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
import uuid

from PIL import Image, ImageStat
import appstore as store

ROOT = Path(__file__).resolve().parents[1]
TABS = ('home', 'channels', 'favorites', 'settings')
LOCALES = {'en-US': ('en', 'en_US'), 'zh-Hans': ('zh-Hans', 'zh_CN'), 'zh-Hant': ('zh-Hant', 'zh_TW')}
# Apple 官方 ScreenshotDisplayType 与截图规格；不包含已取消的 tvOS。
# https://developer.apple.com/documentation/appstoreconnectapi/screenshotdisplaytype
# https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications
GROUPS = {
    'iphone': {'platform': 'ios', 'display_type': 'APP_IPHONE_67', 'size': (1320, 2868)},
    'ipad': {'platform': 'ios', 'display_type': 'APP_IPAD_PRO_3GEN_129', 'size': (2064, 2752)},
    'mac': {'platform': 'macos', 'display_type': 'APP_DESKTOP', 'size': (1440, 900)},
    'vision': {'platform': 'visionos', 'display_type': 'APP_APPLE_VISION_PRO', 'size': (3840, 2160)},
}


def digest(path, algorithm='sha256'):
    return hashlib.new(algorithm, Path(path).read_bytes()).hexdigest()


def normalized_image(path, size):
    """只等比缩放、居中留边并去透明；不裁切、不生成或覆盖应用内容。"""
    with Image.open(path) as original:
        original.load()
        image = original.convert('RGBA')
    background = Image.new('RGBA', image.size, (18, 18, 20, 255))
    background.alpha_composite(image)
    image = background.convert('RGB')
    factor = min(size[0] / image.width, size[1] / image.height)
    dimensions = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    if dimensions != image.size:
        image = image.resize(dimensions, Image.Resampling.LANCZOS)
    result = Image.new('RGB', size, (18, 18, 20))
    result.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return result


def check_raw(path):
    with Image.open(path) as image:
        image.load()
        if min(image.size) < 400 or sum(ImageStat.Stat(image.convert('RGB')).stddev) < 5:
            raise ValueError('截图为空、过小或近乎纯色，不能证明真实 App 已显示')
        return list(image.size)


def prepare_image(raw, destination, platform, locale, group, tab, source):
    if platform not in store.platforms() or group not in GROUPS or GROUPS[group]['platform'] != platform:
        raise ValueError('截图设备组与平台不匹配')
    launch_arguments(tab, locale)
    raw = Path(raw).resolve(); destination = Path(destination).resolve()
    raw_size = check_raw(raw)
    relative_raw = raw.relative_to(destination).as_posix()
    image = normalized_image(raw, GROUPS[group]['size'])
    folder = destination / locale / group
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / (tab + '.png')
    image.save(temporary)
    sha = digest(temporary)
    target = folder / (f'{TABS.index(tab)+1:02}-{tab}-{sha[:16]}.png')
    if target.exists() and digest(target) != sha: raise ValueError('截图目标已存在且哈希不同')
    temporary.replace(target)
    return {'path': target.relative_to(destination).as_posix(), 'raw_path': relative_raw,
            'sha256': sha, 'md5': digest(target, 'md5'), 'raw_sha256': digest(raw),
            'size': list(image.size), 'raw_size': raw_size, 'platform': platform, 'locale': locale,
            'group': group, 'display_type': GROUPS[group]['display_type'], 'tab': tab,
            'source': source, 'transform': 'aspect-fit-center-rgb',
            'captured_at': datetime.now(timezone.utc).isoformat()}


def launch_arguments(tab, locale):
    if tab not in TABS or locale not in LOCALES: raise ValueError('不支持的真实页面或语言')
    language, region = LOCALES[locale]
    return ['--capture-tab', tab, '-AppleLanguages', '(' + language + ')', '-AppleLocale', region]


def run(command, capture=False, timeout=900):
    result = subprocess.run([str(part) for part in command], cwd=ROOT, capture_output=capture, timeout=timeout)
    if result.returncode:
        detail = ''
        if capture and result.stderr:
            detail = result.stderr.decode('utf8', errors='replace')[-3000:]
            for name, value in os.environ.items():
                if value and any(marker in name for marker in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET')):
                    detail = detail.replace(value, '[已隐去凭据]')
        raise RuntimeError(f'{command[0]} 执行失败 (exit {result.returncode})；{detail or "查看构建日志/原图附件"}')
    return result.stdout.decode('utf8') if capture else None


def select_runtime(runtimes, platform):
    marker = {'ios': '.iOS-', 'visionos': '.xrOS-'}[platform]
    matching = [item for item in runtimes if marker in item.get('identifier', '') and item.get('isAvailable') is True]
    if not matching: raise ValueError('没有真正可用的 ' + platform + ' simulator runtime')
    return max(matching, key=lambda item: tuple(int(part) for part in re.findall(r'\d+', item.get('version', '0'))))


def ensure_runtime(platform, download, destination):
    def inventory():
        data = json.loads(run(['xcrun', 'simctl', 'list', '--json'], capture=True))
        (destination / 'simctl-inventory.json').write_text(json.dumps(data, indent=2), encoding='utf8')
        return data
    data = inventory()
    try: runtime = select_runtime(data['runtimes'], platform)
    except ValueError:
        if not download: raise
        print('下载缺失 runtime 后将重新读取 simctl，下载成功本身不代表可用。', flush=True)
        run(['xcodebuild', '-downloadPlatform', 'iOS' if platform == 'ios' else 'visionOS'], timeout=1800)
        data = inventory(); runtime = select_runtime(data['runtimes'], platform)
    return runtime, data['devicetypes']


def select_device_type(types, group, runtime=None):
    if group == 'iphone': matches = [item for item in types if item['name'] == 'iPhone 17 Pro Max']
    elif group == 'ipad': matches = [item for item in types if 'iPad Pro' in item['name'] and '13-inch' in item['name']]
    else: matches = [item for item in types if 'Apple Vision Pro' in item['name']]
    if runtime is not None:
        supported={item['identifier'] for item in runtime.get('supportedDeviceTypes',[])}
        matches=[item for item in matches if item['identifier'] in supported]
    if not matches: raise ValueError('未找到与所选 runtime 兼容的真实模拟设备类型: ' + group)
    return matches[-1]


def build(platform, destination, version=None):
    config = store.platforms()[platform]
    derived = destination / 'DerivedData'
    command = ['xcodebuild', '-project', 'NewsLive.xcodeproj', '-scheme', config['scheme'], '-configuration', 'Debug',
               '-destination', config.get('simulator_destination', config['destination']), '-derivedDataPath', derived,
               'CODE_SIGNING_ALLOWED=NO', 'SWIFT_ACTIVE_COMPILATION_CONDITIONS=DEBUG STORE_SCREENSHOTS']
    if version:
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,2}', version): raise ValueError('构建版本格式无效')
        command.append('MARKETING_VERSION=' + version)
    command.append('build')
    run(command, timeout=1500)
    apps = list((derived / 'Build/Products').glob('Debug*/NewsLive.app'))
    if len(apps) != 1: raise ValueError('没有唯一实际编译 App 成品')
    app = apps[0]
    info = plistlib.loads((app / ('Contents/Info.plist' if platform == 'macos' else 'Info.plist')).read_bytes())
    if info.get('CFBundleIdentifier') != store.BUNDLE or info.get('CFBundleDisplayName') != 'YouTubeNewsLive':
        raise ValueError('实际二进制 Bundle ID 或名称不匹配')
    expected = {'ios': 'iphonesimulator', 'macos': 'macosx', 'visionos': 'xrsimulator'}[platform]
    if info.get('DTPlatformName') != expected: raise ValueError('实际二进制不是所选平台原生成品')
    if not info.get('YouTubeAPIKey') or '$(' in info['YouTubeAPIKey']: raise ValueError('缺少真实 YouTube API 配置')
    executable = app / ('Contents/MacOS' if platform == 'macos' else '') / info['CFBundleExecutable']
    if not executable.is_file() or executable.stat().st_size < 1000: raise ValueError('实际可执行文件不存在或无效')
    if version and info.get('CFBundleShortVersionString') != version: raise ValueError('实际构建版本与请求不符')
    return app, executable, {'configuration': 'Debug', 'scheme': config['scheme'], 'platform': expected,
                              'version': info['CFBundleShortVersionString'], 'build_number': info['CFBundleVersion'],
                              'executable_sha256': digest(executable)}


WINDOW_HELPER = r'''
import AppKit
import CoreGraphics
import Foundation
let pid = pid_t(CommandLine.arguments[1])!
guard let app = NSRunningApplication(processIdentifier: pid), app.bundleIdentifier == "com.luolihao.newslive" else {
    fputs("无法确认本 App 进程\n", stderr); exit(2)
}
app.activate(options: [.activateIgnoringOtherApps])
Thread.sleep(forTimeInterval: 1)
guard let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else { exit(3) }
let matches = windows.filter {
    ($0[kCGWindowOwnerPID as String] as? Int) == Int(pid) &&
    ($0[kCGWindowLayer as String] as? Int) == 0 &&
    (($0[kCGWindowBounds as String] as? [String: Any])?["Width"] as? Double ?? 0) >= 800 &&
    (($0[kCGWindowBounds as String] as? [String: Any])?["Height"] as? Double ?? 0) >= 500
}
guard matches.count == 1 else { fputs("没有唯一真实可见 App 主窗口\n", stderr); exit(4) }
let window = matches[0]
let result: [String: Any] = ["window_id": window[kCGWindowNumber as String]!, "pid": Int(pid),
                          "bounds": window[kCGWindowBounds as String]!, "bundle_id": app.bundleIdentifier!]
let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
'''


def capture_mac(executable, destination, locales, settle):
    helper_source = destination / 'window-helper.swift'; helper_source.write_text(WINDOW_HELPER, encoding='utf8')
    helper = destination / 'window-helper'
    run(['xcrun', 'swiftc', helper_source, '-o', helper], timeout=120)
    images = []
    for locale in locales:
        for tab in TABS:
            with (destination / 'app-console.log').open('ab') as log:
                process = subprocess.Popen([str(executable), *launch_arguments(tab, locale)], stdout=log, stderr=log)
                try:
                    time.sleep(settle)
                    if process.poll() is not None: raise RuntimeError('原生 Mac App 已退出，不能采集')
                    window = json.loads(run([helper, process.pid], capture=True, timeout=15))
                    raw = destination / 'raw' / locale / 'mac' / (tab + '.png'); raw.parent.mkdir(parents=True, exist_ok=True)
                    run(['/usr/sbin/screencapture', '-x', '-o', '-l', window['window_id'], raw], timeout=30)
                    images.append(prepare_image(raw, destination, 'macos', locale, 'mac', tab,
                                                {'method': 'screencapture-window', **window}))
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=10)
                        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
    return images


def capture_simulator(app, platform, destination, locales, settle, runtime, types):
    images = []
    for group in (('iphone', 'ipad') if platform == 'ios' else ('vision',)):
        device_type = select_device_type(types, group, runtime)
        udid = run(['xcrun', 'simctl', 'create', 'NewsLive-Capture-' + uuid.uuid4().hex[:12],
                    device_type['identifier'], runtime['identifier']], capture=True, timeout=120).strip()
        if not re.fullmatch(r'[0-9A-Fa-f-]{36}', udid): raise ValueError('simctl 没有返回有效设备 UUID')
        try:
            run(['xcrun', 'simctl', 'boot', udid], timeout=180)
            run(['open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', udid], timeout=30)
            run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=300)
            run(['xcrun', 'simctl', 'install', udid, app], timeout=180)
            installed_app = Path(run(['xcrun', 'simctl', 'get_app_container', udid, store.BUNDLE, 'app'], capture=True, timeout=30).strip())
            installed_info = plistlib.loads((installed_app / 'Info.plist').read_bytes())
            if installed_info.get('CFBundleIdentifier') != store.BUNDLE:
                raise ValueError('模拟器实际安装 App 的 Bundle ID 不匹配')
            installed_executable = installed_app / installed_info['CFBundleExecutable']
            for locale in locales:
                for tab in TABS:
                    # 首次启动没有进程，后续明确终止前一次 App；只作用于自己创建的设备。
                    subprocess.run(['xcrun', 'simctl', 'terminate', udid, store.BUNDLE], capture_output=True)
                    launched = run(['xcrun', 'simctl', 'launch', udid, store.BUNDLE, *launch_arguments(tab, locale)], capture=True, timeout=60)
                    match = re.search(r':\s*(\d+)\s*$', launched)
                    if not match: raise RuntimeError('模拟器没有确认本 App 启动 PID')
                    time.sleep(settle)
                    verify_process(int(match[1]), installed_executable)
                    raw = destination / 'raw' / locale / group / (tab + '.png'); raw.parent.mkdir(parents=True, exist_ok=True)
                    run(['xcrun', 'simctl', 'io', udid, 'screenshot', '--type=png', raw], timeout=60)
                    verify_process(int(match[1]), installed_executable)
                    if platform == 'visionos':
                        with Image.open(raw) as image:
                            if image.width <= image.height or image.width < 1920:
                                raise ValueError('visionOS 未返回有效空间场景截图，拒绝使用窗口或其他平台图片替代')
                    images.append(prepare_image(raw, destination, platform, locale, group, tab,
                                                {'method': 'simctl', 'udid': udid, 'pid': int(match[1]),
                                                 'runtime': runtime['identifier'], 'device_type': device_type['identifier']}))
        finally:
            subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
            subprocess.run(['xcrun', 'simctl', 'delete', udid], capture_output=True)
    return images


def verify_process(pid, executable):
    """simctl 返回的是宿主机 PID；同时校验存活与安装包路径，避免截到崩溃后的主屏。"""
    try:
        os.kill(pid, 0)
    except OSError as error:
        raise RuntimeError('截图前后 App 进程已退出，拒绝把模拟器主屏当作应用截图') from error
    command = run(['/bin/ps', '-ww', '-p', pid, '-o', 'args='], capture=True, timeout=10).strip()
    expected = str(executable)
    if not command.startswith(expected + ' ') and command != expected:
        raise RuntimeError('模拟器 PID 不属于本次安装的真实 App，拒绝采集')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True, choices=list(store.platforms()))
    parser.add_argument('--locale', action='append', choices=list(LOCALES))
    parser.add_argument('--output', default='build/store-screenshots')
    parser.add_argument('--version', help='可选：覆盖实际构建版本；manifest 始终读取编译成品')
    parser.add_argument('--download-runtime', action='store_true')
    parser.add_argument('--settle-seconds', type=int, default=18)
    args = parser.parse_args()
    if sys.platform != 'darwin': raise SystemExit('真实截图采集仅能在带 Xcode 的 macOS 执行')
    if args.settle_seconds < 3 or args.settle_seconds > 120: raise SystemExit('等待界面稳定时间须为 3 至 120 秒')
    destination = Path(args.output).resolve() / args.platform
    if destination.exists(): raise SystemExit('输出目录已存在；请使用新目录，避免覆盖原图/来源记录')
    destination.mkdir(parents=True)
    try:
        runtime, types = ensure_runtime(args.platform, args.download_runtime, destination) if args.platform != 'macos' else (None, None)
        app, executable, provenance = build(args.platform, destination, args.version)
        locales = args.locale or list(LOCALES)
        images = (capture_mac(executable, destination, locales, args.settle_seconds) if args.platform == 'macos' else
                  capture_simulator(app, args.platform, destination, locales, args.settle_seconds, runtime, types))
        manifest = {'schema': 1, 'bundle_id': store.BUNDLE, 'platform': args.platform, 'version': provenance['version'],
                    'build': provenance, 'git_revision': run(['git', 'rev-parse', 'HEAD'], capture=True).strip(),
                    'screenshots': images}
        (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
        print(f'已采集 {len(images)} 张真实截图、原图及来源哈希；尚未上传商店。')
    except Exception as error:
        (destination / 'capture-failure.json').write_text(json.dumps({'platform': args.platform, 'error': str(error)}, ensure_ascii=False), encoding='utf8')
        raise


if __name__ == '__main__': main()
