import Foundation
import Combine
import NewsCore

@MainActor
final class UpdateChecker: ObservableObject {
    @Published private(set) var newerVersion: String?
    private var checking = false
    var storeURL: URL? {
        guard AppConfiguration.appStoreID.allSatisfy(\.isNumber), !AppConfiguration.appStoreID.isEmpty else { return nil }
        return URL(string: "https://apps.apple.com/app/id\(AppConfiguration.appStoreID)")
    }
    func checkOnSettingsOpen() async {
        guard !checking, storeURL != nil else { return }
        checking = true; defer { checking = false }
        var components = URLComponents(string: "https://itunes.apple.com/lookup")!
        components.queryItems = [URLQueryItem(name: "id", value: AppConfiguration.appStoreID), URLQueryItem(name: "country", value: Locale.current.region?.identifier ?? "TW")]
        do {
            var request = URLRequest(url: components.url!); request.timeoutInterval = 10
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return }
            let result = try JSONDecoder().decode(Lookup.self, from: data)
            guard let app = result.results.first, String(app.trackId) == AppConfiguration.appStoreID else { return }
            newerVersion = AppVersion.isNewer(app.version, than: AppConfiguration.version) ? app.version : nil
        } catch { /* 更新失敗不打斷設定頁及直播功能。 */ }
    }
    private struct Lookup: Decodable {
        struct App: Decodable { let trackId: Int; let version: String }
        let results: [App]
    }
}
