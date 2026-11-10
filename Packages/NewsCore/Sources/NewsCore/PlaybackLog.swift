import Foundation

/// 只記錄播放器排錯白名單欄位。呼叫端應將 directory 設在 App 的文件目錄。
public final class PlaybackLog: @unchecked Sendable {
    public let fileURL: URL
    private let backupURL: URL
    private let maxBytes: Int
    private let lock = NSLock()
    private static let allowedFields: Set<String> = [
        "session", "videoID", "platform", "appVersion", "build", "code", "state",
        "host", "path", "decision", "origin", "reason", "errorDomain", "errorCode", "referrerPresent", "sessionPresent"
    ]
    private enum LogError: Error { case invalidMaximumSize, unableToCreateFile }

    public init(directory: URL, maxBytes: Int = 262_144) throws {
        guard maxBytes > 0 else { throw LogError.invalidMaximumSize }
        self.maxBytes = maxBytes
        fileURL = directory.appendingPathComponent("playback.jsonl")
        backupURL = directory.appendingPathComponent("playback.jsonl.1")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: fileURL.path) {
            guard FileManager.default.createFile(atPath: fileURL.path, contents: Data(), attributes: [.posixPermissions: 0o600]) else {
                throw LogError.unableToCreateFile
            }
        }
        // 修改容量設定或接手舊檔時，也只保留完整且符合上限的最近紀錄。
        try boundExistingFile(fileURL)
        try boundExistingFile(backupURL)
    }

    public func record(_ event: String, fields: [String: String] = [:]) throws {
        lock.lock()
        defer { lock.unlock() }

        var safeFields: [String: String] = [:]
        for (key, value) in fields where Self.allowedFields.contains(key) {
            safeFields[key] = Self.safeValue(value, field: key)
        }
        var safeEvent = Self.safeEvent(event)
        let timestamp = ISO8601DateFormatter().string(from: Date())
        func serialized() throws -> Data {
            var data = try JSONSerialization.data(withJSONObject: ["timestamp": timestamp, "event": safeEvent, "fields": safeFields], options: [.sortedKeys])
            data.append(0x0A)
            return data
        }
        var data = try serialized()
        if data.count > maxBytes {
            safeFields = [:]
            data = try serialized()
        }
        if data.count > maxBytes {
            safeEvent = "truncated"
            data = try serialized()
        }
        // 極小容量無法容納一筆 JSON 時，不寫入半筆紀錄。
        guard data.count <= maxBytes else { return }

        let size = try byteCount(at: fileURL)
        if size + UInt64(data.count) > UInt64(maxBytes) {
            if FileManager.default.fileExists(atPath: backupURL.path) {
                try FileManager.default.removeItem(at: backupURL)
            }
            try FileManager.default.moveItem(at: fileURL, to: backupURL)
            guard FileManager.default.createFile(atPath: fileURL.path, contents: Data(), attributes: [.posixPermissions: 0o600]) else {
                throw LogError.unableToCreateFile
            }
        }
        let handle = try FileHandle(forWritingTo: fileURL)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
    }

    public func clear() throws {
        lock.lock()
        defer { lock.unlock() }
        try Data().write(to: fileURL, options: [.atomic])
        if FileManager.default.fileExists(atPath: backupURL.path) {
            try FileManager.default.removeItem(at: backupURL)
        }
    }

    private func boundExistingFile(_ url: URL) throws {
        guard FileManager.default.fileExists(atPath: url.path),
              try byteCount(at: url) > UInt64(maxBytes) else { return }
        let data = try Data(contentsOf: url)
        let suffix = data.suffix(maxBytes)
        let bounded: Data
        if let newline = suffix.firstIndex(of: 0x0A) {
            bounded = Data(suffix.suffix(from: suffix.index(after: newline)))
        } else {
            bounded = Data()
        }
        try bounded.write(to: url, options: [.atomic])
    }

    private func byteCount(at url: URL) throws -> UInt64 {
        // URL 资源值会缓存；连续写入时必须从实际文件句柄读取当前位置上限。
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        return try handle.seekToEnd()
    }

    private static func safeEvent(_ event: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "._-"))
        guard !containsCredentials(event), event.unicodeScalars.allSatisfy({ allowed.contains($0) }) else { return "redacted" }
        return String(event.prefix(80))
    }

    private static func safeValue(_ value: String, field: String) -> String {
        var sanitized = value
        if field == "path" {
            sanitized = String(value.prefix(while: { $0 != "?" && $0 != "#" }))
            // 路徑欄位不能承載完整 URL、帳號或其他自由文字。
            guard sanitized.hasPrefix("/"), !sanitized.hasPrefix("//") else { return "[redacted]" }
        }
        let decoded = sanitized.removingPercentEncoding ?? sanitized
        guard !containsCredentials(decoded),
              !decoded.contains("?"), !decoded.contains("#"),
              !decoded.contains("@"), !decoded.contains("\n"), !decoded.contains("\r") else { return "[redacted]" }
        return String(sanitized.prefix(256))
    }

    private static func containsCredentials(_ value: String) -> Bool {
        let lower = value.lowercased()
        return ["cookie", "token", "apikey", "api_key", "authorization", "password", "passwd", "bearer ", "client_secret", "credential", "access_key"].contains(where: { lower.contains($0) })
    }
}
