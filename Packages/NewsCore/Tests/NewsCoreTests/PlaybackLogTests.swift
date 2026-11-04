import XCTest
import Foundation
@testable import NewsCore

final class PlaybackLogTests: XCTestCase {
    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("PlaybackLogTests-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    private func entries(_ url: URL) throws -> [[String: Any]] {
        try String(contentsOf: url, encoding: .utf8).split(separator: "\n").map {
            try XCTUnwrap(JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any])
        }
    }

    func testCreatesDirectoryAndWritesValidJSONLines() throws {
        let directory = try temporaryDirectory().appendingPathComponent("Documents/PlaybackDiagnostics")
        let log = try PlaybackLog(directory: directory)
        XCTAssertTrue(FileManager.default.fileExists(atPath: log.fileURL.path))
        try log.record("player.state", fields: ["state": "playing", "videoID": "abc123"])
        let result = try entries(log.fileURL)
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(result[0]["event"] as? String, "player.state")
        XCTAssertEqual((result[0]["fields"] as? [String: String])?["state"], "playing")
        XCTAssertNotNil(result[0]["timestamp"])
    }

    func testSensitiveFieldsAndURLQueriesNeverReachDisk() throws {
        let log = try PlaybackLog(directory: temporaryDirectory())
        try log.record("navigation", fields: [
            "cookie": "cookie-secret", "TOKEN": "token-secret", "apiKey": "key-secret",
            "authorization": "auth-secret", "password": "password-secret",
            "title": "private-title", "rawerror": "raw-error-secret", "fullURL": "https://example.com/?query-secret",
            "path": "/embed/abc?access_token=query-secret#fragment-secret",
            "host": "www.youtube.com", "reason": "Bearer credential-secret",
            "origin": "https://example.com/?query-secret", "state": "token=credential-secret"
        ])
        try log.record("https://example.com/?event-secret", fields: ["reason": "https://user:password@example.com/"])
        let text = try String(contentsOf: log.fileURL, encoding: .utf8)
        for secret in ["cookie-secret", "token-secret", "key-secret", "auth-secret", "password-secret", "private-title", "raw-error-secret", "query-secret", "fragment-secret", "credential-secret", "event-secret", "user:password"] {
            XCTAssertFalse(text.contains(secret), secret)
        }
        let fields = try XCTUnwrap(entries(log.fileURL).first?["fields"] as? [String: String])
        XCTAssertEqual(fields["path"], "/embed/abc")
        XCTAssertEqual(fields["host"], "www.youtube.com")
        XCTAssertEqual(fields["reason"], "[redacted]")
    }

    func testLimitsFieldAndEventLengths() throws {
        let log = try PlaybackLog(directory: temporaryDirectory())
        try log.record(String(repeating: "e", count: 400), fields: ["state": String(repeating: "中", count: 2_000)])
        let entry = try XCTUnwrap(entries(log.fileURL).first)
        XCTAssertLessThanOrEqual((entry["event"] as? String)?.count ?? 0, 80)
        XCTAssertLessThanOrEqual(((entry["fields"] as? [String: String])?["state"] ?? "").count, 256)
    }

    func testCredentialsDisguisedAsAllowedFieldsAreRedacted() throws {
        let log = try PlaybackLog(directory: temporaryDirectory())
        for value in ["client_secret=hidden-value", "credentials=hidden-value", "api%5Fkey=hidden-value", "https://example.com/%3Fhidden-value"] {
            try log.record("navigation", fields: ["reason": value])
        }
        let result = try entries(log.fileURL)
        XCTAssertEqual(result.count, 4)
        for entry in result {
            XCTAssertEqual((entry["fields"] as? [String: String])?["reason"], "[redacted]")
        }
    }

    func testRotationBoundsBothFilesAndRetainsOnlyOneBackup() throws {
        let directory = try temporaryDirectory()
        let log = try PlaybackLog(directory: directory, maxBytes: 512)
        for index in 0..<30 {
            try log.record("player.state", fields: ["session": "\(index)", "state": String(repeating: "x", count: 400)])
        }
        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.fileSizeKey])
        XCTAssertEqual(files.count, 2)
        for file in files {
            XCTAssertLessThanOrEqual(try Data(contentsOf: file).count, 512)
            XCTAssertFalse(try entries(file).isEmpty)
        }
        try log.clear()
        XCTAssertTrue(try Data(contentsOf: log.fileURL).isEmpty)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).count, 1)
        try log.record("restart", fields: [:])
        XCTAssertEqual(try entries(log.fileURL).count, 1)
    }

    func testOversizedSingleEntryStillRespectsByteBudget() throws {
        let log = try PlaybackLog(directory: temporaryDirectory(), maxBytes: 200)
        try log.record(String(repeating: "x", count: 100), fields: ["reason": String(repeating: "中", count: 1_000)])
        XCTAssertLessThanOrEqual(try Data(contentsOf: log.fileURL).count, 200)
        XCTAssertEqual(try entries(log.fileURL).count, 1)
    }

    func testConcurrentWritesKeepEveryEntryAndValidJSON() throws {
        let log = try PlaybackLog(directory: temporaryDirectory(), maxBytes: 1_000_000)
        let failures = LockedFailures()
        DispatchQueue.concurrentPerform(iterations: 200) { index in
            do { try log.record("concurrent", fields: ["session": "\(index)"]) }
            catch { failures.append(error) }
        }
        XCTAssertEqual(failures.count, 0)
        let result = try entries(log.fileURL)
        XCTAssertEqual(result.count, 200)
        let sessions = result.compactMap { ($0["fields"] as? [String: String])?["session"] }
        XCTAssertEqual(Set(sessions).count, 200)
    }
}

private final class LockedFailures: @unchecked Sendable {
    private let lock = NSLock()
    private var errors: [Error] = []
    func append(_ error: Error) { lock.lock(); defer { lock.unlock() }; errors.append(error) }
    var count: Int { lock.lock(); defer { lock.unlock() }; return errors.count }
}
