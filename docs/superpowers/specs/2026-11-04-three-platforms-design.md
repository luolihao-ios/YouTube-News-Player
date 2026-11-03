# YouTubeNewsLive 三平台适配

## 用户要求与最终范围
用户在 App Store Connect 将名称改为 **YouTubeNewsLive**，要求各平台有商店内容和对应二进制。截图最初包含 iOS、macOS、tvOS、visionOS；后续明确取消 tvOS，因此本次只处理 **iOS、macOS、visionOS**。不删除已有 tvOS 草稿，不为它生成或上传二进制。

## 实现方案
- iOS 保留已通过 GitHub 编译的 SwiftUI 四页与 WKWebView 播放器。
- macOS 采用原生侧栏、可搜索频道网格、收藏和播放器窗口布局，WKWebView 使用 NSViewRepresentable。
- visionOS 使用原生可调整窗口、侧栏和空间系统控件，通过 UIKit 版 WKWebView 承载官方播放器；不宣称提供沉浸式视频或后台播放。
- 共享 YouTube Data API、稳定频道 ID、收藏、历史开关、缓存及错误处理；使用同一个 App Store Connect 记录和 Bundle ID `com.luolihao.newslive`。

## 发布与证据
`Config/platforms.json` 是三平台 Scheme、SDK、Apple platform 和最低系统的唯一配置。CI 分别构建，上传流程分别签名/导出 IPA 或 Mac App Store 包，按 Apple 实际处理结果报告。商店标题统一 YouTubeNewsLive，各平台填写与实际能力一致的说明与关键词；真实运行截图才可上传，不能把参考图或概念图当作截图。

macOS 签名/安装包证书、描述文件、visionOS SDK/运行时等须按实际环境核对。可以自动创建的新描述文件仅限本项目；不撤销已有证书、不覆盖其他 App。缺少证书或运行时则明确报告，不能把打包配置完成算作二进制已上传。

## 验证边界
2026-11-04 查询确认此前 iOS CI `41601784218` 已成功，发布流程 `41601779524` 的 Apple 准备成功但无 App 记录而跳过上传。用户现在已创建记录，需在本次重新读取实际 App ID、各平台版本及语言条目。Windows 的静态检查仍不能代替 Mac/visionOS 编译或 Apple 处理状态。
