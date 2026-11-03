import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var store: NewsStore
    @StateObject private var updates = UpdateChecker()
    @AppStorage("appearance") private var appearance = "system"
    @AppStorage("historyEnabled") private var historyEnabled = false
    @AppStorage("playerConsent.v1") private var playerConsent = false
    @State private var confirmClear = false
    @State private var debugKey = ""
    @State private var keySaved = false
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 14) {
                        Image(systemName: "dot.radiowaves.left.and.right").font(.system(size: 27)).foregroundStyle(.white).frame(width: 56, height: 56).background(Color.newsRed, in: RoundedRectangle(cornerRadius: 15))
                        VStack(alignment: .leading, spacing: 5) { Text("新聞直播").font(.title3.bold()); Text("全球時事・一眼掌握").font(.caption).foregroundStyle(.secondary) }
                    }.padding(.vertical, 8)
                }
                Section {
                    Picker("外觀", selection: $appearance) { Text("跟隨系統").tag("system"); Text("淺色").tag("light"); Text("深色").tag("dark") }
                    Toggle("保存最近觀看", isOn: $historyEnabled)
                        .onChange(of: historyEnabled) { _, enabled in if !enabled { store.clearHistory() } }
                    if playerConsent {
                        Button("撤回 YouTube 播放同意") { playerConsent = false }
                    } else {
                        LabeledContent("YouTube 播放器", value: "首次播放時確認")
                    }
                } header: { Text("使用偏好") } footer: {
                    Text("觀看記錄預設關閉，只儲存在本機；關閉時自動清除。撤回播放器同意後，下次播放將再次詢問。")
                }
                Section("本機資料") {
                    Button("清除最近觀看") { store.clearHistory() }.disabled(store.library.recent.isEmpty)
                    Button("清除頻道快取") { store.clearCache() }
                    Button("清除所有本機資料", role: .destructive) { confirmClear = true }
                }
                Section("關於與隱私") {
                    NavigationLink("隱私與資料使用") { PrivacyView() }
                    Link("YouTube 服務條款", destination: URL(string: "https://www.youtube.com/t/terms")!)
                    Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!)
                    if let url = AppConfiguration.privacyURL { Link("完整隱私政策", destination: url) }
                    if let url = AppConfiguration.supportURL { Link("聯絡與支援", destination: url) }
                    if let url = updates.storeURL {
                        Link(destination: url) {
                            HStack {
                                Text("版本").foregroundStyle(.primary)
                                Spacer()
                                if updates.newerVersion != nil { Image(systemName: "arrow.down.circle.fill").foregroundStyle(Color.newsRed).accessibilityLabel("有新版本") }
                                Text(AppConfiguration.version).foregroundStyle(.secondary)
                                Image(systemName: "arrow.up.right").font(.caption).foregroundStyle(.tertiary)
                            }
                        }
                    } else { LabeledContent("版本", value: "\(AppConfiguration.version)・尚未上架") }
                }
                #if DEBUG
                Section("開發設定（僅 Debug）") {
                    SecureField("YouTube Data API Key", text: $debugKey).autocorrectionDisabled().textInputAutocapitalization(.never)
                    Button(keySaved ? "已儲存，點擊可再次更新" : "儲存並連線") {
                        UserDefaults.standard.set(debugKey.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "debugAPIKey")
                        keySaved = true; store.clearCache()
                        Task { await store.bootstrap() }
                    }
                    Text("正式版由開發者在建置設定中配置 API，使用者不需要申請 Key。Debug Key 僅存於測試裝置。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                #endif
                Section {
                    Text("本 App 為獨立的新聞頻道整理工具，與 YouTube、Google 及各新聞媒體無隸屬關係。影音透過 YouTube 官方播放器提供。")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.navigationTitle("設定")
            .onAppear {
                #if DEBUG
                debugKey = UserDefaults.standard.string(forKey: "debugAPIKey") ?? ""
                #endif
                Task { await updates.checkOnSettingsOpen() }
            }
            .confirmationDialog("清除收藏、觀看記錄、快取與播放同意？", isPresented: $confirmClear, titleVisibility: .visible) {
                Button("清除所有本機資料", role: .destructive) {
                    for channel in store.favoriteChannels { store.toggleFavorite(channel) }
                    store.clearHistory(); store.clearCache(); historyEnabled = false; playerConsent = false
                    #if DEBUG
                    UserDefaults.standard.removeObject(forKey: "debugAPIKey"); debugKey = ""; keySaved = false
                    #endif
                }
            }
        }
    }
}

struct PrivacyView: View {
    var body: some View {
        List {
            Section("本機資料") {
                Text("收藏頻道、外觀偏好和播放同意保存在本機。最近觀看預設不記錄，啟用後僅保留最近 20 個頻道，可隨時關閉或清除。App 未設置登入、廣告 SDK 或自有分析追蹤。")
            }
            Section("YouTube / Google") {
                Text("頻道、縮略圖和直播資料透過 YouTube Data API 與 Google 圖片服務載入。這些網路連線會向服務提供者傳送 IP 位址與必要請求資訊。")
                Text("確認載入播放器後，App 會連線至 YouTube 官方 IFrame Player。YouTube / Google 可能處理 IP 位址、裝置、Cookie 及播放互動等資訊，依其服務條款與隱私政策運作。播放器採用非持久 WebKit 資料儲存，這不代表第三方不處理資料。")
                Text("App 不提取媒體地址、不下載影音、不跳過或遮蔽廣告。播放可用性、廣告及地區限制由 YouTube 和內容提供者控制。")
                Link("YouTube 服務條款", destination: URL(string: "https://www.youtube.com/t/terms")!)
                Link("Google 隱私政策", destination: URL(string: "https://policies.google.com/privacy")!)
            }
            Section("刪除與控制") {
                Text("可在設定清除本機資料，並撤回載入播放器的同意。刪除 App 亦會移除其本機資料。API 資料快取最長保留 24 小時。第三方所處理的資料請依 Google 隱私政策管理。")
            }
        }.navigationTitle("隱私與資料使用").navigationBarTitleDisplayMode(.inline)
    }
}
