"""播放器页面的外部依赖边界回归；不能代替 iPhone 实际播放测试。"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InlinePlaybackBoundaryTests(unittest.TestCase):
    def test_mobile_player_does_not_replace_embed_with_system_browser(self):
        source = (ROOT / "NewsLiveApp/Views/PlayerView.swift").read_text(encoding="utf-8")
        self.assertIn("YouTubeWebView(", source)
        for forbidden in ["InAppYouTubeBrowser(", "SFSafariViewController(", "openWebPlayback(", "UIApplication.shared.open("]:
            self.assertNotIn(forbidden, source, "播放失败和验证不应将原生播放页替换成浏览器")

    def test_identity_navigation_never_directly_opens_an_external_browser(self):
        source = (ROOT / "NewsLiveApp/Playback/YouTubeWebView.swift").read_text(encoding="utf-8")
        branch = source.split("case .verificationRequired:", 1)[1].split("case .openExternal:", 1)[0]
        self.assertNotIn("openExternal(", branch)
        self.assertNotIn("webPlaybackRequired", source, "不能用播放事件间接触发自动网页回退")


if __name__ == "__main__":
    unittest.main()
