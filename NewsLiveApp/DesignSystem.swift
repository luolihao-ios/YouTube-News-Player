import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

extension Color {
    static let newsRed = Color(red: 0.94, green: 0.12, blue: 0.16)
    #if os(macOS)
    static let newsBackground = Color(nsColor: .windowBackgroundColor)
    static let newsSurface = Color(nsColor: .controlBackgroundColor)
    static let newsSecondarySurface = Color(nsColor: .underPageBackgroundColor)
    static let newsInput = Color(nsColor: .quaternaryLabelColor).opacity(0.14)
    #else
    static let newsBackground = Color(uiColor: .systemGroupedBackground)
    static let newsSurface = Color(uiColor: .systemBackground)
    static let newsSecondarySurface = Color(uiColor: .secondarySystemGroupedBackground)
    static let newsInput = Color(uiColor: .tertiarySystemFill)
    #endif
    init(newsHex: String) {
        let value = UInt(newsHex, radix: 16) ?? 0x203DA7
        self.init(red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255)
    }
}
