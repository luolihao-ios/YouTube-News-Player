import SwiftUI
import NewsCore

struct DesktopPlayerView: View {
    @EnvironmentObject private var store: NewsStore
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("playerConsent.v1") private var playerConsent = false
    @StateObject private var session = PlayerSession()
    @State private var playerError: String?
    @State private var isPlaying = false
    @State private var reload = 0
    @State private var detailTab = 0
    @State private var selectedVideoID: String?
    let channel: ChannelSeed
    private var snapshot: ChannelSnapshot? { store.snapshots[channel.id] }
    private var video: LiveVideo? {
        snapshot?.videos.first(where: { $0.id == selectedVideoID }) ?? snapshot?.videos.first
    }

    var body: some View {
        NavigationStack {
            GeometryReader { geometry in
                VStack(spacing: 0) {
                    // 播放器固定可见；详情滚动不会将正在播放的画面移出窗口。
                    playbackArea
                        .frame(minWidth: 200, maxWidth: .infinity)
                        .frame(height: max(200, min(geometry.size.width * 9 / 16, min(geometry.size.height * 0.55, 460))))
                        .background(.black)
                        .layoutPriority(1)
                    ScrollView {
                        VStack(alignment: .leading, spacing: 22) {
                            channelInfo
                            if playerError != nil || store.errors[channel.id] != nil {
                                HStack {
                                    Text("暫時無法播放").font(.subheadline).foregroundStyle(.secondary)
                                    Spacer()
                                    Button("重試") { retry() }.buttonStyle(.bordered)
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
                            liveVideoMenu
                            Picker("頻道詳情", selection: $detailTab) {
                                Text("直播資訊").tag(0)
                                Text("頻道簡介").tag(1)
                                Text("相關頻道").tag(2)
                            }.pickerStyle(.segmented)
                            details
                        }.padding(24)
                    }
                }
            }
            .background(Color.newsBackground)
            .navigationTitle(channel.name)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { closePlayer() } label: { Label("返回", systemImage: "chevron.left") }
                }
            }
        }
        .task(id: channel.id) {
            session.pause(); playerError = nil; isPlaying = false
            await store.refresh(channel)
        }
        .onChange(of: scenePhase) { _, phase in if phase != .active { session.pause() } }
        .onChange(of: store.activeChannel?.id) { _, id in if id != channel.id { session.pause() } }
        .onChange(of: playerConsent) { _, consent in if !consent { session.pause() } }
        .onDisappear { session.pause() }
    }

    @ViewBuilder private var playbackArea: some View {
        if !playerConsent {
            VStack(spacing: 14) {
                Image(systemName: "play.rectangle").font(.system(size: 38, weight: .light))
                Text("使用 YouTube 官方播放器").font(.headline)
                Text("載入會連線至 YouTube / Google，並在本 App 保存網站資料，可於設定清除。")
                    .font(.subheadline).foregroundStyle(.white.opacity(0.72)).multilineTextAlignment(.center)
                HStack(spacing: 20) {
                    Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!)
                    Button("同意並載入") { playerConsent = true }.buttonStyle(.borderedProminent).tint(Color.newsRed)
                }.font(.subheadline)
            }.foregroundStyle(.white).padding(28).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let video {
            YouTubeWebView(videoID: video.id, session: session) { event in
                switch event {
                case .ready: playerError = nil; isPlaying = false
                case .state(let state):
                    isPlaying = state == 1
                    if isPlaying {
                        playerError = nil
                        store.didStartPlaying(channel)
                    }
                case .failed(let message): playerError = message; isPlaying = false
                }
            }.id("\(channel.id)-\(video.id)-\(reload)")
        } else {
            VStack(spacing: 14) {
                if store.loading.contains(channel.id) {
                    ProgressView().tint(.white)
                    Text("正在尋找直播…")
                } else {
                    Image(systemName: "video.slash").font(.system(size: 34, weight: .light))
                    Text("暫時沒有直播").font(.headline)
                    Button("更新直播") { retry() }.buttonStyle(.bordered)
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
                if isPlaying { Text("正在播放").font(.caption).foregroundStyle(.secondary) }
            }
        }
    }

    @ViewBuilder private var liveVideoMenu: some View {
        if let videos = snapshot?.videos, videos.count > 1 {
            Menu {
                ForEach(videos) { next in
                    Button {
                        session.pause()
                        selectedVideoID = next.id
                        playerError = nil
                        isPlaying = false
                    } label: {
                        if video?.id == next.id { Label(next.title, systemImage: "checkmark") }
                        else { Text(next.title) }
                    }
                }
            } label: {
                Label("切換本頻道直播", systemImage: "list.bullet.rectangle")
            }.buttonStyle(.bordered)
        }
    }

    @ViewBuilder private var details: some View {
        switch detailTab {
        case 0:
            VStack(alignment: .leading, spacing: 12) {
                Text(video?.title ?? "目前未提供直播資訊").font(.headline)
                Text(video.map { $0.description.isEmpty ? "頻道未提供直播說明。" : $0.description } ?? "頻道未提供直播說明。")
                    .font(.subheadline).foregroundStyle(.secondary).textSelection(.enabled)
                Text("畫質、字幕與全螢幕可在播放器中設定。")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        case 1:
            VStack(alignment: .leading, spacing: 14) {
                Text(channel.name).font(.headline)
                Text(channel.subtitle).foregroundStyle(.secondary)
                Text("本 App 提供獨立的頻道整理與個人收藏功能，並非 YouTube 或各新聞媒體的官方 App。影音與頻道標識屬於各權利人。")
                    .font(.footnote).foregroundStyle(.secondary)
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
                        Button("收看頻道") { session.pause(); store.open(item) }.buttonStyle(.bordered)
                    }.padding(.vertical, 12)
                    Divider()
                }
                if related.isEmpty { Text("暫無相關頻道").foregroundStyle(.secondary).padding() }
            }
        }
    }
    private func retry() {
        session.pause(); playerError = nil; isPlaying = false; reload += 1
        Task { await store.refresh(channel, force: true) }
    }
    private func closePlayer() {
        session.pause()
        store.activeChannel = nil
    }
}
