import SwiftUI

struct DesktopSettingsView: View {
    @EnvironmentObject private var store: NewsStore
    @StateObject private var updates = UpdateChecker()
    @AppStorage("appearance") private var appearance = "system"
    @AppStorage("historyEnabled") private var historyEnabled = false
    @AppStorage("playerConsent.v1") private var playerConsent = false
    @State private var confirmClear = false

    var body: some View {
        Form {
            Section {
                HStack(spacing: 16) {
                    Image(systemName: "dot.radiowaves.left.and.right")
                        .font(.system(size: 28, weight: .medium)).foregroundStyle(.white)
                        .frame(width: 62, height: 62).background(Color.newsRed, in: RoundedRectangle(cornerRadius: 16))
                    VStack(alignment: .leading, spacing: 6) {
                        Text("YouTubeNewsLive").font(.title2.bold())
                        Text("全球時事・一眼掌握").font(.subheadline).foregroundStyle(.secondary)
                    }
                }.padding(.vertical, 12)
            }
            Section {
                Picker("外觀", selection: $appearance) {
                    Text("跟隨系統").tag("system")
                    Text("淺色").tag("light")
                    Text("深色").tag("dark")
                }
                Toggle("保存最近觀看", isOn: $historyEnabled)
                    .onChange(of: historyEnabled) { _, enabled in if !enabled { store.clearHistory() } }
                if playerConsent {
                    Button("撤回 YouTube 播放同意") { playerConsent = false }
                } else {
                    LabeledContent("YouTube 播放器", value: "首次播放時確認")
                }
            } header: { Text("使用偏好") } footer: {
                Text("觀看記錄預設關閉，只保存在本機。關閉後會清除記錄；撤回同意後，播放器會停止並在下次播放時再次詢問。")
            }
            Section("本機資料") {
                Button("清除最近觀看") { store.clearHistory() }.disabled(store.library.recent.isEmpty)
                Button("清除頻道快取") { store.clearCache() }
                Button("清除所有本機資料", role: .destructive) { confirmClear = true }
            }
            Section("隱私與支援") {
                NavigationLink("隱私與資料使用") { DesktopPrivacyView() }
                Link("YouTube 服務條款", destination: URL(string: "https://www.youtube.com/t/terms")!)
                Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!)
                if let url = AppConfiguration.privacyURL { Link("完整隱私政策", destination: url) }
                if let url = AppConfiguration.supportURL { Link("聯絡與支援", destination: url) }
                if let url = updates.storeURL {
                    Link(destination: url) {
                        HStack {
                            Text("版本").foregroundStyle(.primary)
                            Spacer()
                            if updates.newerVersion != nil {
                                Image(systemName: "arrow.down.circle.fill").foregroundStyle(Color.newsRed).accessibilityLabel("有新版本")
                            }
                            Text(AppConfiguration.version).foregroundStyle(.secondary)
                            Image(systemName: "arrow.up.right").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                } else { LabeledContent("版本", value: "\(AppConfiguration.version)・尚未上架") }
            }
            Section {
                Text("本 App 為獨立的新聞頻道整理工具，與 YouTube、Google 及各新聞媒體無隸屬關係。影音、廣告與播放控制由 YouTube 官方播放器提供。")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("設定")
        .task { await updates.checkOnSettingsOpen() }
        .confirmationDialog("清除收藏、觀看記錄、快取與播放同意？", isPresented: $confirmClear, titleVisibility: .visible) {
            Button("清除所有本機資料", role: .destructive) {
                for channel in store.favoriteChannels { store.toggleFavorite(channel) }
                store.clearHistory(); store.clearCache()
                historyEnabled = false; playerConsent = false; appearance = "system"
            }
        }
    }
}

private struct DesktopPrivacyView: View {
    var body: some View {
        Form {
            Section("本機資料") {
                Text("收藏、外觀偏好及播放同意保存在本機。最近觀看預設不記錄，啟用後最多保留 20 個頻道，可隨時清除。本 App 沒有帳號登入、自有廣告 SDK 或分析追蹤。")
            }
            Section("YouTube / Google") {
                Text("頻道、縮圖及直播資料透過 YouTube Data API 與 Google 圖片服務取得。這些連線會向服務提供者傳送 IP 位址及必要的請求資訊。")
                Text("同意後才會載入官方 YouTube IFrame Player。YouTube / Google 可能處理裝置、Cookie 及播放互動等資訊。播放器採用非持久 WebKit 資料儲存，但不代表第三方不處理資料。")
                Text("App 不提取媒體地址、不下載影音、不跳過或遮蔽廣告。播放可用性、地區限制、畫質、字幕與全螢幕功能由官方播放器和內容提供者控制。")
                Link("YouTube 服務條款", destination: URL(string: "https://www.youtube.com/t/terms")!)
                Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!)
            }
            Section("資料控制") {
                Text("可在設定清除本機資料或撤回播放同意。API 快取最長保留 24 小時。第三方資料請依 Google 隱私政策管理。")
            }
        }.formStyle(.grouped).navigationTitle("隱私與資料使用")
    }
}
