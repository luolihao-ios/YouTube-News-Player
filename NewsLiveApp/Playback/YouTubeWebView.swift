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
    private static weak var playingSession: PlayerSession?
    func pause() { webView?.evaluateJavaScript("window.NewsPlayer && window.NewsPlayer.pause()", completionHandler: nil) }
    func claimPlayback() {
        if Self.playingSession !== self { Self.playingSession?.pause() }
        Self.playingSession = self
    }
}

struct YouTubeWebView: NativePlayerRepresentable {
    let videoID: String
    let session: PlayerSession
    let onEvent: (PlayerEvent) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(session: session, onEvent: onEvent) }
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
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(context.coordinator, name: "youtube")
        let webView = WKWebView(frame: .zero, configuration: configuration)
        #if !os(macOS)
        webView.isOpaque = false
        webView.backgroundColor = .black
        webView.scrollView.isScrollEnabled = false
        #endif
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        session.webView = webView
        do {
            let config = try PlayerConfiguration(videoID: videoID, bundleID: AppConfiguration.bundleID)
            guard let url = Bundle.main.url(forResource: "YouTubePlayer", withExtension: "html") else { throw YouTubeError.invalidPlayerConfiguration }
            let template = try String(contentsOf: url, encoding: .utf8)
            let html = template.replacingOccurrences(of: "__PLAYER_CONFIGURATION__", with: config.json)
            // 官方要求：HTTPS baseURL 的 host 為實際 Bundle ID，用於 Referer / API Client identity。
            webView.loadHTMLString(html, baseURL: config.origin)
            context.coordinator.startTimeout()
        } catch {
            DispatchQueue.main.async { onEvent(.failed(error.localizedDescription)) }
        }
        return webView
    }
    private static func dismantle(_ uiView: WKWebView, coordinator: Coordinator) {
        coordinator.timeout?.cancel()
        uiView.evaluateJavaScript("window.NewsPlayer && window.NewsPlayer.destroy()", completionHandler: nil)
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "youtube")
        uiView.stopLoading(); uiView.navigationDelegate = nil; uiView.uiDelegate = nil
    }

    @MainActor
    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate {
        let onEvent: (PlayerEvent) -> Void
        weak var session: PlayerSession?
        var timeout: Task<Void, Never>?
        init(session: PlayerSession, onEvent: @escaping (PlayerEvent) -> Void) { self.session = session; self.onEvent = onEvent }
        func startTimeout() {
            timeout = Task { [weak self] in
                do { try await Task.sleep(for: .seconds(25)) } catch { return }
                self?.onEvent(.failed("播放器連線逾時，請檢查網路後重試。"))
            }
        }
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "youtube", message.frameInfo.isMainFrame,
                  let body = message.body as? [String: Any], let type = body["type"] as? String else { return }
            switch type {
            case "ready": timeout?.cancel(); onEvent(.ready)
            case "state":
                if let state = body["state"] as? Int {
                    if state == 1 { session?.claimPlayback() }
                    onEvent(.state(state))
                }
            case "error":
                timeout?.cancel()
                let code = body["code"] as? Int ?? -1
                let text: String
                switch code {
                case 100: text = "這場直播已移除或設為私人，請重新查詢頻道。"
                case 101, 150: text = "頻道不允許內嵌播放，請前往 YouTube 收看。"
                case 153: text = "YouTube 無法識別此 App（153），請聯絡開發者檢查播放器設定。"
                default: text = "YouTube 暫時無法播放（\(code)），可重試或前往 YouTube。"
                }
                onEvent(.failed(text))
            default: break
            }
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            timeout?.cancel(); onEvent(.failed("播放器載入失敗，請檢查網路後重試。"))
        }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            timeout?.cancel(); onEvent(.failed("播放器已中斷，請點擊重新載入。"))
        }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if action.navigationType == .linkActivated, let url = action.request.url {
                openExternal(url)
                decisionHandler(.cancel); return
            }
            let scheme = action.request.url?.scheme
            decisionHandler(scheme == "https" || scheme == "about" ? .allow : .cancel)
        }
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url { openExternal(url) }
            return nil
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
