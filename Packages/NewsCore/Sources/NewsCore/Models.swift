import Foundation

public enum ChannelCategory: String, Codable, CaseIterable, Sendable, Identifiable {
    case taiwan = "台灣新聞", international = "國際新聞", finance = "財經", general = "綜合"
    public var id: String { rawValue }
    public var symbol: String {
        switch self {
        case .taiwan: return "building.2.crop.circle"
        case .international: return "globe.asia.australia"
        case .finance: return "chart.line.uptrend.xyaxis"
        case .general: return "newspaper"
        }
    }
}

public struct ChannelSeed: Codable, Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let subtitle: String
    public let category: ChannelCategory
    public let monogram: String
    public let color: String
    public let youtubeChannelID: String?
    public init(id: String, name: String, subtitle: String, category: ChannelCategory, monogram: String, color: String, youtubeChannelID: String? = nil) {
        self.id = id; self.name = name; self.subtitle = subtitle
        self.category = category; self.monogram = monogram; self.color = color
        self.youtubeChannelID = youtubeChannelID
    }
    public var channelURL: URL {
        if let youtubeChannelID { return URL(string: "https://www.youtube.com/channel/\(youtubeChannelID)")! }
        return URL(string: "https://www.youtube.com/@\(id)")!
    }
}

public struct ResolvedChannel: Codable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let thumbnailURL: URL?
    public init(id: String, title: String, thumbnailURL: URL?) {
        self.id = id; self.title = title; self.thumbnailURL = thumbnailURL
    }
}

public struct ChannelSnapshot: Codable, Sendable {
    public let channel: ResolvedChannel
    public let videos: [LiveVideo]
    public let checkedAt: Date
    public let channelResolvedAt: Date
    public init(channel: ResolvedChannel, videos: [LiveVideo], checkedAt: Date, channelResolvedAt: Date) {
        self.channel = channel; self.videos = videos; self.checkedAt = checkedAt; self.channelResolvedAt = channelResolvedAt
    }
    public var isFresh: Bool { isFresh(at: Date()) }
    public func isFresh(at now: Date) -> Bool {
        let age = now.timeIntervalSince(checkedAt)
        return age >= 0 && age < 900
    }
    public func canReuseChannel(at now: Date) -> Bool {
        let age = now.timeIntervalSince(channelResolvedAt)
        return age >= 0 && age < 86400
    }
    public func isExpired(at now: Date) -> Bool {
        let age = now.timeIntervalSince(checkedAt)
        return age < 0 || age >= 86400 || !canReuseChannel(at: now)
    }
}

public struct LiveVideo: Codable, Identifiable, Equatable, Sendable {
    public let id: String
    public let channelID: String
    public let title: String
    public let description: String
    public let thumbnailURL: URL?
    public let concurrentViewers: UInt?
    public let fetchedAt: Date
    public var watchURL: URL { URL(string: "https://www.youtube.com/watch?v=\(id)")! }
    public var viewerText: String? {
        concurrentViewers.map { "\($0.formatted()) 人正在觀看" }
    }
}

public enum ChannelFilter {
    public static func preferred(_ channels: [ChannelSeed], liveIDs: Set<String>, category: ChannelCategory?) -> [ChannelSeed] {
        let visible = apply(channels, query: "", category: category)
        let live = visible.filter { liveIDs.contains($0.id) }
        return live.isEmpty ? visible : live
    }
    public static func apply(_ channels: [ChannelSeed], query: String, category: ChannelCategory?) -> [ChannelSeed] {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return channels.filter {
            (category == nil || $0.category == category) &&
            (text.isEmpty || "\($0.name) \($0.id) \($0.subtitle)".localizedStandardContains(text))
        }
    }
}

public struct LibraryState: Codable, Equatable, Sendable {
    public private(set) var favorites: [String] = []
    public private(set) var recent: [String] = []
    public init() {}

    public static func restore(from data: Data?) -> Self {
        guard let data, var state = try? JSONDecoder().decode(Self.self, from: data) else { return Self() }
        state.favorites = unique(state.favorites)
        state.recent = Array(unique(state.recent).prefix(20))
        return state
    }

    public mutating func setFavorite(_ id: String, enabled: Bool) {
        favorites.removeAll { $0 == id }
        if enabled { favorites.append(id) }
    }
    public mutating func moveFavorites(from indices: IndexSet, to destination: Int) {
        let moving = indices.sorted().compactMap { favorites.indices.contains($0) ? favorites[$0] : nil }
        let valid = indices.filter { favorites.indices.contains($0) }
        for index in valid.sorted(by: >) { favorites.remove(at: index) }
        let insertion = max(0, min(favorites.count, destination - valid.filter { $0 < destination }.count))
        favorites.insert(contentsOf: moving, at: insertion)
    }
    public mutating func recordViewing(_ id: String, enabled: Bool) {
        guard enabled else { return }
        recent.removeAll { $0 == id }
        recent.insert(id, at: 0)
        recent = Array(recent.prefix(20))
    }
    public mutating func clearHistory() { recent = [] }
    private static func unique(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { seen.insert($0).inserted }
    }
}

public struct PlayerConfiguration: Sendable {
    public let videoID: String
    public let origin: URL
    public init(videoID: String, bundleID: String) throws {
        guard videoID.range(of: #"^[A-Za-z0-9_-]{11}$"#, options: .regularExpression) != nil,
              bundleID.range(of: #"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$"#, options: .regularExpression) != nil,
              let origin = URL(string: "https://\(bundleID.lowercased())") else {
            throw YouTubeError.invalidPlayerConfiguration
        }
        self.videoID = videoID; self.origin = origin
    }
    public var json: String {
        let data = try! JSONSerialization.data(withJSONObject: ["videoID": videoID, "origin": origin.absoluteString], options: [.sortedKeys, .withoutEscapingSlashes])
        return String(decoding: data, as: UTF8.self)
    }
}

public enum AppVersion {
    public static func isNewer(_ remote: String, than local: String) -> Bool {
        func components(_ text: String) -> [Int]? {
            let parts = text.split(separator: ".", omittingEmptySubsequences: false)
            guard !parts.isEmpty, parts.allSatisfy({ !$0.isEmpty && $0.allSatisfy(\.isNumber) }) else { return nil }
            let numbers = parts.compactMap { Int($0) }
            return numbers.count == parts.count ? numbers : nil
        }
        guard let lhs = components(remote), let rhs = components(local) else { return false }
        for index in 0..<max(lhs.count, rhs.count) {
            let a = index < lhs.count ? lhs[index] : 0
            let b = index < rhs.count ? rhs[index] : 0
            if a != b { return a > b }
        }
        return false
    }
}
