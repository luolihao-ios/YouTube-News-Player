# 三平台实现计划

**目标：** YouTubeNewsLive 的 iOS、macOS、visionOS 原生适配、商店内容与签名上传流程。
**设计：** `docs/superpowers/specs/2026-11-04-three-platforms-design.md`
**执行：** 原生界面与 Apple 发布脚本并行、文件所有权隔离；主代理负责工程生成、CI 集成和最终验证。

- [x] 用回归测试固定三平台 Scheme/SDK/源文件隔离，生成工程。
- [x] macOS/visionOS 原生侧栏与网格、设置、播放器桥接；保留 iOS 行为。
- [x] 统一名称和三平台资产，补齐 Mac/visionOS 图标。
- [x] Apple 读取当前记录，各平台三语言商店文字已写入并回读；按平台签名上传流程已接好，二进制结果待云端构建。
- [ ] 三平台 CI 与真实截图采集，回读已生成的二进制和商店状态。
- [ ] 运行本地回归、独立审查、推送并触发 GitHub；纯等待构建阶段按用户要求停止轮询。

## 已取得的远端证据

- App ID `6830361548`，Bundle `com.luolihao.newslive`，平台为 `UNIVERSAL`。
- 三平台 iOS/macOS/visionOS 均有 1.0 草稿；用户已移除 tvOS 草稿。
- 商店文字任务 `41727021991` 成功，三个目标平台各有 en-US、zh-Hans、zh-Hant 资料并逐字段回读。
- Installer 证书准备任务 `41727509516` 成功，新证书 ID `K23B3SXBK7`。两项 Mac Installer Secrets 已通过目标仓库公钥密封同步。
- 本地 Python 74 项测试与播放器 5 项通过；独立只读审查未发现高置信度编译阻断。
- 三平台正式发布流程 `41727934122` 已触发；此处不把排队或命令触发当作已生成/已上传二进制。
- 该流程的 iOS、macOS、visionOS 验证构建均已成功；三个归档上传任务排队中。
- 真实截图采集、像素来源校验、平台语言草稿追加及构建关联流程已加入；远端截图与关联结果仍待运行验证。

## 接口
- 配置：`Config/platforms.json`（ios/macos/visionos；无 tvos）。
- Scheme：`NewsLive`、`NewsLive-macOS`、`NewsLive-visionOS`。
- Bundle：三平台均 `com.luolihao.newslive`，显示名 `YouTubeNewsLive`。
- UI：`DesktopRootView` 供 macOS/visionOS；`YouTubeWebView(videoID:session:onEvent:)` 接口保留。
- 发布：`scripts/appstore.py` 支持显式平台参数，既有入口兼容；商店更新严格限定对应平台可编辑草稿。
