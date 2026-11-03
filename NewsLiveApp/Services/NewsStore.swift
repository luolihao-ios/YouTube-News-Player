import Foundation
import SwiftUI
import NewsCore

enum AppTab: Hashable { case home, channels, favorites, settings }

@MainActor
final class NewsStore: ObservableObject {
    @Published var selectedTab = AppTab.home
    @Published var selectedCategory: ChannelCategory?
    @Published var search = ""
    @Published var activeChannel: ChannelSeed?
    @Published private(set) var channels: [ChannelSeed] = []
    @Published private(set) var snapshots: [String: ChannelSnapshot] = [:]
    @Published private(set) var loading = Set<String>()
    @Published private(set) var errors: [String: String] = [:]
    @Published private(set) var library: LibraryState
    @Published private(set) var catalogError: String?
    @Published private(set) var clock = Date()
    private let defaults: UserDefaults
    private let cacheURL: URL
    private var cacheGeneration = 0
    private var client: YouTubeClient { YouTubeClient(apiKey: AppConfiguration.apiKey, bundleID: AppConfiguration.bundleID) }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        library = LibraryState.restore(from: defaults.data(forKey: "library.v1"))
        let root = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        cacheURL = root.appendingPathComponent("youtube-metadata-v1.json")
        if let url = Bundle.main.url(forResource: "channels", withExtension: "json"),
           let data = try? Data(contentsOf: url),
           let seeds = try? JSONDecoder().decode([ChannelSeed].self, from: data) {
            channels = seeds
        } else { catalogError = "頻道清單無法讀取，請重新安裝或聯絡開發者。" }
        if let data = try? Data(contentsOf: cacheURL),
           let saved = try? JSONDecoder().decode([String: ChannelSnapshot].self, from: data) {
            snapshots = saved.filter { !$0.value.isExpired(at: Date()) }
            persistCache()
        }
    }

    var filteredChannels: [ChannelSeed] { ChannelFilter.apply(channels, query: search, category: selectedCategory) }
    var favoriteChannels: [ChannelSeed] { library.favorites.compactMap { id in channels.first { $0.id == id } } }
    var recentChannels: [ChannelSeed] { library.recent.compactMap { id in channels.first { $0.id == id } } }
    var liveChannels: [ChannelSeed] { channels.filter { snapshots[$0.id]?.isFresh == true && !(snapshots[$0.id]?.videos.isEmpty ?? true) } }
    var recommendations: [ChannelSeed] { channels.filter { !isFavorite($0) } }
    func isFavorite(_ channel: ChannelSeed) -> Bool { library.favorites.contains(channel.id) }
    func toggleFavorite(_ channel: ChannelSeed) {
        library.setFavorite(channel.id, enabled: !isFavorite(channel)); persistLibrary()
    }
    func removeFavorites(at indices: IndexSet) {
        let ids = indices.compactMap { favoriteChannels.indices.contains($0) ? favoriteChannels[$0].id : nil }
        for id in ids { library.setFavorite(id, enabled: false) }; persistLibrary()
    }
    func moveFavorites(from indices: IndexSet, to destination: Int) {
        library.moveFavorites(from: indices, to: destination); persistLibrary()
    }
    func didStartPlaying(_ channel: ChannelSeed) {
        library.recordViewing(channel.id, enabled: defaults.bool(forKey: "historyEnabled")); persistLibrary()
    }
    func clearHistory() { library.clearHistory(); persistLibrary() }
    func clearCache() {
        cacheGeneration += 1
        snapshots = [:]; errors = [:]; loading = []
        try? FileManager.default.removeItem(at: cacheURL)
    }
    func expireCache() {
        clock = Date()
        let valid = snapshots.filter { !$0.value.isExpired(at: clock) }
        if valid.count != snapshots.count { snapshots = valid; persistCache() }
    }
    func open(_ channel: ChannelSeed) { activeChannel = channel }
    func browse(_ category: ChannelCategory? = nil) {
        selectedCategory = category; search = ""; selectedTab = .channels
    }

    func bootstrap() async {
        expireCache()
        guard AppConfiguration.isConfigured else { return }
        await refresh(Array(channels.prefix(3)))
    }
    func refresh(_ items: [ChannelSeed], force: Bool = false) async {
        // 不在背景輪詢。依序查詢，避免首頁同時發送大量 search.list。
        for channel in items {
            guard !Task.isCancelled else { return }
            await refresh(channel, force: force)
            if errors[channel.id] == YouTubeError.quotaExceeded.localizedDescription { return }
        }
    }
    func refresh(_ channel: ChannelSeed, force: Bool = false) async {
        expireCache()
        guard !loading.contains(channel.id) else { return }
        if !force, snapshots[channel.id]?.isFresh == true { return }
        let generation = cacheGeneration
        let api = client
        loading.insert(channel.id); errors[channel.id] = nil
        defer { if generation == cacheGeneration { loading.remove(channel.id) } }
        do {
            let resolved: ResolvedChannel
            let resolvedAt: Date
            if let existing = snapshots[channel.id], existing.canReuseChannel(at: Date()) {
                resolved = existing.channel
                resolvedAt = existing.channelResolvedAt
            } else { resolved = try await api.resolve(handle: channel.id, channelID: channel.youtubeChannelID); resolvedAt = Date() }
            guard generation == cacheGeneration else { return }
            let videos = try await api.liveVideos(channelID: resolved.id)
            try Task.checkCancellation()
            guard generation == cacheGeneration else { return }
            snapshots[channel.id] = ChannelSnapshot(channel: resolved, videos: videos, checkedAt: Date(), channelResolvedAt: resolvedAt)
            persistCache()
        } catch is CancellationError { return }
        catch { if generation == cacheGeneration { errors[channel.id] = error.localizedDescription } }
    }

    func statusText(_ channel: ChannelSeed) -> String {
        if loading.contains(channel.id) { return "正在查詢 YouTube…" }
        if errors[channel.id] != nil { return "查詢失敗・點擊重試" }
        guard let snapshot = snapshots[channel.id] else { return "點擊查看直播" }
        if !snapshot.isFresh { return "上次資料・點擊更新" }
        guard let video = snapshot.videos.first else { return "暫無可嵌入的公開直播" }
        return video.viewerText ?? "YouTube 直播・未提供觀看人數"
    }
    private func persistLibrary() {
        if let data = try? JSONEncoder().encode(library) { defaults.set(data, forKey: "library.v1") }
    }
    private func persistCache() {
        snapshots = snapshots.filter { !$0.value.isExpired(at: Date()) }
        if let data = try? JSONEncoder().encode(snapshots) { try? data.write(to: cacheURL, options: .atomic) }
    }
}
