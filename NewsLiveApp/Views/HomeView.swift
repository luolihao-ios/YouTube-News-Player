import SwiftUI
import NewsCore

struct HomeView: View {
    @EnvironmentObject private var store: NewsStore
    @State private var category: ChannelCategory?
    @State private var heroIndex = 0
    @State private var showingSignIn = false
    @AppStorage("historyEnabled") private var historyEnabled = false
    private var visible: [ChannelSeed] { ChannelFilter.apply(store.channels, query: "", category: category) }
    private var categoryLive: [ChannelSeed] { store.liveChannels.filter { category == nil || $0.category == category } }
    private var displayed: [ChannelSeed] { ChannelFilter.preferred(store.channels, liveIDs: Set(store.liveChannels.map(\.id)), category: category) }
    private var featured: [ChannelSeed] { Array(displayed.prefix(4)) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 22) {
                    header.padding(.horizontal, 20)
                    Button { showingSignIn = true } label: {
                        Label("Google 登入", systemImage: "person.crop.circle")
                            .frame(maxWidth: .infinity)
                    }.buttonStyle(.bordered).padding(.horizontal, 20)
                    CategoryPicker(selection: $category, allTitle: "推薦")
                    if let message = store.catalogError {
                        MessageCard(symbol: "exclamationmark.triangle", title: "無法載入頻道", message: message).padding(.horizontal, 20)
                    }
                    if !AppConfiguration.isConfigured { setupBanner.padding(.horizontal, 20) }
                    if !featured.isEmpty {
                        VStack(spacing: 10) {
                            TabView(selection: $heroIndex) {
                                ForEach(Array(featured.enumerated()), id: \.element.id) { index, channel in
                                    hero(channel).tag(index).padding(.horizontal, 20)
                                }
                            }.tabViewStyle(.page(indexDisplayMode: .never)).frame(height: 224)
                            HStack(spacing: 6) {
                                ForEach(featured.indices, id: \.self) { index in
                                    Capsule().fill(index == heroIndex ? Color.newsRed : Color.gray.opacity(0.25)).frame(width: index == heroIndex ? 18 : 5, height: 5)
                                }
                            }.accessibilityHidden(true)
                        }
                    }
                    VStack(spacing: 6) {
                        SectionHeading(title: categoryLive.isEmpty ? "精選新聞頻道" : "正在直播", actionTitle: "查看全部") { store.browse(category) }
                            .padding(.bottom, 8)
                        ForEach(Array(displayed.prefix(4))) { channel in
                            ChannelRow(channel: channel, favoriteAction: false)
                            if channel.id != displayed.prefix(4).last?.id { Divider().opacity(0.45) }
                        }
                        if visible.isEmpty { Text("此分類暫無頻道").foregroundStyle(.secondary).padding() }
                    }.padding(.horizontal, 20)
                    categories
                    if historyEnabled && !store.recentChannels.isEmpty {
                        VStack(spacing: 8) {
                            SectionHeading(title: "最近觀看")
                            ForEach(Array(store.recentChannels.prefix(3))) { ChannelRow(channel: $0) }
                        }.padding(.horizontal, 20)
                    }
                    HStack(spacing: 5) {
                        Image(systemName: "play.rectangle.fill").foregroundStyle(Color.newsRed)
                        Text("影音與直播資訊來自 YouTube").foregroundStyle(.secondary)
                    }.font(.system(size: 11)).padding(.bottom, 18)
                }.padding(.top, 12)
            }
            .background(Color(uiColor: .systemBackground))
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await store.refresh(Array(visible.prefix(3)), force: true) }
            .onChange(of: category) { _, _ in heroIndex = 0 }
            .fullScreenCover(isPresented: $showingSignIn) { YouTubeSignInView(onSignedIn: {}) }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            HStack(spacing: 9) {
                Image(systemName: "dot.radiowaves.left.and.right").font(.system(size: 26, weight: .semibold)).foregroundStyle(Color.newsRed)
                VStack(alignment: .leading, spacing: 4) {
                    Text("新聞直播").font(.system(size: 27, weight: .bold))
                    Text("全球時事・一眼掌握").font(.system(size: 11)).foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button { store.browse() } label: { Image(systemName: "magnifyingglass").font(.system(size: 20)).frame(width: 38, height: 42) }.accessibilityLabel("搜尋頻道")
            Button { store.selectedTab = .settings } label: { Image(systemName: "gearshape").font(.system(size: 20)).frame(width: 30, height: 42) }.accessibilityLabel("設定")
        }.foregroundStyle(.primary)
    }

    private var setupBanner: some View {
        Button { store.selectedTab = .settings } label: {
            HStack(spacing: 10) {
                Image(systemName: "info.circle")
                Text("服務尚未設定，完成 YouTube API 設定後即可收看").font(.system(size: 12)).multilineTextAlignment(.leading)
                Spacer(minLength: 0); Image(systemName: "chevron.right").font(.system(size: 10))
            }.foregroundStyle(.secondary).padding(13).background(Color.newsBackground, in: RoundedRectangle(cornerRadius: 12))
        }.buttonStyle(.plain)
    }

    private func hero(_ channel: ChannelSeed) -> some View {
        let snapshot = store.snapshots[channel.id]
        let video = snapshot?.videos.first
        return Button { store.open(channel) } label: {
            GeometryReader { geometry in
            ZStack(alignment: .bottomLeading) {
                LinearGradient(colors: [Color(newsHex: channel.color).opacity(0.85), Color(newsHex: channel.color).opacity(0.5), Color(red: 0.05, green: 0.10, blue: 0.22)], startPoint: .topLeading, endPoint: .bottomTrailing)
                if let video {
                    AsyncImage(url: video.thumbnailURL) { image in image.resizable().scaledToFill() } placeholder: { Color.clear }
                        .frame(width: geometry.size.width, height: geometry.size.height).clipped()
                } else {
                    HStack {
                        Spacer()
                        Image(systemName: "globe.asia.australia.fill").font(.system(size: 165, weight: .ultraLight)).foregroundStyle(.white.opacity(0.13)).rotationEffect(.degrees(-15)).offset(x: 18, y: -5)
                    }
                    Text("每個角度\n看見世界").font(.system(size: 26, weight: .bold)).foregroundStyle(.white.opacity(0.9)).padding(22).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                LinearGradient(colors: [.clear, .black.opacity(0.8)], startPoint: .center, endPoint: .bottom)
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(channel.name).font(.system(size: 22, weight: .bold))
                        Text(video?.title ?? channel.subtitle).font(.system(size: 12)).lineLimit(1)
                    }
                    Spacer()
                    Image(systemName: "play.fill").font(.system(size: 17)).frame(width: 43, height: 43).background(.white.opacity(0.12), in: Circle()).overlay { Circle().stroke(.white.opacity(0.9), lineWidth: 1.5) }
                }.foregroundStyle(.white).padding(18)
            }.frame(width: geometry.size.width, height: geometry.size.height).overlay(alignment: .topTrailing) {
                if video != nil { LiveBadge(cached: snapshot?.isFresh != true).padding(13) }
                else { Text("精選頻道").font(.system(size: 11, weight: .medium)).foregroundStyle(.white).padding(7).background(.black.opacity(0.15), in: Capsule()).padding(13) }
            }.clipShape(RoundedRectangle(cornerRadius: 17))
            }
        }.buttonStyle(.plain)
    }

    private var categories: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("精選分類").font(.system(size: 21, weight: .bold)).padding(.horizontal, 20)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(Array(ChannelCategory.allCases.enumerated()), id: \.element.id) { index, category in
                        Button { store.browse(category) } label: {
                            VStack(alignment: .leading, spacing: 18) {
                                Image(systemName: category.symbol).font(.system(size: 24, weight: .light)).foregroundStyle(.white.opacity(0.8))
                                HStack { Text(category.rawValue).font(.system(size: 13, weight: .semibold)); Spacer(minLength: 0); Image(systemName: "arrow.up.right").font(.system(size: 10)) }
                            }.foregroundStyle(.white).padding(13).frame(width: 118, height: 102)
                                .background(LinearGradient(colors: [Color(newsHex: ["486F9D", "244D71", "788E9C", "655B75"][index]), .black.opacity(0.9)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 12))
                        }.buttonStyle(.plain)
                    }
                }.padding(.horizontal, 20)
            }
        }
    }
}
