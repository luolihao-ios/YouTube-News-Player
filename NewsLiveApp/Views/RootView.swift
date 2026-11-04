import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: NewsStore
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        TabView(selection: $store.selectedTab) {
            HomeView().tabItem { Label("首頁", systemImage: "house.fill") }.tag(AppTab.home)
            ChannelsView().tabItem { Label("頻道", systemImage: "square.grid.2x2") }.tag(AppTab.channels)
            FavoritesView().tabItem { Label("收藏", systemImage: "heart") }.tag(AppTab.favorites)
            SettingsView().tabItem { Label("設定", systemImage: "gearshape") }.tag(AppTab.settings)
        }
        .fullScreenCover(item: $store.activeChannel) { channel in
            PlayerView(channel: channel).id(channel.id).environmentObject(store)
        }
        .task { await store.bootstrap() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { store.expireCache() } }
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { _ in
            if scenePhase == .active { store.expireCache() }
        }
    }
}
