import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public enum YouTubeError: LocalizedError, Equatable, Sendable {
    case missingAPIKey, quotaExceeded, accessDenied, channelNotFound, invalidResponse, invalidPlayerConfiguration
    case server(Int)
    public var errorDescription: String? {
        switch self {
        case .missingAPIKey: return "尚未設定 YouTube API。請由開發者完成服務設定。"
        case .quotaExceeded: return "YouTube API 配額暫時用完，請稍後重試，或前往 YouTube 觀看。"
        case .accessDenied: return "YouTube API 授權失敗，請檢查 API Key、服務啟用和 App 限制設定。"
        case .channelNotFound: return "找不到這個 YouTube 頻道。"
        case .invalidResponse: return "YouTube 回傳的資料無法讀取，請稍後重試。"
        case .invalidPlayerConfiguration: return "播放器設定無效。"
        case .server(let code): return "YouTube 服務暫時無法使用（\(code)）。"
        }
    }
}

public struct YouTubeClient: Sendable {
    public typealias Transport = @Sendable (URLRequest) async throws -> (Data, HTTPURLResponse)
    private let apiKey: String
    private let bundleID: String
    private let transport: Transport

    public init(apiKey: String, bundleID: String, transport: @escaping Transport = { request in
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw YouTubeError.invalidResponse }
        return (data, http)
    }) {
        self.apiKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        self.bundleID = bundleID
        self.transport = transport
    }

    public func resolve(handle: String, channelID: String? = nil) async throws -> ResolvedChannel {
        // 目录使用稳定 Channel ID；保留 handle 入口兼容未固定身份的新频道。
        let identity = channelID.map { ["id": $0] } ?? ["forHandle": handle]
        let envelope: ChannelEnvelope = try await get("channels", parameters: identity.merging(["part": "snippet"]) { _, new in new })
        guard let item = envelope.items.first, channelID == nil || item.id == channelID else { throw YouTubeError.channelNotFound }
        return ResolvedChannel(id: item.id, title: item.snippet.title, thumbnailURL: item.snippet.thumbnails?.best)
    }

    public func liveVideos(channelID: String) async throws -> [LiveVideo] {
        let search: SearchEnvelope = try await get("search", parameters: [
            "part": "snippet", "channelId": channelID, "type": "video", "eventType": "live",
            "videoEmbeddable": "true", "videoSyndicated": "true", "maxResults": "5"
        ])
        let ids = search.items.compactMap(\.id.videoId)
        guard !ids.isEmpty else { return [] }
        let videos: VideoEnvelope = try await get("videos", parameters: [
            "part": "snippet,status,liveStreamingDetails", "id": ids.joined(separator: ",")
        ])
        return videos.items.compactMap { video in
            guard video.status.embeddable == true,
                  video.status.privacyStatus == "public",
                  video.snippet.channelId == channelID,
                  video.snippet.liveBroadcastContent == "live",
                  video.liveStreamingDetails?.actualEndTime == nil,
                  video.id.range(of: #"^[A-Za-z0-9_-]{11}$"#, options: .regularExpression) != nil else { return nil }
            return LiveVideo(id: video.id, channelID: channelID, title: video.snippet.title,
                             description: video.snippet.description ?? "", thumbnailURL: video.snippet.thumbnails?.best,
                             concurrentViewers: video.liveStreamingDetails?.concurrentViewers.flatMap(UInt.init), fetchedAt: Date())
        }
    }

    private func get<T: Decodable>(_ path: String, parameters: [String: String]) async throws -> T {
        guard !apiKey.isEmpty, !apiKey.contains("$("), apiKey != "YOUR_YOUTUBE_API_KEY" else { throw YouTubeError.missingAPIKey }
        var components = URLComponents(string: "https://www.googleapis.com/youtube/v3/\(path)")!
        components.queryItems = (parameters.merging(["key": apiKey]) { _, new in new })
            .sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        var request = URLRequest(url: components.url!)
        request.timeoutInterval = 20
        request.setValue(bundleID, forHTTPHeaderField: "X-Ios-Bundle-Identifier")
        let (data, response) = try await transport(request)
        guard (200..<300).contains(response.statusCode) else {
            let reason = (try? JSONDecoder().decode(ErrorEnvelope.self, from: data))?.error.errors?.first?.reason
            if reason == "quotaExceeded" || reason == "dailyLimitExceeded" || response.statusCode == 429 { throw YouTubeError.quotaExceeded }
            if response.statusCode == 400 || response.statusCode == 401 || response.statusCode == 403 { throw YouTubeError.accessDenied }
            throw YouTubeError.server(response.statusCode)
        }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw YouTubeError.invalidResponse }
    }
}

private struct Thumbnails: Decodable {
    struct Image: Decodable { let url: URL }
    let `default`: Image?
    let medium: Image?
    let high: Image?
    let maxres: Image?
    var best: URL? { maxres?.url ?? high?.url ?? medium?.url ?? `default`?.url }
}
private struct Snippet: Decodable {
    let title: String
    let channelId: String?
    let description: String?
    let liveBroadcastContent: String?
    let thumbnails: Thumbnails?
}
private struct ChannelEnvelope: Decodable {
    struct Item: Decodable { let id: String; let snippet: Snippet }
    let items: [Item]
}
private struct SearchEnvelope: Decodable {
    struct Item: Decodable {
        struct ID: Decodable { let videoId: String? }
        let id: ID
    }
    let items: [Item]
}
private struct VideoEnvelope: Decodable {
    struct Item: Decodable {
        struct Status: Decodable { let embeddable: Bool?; let privacyStatus: String? }
        struct Details: Decodable { let actualEndTime: String?; let concurrentViewers: String? }
        let id: String
        let snippet: Snippet
        let status: Status
        let liveStreamingDetails: Details?
    }
    let items: [Item]
}
private struct ErrorEnvelope: Decodable {
    struct ErrorBody: Decodable {
        struct Detail: Decodable { let reason: String }
        let errors: [Detail]?
    }
    let error: ErrorBody
}
