"""真实截图来源、平台隔离和只追加上传的离线回归测试。"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
if (ROOT / '.test-tools').is_dir():
    sys.path.insert(0, str(ROOT / '.test-tools'))
from PIL import Image, ImageDraw


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.capture = load('capture_store_screenshots')
        self.upload = load('apple_screenshots')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def manifest(self, platform='macos'):
        group = {'macos': 'mac', 'ios': 'iphone', 'visionos': 'vision'}[platform]
        raw = self.root / 'raw.png'
        image = Image.new('RGB', (1000, 700), 'white')
        ImageDraw.Draw(image).rectangle((20, 20, 700, 600), fill='red')
        image.save(raw)
        item = self.capture.prepare_image(raw, self.root, platform, 'en-US', group, 'home',
                                          {'method': 'screencapture-window' if platform == 'macos' else 'simctl', 'pid': 42})
        document = {'schema': 1, 'bundle_id': 'com.luolihao.newslive', 'platform': platform,
                    'version': '1.0', 'build': {'configuration': 'Debug', 'executable_sha256': 'a' * 64},
                    'screenshots': [item]}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(document), encoding='utf8')
        return path, document

    def test_runtime_must_be_available_and_match_platform(self):
        items = [{'identifier': 'com.apple.CoreSimulator.SimRuntime.iOS-26-0', 'version': '26.0', 'isAvailable': False},
                 {'identifier': 'com.apple.CoreSimulator.SimRuntime.xrOS-26-0', 'version': '26.0', 'isAvailable': True}]
        with self.assertRaisesRegex(ValueError, 'runtime'):
            self.capture.select_runtime(items, 'ios')
        self.assertEqual(self.capture.select_runtime(items, 'visionos')['identifier'], items[1]['identifier'])

    def test_device_type_must_be_supported_by_selected_runtime(self):
        types=[{'name':'Apple Vision Pro','identifier':'vision-new'},
               {'name':'Apple Vision Pro (at 2732x2048)','identifier':'vision-old'}]
        runtime={'supportedDeviceTypes':[{'identifier':'vision-new'}]}
        self.assertEqual(self.capture.select_device_type(types,'vision',runtime)['identifier'],'vision-new')
        with self.assertRaisesRegex(ValueError,'兼容'):
            self.capture.select_device_type(types,'vision',{'supportedDeviceTypes':[]})

    def test_arguments_only_select_real_tab_and_language(self):
        self.assertEqual(self.capture.launch_arguments('favorites', 'zh-Hans'),
                         ['--capture-tab', 'favorites', '-AppleLanguages', '(zh-Hans)', '-AppleLocale', 'zh_CN'])
        with self.assertRaises(ValueError): self.capture.launch_arguments('fake-favorites', 'en-US')

    def test_real_image_is_scaled_without_crop_and_hashes_verified(self):
        path, document = self.manifest()
        item = document['screenshots'][0]
        self.assertEqual(item['size'], [1440, 900])
        self.assertEqual(item['raw_size'], [1000, 700])
        checked = self.upload.validate_manifest(path, 'macos', ['en-US'])
        self.assertEqual(len(checked['screenshots']), 1)
        image = Image.open(self.root / item['path'])
        self.assertEqual(image.mode, 'RGB')
        image.putpixel((0, 0), (1, 2, 3)); image.save(self.root / item['path'])
        with self.assertRaisesRegex(ValueError, '哈希'):
            self.upload.validate_manifest(path, 'macos', ['en-US'])

    def test_cross_platform_locale_and_path_escape_are_rejected(self):
        path, document = self.manifest()
        with self.assertRaises(ValueError): self.upload.validate_manifest(path, 'visionos', ['en-US'])
        with self.assertRaises(ValueError): self.upload.validate_manifest(path, 'macos', ['zh-Hans'])
        document['screenshots'][0]['path'] = '../escape.png'
        path.write_text(json.dumps(document), encoding='utf8')
        with self.assertRaises(ValueError): self.upload.validate_manifest(path, 'macos', ['en-US'])

    def test_modified_pixels_cannot_be_hidden_by_replacing_manifest_hash(self):
        path, document = self.manifest()
        item = document['screenshots'][0]
        target = self.root / item['path']
        image = Image.open(target); image.putpixel((200, 200), (0, 255, 0)); image.save(target)
        item['sha256'] = self.capture.digest(target)
        item['md5'] = self.capture.digest(target, 'md5')
        path.write_text(json.dumps(document), encoding='utf8')
        with self.assertRaisesRegex(ValueError, '原图'):
            self.upload.validate_manifest(path, 'macos', ['en-US'])

    def test_existing_asset_collision_and_limit_fail_before_mutation(self):
        _, document = self.manifest()
        item = document['screenshots'][0]
        old = {'id': 'old', 'attributes': {'fileName': Path(item['path']).name, 'sourceFileChecksum': 'different'}}
        with self.assertRaisesRegex(ValueError, '同名'):
            self.upload.plan_assets([old], [item])
        old['attributes']['fileName'] = 'unrelated.png'
        existing = []
        for index in range(10):
            previous = copy.deepcopy(old)
            previous['id'] = str(index); previous['attributes']['fileName'] = str(index) + '.png'
            existing.append(previous)
        with self.assertRaisesRegex(ValueError, '10'):
            self.upload.plan_assets(existing, [item])

    def test_identical_existing_asset_is_reused_and_no_asset_is_deleted(self):
        _, document = self.manifest(); item = document['screenshots'][0]
        old = {'id': 'old', 'attributes': {'fileName': Path(item['path']).name, 'sourceFileChecksum': item['md5']}}
        actions = self.upload.plan_assets([old], [item])
        self.assertEqual(actions[0]['existing_id'], 'old')
        self.assertNotIn('DELETE', (ROOT / 'scripts/apple_screenshots.py').read_text(encoding='utf8'))

    def test_version_mismatch_is_rejected_before_writes(self):
        path, _ = self.manifest()
        api = FakeAPI('2.0')
        with self.assertRaisesRegex(ValueError, '版本'):
            self.upload.upload(api, path, 'macos', ['en-US'], wait_seconds=0)
        self.assertTrue(all(method == 'GET' for _, method, _ in api.calls))

    def test_platform_localization_is_used_and_processing_is_read_back(self):
        path, _ = self.manifest(); api = FakeAPI('1.0')
        with patch.object(self.upload, 'upload_chunks') as chunks:
            result = self.upload.upload(api, path, 'macos', ['en-US'], wait_seconds=0)
        self.assertEqual(result['platform'], 'macos')
        self.assertEqual(result['assets'][0]['state'], 'COMPLETE')
        self.assertEqual(chunks.call_count, 1)
        writes = [(path, data) for path, method, data in api.calls if method == 'POST']
        self.assertEqual(writes[0][1]['data']['relationships']['appStoreVersionLocalization']['data']['id'], 'loc-mac')
        self.assertTrue(any('appScreenshots/new' in path and method == 'GET' for path, method, _ in api.calls))

    def test_pending_processing_is_an_explicit_failure(self):
        path, _ = self.manifest(); api = FakeAPI('1.0', 'UPLOAD_COMPLETE')
        with patch.object(self.upload, 'upload_chunks'), self.assertRaisesRegex(RuntimeError, 'UPLOAD_COMPLETE'):
            self.upload.upload(api, path, 'macos', ['en-US'], wait_seconds=0)

    def test_all_images_are_uploaded_before_waiting_for_apple_processing(self):
        path,document=self.manifest()
        second=self.capture.prepare_image(self.root/'raw.png',self.root,'macos','en-US','mac','channels',
                                          {'method':'screencapture-window','pid':42})
        document['screenshots'].append(second); path.write_text(json.dumps(document),encoding='utf8')
        class BatchAPI(FakeAPI):
            def call(self,path,method='GET',data=None):
                if path=='appScreenshots' and method=='POST':
                    self.calls.append((path,method,data))
                    asset={'id':str(len(self.assets)),'attributes':{**data['data']['attributes'],'sourceFileChecksum':'',
                           'assetDeliveryState':{'state':'COMPLETE'},'uploadOperations':[]}}
                    self.assets.append(asset); return {'data':asset}
                if path.startswith('appScreenshots/'):
                    self.calls.append((path,method,data))
                    asset=next(a for a in self.assets if a['id']==path.split('/')[1])
                    if method=='PATCH': asset['attributes'].update(data['data']['attributes'])
                    else:
                        if len(self.assets)!=2 or not all(a['attributes'].get('uploaded') for a in self.assets):
                            raise AssertionError('不能等第一张处理完成后才上传后续图片')
                    return {'data':asset}
                return super().call(path,method,data)
        api=BatchAPI('1.0')
        with patch.object(self.upload,'upload_chunks'):
            result=self.upload.upload(api,path,'macos',['en-US'],wait_seconds=0)
        self.assertEqual(len(result['assets']),2)
        self.assertTrue(result['complete'])

    def test_invalid_chunk_coverage_and_insecure_url_fail_before_network(self):
        path = self.root / 'chunk.bin'; path.write_bytes(b'0123456789')
        cases = [
            [{'offset': 0, 'length': 5, 'url': 'https://assets.apple.com/a', 'method': 'PUT'}],
            [{'offset': 0, 'length': 10, 'url': 'http://assets.apple.com/a', 'method': 'PUT'}],
            [{'offset': 0, 'length': 10, 'url': 'https://assets.apple.com/a', 'method': 'POST'}],
            [{'offset': 0, 'length': 7, 'url': 'https://assets.apple.com/a', 'method': 'PUT'},
             {'offset': 5, 'length': 5, 'url': 'https://assets.apple.com/a', 'method': 'PUT'}],
        ]
        with patch.object(self.upload.urllib.request, 'build_opener') as opener:
            for operations in cases:
                with self.subTest(operations=operations), self.assertRaises(ValueError):
                    self.upload.upload_chunks(path, operations)
            opener.assert_not_called()

    def test_chunk_upload_uses_exact_ranges_and_apple_headers_without_bearer(self):
        path = self.root / 'chunk.bin'; path.write_bytes(b'0123456789')
        operations = [{'offset': 0, 'length': 4, 'url': 'https://assets.apple.com/one', 'method': 'PUT',
                       'requestHeaders': [{'name': 'Content-Type', 'value': 'image/png'}]},
                      {'offset': 4, 'length': 6, 'url': 'https://assets.apple.com/two', 'method': 'PUT'}]
        with patch.object(self.upload.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value.__enter__.return_value.status = 200
            self.upload.upload_chunks(path, operations)
        requests = [call.args[0] for call in build.return_value.open.call_args_list]
        self.assertEqual([request.data for request in requests], [b'0123', b'456789'])
        self.assertEqual(requests[0].get_header('Content-type'), 'image/png')
        self.assertTrue(all(not request.has_header('Authorization') for request in requests))

    def test_no_api_mutation_when_any_local_image_is_invalid(self):
        path, document = self.manifest()
        (self.root / document['screenshots'][0]['raw_path']).write_bytes(b'invalid')
        api = FakeAPI('1.0')
        with self.assertRaises(ValueError): self.upload.upload(api, path, 'macos', ['en-US'], wait_seconds=0)
        self.assertEqual(api.calls, [])

    def test_all_groups_are_preflighted_before_creating_sets(self):
        path, document = self.manifest()
        second = copy.deepcopy(document['screenshots'][0]); second['locale'] = 'zh-Hans'
        document['screenshots'].append(second); path.write_text(json.dumps(document), encoding='utf8')
        api = FakeAPI('1.0')
        with self.assertRaisesRegex(ValueError, '语言'):
            self.upload.upload(api, path, 'macos', ['en-US', 'zh-Hans'], wait_seconds=0)
        self.assertTrue(all(method == 'GET' for _, method, _ in api.calls))

    def test_invalid_platform_and_unknown_runtime_never_fall_back(self):
        with self.assertRaises(ValueError): self.upload.store.selected_platforms(['tvos'])
        with self.assertRaises(ValueError): self.capture.select_runtime([], 'visionos')
        with self.assertRaises(ValueError): self.capture.select_device_type([], 'vision')

    def test_simulator_process_must_stay_alive_and_match_installed_app(self):
        executable = Path('/simulator/NewsLive.app/NewsLive')
        with patch.object(self.capture.os, 'kill', side_effect=ProcessLookupError), self.assertRaisesRegex(RuntimeError, '进程'):
            self.capture.verify_process(42, executable)
        with patch.object(self.capture.os, 'kill'), patch.object(self.capture, 'run', return_value='/System/SpringBoard'), self.assertRaisesRegex(RuntimeError, 'PID'):
            self.capture.verify_process(42, executable)
        with patch.object(self.capture.os, 'kill'), patch.object(self.capture, 'run', return_value=str(executable) + ' --capture-tab home'):
            self.capture.verify_process(42, executable)

    def test_workflow_manifest_requires_all_four_pages(self):
        _, document = self.manifest()
        with self.assertRaisesRegex(ValueError, '不完整'):
            self.upload.validate_capture_layout(document, 'macos', ['en-US'])
        original = document['screenshots'][0]
        document['screenshots'] = [{**original, 'tab': tab} for tab in self.capture.TABS]
        self.upload.validate_capture_layout(document, 'macos', ['en-US'])

    def test_ios_complete_capture_requires_both_iphone_and_ipad(self):
        document = {'screenshots': [{'locale': 'en-US', 'group': 'iphone', 'tab': tab} for tab in self.capture.TABS]}
        with self.assertRaisesRegex(ValueError, '设备组'):
            self.upload.validate_capture_layout(document, 'ios', ['en-US'])
        document['screenshots'] += [{'locale': 'en-US', 'group': 'ipad', 'tab': tab} for tab in self.capture.TABS]
        self.upload.validate_capture_layout(document, 'ios', ['en-US'])


class FakeAPI:
    def __init__(self, version, delivery='COMPLETE'):
        self.calls = []; self.version = version; self.delivery = delivery; self.assets = []
    def call(self, path, method='GET', data=None):
        self.calls.append((path, method, data))
        if path.startswith('apps?'):
            return {'data': [{'id': '6830361548', 'attributes': {'bundleId': 'com.luolihao.newslive'}}]}
        if path == 'appScreenshotSets' and method == 'POST': return {'data': {'id': 'set-mac'}}
        if path == 'appScreenshots' and method == 'POST':
            attrs = data['data']['attributes']
            self.assets = [{'id': 'new', 'attributes': {**attrs, 'sourceFileChecksum': self.checksum,
                           'assetDeliveryState': {'state': self.delivery}, 'uploadOperations': []}}]
            return {'data': self.assets[0]}
        if path.startswith('appScreenshots/new'):
            if method == 'PATCH': self.assets[0]['attributes']['sourceFileChecksum'] = data['data']['attributes']['sourceFileChecksum']
            return {'data': self.assets[0]}
        raise AssertionError((path, method))
    def all(self, path):
        self.calls.append((path, 'GET', None))
        if '/appStoreVersions?' in path:
            return [{'id': 'wrong-ios', 'attributes': {'platform': 'IOS', 'versionString': '1.0', 'appVersionState': 'PREPARE_FOR_SUBMISSION'}},
                    {'id': 'version-mac', 'attributes': {'platform': 'MAC_OS', 'versionString': self.version, 'appVersionState': 'PREPARE_FOR_SUBMISSION'}}]
        if path == 'appStoreVersions/version-mac/appStoreVersionLocalizations?limit=200':
            return [{'id': 'loc-mac', 'attributes': {'locale': 'en-US'}}]
        if '/appScreenshotSets?' in path: return []
        if '/appScreenshots?' in path: return self.assets
        raise AssertionError(path)
    checksum = ''


if __name__ == '__main__': unittest.main()
