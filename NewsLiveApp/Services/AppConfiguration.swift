import Foundation

enum AppConfiguration {
    static let bundleID = Bundle.main.bundleIdentifier ?? "com.luolihao.newslive"
    static var apiKey: String {
        #if DEBUG
        let override = UserDefaults.standard.string(forKey: "debugAPIKey") ?? ""
        if !override.isEmpty { return override }
        #endif
        return value("YouTubeAPIKey")
    }
    static let appStoreID = value("AppStoreID")
    static let privacyURL = configuredURL("PrivacyPolicyURL")
    static let supportURL = configuredURL("SupportURL")
    static let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    static var isConfigured: Bool { !apiKey.isEmpty && apiKey != "YOUR_YOUTUBE_API_KEY" }
    private static func value(_ key: String) -> String {
        let text = (Bundle.main.object(forInfoDictionaryKey: key) as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return text.contains("$(") ? "" : text
    }
    private static func configuredURL(_ key: String) -> URL? {
        guard let url = URL(string: value(key)), url.scheme == "https", url.host != nil else { return nil }
        return url
    }
}
