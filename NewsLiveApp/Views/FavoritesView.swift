import SwiftUI
import NewsCore

struct FavoritesView: View {
    @EnvironmentObject private var store: NewsStore
    @State private var recommendationOffset = 0
    var body: some View {
        NavigationStack {
            List {
                Section {
                    if store.favoriteChannels.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "heart").font(.system(size: 35, weight: .light)).foregroundStyle(Color.newsRed)
                            Text("把關心的新聞，放在一起").font(.headline)
                            Text("點擊頻道旁的愛心，下次就能快速收看。").font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                            Button("探索頻道") { store.browse() }.buttonStyle(.borderedProminent).padding(.top, 4)
                        }.frame(maxWidth: .infinity).padding(.vertical, 28).listRowSeparator(.hidden)
                    }
                    ForEach(store.favoriteChannels) { channel in
                        ChannelRow(channel: channel, favoriteAction: false)
                            .swipeActions { Button(role: .destructive) { store.toggleFavorite(channel) } label: { Label("取消收藏", systemImage: "heart.slash") } }
                    }.onDelete { store.removeFavorites(at: $0) }.onMove { store.moveFavorites(from: $0, to: $1) }
                } footer: {
                    if !store.favoriteChannels.isEmpty { Text("收藏僅保存在此裝置；點擊編輯可拖動排序。") }
                }
                if !store.recommendations.isEmpty {
                    Section {
                        ForEach(Array(rotatedRecommendations.prefix(3))) { channel in
                            ChannelRow(channel: channel)
                        }
                    } header: {
                        HStack {
                            Text("推薦頻道").font(.system(size: 18, weight: .bold)).foregroundStyle(.primary)
                            Spacer()
                            Button { recommendationOffset += 3 } label: { Label("換一批", systemImage: "arrow.triangle.2.circlepath").font(.system(size: 12)) }
                        }.textCase(nil).padding(.vertical, 10)
                    }
                }
            }
            .listStyle(.insetGrouped).scrollContentBackground(.hidden)
            .navigationTitle("我的收藏")
            .toolbar { if !store.favoriteChannels.isEmpty { EditButton().tint(.primary) } }
            .refreshable { await store.refresh(store.favoriteChannels, force: true) }
        }
    }
    private var rotatedRecommendations: [NewsCore.ChannelSeed] {
        let items = store.recommendations
        guard !items.isEmpty else { return [] }
        let offset = recommendationOffset % items.count
        return Array(items[offset...]) + Array(items[..<offset])
    }
}
