import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module():
    path = ROOT / "scripts/appstore.py"
    if not path.exists(): raise AssertionError("尚未实现 Apple 工作流脚本")
    spec = importlib.util.spec_from_file_location("newslive_appstore", path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

class FakeAPI:
    def __init__(self, bundle_exists=False):
        self.calls = []; self.bundle_exists = bundle_exists
    def call(self, path, method="GET", data=None):
        self.calls.append((path,method,data))
        if path.startswith("bundleIds?"):
            return {"data": [{"id":"bundle1","attributes":{"identifier":"com.luolihao.newslive"}}] if self.bundle_exists else []}
        if path == "bundleIds" and method == "POST":
            return {"data":{"id":"bundle1","attributes":data["data"]["attributes"]}}
        raise AssertionError("非预期调用: " + path)

class AppStoreTests(unittest.TestCase):
    def test_existing_bundle_is_reused_without_new_registration(self):
        api = FakeAPI(bundle_exists=True)
        self.assertEqual(module().ensure_bundle(api)["id"], "bundle1")
        self.assertEqual(len(api.calls), 1)
    def test_new_bundle_registration_has_correct_identity(self):
        api = FakeAPI()
        result = module().ensure_bundle(api)
        self.assertEqual(result["attributes"]["identifier"], "com.luolihao.newslive")
        self.assertEqual(result["attributes"]["platform"], "IOS")
    def test_build_number_always_exceeds_previous_uploads(self):
        self.assertEqual(module().next_build_number(["1", "9", "27", "1.2.3"], 5), 28)
        self.assertEqual(module().next_build_number([], 42), 42)
    def test_app_identity_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            module().unique_app([{"id":"old","attributes":{"bundleId":"com.other.app"}}])
    def test_store_names_and_subtitles_fit_apple_limits(self):
        labels = module().LABELS
        self.assertEqual(labels["en-US"]["name"], "YouTubeNewsLive")
        for values in labels.values():
            for value in values.values(): self.assertTrue(0 < len(value) <= 30)

if __name__ == "__main__": unittest.main()
