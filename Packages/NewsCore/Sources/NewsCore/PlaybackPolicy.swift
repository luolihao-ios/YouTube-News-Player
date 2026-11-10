import Foundation

public enum PlayerNavigationDecision: Equatable, Sendable {
    case allow
    case openExternal
    case verificationRequired
    case cancel
}

/// 播放器只在使用者明確點擊時開啟外部頁面；驗證失敗留在原生頁面，不自動跳轉瀏覽器。
public enum PlayerNavigationPolicy {
    public static func decision(for url: URL?, isMainFrame: Bool, isUserActivated: Bool, opensNewWindow: Bool) -> PlayerNavigationDecision {
        guard let url else { return .cancel }
        if url.scheme?.lowercased() == "about" {
            return ["about:blank", "about:srcdoc"].contains(url.absoluteString.lowercased()) ? .allow : .cancel
        }
        guard url.scheme?.lowercased() == "https",
              let host = url.host?.lowercased(), !host.isEmpty,
              url.user == nil, url.password == nil else { return .cancel }

        if ["accounts.google.com", "accounts.youtube.com"].contains(host) {
            // 這兩個已知路徑只維護背景會話，不代表使用者正在進入登入流程。
            // 僅允許被動子框架，避免把例外擴展成可嵌入的帳號頁。
            let isSessionMaintenance = (host == "accounts.youtube.com" && url.path == "/accounts/CheckConnection")
                || (host == "accounts.google.com" && url.path == "/RotateCookiesPage")
            if isSessionMaintenance && !isMainFrame && !isUserActivated && !opensNewWindow {
                return .allow
            }
            return .verificationRequired
        }
        if ["youtube.com", "www.youtube.com", "m.youtube.com"].contains(host) {
            // 只檢查目的地路徑，不把 watch URL 的 continue 等查詢參數誤認成登入頁。
            let path = (url.path.removingPercentEncoding ?? url.path).lowercased()
            let authenticationPaths = ["/signin", "/login", "/servicelogin", "/o/oauth2", "/oauth2", "/account/login"]
            if authenticationPaths.contains(where: { path == $0 || path.hasPrefix($0 + "/") }) {
                return .verificationRequired
            }
        }

        if opensNewWindow && !isUserActivated { return .cancel }
        if isUserActivated && (isMainFrame || opensNewWindow) { return .openExternal }
        return .allow
    }
}

public enum PlayerFailure {
    public static let verificationMessage = "YouTube 要求登入或確認您不是機器人。App 無法在內嵌播放器完成這項驗證；可選擇在外部瀏覽器觀看。外部瀏覽器登入不會同步回 App。"

    public static func message(for code: Int) -> String {
        switch code {
        case 2:
            return "YouTube 播放參數無效（代碼 2），請重新選擇影片。"
        case 5:
            return "YouTube 播放器暫時無法載入影片（代碼 5），請重試或在外部瀏覽器觀看。"
        case 100:
            return "影片已移除、設為私人或目前無法提供（YouTube 代碼 100）。"
        case 101, 150:
            return "本次內嵌播放遭 YouTube 拒絕（代碼 \(code)），可能涉及驗證、地區或直播限制。外部瀏覽器登入不會同步回 App。"
        case 153:
            return "YouTube 無法確認 App 的播放請求身分（代碼 153），請重試或在外部瀏覽器觀看。"
        default:
            return "YouTube 播放失敗（代碼 \(code)），請重試或在外部瀏覽器觀看。"
        }
    }
}

/// 仅允许 YouTube 与 Google 的官方登入流程留在登入 WebView。
public enum YouTubeSignInPolicy {
    private static let youtubeHosts = ["youtube.com", "www.youtube.com", "m.youtube.com"]
    private static let signInHosts = ["accounts.google.com", "accounts.youtube.com", "consent.google.com", "consent.youtube.com"]

    public static let entryURL: URL = {
        // 使用 YouTube 手机版登入所指向的 Google 入口，保留 YouTube 的会话回调。
        var entry = URLComponents(string: "https://accounts.google.com/ServiceLogin")!
        entry.queryItems = [
            URLQueryItem(name: "service", value: "youtube"),
            URLQueryItem(name: "continue", value: "https://m.youtube.com/signin?action_handle_signin=true&app=m&next=%2F&noapp=1")
        ]
        return entry.url!
    }()

    public static func allows(_ url: URL?, isMainFrame: Bool) -> Bool {
        if !isMainFrame, url?.absoluteString == "about:blank" { return true }
        guard let url, let host = trustedHost(url) else { return false }
        return youtubeHosts.contains(host) || signInHosts.contains(host)
            || (!isMainFrame && host == "www.google.com" && url.path.hasPrefix("/recaptcha/"))
    }

    public static func isYouTubeReturn(_ url: URL?) -> Bool {
        guard let url, let host = trustedHost(url), youtubeHosts.contains(host) else { return false }
        return url.path == "/" || url.path.isEmpty
    }

    public static func hasSession(_ cookies: [HTTPCookie], now: Date = .now) -> Bool {
        cookies.contains { cookie in
            let domain = cookie.domain.lowercased().trimmingPrefix(".")
            return cookie.name == "LOGIN_INFO" && cookie.isSecure && youtubeHosts.contains(String(domain))
                && (cookie.expiresDate.map { $0 > now } ?? true)
        }
    }

    private static func trustedHost(_ url: URL) -> String? {
        guard url.scheme == "https", url.user == nil, url.password == nil,
              url.port == nil || url.port == 443 else { return nil }
        return url.host?.lowercased()
    }
}
