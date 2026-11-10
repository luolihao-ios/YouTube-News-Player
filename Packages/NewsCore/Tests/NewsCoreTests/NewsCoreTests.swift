import XCTest
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
@testable import NewsCore

final class NewsCoreTests: XCTestCase {
    func testSearchTrimsWhitespaceIgnoresCaseAndCombinesCategory() {
        let seeds = [
            ChannelSeed(id: "tvbs", name: "TVBS 新聞台", subtitle: "即時新聞", category: .taiwan, monogram: "TVBS", color: "203DA7"),
            ChannelSeed(id: "sky", name: "Sky News", subtitle: "國際直播", category: .international, monogram: "sky", color: "CC0000")
        ]
        XCTAssertEqual(ChannelFilter.apply(seeds, query: "  tvBS  ", category: nil).map(\.id), ["tvbs"])
        XCTAssertTrue(ChannelFilter.apply(seeds, query: "tvbs", category: .international).isEmpty)
        XCTAssertEqual(ChannelFilter.apply(seeds, query: "   ", category: nil).count, 2)
        XCTAssertEqual(ChannelFilter.preferred(seeds, liveIDs: ["tvbs"], category: .international).map(\.id), ["sky"])
        XCTAssertEqual(ChannelFilter.preferred(seeds, liveIDs: ["tvbs"], category: nil).map(\.id), ["tvbs"])
    }

    func testCacheDoesNotRenewChannelMetadataByRefreshingLiveResults() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let channel = ResolvedChannel(id: "UC1", title: "title", thumbnailURL: nil)
        let snapshot = ChannelSnapshot(channel: channel, videos: [], checkedAt: now, channelResolvedAt: now.addingTimeInterval(-86401))
        XCTAssertTrue(snapshot.isFresh(at: now))
        XCTAssertFalse(snapshot.canReuseChannel(at: now))
        XCTAssertTrue(snapshot.isExpired(at: now))
    }

    func testCacheExpiresAndFutureTimestampsAreNotTrusted() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let channel = ResolvedChannel(id: "UC1", title: "title", thumbnailURL: nil)
        let snapshot = ChannelSnapshot(channel: channel, videos: [], checkedAt: now, channelResolvedAt: now)
        XCTAssertTrue(snapshot.isFresh(at: now.addingTimeInterval(899)))
        XCTAssertFalse(snapshot.isFresh(at: now.addingTimeInterval(900)))
        XCTAssertTrue(snapshot.isExpired(at: now.addingTimeInterval(86400)))
        XCTAssertTrue(snapshot.isExpired(at: now.addingTimeInterval(-60)))
    }

    func testLibraryDeduplicatesPersistsAndRecoversInvalidJSON() {
        var library = LibraryState()
        library.setFavorite("tvbs", enabled: true)
        library.setFavorite("tvbs", enabled: true)
        library.setFavorite("sky", enabled: true)
        XCTAssertEqual(library.favorites, ["tvbs", "sky"])
        library.moveFavorites(from: IndexSet(integer: 1), to: 0)
        XCTAssertEqual(library.favorites, ["sky", "tvbs"])
        let copy = LibraryState.restore(from: try? JSONEncoder().encode(library))
        XCTAssertEqual(copy.favorites, library.favorites)
        XCTAssertTrue(LibraryState.restore(from: Data("broken".utf8)).favorites.isEmpty)
    }

    func testHistoryRequiresConsentAndIsBoundedAndDeduplicated() {
        var library = LibraryState()
        library.recordViewing("tvbs", enabled: false)
        XCTAssertTrue(library.recent.isEmpty)
        for number in 0..<25 { library.recordViewing("ch\(number)", enabled: true) }
        library.recordViewing("ch10", enabled: true)
        XCTAssertEqual(library.recent.count, 20)
        XCTAssertEqual(library.recent.first, "ch10")
        XCTAssertEqual(library.recent.filter { $0 == "ch10" }.count, 1)
    }

    func testPlayerConfigurationRejectsInjectionAndUsesBundleOrigin() throws {
        XCTAssertThrowsError(try PlayerConfiguration(videoID: "bad<script>", bundleID: "com.example.news"))
        let config = try PlayerConfiguration(videoID: "abcdefghijk", bundleID: "COM.Example.News")
        XCTAssertEqual(config.origin.absoluteString, "https://com.example.news")
        XCTAssertTrue(config.json.contains("abcdefghijk"))
    }

    func testPlayerPageRequestKeepsHTTPSAppIdentityWithoutCredentials() throws {
        let config = try PlayerConfiguration(videoID: "abcdefghijk", bundleID: "COM.Example.News")
        let request = config.pageRequest
        XCTAssertEqual(request.url?.absoluteString, "https://com.example.news/player")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Referer"), "https://com.example.news")
        XCTAssertNil(request.url?.query)
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
    }

    func testDirectPlayerRequestUsesYouTubeAndBundleReferer() throws {
        let config = try PlayerConfiguration(videoID: "abcdefghijk", bundleID: "COM.Example.News")
        let request = config.embedRequest
        XCTAssertEqual(request.url?.absoluteString, "https://www.youtube.com/embed/abcdefghijk?playsinline=1")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Referer"), "https://com.example.news")
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(request.value(forHTTPHeaderField: "Cookie"))
    }

    func testVersionsCompareNumericallyWithoutFalsePatchUpdates() {
        XCTAssertTrue(AppVersion.isNewer("1.10.0", than: "1.9.9"))
        XCTAssertFalse(AppVersion.isNewer("1.0.0", than: "1.0"))
        XCTAssertFalse(AppVersion.isNewer("0.9", than: "1.0"))
        XCTAssertFalse(AppVersion.isNewer("garbage", than: "1.0"))
    }

    func testMissingAPIKeyDoesNotMakeNetworkRequests() async {
        let client = YouTubeClient(apiKey: "", bundleID: "com.example.news", transport: { _ in
            XCTFail("缺 Key 不應發起網路請求")
            throw URLError(.badURL)
        })
        do { _ = try await client.resolve(handle: "TVBSNEWS01"); XCTFail("應失敗") }
        catch { XCTAssertEqual(error as? YouTubeError, .missingAPIKey) }
    }

    func testStableChannelIDWorksWhenOldHandleNoLongerResolves() async throws {
        let expectedID = "UC5l1Yto5oOIgRXlI4p4VKbw"
        let seed = ChannelSeed(id: "old-handle", name: "新聞", subtitle: "", category: .taiwan, monogram: "新聞", color: "203DA7", youtubeChannelID: expectedID)
        XCTAssertEqual(seed.channelURL.absoluteString, "https://www.youtube.com/channel/\(expectedID)")
        let client = YouTubeClient(apiKey: "test-key", bundleID: "com.example.news", transport: { request in
            let url = try XCTUnwrap(request.url)
            let items = URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertTrue(items.contains(URLQueryItem(name: "id", value: expectedID)))
            XCTAssertFalse(items.contains { $0.name == "forHandle" })
            return response(url, #"{"items":[{"id":"UC5l1Yto5oOIgRXlI4p4VKbw","snippet":{"title":"中天電視","thumbnails":{}}}]}"#)
        })
        let channel = try await client.resolve(handle: seed.id, channelID: seed.youtubeChannelID)
        XCTAssertEqual(channel.id, expectedID)
    }

    func testLiveDiscoveryFiltersEndedPrivateAndUnembeddableVideos() async throws {
        let client = YouTubeClient(apiKey: "test-key", bundleID: "com.example.news", transport: { request in
            let url = try XCTUnwrap(request.url)
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Ios-Bundle-Identifier"), "com.example.news")
            if url.path.hasSuffix("search") {
                let items = URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!
                XCTAssertTrue(items.contains(URLQueryItem(name: "eventType", value: "live")))
                XCTAssertTrue(items.contains(URLQueryItem(name: "videoEmbeddable", value: "true")))
                return response(url, #"{"items":[{"id":{"videoId":"abcdefghijk"}},{"id":{"videoId":"bcdefghijkl"}},{"id":{"videoId":"cdefghijklm"}}]}"#)
            }
            return response(url, #"{"items":[{"id":"abcdefghijk","snippet":{"title":"直播","channelId":"UC123","description":"新聞","liveBroadcastContent":"live","thumbnails":{}},"status":{"embeddable":true,"privacyStatus":"public"},"liveStreamingDetails":{"actualStartTime":"2026-10-27T00:00:00Z","concurrentViewers":"123"}},{"id":"bcdefghijkl","snippet":{"title":"結束","channelId":"UC123","liveBroadcastContent":"none","thumbnails":{}},"status":{"embeddable":true,"privacyStatus":"public"},"liveStreamingDetails":{"actualEndTime":"2026-10-27T00:00:00Z"}},{"id":"cdefghijklm","snippet":{"title":"禁止嵌入","channelId":"UC123","liveBroadcastContent":"live","thumbnails":{}},"status":{"embeddable":false,"privacyStatus":"public"}}]}"#)
        })
        let videos = try await client.liveVideos(channelID: "UC123")
        XCTAssertEqual(videos.map(\.id), ["abcdefghijk"])
        XCTAssertEqual(videos.first?.concurrentViewers, 123)
    }

    func testHiddenViewerCountRemainsNil() async throws {
        let client = YouTubeClient(apiKey: "key", bundleID: "com.example.news", transport: { request in
            let url = request.url!
            if url.path.hasSuffix("search") { return response(url, #"{"items":[{"id":{"videoId":"abcdefghijk"}}]}"#) }
            return response(url, #"{"items":[{"id":"abcdefghijk","snippet":{"title":"新聞","channelId":"UC1","liveBroadcastContent":"live","thumbnails":{}},"status":{"embeddable":true,"privacyStatus":"public"},"liveStreamingDetails":{}}]}"#)
        })
        let videos = try await client.liveVideos(channelID: "UC1")
        XCTAssertNil(videos.first?.concurrentViewers)
    }

    func testQuotaErrorHasActionableMessageWithoutLeakingKey() async {
        let client = YouTubeClient(apiKey: "secret", bundleID: "com.example.news", transport: { request in
            response(request.url!, #"{"error":{"errors":[{"reason":"quotaExceeded"}]}}"#, status: 403)
        })
        do { _ = try await client.resolve(handle: "test"); XCTFail("應報配額錯誤") }
        catch { XCTAssertEqual(error as? YouTubeError, .quotaExceeded) }
    }
}

private func response(_ url: URL, _ json: String, status: Int = 200) -> (Data, HTTPURLResponse) {
    (Data(json.utf8), HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!)
}
