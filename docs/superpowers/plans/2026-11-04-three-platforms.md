# 三平台实现计划

**目标：** YouTubeNewsLive 的 iOS、macOS、visionOS 原生适配、商店内容与签名上传流程。
**设计：** `docs/superpowers/specs/2026-11-04-three-platforms-design.md`
**执行：** 原生界面与 Apple 发布脚本并行、文件所有权隔离；主代理负责工程生成、CI 集成和最终验证。

- [ ] 用回归测试固定三平台 Scheme/SDK/源文件隔离，生成工程。
- [ ] macOS/visionOS 原生侧栏与网格、设置、播放器桥接；保留 iOS 行为。
- [ ] 统一名称和三平台资产，补齐 Mac/visionOS 图标。
- [ ] Apple 读取当前记录，各平台填充三语言商店文字，并按实际平台生成描述文件及打包上传。
- [ ] 三平台 CI 与真实截图采集，回读已生成的二进制和商店状态。
- [ ] 运行本地回归、独立审查、推送并触发 GitHub；纯等待构建阶段按用户要求停止轮询。

## 接口
- 配置：`Config/platforms.json`（ios/macos/visionos；无 tvos）。
- Scheme：`NewsLive`、`NewsLive-macOS`、`NewsLive-visionOS`。
- Bundle：三平台均 `com.luolihao.newslive`，显示名 `YouTubeNewsLive`。
- UI：`DesktopRootView` 供 macOS/visionOS；`YouTubeWebView(videoID:session:onEvent:)` 接口保留。
- 发布：`scripts/appstore.py` 支持显式平台参数，既有入口兼容；商店更新严格限定对应平台可编辑草稿。
