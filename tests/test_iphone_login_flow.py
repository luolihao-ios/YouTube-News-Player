"""固定 iPhone 登录与播放入口的连接，实际登录仍须用 iPhone 验证。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class IPhoneLoginFlowTests(unittest.TestCase):
    def test_home_and_playback_entry_use_app_owned_sign_in(self):
        self.assertIn("YouTubeSignInView(", source("NewsLiveApp/Views/HomeView.swift"))
        player = source("NewsLiveApp/Views/PlayerView.swift")
        self.assertIn("await PlayerWebData.hasYouTubeSession()", player)
        self.assertIn("YouTubeSignInView {", player)
        self.assertIn("hasSession = true", player)
        sign_in = source("NewsLiveApp/Views/YouTubeSignInView.swift")
        self.assertIn("configuration.websiteDataStore = PlayerWebData.store", sign_in)
        self.assertNotIn("UIApplication.shared.open", sign_in)
        self.assertNotIn("userContentController.add", sign_in)

    def test_signed_in_ios_player_loads_official_embed_in_shared_store(self):
        self.assertIn("signedIn: hasSession", source("NewsLiveApp/Views/PlayerView.swift"))
        player = source("NewsLiveApp/Playback/YouTubeWebView.swift")
        self.assertIn("configuration.websiteDataStore = PlayerWebData.store", player)
        self.assertIn("webView.load(config.embedRequest)", player)
        self.assertIn('"direct_media_playing"', player)

    def test_official_player_login_tap_and_loading_state_stay_in_app(self):
        player = source("NewsLiveApp/Playback/YouTubeWebView.swift")
        self.assertIn("action.navigationType == .linkActivated, let onSignInRequested", player)
        self.assertIn("onSignInRequested: showSignIn", source("NewsLiveApp/Views/PlayerView.swift"))
        sign_in = source("NewsLiveApp/Views/YouTubeSignInView.swift")
        self.assertIn("didStartProvisionalNavigation", sign_in)
        self.assertIn('"youtube_sign_in_timeout"', sign_in)
        self.assertIn("NSURLErrorFailingURLErrorKey", sign_in)


if __name__ == "__main__":
    unittest.main()
