import SwiftUI

@main
@MainActor
struct NewsLiveApp: App {
    @StateObject private var store = NewsStore()
    @AppStorage("appearance") private var appearance = "system"
    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .tint(.newsRed)
                .preferredColorScheme(appearance == "light" ? .light : appearance == "dark" ? .dark : nil)
        }
    }
}
