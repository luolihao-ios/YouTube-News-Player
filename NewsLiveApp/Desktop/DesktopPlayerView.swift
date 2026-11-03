import SwiftUI
import NewsCore

struct DesktopPlayerView: View {
    @EnvironmentObject private var store: NewsStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("playerConsent.v1") private var playerConsent = false
    @StateObject private var session = PlayerSession()
    @State private var playerError: String?
    @State private var playbackMessage = "點擊 YouTube 播放按鈕開始收看"
    @State private var reload = 0
    @State private var detailTab = 0
    let channel: ChannelSeed
    private var snapshot: ChannelSnapshot? { store.snapshots[channel.id] }
    private var video: LiveVideo? { snapshot?.videos.first }

    var body: some View {
        NavigationStack {
            GeometryReader { geometry in
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        playbackArea
                            .frame(minWidth: 200, maxWidth: .infinity)
                            .frame(height: max(220, min((geometry.size.width - 48) * 9 / 16, 460)))
                            .background(.black, in: RoundedRectangle(cornerRadius: 16))
                            .clipShape(RoundedRectangle(cornerRadius: 16))
                        channelInfo
                        if let error = playerError ?? store.errors[channel.id] {
                            VStack(alignment: .leading, spacing: 10) {
                                Label(error, systemImage: "exclamationmark.triangle").font(.subheadline).foregroundStyle(.secondary)
                                HStack {
                                    Button("重新載入") { retry() }.buttonStyle(.bordered)
                                    Link("在 YouTube 開啟", destination: video?.watchURL ?? channel.channelURL)
                                }
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.newsSurface, in: RoundedRectangle(cornerRadius: 13))
                        }
                        HStack(spacing: 14) {
                            Button { store.toggleFavorite(channel) } label: {
                                Label(store.isFavorite(channel) ? "已收藏" : "加入收藏", systemImage: store.isFavorite(channel) ? "heart.fill" : "heart")
                            }.tint(store.isFavorite(channel) ? Color.newsRed : Color.accentColor)
                            ShareLink(item: video?.watchURL ?? channel.channelURL) { Label("分享", systemImage: "square.and.arrow.up") }
                            Button { retry() } label: { Label("更新直播", systemImage: "arrow.clockwise") }
                                .disabled(store.loading.contains(channel.id))
                            Spacer()
                        }.buttonStyle(.bordered)
                        Picker("頻道詳情", selection: $detailTab) {
                            Text("直播資訊").tag(0)
                            Text("頻道簡介").tag(1)
                            Text("相關頻道").tag(2)
                        }.pickerStyle(.segmented)
                        details
                    }.padding(24)
                }
            }
            .background(Color.newsBackground)
            .navigationTitle(channel.name)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { session.pause(); dismiss() } label: { Label("關閉", systemImage: "xmark") }
                }
                ToolbarItem(placement: .primaryAction) {
                    Link(destination: video?.watchURL ?? channel.channelURL) { Label("在 YouTube 開啟", systemImage: "arrow.up.right.square") }
                }
            }
        }
        .frame(minWidth: 560, idealWidth: 980, minHeight: 620, idealHeight: 780)
        .task(id: channel.id) {
            session.pause(); playerError = nil
            await store.refresh(channel)
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { session.pause() } }
        .onChange(of: playerConsent) { _, consent in if !consent { session.pause() } }
        .onDisappear { session.pause() }
    }

    @ViewBuilder private var playbackArea: some View {
        if !playerConsent {
            VStack(spacing: 14) {
                Image(systemName: "play.rectangle").font(.system(size: 38, weight: .light))
                Text("使用 YouTube 官方播放器").font(.headline)
                Text("載入播放器會連線至 YouTube / Google，並依其政策處理裝置與播放資訊。")
                    .font(.subheadline).foregroundStyle(.white.opacity(0.72)).multilineTextAlignment(.center)
                HStack(spacing: 20) {
                    Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!)
                    Button("同意並載入") { playerConsent = true }.buttonStyle(.borderedProminent).tint(Color.newsRed)
                }.font(.subheadline)
            }.foregroundStyle(.white).padding(28).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let video {
            YouTubeWebView(videoID: video.id, session: session) { event in
                switch event {
                case .ready: playerError = nil; playbackMessage = "點擊 YouTube 播放按鈕開始收看"
                case .state(let state):
                    switch state {
                    case 1: playerError = nil; playbackMessage = "正在播放・YouTube"; store.didStartPlaying(channel)
                    case 2: playbackMessage = "已暫停"
                    case 0: playbackMessage = "直播已結束，可更新以查詢最新直播"
                    case 3: playbackMessage = "YouTube 正在緩衝…"
                    default: break
                    }
                case .failed(let message): playerError = message
                }
            }.id("\(channel.id)-\(video.id)-\(reload)")
        } else {
            VStack(spacing: 14) {
                if store.loading.contains(channel.id) {
                    ProgressView().tint(.white)
                    Text("正在尋找直播…")
                } else {
                    Image(systemName: "video.slash").font(.system(size: 34, weight: .light))
                    Text(AppConfiguration.isConfigured ? "目前沒有可嵌入的公開直播" : "YouTube 服務尚未設定").font(.headline)
                    Text("可前往頻道頁確認最新節目").font(.subheadline).foregroundStyle(.white.opacity(0.7))
                    Link("前往 YouTube 頻道", destination: channel.channelURL).buttonStyle(.bordered)
                }
            }.foregroundStyle(.white).padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var channelInfo: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .firstTextBaseline) {
                Text(snapshot?.channel.title ?? channel.name).font(.title.bold())
                Spacer()
                if video != nil {
                    Label(snapshot?.isFresh == true ? "YouTube 直播" : "上次直播資料", systemImage: "dot.radiowaves.left.and.right")
                        .font(.caption.bold()).foregroundStyle(Color.newsRed)
                }
            }
            Text(video?.title ?? channel.subtitle).font(.subheadline).foregroundStyle(.secondary)
            if let video {
                HStack(spacing: 14) {
                    if let viewers = video.viewerText { Label(viewers, systemImage: "person") }
                    Text("資料更新於 \(video.fetchedAt.formatted(date: .omitted, time: .shortened))")
                }.font(.caption).foregroundStyle(.secondary)
                Text(playbackMessage).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder private var details: some View {
        switch detailTab {
        case 0:
            VStack(alignment: .leading, spacing: 12) {
                Text(video?.title ?? "目前未提供直播資訊").font(.headline)
                Text(video.map { $0.description.isEmpty ? "頻道未提供直播說明。" : $0.description } ?? "頻道未提供直播說明。")
                    .font(.subheadline).foregroundStyle(.secondary).textSelection(.enabled)
                Text("畫質、字幕與全螢幕請使用 YouTube 官方播放器中的控制項。直播可能因地區或頻道設定而無法內嵌。")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        case 1:
            VStack(alignment: .leading, spacing: 14) {
                Text(channel.name).font(.headline)
                Text(channel.subtitle).foregroundStyle(.secondary)
                Text("本 App 提供獨立的頻道整理與個人收藏功能，並非 YouTube 或各新聞媒體的官方 App。影音與頻道標識屬於各權利人。")
                    .font(.footnote).foregroundStyle(.secondary)
                Link("在 YouTube 查看完整頻道", destination: channel.channelURL)
            }
        default:
            let related = store.channels.filter { $0.id != channel.id && $0.category == channel.category }
            VStack(spacing: 0) {
                ForEach(related.prefix(6)) { item in
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.name).font(.headline)
                            Text(item.subtitle).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Link("查看頻道", destination: item.channelURL)
                    }.padding(.vertical, 12)
                    Divider()
                }
                if related.isEmpty { Text("暫無相關頻道").foregroundStyle(.secondary).padding() }
            }
        }
    }
    private func retry() {
        session.pause(); playerError = nil; reload += 1
        Task { await store.refresh(channel, force: true) }
    }
}
