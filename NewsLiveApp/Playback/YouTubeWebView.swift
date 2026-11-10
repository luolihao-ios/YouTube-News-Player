import SwiftUI
import WebKit
import NewsCore
#if os(macOS)
import AppKit
typealias NativePlayerRepresentable = NSViewRepresentable
#else
import UIKit
typealias NativePlayerRepresentable = UIViewRepresentable
#endif

enum PlayerEvent {
    case ready, state(Int), failed(String)
}

@MainActor
final class PlayerSession: ObservableObject {
    weak var webView: WKWebView?
    var usesWrapper = true
    let diagnosticID = UUID().uuidString
    private static weak var playingSession: PlayerSession?
    func pause() {
        guard let webView else { return }
        webView.pauseAllMediaPlayback(completionHandler: nil)
        if usesWrapper {
            webView.evaluateJavaScript("window.NewsPlayer && window.NewsPlayer.pause()", completionHandler: nil)
        }
        PlaybackDiagnostics.shared.record("pause_requested", fields: ["session": diagnosticID])
    }
    static func pauseCurrent() { playingSession?.pause() }
    func claimPlayback() {
        if Self.playingSession !== self { Self.playingSession?.pause() }
        Self.playingSession = self
    }
}

struct YouTubeWebView: NativePlayerRepresentable {
    let videoID: String
    let session: PlayerSession
    var signedIn = false
    let onEvent: (PlayerEvent) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(session: session, videoID: videoID, signedIn: signedIn, onEvent: onEvent) }
    #if os(macOS)
    func makeNSView(context: Context) -> WKWebView { makeWebView(context: context) }
    func updateNSView(_ nsView: WKWebView, context: Context) {}
    static func dismantleNSView(_ nsView: WKWebView, coordinator: Coordinator) { dismantle(nsView, coordinator: coordinator) }
    #else
    func makeUIView(context: Context) -> WKWebView {
        makeWebView(context: context)
    }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) { dismantle(uiView, coordinator: coordinator) }
    #endif

    private func makeWebView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        #if !os(macOS)
        configuration.allowsInlineMediaPlayback = true
        configuration.allowsPictureInPictureMediaPlayback = false
        configuration.mediaTypesRequiringUserActionForPlayback = .all
        #endif
        configuration.websiteDataStore = PlayerWebData.store
        configuration.applicationNameForUserAgent = "YouTubeNewsLive/\(AppConfiguration.version)"
        if !signedIn { configuration.userContentController.add(context.coordinator, name: "youtube") }
        let webView = WKWebView(frame: .zero, configuration: configuration)
        #if !os(macOS)
        webView.isOpaque = false
        webView.backgroundColor = .black
        webView.scrollView.isScrollEnabled = false
        #endif
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        session.webView = webView
        session.usesWrapper = !signedIn
        do {
            let config = try PlayerConfiguration(videoID: videoID, bundleID: AppConfiguration.bundleID)
            if signedIn {
                guard let url = Bundle.main.url(forResource: "PlaybackObservation", withExtension: "js") else { throw YouTubeError.invalidPlayerConfiguration }
                context.coordinator.observationScript = try String(contentsOf: url, encoding: .utf8)
                webView.load(config.embedRequest)
                context.coordinator.record("direct_page_load", fields: ["origin": config.origin.absoluteString])
            } else {
                guard let url = Bundle.main.url(forResource: "YouTubePlayer", withExtension: "html") else { throw YouTubeError.invalidPlayerConfiguration }
                let template = try String(contentsOf: url, encoding: .utf8)
                let html = template.replacingOccurrences(of: "__PLAYER_CONFIGURATION__", with: config.json)
                // 使用实际 HTTPS 文档地址及明确 Referer；页面本身仍来自本地资源，不请求虚构域名。
                webView.loadSimulatedRequest(config.pageRequest, responseHTML: html)
                context.coordinator.record("page_load", fields: ["origin": config.origin.absoluteString, "reason": "persistent_webkit"])
            }
            context.coordinator.startTimeout()
        } catch {
            context.coordinator.record("configuration_failure")
            DispatchQueue.main.async { onEvent(.failed(error.localizedDescription)) }
        }
        return webView
    }
    private static func dismantle(_ uiView: WKWebView, coordinator: Coordinator) {
        coordinator.timeout?.cancel()
        coordinator.observation?.cancel()
        coordinator.record("player_disposed")
        uiView.pauseAllMediaPlayback(completionHandler: nil)
        if !coordinator.signedIn {
            uiView.evaluateJavaScript("window.NewsPlayer && window.NewsPlayer.destroy()", completionHandler: nil)
            uiView.configuration.userContentController.removeScriptMessageHandler(forName: "youtube")
        }
        uiView.stopLoading(); uiView.navigationDelegate = nil; uiView.uiDelegate = nil
        if coordinator.session?.webView === uiView { coordinator.session?.webView = nil }
    }

    @MainActor
    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate {
        let onEvent: (PlayerEvent) -> Void
        weak var session: PlayerSession?
        let videoID: String
        let signedIn: Bool
        private let diagnosticID: String
        var timeout: Task<Void, Never>?
        var observation: Task<Void, Never>?
        var observationScript: String?
        private var failureReported = false
        init(session: PlayerSession, videoID: String, signedIn: Bool, onEvent: @escaping (PlayerEvent) -> Void) {
            self.session = session; self.videoID = videoID; self.signedIn = signedIn; self.onEvent = onEvent; diagnosticID = session.diagnosticID
        }
        func record(_ event: String, fields: [String: String] = [:]) {
            var context = fields; context["videoID"] = videoID; context["session"] = diagnosticID
            PlaybackDiagnostics.shared.record(event, fields: context)
        }
        private func fail(_ message: String) {
            timeout?.cancel(); observation?.cancel(); failureReported = true; onEvent(.failed(message))
        }
        func startTimeout() {
            timeout = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(25)) } catch { return }
                self?.record(self?.signedIn == true ? "direct_page_timeout" : "iframe_ready_timeout")
                self?.fail("播放器連線逾時，請檢查網路後重試。可匯出播放診斷供開發者排查。")
            }
        }
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "youtube", message.frameInfo.isMainFrame,
                  let body = message.body as? [String: Any], let type = body["type"] as? String else { return }
            switch type {
            case "ready":
                timeout?.cancel(); record("iframe_ready")
                if !failureReported { onEvent(.ready) }
            case "state":
                if let state = body["state"] as? Int {
                    record("player_state", fields: ["state": String(state)])
                    if state == 1 { failureReported = false; session?.claimPlayback() }
                    if !failureReported || state == 1 { onEvent(.state(state)) }
                }
            case "error":
                let code = body["code"] as? Int ?? -1
                record("youtube_error", fields: ["code": String(code)])
                fail(PlayerFailure.message(for: code))
            case "autoplayBlocked": record("user_gesture_required")
            case "loadError":
                record("iframe_api_load_failure")
                fail("YouTube 播放器腳本無法載入，請檢查網路後重試。")
            case "diagnostic":
                // 只接收固定字段，绝不记录页面正文、Cookie 或完整网址。
                if let origin = body["origin"] as? String { record("player_document", fields: ["origin": origin]) }
            default: break
            }
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            navigationFailed(error)
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            navigationFailed(error)
        }
        private func navigationFailed(_ error: Error) {
            let failure = error as NSError
            guard failure.domain != NSURLErrorDomain || failure.code != NSURLErrorCancelled else { return }
            record("navigation_failure", fields: ["errorDomain": failure.domain, "errorCode": String(failure.code)])
            fail("播放器載入失敗，請檢查網路後重試。")
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            let url = webView.url
            let origin = url.flatMap { item in item.host.map { "\(item.scheme ?? "https")://\($0)" } } ?? "unknown"
            record("document_loaded", fields: ["origin": origin])
            if signedIn, isOfficialEmbed(url) {
                timeout?.cancel()
                failureReported = false
                onEvent(.ready)
                observeDirectPlayback(in: webView)
            }
        }

        private func isOfficialEmbed(_ url: URL?) -> Bool {
            url?.scheme == "https" && url?.host == "www.youtube.com" && url?.port == nil
                && url?.path == "/embed/\(videoID)"
        }

        private func observeDirectPlayback(in webView: WKWebView) {
            guard let observationScript else { return }
            observation?.cancel()
            observation = Task { [weak self, weak webView] in
                var previousTime: Double?
                var isPlaying = false
                while !Task.isCancelled {
                    guard let webView, self?.isOfficialEmbed(webView.url) == true else { return }
                    let value = try? await webView.evaluateJavaScript(observationScript, in: nil, contentWorld: .defaultClient)
                    guard !Task.isCancelled, let self else { return }
                    if let sample = value as? [String: Any] {
                        if sample["verificationRequired"] as? Bool == true {
                            self.record("direct_verification_required")
                            self.fail("YouTube 要求重新登入。")
                            return
                        }
                        if sample["unavailable"] as? Bool == true || sample["mediaErrorCode"] is Int {
                            self.record("direct_media_unavailable", fields: ["code": (sample["mediaErrorCode"] as? Int).map { String($0) } ?? "none"])
                            self.fail("YouTube 暫時無法播放這場直播。")
                            return
                        }
                        let currentTime = sample["playing"] as? Bool == true ? sample["time"] as? Double : nil
                        if !isPlaying, let previousTime, let currentTime, currentTime > previousTime + 0.5 {
                            isPlaying = true
                            self.record("direct_media_playing")
                            self.session?.claimPlayback()
                            self.onEvent(.state(1))
                        } else if isPlaying, currentTime == nil {
                            isPlaying = false
                            self.onEvent(.state(2))
                        }
                        previousTime = currentTime
                    }
                    do { try await Task.sleep(for: .seconds(2)) } catch { return }
                }
            }
        }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            record("web_content_terminated")
            fail("播放器已中斷，請點擊重新載入。")
        }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            var decision = PlayerNavigationPolicy.decision(for: action.request.url,
                isMainFrame: action.targetFrame?.isMainFrame == true,
                isUserActivated: action.navigationType == .linkActivated,
                opensNewWindow: action.targetFrame == nil)
            if signedIn, action.targetFrame?.isMainFrame == true, decision == .allow, !isOfficialEmbed(action.request.url) {
                decision = .cancel
            }
            recordNavigation(action, decision: decision)
            switch decision {
            case .allow: decisionHandler(.allow)
            case .verificationRequired:
                decisionHandler(.cancel); fail(PlayerFailure.verificationMessage)
            case .openExternal:
                if let url = action.request.url { openExternal(url) }
                decisionHandler(.cancel)
            case .cancel: decisionHandler(.cancel)
            }
        }
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            let decision = PlayerNavigationPolicy.decision(for: action.request.url, isMainFrame: true,
                isUserActivated: action.navigationType == .linkActivated, opensNewWindow: true)
            recordNavigation(action, decision: decision)
            if decision == .verificationRequired { fail(PlayerFailure.verificationMessage) }
            else if decision == .openExternal, let url = action.request.url { openExternal(url) }
            return nil
        }
        private func recordNavigation(_ action: WKNavigationAction, decision: PlayerNavigationDecision) {
            let url = action.request.url
            let path = signedIn && !isOfficialEmbed(url) ? "" : url?.path ?? ""
            record("navigation_decision", fields: ["host": url?.host ?? "", "path": path,
                "decision": String(describing: decision), "referrerPresent": action.request.value(forHTTPHeaderField: "Referer") == nil ? "false" : "true"])
        }
        private func openExternal(_ url: URL) {
            guard url.scheme == "https" else { return }
            #if os(macOS)
            NSWorkspace.shared.open(url)
            #else
            UIApplication.shared.open(url)
            #endif
        }
    }
}
