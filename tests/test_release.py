import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReleaseTests(unittest.TestCase):
    def load(self):
        path = ROOT / "scripts/validate_release.py"
        self.assertTrue(path.exists(), "尚未實作 Release 設定驗證")
        spec = importlib.util.spec_from_file_location("validate_release", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def valid(self):
        return {"YOUTUBE_API_KEY": "configured-key", "APP_STORE_ID": "123456789", "PRIVACY_POLICY_URL": "https://news.example.org/privacy", "SUPPORT_URL": "https://news.example.org/support", "PRODUCT_BUNDLE_IDENTIFIER": "org.news.live"}

    def test_empty_settings_fail_with_names(self):
        errors = self.load().validate({})
        self.assertTrue(any("YOUTUBE_API_KEY" in item for item in errors))
        self.assertTrue(any("APP_STORE_ID" in item for item in errors))

    def test_unexpanded_values_and_bad_urls_are_rejected(self):
        config = self.valid()
        config.update(YOUTUBE_API_KEY="$(YOUTUBE_API_KEY)", PRIVACY_POLICY_URL="http://invalid.test/privacy", APP_STORE_ID="YOUR_NUMERIC_APP_STORE_ID")
        self.assertEqual(len(self.load().validate(config)), 3)

    def test_configured_release_values_pass(self):
        self.assertEqual(self.load().validate(self.valid()), [])

    def test_testflight_does_not_require_unpublished_policy_urls(self):
        config = self.valid()
        config.update(PRIVACY_POLICY_URL="", SUPPORT_URL="")
        self.assertEqual(self.load().validate(config, for_submission=False), [])
        self.assertEqual(len(self.load().validate(config)), 2)

    def test_testflight_still_rejects_non_https_policy_if_supplied(self):
        config = self.valid(); config.update(PRIVACY_POLICY_URL="http://invalid.test")
        self.assertTrue(self.load().validate(config, for_submission=False))

if __name__ == "__main__": unittest.main()
