import SwiftUI
import NewsCore

struct PlayerView: View {
    @EnvironmentObject private var store: NewsStore
    @Environment(\.scenePhase) private var scenePhase
    let channel: ChannelSeed
    @StateObject private var session = PlayerSession()
    @AppStorage("playerConsent.v1") private var playerConsent = false
    @State private var detailTab = 0
    @State private var isPlaying = false
    @State private var playerError: String?
    @State private var reload = 0
    @State private var selectedVideoID: String?
    @State private var recovery = InAppPlaybackRecovery()
    @State private var showWebPlayback = false
    private var snapshot: ChannelSnapshot? { store.snapshots[channel.id] }
    private var video: LiveVideo? {
        snapshot?.videos.first(where: { $0.id == selectedVideoID }) ?? snapshot?.videos.first
    }

    var body: some View {
        NavigationStack {
            GeometryReader { geometry in
                VStack(spacing: 0) {
                    playbackArea
                        .frame(height: max(220, min(geometry.size.width * 9 / 16, geometry.size.height * 0.48)))
                        .background(.black)
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            if playerError != nil || store.errors[channel.id] != nil {
                                HStack {
                                    Text("暫時無法播放").font(.subheadline).foregroundStyle(.secondary)
                                    Spacer()
                                    Button("重試") { retry() }.buttonStyle(.bordered)
                                }.padding(14).frame(maxWidth: .infinity, alignment: .leading).background(Color.newsBackground, in: RoundedRectangle(cornerRadius: 12))
                            }
                            channelInfo
                            actionBar
                            liveVideoMenu
                            Picker("頻道詳情", selection: $detailTab) {
                                Text("相關頻道").tag(0)
                                Text("直播資訊").tag(1)
                                Text("頻道簡介").tag(2)
                            }.pickerStyle(.segmented)
                            detailContent
                        }.padding(20)
                    }
                }
            }
            .navigationTitle(channel.name).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button { closePlayer() } label: { Label("返回", systemImage: "chevron.left") }.accessibilityLabel("返回頻道列表") }
            }
            .task(id: channel.id) {
                session.pause(); playerError = nil; isPlaying = false
                await store.refresh(channel)
            }
            .onChange(of: scenePhase) { _, phase in if phase != .active { session.pause() } }
            .onChange(of: store.activeChannel?.id) { _, id in if id != channel.id { session.pause() } }
            .onChange(of: playerConsent) { _, consent in if !consent { session.pause() } }
            .onDisappear { session.pause() }
            .fullScreenCover(isPresented: $showWebPlayback, onDismiss: {
                recovery.dismiss()
                PlaybackDiagnostics.shared.record("web_playback_dismissed")
            }) {
                if let identity = recovery.activeVideoID,
                   let url = URL(string: "https://www.youtube.com/watch?v=\(identity)") {
                    InAppYouTubeBrowser(url: url) { showWebPlayback = false }
                        .ignoresSafeArea()
                }
            }
        }
    }

    @ViewBuilder private var playbackArea: some View {
        if !playerConsent {
            VStack(spacing: 12) {
                Image(systemName: "play.rectangle").font(.system(size: 31, weight: .light))
                Text("使用 YouTube 官方播放器").font(.headline)
                Text("載入會連線至 YouTube / Google，並在本 App 保存網站資料，可於設定清除。")
                    .font(.system(size: 12)).multilineTextAlignment(.center).foregroundStyle(.white.opacity(0.7))
                HStack(spacing: 18) {
                    Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!).font(.system(size: 12))
                    Button("同意並載入") { playerConsent = true }.font(.system(size: 13, weight: .semibold)).buttonStyle(.borderedProminent)
                }
            }.foregroundStyle(.white).padding(20).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let video {
            if recovery.usesWebpage(for: video.id) {
                Button { openWebPlayback(videoID: video.id, automatically: false) } label: {
                    Label("在 App 內繼續觀看", systemImage: "play.circle.fill")
                        .font(.headline).foregroundStyle(.white)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }.buttonStyle(.plain)
            } else {
            YouTubeWebView(videoID: video.id, session: session) { event in
                switch event {
                case .ready: isPlaying = false; playerError = nil
                case .state(let value):
                    isPlaying = value == 1
                    if isPlaying {
                        playerError = nil
                        store.didStartPlaying(channel)
                    }
                case .failed(let message): playerError = message; isPlaying = false
                case .webPlaybackRequired: openWebPlayback(videoID: video.id, automatically: true)
                }
            }.id("\(channel.id)-\(video.id)-\(reload)")
            }
        } else {
            VStack(spacing: 12) {
                if store.loading.contains(channel.id) { ProgressView().tint(.white); Text("正在尋找直播…") }
                else {
                    Image(systemName: "video.slash").font(.system(size: 30, weight: .light))
                    Text("暫時沒有直播").font(.headline)
                    Button("更新直播") { retry() }.buttonStyle(.bordered)
                }
            }.foregroundStyle(.white).padding(20).frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func openWebPlayback(videoID: String, automatically: Bool) {
        guard store.activeChannel?.id == channel.id, video?.id == videoID,
              recovery.present(videoID: videoID, automatically: automatically) else { return }
        selectedVideoID = videoID
        session.pause()
        isPlaying = false
        playerError = nil
        PlaybackDiagnostics.shared.record("web_playback_presented", fields: ["videoID": videoID])
        showWebPlayback = true
    }

    private var channelInfo: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top) {
                Text(snapshot?.channel.title ?? channel.name).font(.system(size: 25, weight: .bold))
                Spacer()
                if video != nil { LiveBadge(cached: snapshot?.isFresh != true) }
            }
            Text(video?.title ?? channel.subtitle).font(.system(size: 14)).foregroundStyle(.secondary)
            if let video {
                if let viewers = video.viewerText {
                    Label(viewers, systemImage: "person.fill").font(.system(size: 12)).foregroundStyle(.secondary)
                }
                Text("YouTube 資料更新於 \(video.fetchedAt.formatted(date: .omitted, time: .shortened))")
                    .font(.system(size: 11)).foregroundStyle(.tertiary)
                if isPlaying { Text("正在播放").font(.system(size: 12)).foregroundStyle(.secondary) }
            }
        }
    }

    private var actionBar: some View {
        HStack(spacing: 10) {
            Button { store.toggleFavorite(channel) } label: {
                actionLabel(store.isFavorite(channel) ? "已收藏" : "收藏", symbol: store.isFavorite(channel) ? "heart.fill" : "heart")
            }.foregroundStyle(store.isFavorite(channel) ? Color.newsRed : .primary)
            ShareLink(item: video?.watchURL ?? channel.channelURL) { actionLabel("分享", symbol: "square.and.arrow.up") }.foregroundStyle(.primary)
            Button { retry() } label: { actionLabel("更新直播", symbol: "arrow.clockwise") }.foregroundStyle(.primary).disabled(store.loading.contains(channel.id))
        }.buttonStyle(.plain)
    }
    private func actionLabel(_ title: String, symbol: String) -> some View {
        VStack(spacing: 7) { Image(systemName: symbol).font(.system(size: 20)); Text(title).font(.system(size: 12)) }
            .frame(maxWidth: .infinity).padding(.vertical, 13).background(Color.newsBackground, in: RoundedRectangle(cornerRadius: 13))
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

    @ViewBuilder private var detailContent: some View {
        switch detailTab {
        case 0:
            VStack(spacing: 0) {
                ForEach(Array(store.channels.filter { $0.id != channel.id && $0.category == channel.category }.prefix(5))) { related in
                    ChannelRow(channel: related)
                    Divider().opacity(0.4)
                }
                if store.channels.filter({ $0.id != channel.id && $0.category == channel.category }).isEmpty { Text("暫無相關頻道").foregroundStyle(.secondary).padding() }
            }
        case 1:
            VStack(alignment: .leading, spacing: 12) {
                Text(video?.title ?? "目前未提供直播資訊").font(.headline)
                if let video { Text(video.description.isEmpty ? "頻道未提供直播說明。" : video.description).font(.subheadline).foregroundStyle(.secondary).textSelection(.enabled) }
                Text("畫質、字幕與全螢幕可在播放器中設定。")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        default:
            VStack(alignment: .leading, spacing: 14) {
                HStack { ChannelLogo(channel: channel, url: snapshot?.channel.thumbnailURL); VStack(alignment: .leading, spacing: 5) { Text(snapshot?.channel.title ?? channel.name).font(.headline); Text("YouTube 頻道").font(.subheadline).foregroundStyle(.secondary) } }
                Text(channel.subtitle).font(.subheadline).foregroundStyle(.secondary)
                Text("本 App 提供獨立的頻道整理與個人收藏功能，並非 YouTube 或各新聞媒體的官方 App。影音與頻道標識屬於各權利人。")
                    .font(.footnote).foregroundStyle(.secondary)
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
