import XCTest
@testable import NewsCore

final class InAppPlaybackRecoveryTests: XCTestCase {
    func testVerificationOpensTheSameVideoInApp() {
        var recovery = InAppPlaybackRecovery()
        XCTAssertTrue(recovery.present(videoID: "2wXzyS-kSNk"))
        XCTAssertEqual(recovery.activeVideoID, "2wXzyS-kSNk")
        XCTAssertTrue(recovery.usesWebpage(for: "2wXzyS-kSNk"))
    }

    func testRepeatedErrorsAndDismissalNeverReopenOrReturnToEmbed() {
        var recovery = InAppPlaybackRecovery()
        XCTAssertTrue(recovery.present(videoID: "2wXzyS-kSNk"))
        XCTAssertFalse(recovery.present(videoID: "2wXzyS-kSNk"))
        recovery.dismiss()
        XCTAssertNil(recovery.activeVideoID)
        XCTAssertFalse(recovery.present(videoID: "2wXzyS-kSNk"))
        XCTAssertTrue(recovery.usesWebpage(for: "2wXzyS-kSNk"))
    }

    func testUserCanReopenButSwitchingVideoDoesNotReuseOldDestination() {
        var recovery = InAppPlaybackRecovery()
        XCTAssertTrue(recovery.present(videoID: "2wXzyS-kSNk"))
        recovery.dismiss()
        XCTAssertTrue(recovery.present(videoID: "2wXzyS-kSNk", automatically: false))
        recovery.dismiss()
        XCTAssertFalse(recovery.usesWebpage(for: "m_dhMSvUCIc"))
        XCTAssertTrue(recovery.present(videoID: "m_dhMSvUCIc"))
        XCTAssertEqual(recovery.activeVideoID, "m_dhMSvUCIc")
    }

    func testUnrelatedErrorsDoNotAskForLogin() {
        for code in [2, 5, 100, 153, -1, 987] {
            XCTAssertFalse(InAppPlaybackRecovery.shouldOfferWebpage(for: code))
        }
        for code in [101, 150] { XCTAssertTrue(InAppPlaybackRecovery.shouldOfferWebpage(for: code)) }
    }

    func testInvalidVideoNeverOpensArbitraryURL() {
        var recovery = InAppPlaybackRecovery()
        for identity in ["", "short", "abcdefghijk?next=evil", "https://evil.test", "abcdefghijk\n"] {
            XCTAssertFalse(recovery.present(videoID: identity, automatically: false))
        }
        XCTAssertNil(recovery.activeVideoID)
    }

    func testActiveSystemPageCannotBeReplacedByALateFailureFromAnotherVideo() {
        var recovery = InAppPlaybackRecovery()
        XCTAssertTrue(recovery.present(videoID: "2wXzyS-kSNk"))
        XCTAssertFalse(recovery.present(videoID: "m_dhMSvUCIc"))
        XCTAssertFalse(recovery.present(videoID: "m_dhMSvUCIc", automatically: false))
        XCTAssertEqual(recovery.activeVideoID, "2wXzyS-kSNk")
        XCTAssertFalse(recovery.usesWebpage(for: "m_dhMSvUCIc"))
    }
}
