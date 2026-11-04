import Foundation

/// 验证和观看留在同一个系统网页中；关闭后不自动重试未登录的内嵌播放器。
public struct InAppPlaybackRecovery: Sendable {
    public private(set) var activeVideoID: String?
    private var webpageVideoIDs: Set<String> = []

    public init() {}

    public static func shouldOfferWebpage(for code: Int) -> Bool { [101, 150].contains(code) }

    public func usesWebpage(for videoID: String) -> Bool { webpageVideoIDs.contains(videoID) }

    @discardableResult
    public mutating func present(videoID: String, automatically: Bool = true) -> Bool {
        guard videoID.utf8.count == 11,
              videoID.utf8.allSatisfy({ (65...90).contains($0) || (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95 }),
              activeVideoID == nil,
              !automatically || !webpageVideoIDs.contains(videoID) else { return false }
        webpageVideoIDs.insert(videoID)
        activeVideoID = videoID
        return true
    }

    public mutating func dismiss() { activeVideoID = nil }
}
