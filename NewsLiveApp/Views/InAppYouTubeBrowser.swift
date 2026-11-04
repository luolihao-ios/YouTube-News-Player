import SwiftUI
import SafariServices

/// 登录和观看始终留在系统管理的同一网页中，不读取或转移账户、Cookie。
struct InAppYouTubeBrowser: UIViewControllerRepresentable {
    let url: URL
    let onClose: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onClose: onClose) }

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let configuration = SFSafariViewController.Configuration()
        configuration.entersReaderIfAvailable = false
        let controller = SFSafariViewController(url: url, configuration: configuration)
        controller.dismissButtonStyle = .close
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}

    @MainActor
    final class Coordinator: NSObject, SFSafariViewControllerDelegate {
        private let onClose: () -> Void
        init(onClose: @escaping () -> Void) { self.onClose = onClose }
        func safariViewControllerDidFinish(_ controller: SFSafariViewController) { onClose() }
        func safariViewController(_ controller: SFSafariViewController, didCompleteInitialLoad didLoadSuccessfully: Bool) {
            // 页面加载不代表已登录或已播放；系统不向 App 暴露这些状态。
            PlaybackDiagnostics.shared.record("web_page_initial_load", fields: ["state": didLoadSuccessfully ? "loaded" : "failed"])
        }
    }
}
