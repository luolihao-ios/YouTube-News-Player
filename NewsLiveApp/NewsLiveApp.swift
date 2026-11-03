import SwiftUI

@main
@MainActor
struct NewsLiveApp: App {
    @StateObject private var store = NewsStore()
    @AppStorage("appearance") private var appearance = "system"
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
