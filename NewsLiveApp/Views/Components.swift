import SwiftUI
import NewsCore

struct ChannelLogo: View {
    let channel: ChannelSeed
    var url: URL?
    var size: CGFloat = 48
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.24).fill(Color(newsHex: channel.color).opacity(0.08))
            AsyncImage(url: url) { image in image.resizable().scaledToFit() } placeholder: {
                Text(channel.monogram).font(.system(size: size * 0.28, weight: .black, design: .rounded))
                    .minimumScaleFactor(0.5).foregroundStyle(Color(newsHex: channel.color)).padding(5)
            }
        }
        .frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: size * 0.24))
        .accessibilityHidden(true)
    }
}

struct LiveBadge: View {
    var cached = false
    var body: some View {
        HStack(spacing: 4) {
            if !cached { Circle().frame(width: 5, height: 5) }
            Text(cached ? "直播快照" : "LIVE").font(.system(size: 10, weight: .bold, design: .rounded))
        }.foregroundStyle(.white).padding(.horizontal, 7).padding(.vertical, 4)
            .background(cached ? Color.gray : Color.newsRed, in: RoundedRectangle(cornerRadius: 5))
    }
}

struct CategoryPicker: View {
    @Binding var selection: ChannelCategory?
    var allTitle = "全部"
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 9) {
                chip(allTitle, value: nil)
                ForEach(ChannelCategory.allCases) { chip($0.rawValue, value: $0) }
            }.padding(.horizontal, 20).padding(.vertical, 4)
        }
    }
    private func chip(_ title: String, value: ChannelCategory?) -> some View {
        Button { withAnimation(.easeInOut(duration: 0.18)) { selection = value } } label: {
            Text(title).font(.system(size: 14, weight: selection == value ? .semibold : .medium))
                .padding(.horizontal, 15).padding(.vertical, 10)
                .foregroundStyle(selection == value ? .white : .primary)
                .background(selection == value ? Color.newsRed : Color(uiColor: .tertiarySystemFill), in: Capsule())
        }.buttonStyle(.plain).accessibilityAddTraits(selection == value ? .isSelected : [])
    }
}

struct ChannelRow: View {
    @EnvironmentObject private var store: NewsStore
    let channel: ChannelSeed
    var favoriteAction = true
    var body: some View {
        HStack(spacing: 12) {
            Button { store.open(channel) } label: {
                HStack(spacing: 12) {
                    ChannelLogo(channel: channel, url: store.snapshots[channel.id]?.channel.thumbnailURL)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(store.snapshots[channel.id]?.channel.title ?? channel.name).font(.system(size: 16, weight: .semibold)).foregroundStyle(.primary).lineLimit(1)
                        Text(channel.subtitle).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(1)
                        HStack(spacing: 4) {
                            if store.loading.contains(channel.id) { ProgressView().controlSize(.mini) }
                            else if store.snapshots[channel.id]?.isFresh == true && store.snapshots[channel.id]?.videos.first != nil {
                                Image(systemName: "person.fill").foregroundStyle(Color.newsRed).font(.system(size: 9))
                            }
                            Text(store.statusText(channel)).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                    if let snapshot = store.snapshots[channel.id], let video = snapshot.videos.first {
                        AsyncImage(url: video.thumbnailURL) { image in image.resizable().scaledToFill() } placeholder: { Color.gray.opacity(0.1) }
                            .frame(width: 96, height: 60).clipped().overlay(alignment: .bottomTrailing) {
                                LiveBadge(cached: !snapshot.isFresh).padding(3)
                            }.clipShape(RoundedRectangle(cornerRadius: 8))
                    } else {
                        Image(systemName: "play.circle").font(.system(size: 25, weight: .light)).foregroundStyle(.tertiary)
                    }
                }.contentShape(Rectangle())
            }.buttonStyle(.plain)
            if favoriteAction {
                Button { store.toggleFavorite(channel) } label: {
                    Image(systemName: store.isFavorite(channel) ? "heart.fill" : "heart")
                        .font(.system(size: 17)).foregroundStyle(store.isFavorite(channel) ? Color.newsRed : .secondary)
                        .frame(width: 32, height: 44)
                }.buttonStyle(.plain).accessibilityLabel(store.isFavorite(channel) ? "取消收藏 \(channel.name)" : "收藏 \(channel.name)")
            }
        }.padding(.vertical, 9)
    }
}

struct SectionHeading: View {
    let title: String
    var actionTitle: String?
    var action: (() -> Void)?
    var body: some View {
        HStack {
            Text(title).font(.system(size: 21, weight: .bold))
            Spacer()
            if let actionTitle, let action {
                Button(action: action) {
                    HStack(spacing: 3) { Text(actionTitle); Image(systemName: "chevron.right").font(.system(size: 10, weight: .semibold)) }
                        .font(.system(size: 13)).foregroundStyle(.secondary)
                }
            }
        }
    }
}

struct MessageCard: View {
    let symbol: String
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 34, weight: .light)).foregroundStyle(Color.newsRed)
            Text(title).font(.headline)
            Text(message).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }.padding(28).frame(maxWidth: .infinity).background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20))
    }
}
