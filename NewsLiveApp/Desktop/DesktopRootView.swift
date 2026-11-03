import SwiftUI
import NewsCore

/// macOS 与 visionOS 共享原生窗口布局，播放器始终由根视图的唯一 sheet 承载。
struct DesktopRootView: View {
    @EnvironmentObject private var store: NewsStore
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("historyEnabled") private var historyEnabled = false

    private var selection: Binding<AppTab?> {
        Binding(get: { store.selectedTab }, set: {
            if let value = $0 {
                store.search = ""; store.selectedCategory = nil; store.selectedTab = value
            }
        })
    }

    var body: some View {
        NavigationSplitView {
            List(selection: selection) {
                Section {
                    Label("首頁", systemImage: "house").tag(AppTab.home)
                    Label("所有頻道", systemImage: "square.grid.2x2").tag(AppTab.channels)
                    Label("我的收藏", systemImage: "heart").tag(AppTab.favorites)
                }
                Section("探索分類") {
                    ForEach(ChannelCategory.allCases) { category in
                        Button { store.browse(category) } label: {
                            Label(category.rawValue, systemImage: category.symbol)
                        }.buttonStyle(.plain)
                    }
                }
                Section {
                    Label("設定", systemImage: "gearshape").tag(AppTab.settings)
                }
            }
            .listStyle(.sidebar)
            .navigationTitle("YouTubeNewsLive")
            .navigationSplitViewColumnWidth(min: 200, ideal: 230, max: 280)
            .safeAreaInset(edge: .bottom) {
                Label("透過 YouTube 官方播放器收看", systemImage: "play.rectangle")
                    .font(.caption2).foregroundStyle(.secondary).padding(16)
            }
        } detail: {
            if store.selectedTab == .settings {
                DesktopSettingsView()
            } else {
                libraryContent
            }
        }
        .tint(Color.newsRed)
        .sheet(item: $store.activeChannel) { channel in
            DesktopPlayerView(channel: channel).environmentObject(store)
        }
        .task { await store.bootstrap() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { store.expireCache() } }
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { _ in
            if scenePhase == .active { store.expireCache() }
        }
    }

    private var title: String {
        switch store.selectedTab {
        case .home: return "全球時事，一眼掌握"
        case .channels: return "所有頻道"
        case .favorites: return "我的收藏"
        case .settings: return "設定"
        }
    }
    private var visible: [ChannelSeed] {
        ChannelFilter.apply(store.selectedTab == .favorites ? store.favoriteChannels : store.channels,
                            query: store.search, category: store.selectedCategory)
    }
    private var isHome: Bool { store.selectedTab == .home && store.search.isEmpty && store.selectedCategory == nil }

    private var libraryContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(title).font(.largeTitle.bold())
                    Text(store.selectedTab == .favorites ? "把在意的視角，留在身邊。" : "從熟悉的頻道出發，看見世界的每個角度。")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                categoryPicker
                if let error = store.catalogError { notice(error, symbol: "exclamationmark.triangle") }
                if !AppConfiguration.isConfigured {
                    notice("YouTube 服務尚未設定。目前可瀏覽頻道、管理收藏，或前往 YouTube 收看。", symbol: "info.circle")
                }
                if isHome, let featured = store.liveChannels.first ?? store.channels.first {
                    featuredCard(featured)
                }
                if visible.isEmpty {
                    ContentUnavailableView(store.selectedTab == .favorites && store.search.isEmpty ? "尚未收藏頻道" : "沒有符合的頻道",
                                           systemImage: store.selectedTab == .favorites ? "heart" : "magnifyingglass",
                                           description: Text("調整搜尋或分類，或在頻道卡片上點擊愛心加入收藏。"))
                        .frame(minHeight: 260)
                } else {
                    grid(visible, title: isHome ? "精選新聞頻道" : "\(visible.count) 個頻道")
                }
                if isHome && historyEnabled && !store.recentChannels.isEmpty {
                    grid(Array(store.recentChannels.prefix(6)), title: "最近觀看")
                }
                Text("獨立新聞頻道整理工具・影音、廣告與播放控制由 YouTube 提供")
                    .font(.caption).foregroundStyle(.tertiary).frame(maxWidth: .infinity).padding(.vertical, 8)
            }.padding(28).frame(maxWidth: 1300, alignment: .leading).frame(maxWidth: .infinity)
        }
        .background(Color.newsBackground)
        .navigationTitle(store.selectedTab == .home ? "首頁" : title)
        .searchable(text: $store.search, prompt: "搜尋頻道、地區或主題")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await store.refresh(Array(visible.prefix(3)), force: true) } } label: {
                    Label("更新直播", systemImage: "arrow.clockwise")
                }.disabled(!store.loading.isEmpty || !AppConfiguration.isConfigured)
            }
        }
    }

    private var categoryPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                categoryButton("全部", category: nil)
                ForEach(ChannelCategory.allCases) { category in categoryButton(category.rawValue, category: category) }
            }.padding(.vertical, 2)
        }
    }
    private func categoryButton(_ title: String, category: ChannelCategory?) -> some View {
        Button { store.selectedCategory = category } label: {
            Text(title).font(.subheadline.weight(.medium)).padding(.horizontal, 15).padding(.vertical, 9)
                .foregroundStyle(store.selectedCategory == category ? Color.white : Color.primary)
                .background(store.selectedCategory == category ? Color.newsRed : Color.newsSurface, in: Capsule())
        }.buttonStyle(.plain).accessibilityAddTraits(store.selectedCategory == category ? .isSelected : [])
    }
    private func grid(_ channels: [ChannelSeed], title: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.title2.bold())
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230, maximum: 380), spacing: 18)], spacing: 18) {
                ForEach(channels) { channel in
                    DesktopChannelCard(channel: channel)
                        .contextMenu {
                            Button(store.isFavorite(channel) ? "取消收藏" : "加入收藏", systemImage: store.isFavorite(channel) ? "heart.slash" : "heart") { store.toggleFavorite(channel) }
                            if store.selectedTab == .favorites,
                               let index = store.favoriteChannels.firstIndex(where: { $0.id == channel.id }) {
                                Button("移到最前", systemImage: "arrow.up.to.line") {
                                    store.moveFavorites(from: IndexSet(integer: index), to: 0)
                                }.disabled(index == 0)
                            }
                            ShareLink(item: channel.channelURL)
                            Link("在 YouTube 開啟", destination: channel.channelURL)
                        }
                }
            }
        }
    }
    private func notice(_ text: String, symbol: String) -> some View {
        Label(text, systemImage: symbol).font(.subheadline).foregroundStyle(.secondary)
            .padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.newsSurface, in: RoundedRectangle(cornerRadius: 14))
    }
    private func featuredCard(_ channel: ChannelSeed) -> some View {
        Button { store.open(channel) } label: {
            HStack(spacing: 24) {
                VStack(alignment: .leading, spacing: 12) {
                    Label(store.liveChannels.contains(channel) ? "正在直播・YouTube" : "今日精選", systemImage: "dot.radiowaves.left.and.right")
                        .font(.caption.weight(.semibold))
                    Text(channel.name).font(.system(.largeTitle, design: .rounded, weight: .bold))
                    Text(store.snapshots[channel.id]?.videos.first?.title ?? channel.subtitle)
                        .font(.subheadline).lineLimit(2).foregroundStyle(.white.opacity(0.8))
                    Label("查看直播", systemImage: "play.fill").font(.subheadline.bold()).padding(.top, 6)
                }
                Spacer(minLength: 0)
                Image(systemName: "globe.asia.australia.fill").font(.system(size: 110, weight: .ultraLight))
                    .foregroundStyle(.white.opacity(0.18)).accessibilityHidden(true)
            }.foregroundStyle(.white).padding(30).frame(maxWidth: .infinity, minHeight: 220, alignment: .leading)
                .background(LinearGradient(colors: [Color(newsHex: channel.color), Color(newsHex: "15283E")], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 22))
        }.buttonStyle(.plain)
    }
}

private struct DesktopChannelCard: View {
    @EnvironmentObject private var store: NewsStore
    let channel: ChannelSeed
    private var snapshot: ChannelSnapshot? { store.snapshots[channel.id] }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { store.open(channel) } label: {
                VStack(alignment: .leading, spacing: 14) {
                    ZStack(alignment: .bottomLeading) {
                        LinearGradient(colors: [Color(newsHex: channel.color), Color(newsHex: "192639")], startPoint: .topLeading, endPoint: .bottomTrailing)
                        if let url = snapshot?.videos.first?.thumbnailURL {
                            AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { Color.clear }
                        } else {
                            Image(systemName: channel.category.symbol).font(.system(size: 65, weight: .ultraLight))
                                .foregroundStyle(.white.opacity(0.22)).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing).padding(20)
                        }
                        LinearGradient(colors: [.clear, .black.opacity(0.6)], startPoint: .center, endPoint: .bottom)
                        HStack {
                            Text(channel.monogram).font(.headline.bold())
                            Spacer()
                            Image(systemName: "play.circle.fill").font(.title)
                        }.foregroundStyle(.white).padding(16)
                    }.frame(height: 142).clipped()
                    VStack(alignment: .leading, spacing: 6) {
                        Text(channel.name).font(.headline).foregroundStyle(.primary)
                        Text(channel.subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(2).frame(height: 32, alignment: .top)
                    }.padding(.horizontal, 16)
                }.contentShape(Rectangle())
            }.buttonStyle(.plain)
            HStack(spacing: 8) {
                if store.loading.contains(channel.id) { ProgressView().controlSize(.small) }
                Circle().fill(snapshot?.isFresh == true && snapshot?.videos.isEmpty == false ? Color.newsRed : Color.secondary.opacity(0.4)).frame(width: 6, height: 6)
                Text(store.statusText(channel)).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                Spacer(minLength: 0)
                Button { store.toggleFavorite(channel) } label: {
                    Image(systemName: store.isFavorite(channel) ? "heart.fill" : "heart")
                        .foregroundStyle(store.isFavorite(channel) ? Color.newsRed : Color.secondary).padding(7)
                }.buttonStyle(.plain).accessibilityLabel(store.isFavorite(channel) ? "取消收藏\(channel.name)" : "收藏\(channel.name)")
            }.padding(.horizontal, 12).padding(.vertical, 9)
        }.background(Color.newsSurface, in: RoundedRectangle(cornerRadius: 17))
            .clipShape(RoundedRectangle(cornerRadius: 17))
            .overlay { RoundedRectangle(cornerRadius: 17).stroke(.primary.opacity(0.04), lineWidth: 1) }
    }
}
