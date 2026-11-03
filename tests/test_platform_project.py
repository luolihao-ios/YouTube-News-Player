"""固定同一产品、三个构建目标及 UIKit/AppKit 源文件隔离。"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def generator():
    spec = importlib.util.spec_from_file_location("three_platform_project", ROOT / "scripts/generate_project.py")
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

class PlatformProjectTests(unittest.TestCase):
    def test_three_native_targets_share_one_bundle_identifier(self):
        graph = generator().project_graph()
        objects = graph["objects"]
        targets = [item for item in objects.values() if item["isa"] == "PBXNativeTarget"]
        self.assertEqual({item["name"] for item in targets}, {"NewsLive", "NewsLive-macOS", "NewsLive-visionOS"})
        sdk_roots = set()
        for target in targets:
            config_list = objects[target["buildConfigurationList"]]
            for identity in config_list["buildConfigurations"]:
                settings = objects[identity]["buildSettings"]
                self.assertEqual(settings["PRODUCT_BUNDLE_IDENTIFIER"], "com.luolihao.newslive")
                sdk_roots.add(settings["SDKROOT"])
        self.assertEqual(sdk_roots, {"iphoneos", "macosx", "xros"})

    def test_macos_does_not_compile_mobile_only_views(self):
        paths = generator().source_paths("macos")
        self.assertTrue(all("/Views/" not in path for path in paths))
        self.assertIn("NewsLiveApp/NewsLiveApp.swift", paths)
        self.assertIn("NewsLiveApp/Playback/YouTubeWebView.swift", paths)
        self.assertIn("NewsLiveApp/DesignSystem.swift", paths)

    def test_ios_does_not_compile_desktop_views(self):
        paths = generator().source_paths("ios")
        self.assertTrue(all("/Desktop/" not in path for path in paths))
        self.assertIn("NewsLiveApp/Views/RootView.swift", paths)

if __name__ == "__main__": unittest.main()
