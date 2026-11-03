import SwiftUI
import NewsCore

struct ChannelsView: View {
    @EnvironmentObject private var store: NewsStore
    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                HStack(spacing: 10) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("搜尋頻道名稱", text: $store.search).submitLabel(.search).autocorrectionDisabled()
                    if !store.search.isEmpty { Button { store.search = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) }.accessibilityLabel("清除搜尋") }
                }.padding(12).background(Color.newsBackground, in: RoundedRectangle(cornerRadius: 12)).padding(.horizontal, 20)
                CategoryPicker(selection: $store.selectedCategory)
                ScrollView {
                    LazyVStack(spacing: 0) {
                        HStack {
                            Text("\(store.filteredChannels.count) 個頻道").font(.system(size: 12)).foregroundStyle(.secondary)
                            Spacer()
                            Text("資料來源 YouTube").font(.system(size: 11)).foregroundStyle(.tertiary)
                        }.padding(.vertical, 8)
                        ForEach(store.filteredChannels) { channel in
                            ChannelRow(channel: channel)
                            Divider().opacity(0.4)
                        }
                        if store.filteredChannels.isEmpty {
                            ContentUnavailableView.search(text: store.search)
                        }
                    }.padding(.horizontal, 20).padding(.bottom, 20)
                }.refreshable { await store.refresh(store.filteredChannels, force: true) }
            }.navigationTitle("頻道").navigationBarTitleDisplayMode(.large)
        }
    }
}
