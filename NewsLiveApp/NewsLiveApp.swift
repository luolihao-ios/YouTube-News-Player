import SwiftUI

@main
@MainActor
struct NewsLiveApp: App {
    @StateObject private var store: NewsStore
    @AppStorage("appearance") private var appearance = "system"

    init() {
        let initialStore = NewsStore()
        #if DEBUG
        // 仅用于采集真实页面；不填充收藏、不触发播放或同意播放器条款。
        let arguments = ProcessInfo.processInfo.arguments
        if let index = arguments.firstIndex(of: "--capture-tab"), arguments.indices.contains(index + 1) {
            switch arguments[index + 1] {
            case "home": initialStore.selectedTab = .home
            case "channels": initialStore.selectedTab = .channels
            case "favorites": initialStore.selectedTab = .favorites
            case "settings": initialStore.selectedTab = .settings
            default: break
            }
        }
        #endif
        _store = StateObject(wrappedValue: initialStore)
    }

    var body: some Scene {
        WindowGroup {
            #if os(iOS)
            RootView()
                .environmentObject(store)
                .tint(.newsRed)
                .preferredColorScheme(appearance == "light" ? .light : appearance == "dark" ? .dark : nil)
            #else
            DesktopRootView()
                .environmentObject(store)
                .tint(.newsRed)
                .preferredColorScheme(appearance == "light" ? .light : appearance == "dark" ? .dark : nil)
                .frame(minWidth: 900, minHeight: 620)
            #endif
        }
        #if os(macOS) || os(visionOS)
        .defaultSize(width: 1200, height: 820)
        #endif
    }
}
