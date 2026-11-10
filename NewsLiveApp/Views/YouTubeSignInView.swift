import NewsCore
import SwiftUI
import WebKit

struct YouTubeSignInView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var host = "www.youtube.com"
    @State private var loadFailed = false
    @State private var attempt = 0
    let onSignedIn: () -> Void

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                VStack(spacing: 4) {
                    Text(host).font(.footnote)
                    Text("登入狀態儲存在本機，可於設定清除。").font(.caption)
                }.foregroundStyle(.secondary).padding(.vertical, 6)
                if loadFailed {
                    Button("重新載入登入頁面") {
                        loadFailed = false
                        attempt += 1
                    }.padding(8)
                }
                SignInWebView(onHost: { host = $0 }, onFailure: { loadFailed = true }) {
                    onSignedIn()
                    dismiss()
                }.id(attempt)
            }
            .navigationTitle("Google 登入").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("返回") { dismiss() } }
            }
        }
        .onAppear { PlaybackDiagnostics.shared.record("youtube_sign_in_opened") }
    }
}

private struct SignInWebView: UIViewRepresentable {
    let onHost: (String) -> Void
    let onFailure: () -> Void
    let onSignedIn: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(view: self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = PlayerWebData.store
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        context.coordinator.webView = webView
        configuration.websiteDataStore.httpCookieStore.add(context.coordinator)
        webView.load(URLRequest(url: YouTubeSignInPolicy.entryURL))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        coordinator.webView = nil
        coordinator.check?.cancel()
        webView.configuration.websiteDataStore.httpCookieStore.remove(coordinator)
        webView.navigationDelegate = nil
        webView.uiDelegate = nil
        webView.stopLoading()
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKHTTPCookieStoreObserver {
        let view: SignInWebView
        weak var webView: WKWebView?
        var check: Task<Void, Never>?
        private var reported = false

        init(view: SignInWebView) { self.view = view }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            if let host = webView.url?.host {
                view.onHost(host)
                PlaybackDiagnostics.shared.record("youtube_sign_in_page", fields: ["host": host])
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            checkSession()
        }

        nonisolated func cookiesDidChange(in cookieStore: WKHTTPCookieStore) {
            Task { @MainActor [weak self] in self?.checkSession() }
        }

        private func checkSession() {
            guard !reported, YouTubeSignInPolicy.isYouTubeReturn(webView?.url) else { return }
            check?.cancel()
            check = Task { [weak self] in
                let present = await PlayerWebData.hasYouTubeSession()
                guard let self, !Task.isCancelled, !self.reported,
                      YouTubeSignInPolicy.isYouTubeReturn(self.webView?.url) else { return }
                PlaybackDiagnostics.shared.record("youtube_sign_in_return", fields: ["sessionPresent": String(present)])
                if present {
                    self.reported = true
                    self.view.onSignedIn()
                }
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            let mainFrame = action.targetFrame?.isMainFrame ?? true
            let allowed = YouTubeSignInPolicy.allows(action.request.url, isMainFrame: mainFrame)
            decisionHandler(allowed ? .allow : .cancel)
            if !allowed && mainFrame {
                PlaybackDiagnostics.shared.record("youtube_sign_in_navigation_blocked")
            }
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if action.targetFrame == nil, YouTubeSignInPolicy.allows(action.request.url, isMainFrame: true) {
                webView.load(action.request)
            }
            return nil
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            reportFailure(error)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            reportFailure(error)
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            PlaybackDiagnostics.shared.record("youtube_sign_in_content_terminated")
            view.onFailure()
        }

        private func reportFailure(_ error: Error) {
            let failure = error as NSError
            guard failure.domain != NSURLErrorDomain || failure.code != NSURLErrorCancelled else { return }
            PlaybackDiagnostics.shared.record("youtube_sign_in_load_failed", fields: ["errorCode": String(failure.code)])
            view.onFailure()
        }
    }
}
