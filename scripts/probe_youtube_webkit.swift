import AppKit
import WebKit

/// 实际加载官方播放器并检查视频时间推进；不读取媒体地址、帐号或 Cookie。
@MainActor
final class PlaybackProbe: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var timer: Timer?
    private var finished = false
    private var previousTime: Double?
    private var advancingSamples = 0
    private let started = Date()
    private let mode: String
    private let videoID: String
    private let output: URL
    private var samples: [[String: Any]] = []
    private var youtubeErrors: [Int] = []

    init(mode: String, videoID: String, output: URL) {
        self.mode = mode; self.videoID = videoID; self.output = output
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.applicationNameForUserAgent = "YouTubeNewsLive/1.0"
        configuration.userContentController.add(self, name: "youtube")
        webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 960, height: 540), configuration: configuration)
        webView.navigationDelegate = self
        window = NSWindow(contentRect: webView.frame, styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "YouTubeNewsLive 播放验证"
        window.contentView = webView; window.center(); window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        let identity = "https://com.luolihao.newslive"
        if mode == "wrapper" {
            do {
                let path = CommandLine.arguments[4]
                let template = try String(contentsOfFile: path, encoding: .utf8)
                let json = try JSONSerialization.data(withJSONObject: ["videoID": videoID, "origin": identity])
                let html = template.replacingOccurrences(of: "__PLAYER_CONFIGURATION__", with: String(decoding: json, as: UTF8.self))
                    .replacingOccurrences(of: "autoplay:0", with: "autoplay:1")
                var request = URLRequest(url: URL(string: identity + "/player")!)
                request.setValue(identity, forHTTPHeaderField: "Referer")
                webView.loadSimulatedRequest(request, responseHTML: html)
            } catch { finish("probe_configuration_error"); return }
        } else {
            var url = URLComponents(string: "https://www.youtube.com/embed/" + videoID)!
            url.queryItems = ["autoplay":"1", "controls":"1", "playsinline":"1", "fs":"1", "origin":identity]
                .sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
            var request = URLRequest(url: url.url!)
            request.setValue(identity, forHTTPHeaderField: "Referer")
            webView.load(request)
        }
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.sample() }
        }
    }

    private func sample() {
        guard !finished else { return }
        if Date().timeIntervalSince(started) > 60 { finish("no_playback_timeout"); return }
        let script: String
        if mode == "wrapper" {
            script = "({playing:typeof player!=='undefined'&&player&&player.getPlayerState&&player.getPlayerState()===1,time:typeof player!=='undefined'&&player&&player.getCurrentTime?player.getCurrentTime():0,challenge:false})"
        } else {
            guard let observation = try? String(contentsOfFile: "scripts/fixtures/PlaybackObservation.js", encoding: .utf8) else {
                finish("probe_configuration_error"); return
            }
            script = observation
        }
        webView.requestMediaPlaybackState { [weak self] state in
            guard let self, !self.finished else { return }
            self.webView.evaluateJavaScript(script) { [weak self] value, _ in
                guard let self, !self.finished else { return }
                let sample = value as? [String: Any] ?? [:]
                let playing = sample["playing"] as? Bool ?? false
                let current = sample["time"] as? Double ?? 0
                self.samples.append(["seconds": Int(Date().timeIntervalSince(self.started)), "webkitState": state.rawValue,
                                     "playing": playing, "mediaTime": current])
                if sample["verificationRequired"] as? Bool == true { self.finish("youtube_verification_required"); return }
                if playing, let previous = self.previousTime, current > previous + 0.5 { self.advancingSamples += 1 }
                else { self.advancingSamples = 0 }
                self.previousTime = current
                if self.advancingSamples >= 2 { self.finish("media_playing"); return }
            }
        }
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let value = message.body as? [String: Any], value["type"] as? String == "error" else { return }
        if let code = value["code"] as? Int { youtubeErrors.append(code) }
        finish("youtube_embed_error")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { finish("navigation_failed") }
    }

    private func finish(_ result: String) {
        guard !finished else { return }
        finished = true; timer?.invalidate()
        try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let report: [String: Any] = ["mode": mode, "videoID": videoID, "result": result, "samples": samples, "youtubeErrors": youtubeErrors,
            "scope": "真实 macOS WebKit 与 runner 网络；不能代替用户 iPhone 网络验证"]
        let name = mode + "-" + videoID
        if let data = try? JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: output.appendingPathComponent(name + ".json"))
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 8) { NSApplication.shared.terminate(nil) }
        webView.takeSnapshot(with: nil) { [weak self] image, _ in
            guard let self else { return }
            if let tiff = image?.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
               let png = bitmap.representation(using: .png, properties: [:]) {
                try? png.write(to: self.output.appendingPathComponent(name + ".png"))
            }
            self.webView.pauseAllMediaPlayback(completionHandler: nil)
            NSApplication.shared.terminate(nil)
        }
    }
}

@main
enum Main {
    @MainActor static func main() {
        guard CommandLine.arguments.count >= 4,
              ["wrapper", "direct"].contains(CommandLine.arguments[1]),
              CommandLine.arguments[1] != "wrapper" || CommandLine.arguments.count >= 5,
              CommandLine.arguments[2].range(of: "^[A-Za-z0-9_-]{11}$", options: .regularExpression) != nil else { exit(2) }
        let delegate = PlaybackProbe(mode: CommandLine.arguments[1], videoID: CommandLine.arguments[2],
                                     output: URL(fileURLWithPath: CommandLine.arguments[3], isDirectory: true))
        let application = NSApplication.shared
        application.setActivationPolicy(.regular); application.delegate = delegate
        application.run()
        withExtendedLifetime(delegate) {}
    }
}
