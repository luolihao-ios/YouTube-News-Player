import XCTest
import Foundation
@testable import NewsCore

final class PlaybackPolicyTests: XCTestCase {
    private func decision(_ text: String?, main: Bool = true, user: Bool = false, newWindow: Bool = false) -> PlayerNavigationDecision {
        PlayerNavigationPolicy.decision(for: text.flatMap(URL.init(string:)), isMainFrame: main, isUserActivated: user, opensNewWindow: newWindow)
    }

    func testIdentityPagesNeverEmbedOrAutomaticallyOpen() {
        for address in ["https://accounts.google.com/ServiceLogin", "https://accounts.youtube.com/", "https://www.youtube.com/signin", "https://youtube.com/login/step", "https://m.youtube.com/ServiceLogin", "https://www.youtube.com/o/oauth2/auth", "https://www.youtube.com/%73ignin"] {
            XCTAssertEqual(decision(address), .verificationRequired, address)
            XCTAssertEqual(decision(address, main: false, user: true, newWindow: true), .verificationRequired, address)
        }
    }

    func testKnownSessionMaintenanceOnlyAllowsPassiveSubframes() {
        for address in ["https://accounts.youtube.com/accounts/CheckConnection", "https://accounts.google.com/RotateCookiesPage?origin=https%3A%2F%2Fwww.youtube.com"] {
            XCTAssertEqual(decision(address, main: false), .allow, address)
            XCTAssertEqual(decision(address), .verificationRequired, address)
            XCTAssertEqual(decision(address, main: false, user: true), .verificationRequired, address)
            XCTAssertEqual(decision(address, main: false, newWindow: true), .verificationRequired, address)
            XCTAssertEqual(decision(address, main: false, user: true, newWindow: true), .verificationRequired, address)
        }
    }

    func testSessionMaintenanceExceptionDoesNotAllowOtherIdentityPaths() {
        for address in ["https://accounts.youtube.com/accounts/CheckConnection/next", "https://accounts.youtube.com/RotateCookiesPage", "https://accounts.google.com/accounts/CheckConnection", "https://accounts.google.com/RotateCookiesPage/next", "https://accounts.google.com/ServiceLogin", "https://accounts.youtube.com/accounts/Unknown"] {
            XCTAssertEqual(decision(address, main: false), .verificationRequired, address)
        }
    }

    func testWatchURLQueryDoesNotTurnIntoAuthenticationNavigation() {
        XCTAssertEqual(decision("https://www.youtube.com/watch?v=abc&continue=https%3A%2F%2Faccounts.google.com%2FServiceLogin"), .allow)
        XCTAssertEqual(decision("https://www.youtube.com/watch?v=abc&continue=https%3A%2F%2Faccounts.google.com%2FServiceLogin", user: true), .openExternal)
    }

    func testOnlyExplicitTopLevelOrNewWindowClicksOpenExternally() {
        let address = "https://www.youtube.com/watch?v=abc"
        XCTAssertEqual(decision(address), .allow)
        XCTAssertEqual(decision(address, main: false), .allow)
        XCTAssertEqual(decision(address, main: false, user: true), .allow)
        XCTAssertEqual(decision(address, user: true), .openExternal)
        XCTAssertEqual(decision(address, main: false, user: true, newWindow: true), .openExternal)
        XCTAssertEqual(decision(address, main: false, newWindow: true), .cancel)
        XCTAssertEqual(decision("https://consent.youtube.com/m"), .allow)
        XCTAssertEqual(decision("https://www.google.com/recaptcha/api2/anchor", main: false), .allow)
    }

    func testDomainMatchingDoesNotConfuseSuffixesWithIdentityHosts() {
        for address in ["https://youtube.com.evil.test/signin", "https://accounts.google.com.evil.test/", "https://evilyoutube.com/login"] {
            XCTAssertEqual(decision(address), .allow)
            XCTAssertEqual(decision(address, user: true), .openExternal)
        }
    }

    func testUnsafeSchemesAndCredentialURLsAreCancelled() {
        for address in [nil, "http://www.youtube.com/", "javascript:alert(1)", "data:text/html,hi", "file:///tmp/player.html", "youtube://watch?v=abc", "https://user:password@youtube.com/watch", "about:config"] as [String?] {
            XCTAssertEqual(decision(address, user: true, newWindow: true), .cancel, address ?? "nil")
        }
        XCTAssertEqual(decision("about:blank"), .allow)
        XCTAssertEqual(decision("about:srcdoc", main: false), .allow)
    }

    func testFailureMessagesRetainCodesAndExplainVerificationBoundary() {
        for code in [101, 150] {
            let message = PlayerFailure.message(for: code)
            XCTAssertTrue(message.contains(String(code)))
            XCTAssertTrue(message.contains("驗證"))
            XCTAssertTrue(message.contains("不會同步"))
            XCTAssertFalse(message.contains("頻道禁止"))
        }
        XCTAssertTrue(PlayerFailure.message(for: 153).contains("身分"))
        XCTAssertTrue(PlayerFailure.message(for: 100).contains("私人"))
        XCTAssertTrue(PlayerFailure.message(for: 987).contains("987"))
        XCTAssertTrue(PlayerFailure.verificationMessage.contains("不會同步"))
    }
}
