import Foundation
import NewsCore
import WebKit

/// 只在本机保存有限的播放诊断；不记录 Cookie、帐号、API Key 或请求参数。
@MainActor
final class PlaybackDiagnostics {
    static let shared = PlaybackDiagnostics()
    let fileURL: URL
    private let recorder: PlaybackLog?

    private init() {
        let manager = FileManager.default
        let documents = manager.urls(for: .documentDirectory, in: .userDomainMask).first ?? manager.temporaryDirectory
        let directory = documents.appendingPathComponent("PlaybackLogs", isDirectory: true)
        let fallback = manager.temporaryDirectory.appendingPathComponent("PlaybackLogs", isDirectory: true)
        recorder = (try? PlaybackLog(directory: directory)) ?? (try? PlaybackLog(directory: fallback))
        fileURL = recorder?.fileURL ?? fallback.appendingPathComponent("playback.jsonl")
        record("app_diagnostics_ready")
    }

    func record(_ event: String, fields: [String: String] = [:]) {
        var context = fields
        context["appVersion"] = AppConfiguration.version
        context["build"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
        #if os(macOS)
        context["platform"] = "macOS"
        #elseif os(visionOS)
        context["platform"] = "visionOS"
        #else
        context["platform"] = "iOS"
        #endif
        try? recorder?.record(event, fields: context)
    }

    func clear() { try? recorder?.clear() }
}

/// 各个频道共用本 App 的网站资料；Safari 的帐号会话不会被导入。
@MainActor
enum PlayerWebData {
    static let store = WKWebsiteDataStore.default()

    static func clear() async {
        PlayerSession.pauseCurrent()
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            store.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) {
                continuation.resume()
            }
        }
        PlaybackDiagnostics.shared.record("website_data_cleared")
    }
}
