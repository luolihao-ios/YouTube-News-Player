import SwiftUI
import SafariServices

/// 系统管理的备用网页入口；不读取网页内容、Cookie 或登录状态。
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

    final class Coordinator: NSObject, SFSafariViewControllerDelegate {
        private let onClose: () -> Void

        init(onClose: @escaping () -> Void) { self.onClose = onClose }

        func safariViewControllerDidFinish(_ controller: SFSafariViewController) {
            onClose()
        }
    }
}
