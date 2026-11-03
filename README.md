# 新闻直播 · iOS

以提供的四屏红白 UI 为基准构建的原生新闻直播聚合器。**SwiftUI + WKWebView + YouTube IFrame Player API + YouTube Data API v3**，最低 iOS 17，建议 Xcode 16.2 或以上。

## 现有功能

- 首页精选频道、直播缩略图、分类入口，区分真实直播、过期快照和未查询状态。
- 频道本地搜索、分类过滤、按需查询公开且允许嵌入的直播，下拉刷新。
- 官方 YouTube 播放器、系统分享、收藏、直播说明和相关频道；原生播放器区域始终可见，关闭或切入后台暂停。
- 收藏编辑、拖动排序、删除；最近观看默认关闭，启用后仅在真正播放时记录最近20个频道。
- 浅色/深色外观、隐私告知、播放同意撤回、本机资料清除。
- 设置页打开时查询 App Store 版本；新版在版本项显示下载图标，点击进入系统 App Store。不在启动时查询。
- 直播发现缓存15分钟，频道身份缓存24小时，API持久化数据最长24小时。前台每分钟只更新本地失效状态，不轮询网络。

## 在 Mac 运行

1. 将整个目录复制到 Mac，双击 `NewsLive.xcodeproj`，选择 `NewsLive` Scheme。
2. 将 `Config/Local.xcconfig.example` 复制为 `Config/Local.xcconfig`，配置自己的 Bundle ID、签名 Team 和 YouTube API Key。
3. Google Cloud 项目启用 **YouTube Data API v3**，将 Key 限制为该 API，并按实际 Bundle ID 设置 iOS 应用限制。App 的 API 请求包含 `X-Ios-Bundle-Identifier`。
4. 选择模拟器或 iPhone，运行 Debug。Debug 的设置页也能临时输入 Key，正式版没有这个输入项。

工程没有依赖第三方播放 SDK，也不需要 CocoaPods / XcodeGen。修改新增文件后可运行 `python3 scripts/generate_project.py` 更新工程。

缺少 Key 时仍能浏览目录、分类和管理收藏，界面会明确说明服务尚未设置；**不会用假直播、假观看人数替代 API 结果**。2026-11-03 已使用本地配置完成真实 HTTP API 验证：12 个频道身份均成功返回，首页 3 个频道的直播发现和详情均成功。iOS 真机播放仍未验证。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `NewsLiveApp/Views` | 四个主要页面及播放详情 |
| `NewsLiveApp/Playback` | WebKit、官方 iframe 桥接及生命周期 |
| `NewsLiveApp/Services` | App 状态、缓存和版本检查 |
| `NewsLiveApp/Resources/channels.json` | 人工整理的新闻频道目录；使用真实 API 验证的稳定 Channel ID |
| `Packages/NewsCore` | 模型、API、筛选、收藏与核心 XCTest |
| `Config` | 建置配置与 Info.plist，真实 Key 不提交版本控制 |
| `tests` | Windows/macOS 均可执行的播放器与 Release 配置测试 |
| `.github/workflows/ios.yml` | macOS 核心测试及模拟器构建；没有自动发布步骤 |

## 验证命令

```powershell
node --test tests/player.test.mjs
python -m unittest discover -s tests -p "test_*.py"
python -m pip install --target .test-tools -r requirements-dev.txt
python scripts/verify_project.py
# 读取本地 Key；默认只检查首页3个频道的直播，控制 API 配额。
python scripts/check_youtube_api.py
```

在 Mac 上再执行：

```sh
swift test --package-path Packages/NewsCore
xcodebuild -project NewsLive.xcodeproj -scheme NewsLive -configuration Debug \
  -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Windows 的语法解析、脚本测试和工程引用检查不等于 Xcode 编译通过。CI 输出的模拟器 App 也不是可安装到真机的 IPA。项目保存在私有仓库 [luolihao-ios/YouTube-News-Player](https://github.com/luolihao-ios/YouTube-News-Player)，GitHub Actions 执行 macOS 编译。

## API 与上线

直播发现使用 `channels.list(id)` → `search.list(eventType=live, type=video, videoEmbeddable=true)` → `videos.list`，再次检查公开、仍在直播及允许嵌入。目录使用稳定 Channel ID；`id` 字段保留为本机收藏的目录标识，避免频道 handle 改名后收藏失效。未配置稳定 Channel ID 的新增频道仍支持 `forHandle` 解析。观看人数仅使用官方返回值，并标示更新时间。频道可能下播、修改地区或嵌入权限；提供稳定的官方频道链接作为失败后的去向。

API 验证报告写入 `.test-output/youtube-api-check.json`，不包含 Key 或带 Key 的请求 URL。API 报告中的允许嵌入不等于已在全部地区播放成功；例如本次 TVBS 和三立部分海外版直播明确禁止在台湾播放，最终仍由 YouTube 播放器执行地区限制。

当前为直接调用 API 的首版架构，设备之间不共享缓存。大量用户上线前应评估实际 Google Cloud 配额，必要时建设共享发现缓存服务。客户端 Key 能从安装包中提取，不能当作服务器秘密使用；不要放入管理凭据、OAuth client secret 或其他私密凭据。

正式提交用的 Release 建置会检查 Key、App Store ID、隐私政策与支援网址是否已配置。TestFlight 工作流显式设置 `RELEASE_STAGE=testflight`，仍检查 Key 与实际 App ID，但允许尚未公开的隐私/支援网址为空；若提供网址，仍要求 HTTPS。需要在手写 `Local.xcconfig` 的 URL 中用 `https:/$()/域名/路径`，避免 `//` 被 xcconfig 解析为注释。该检查仅验证配置形式，不证明 Key 有效、网站可达或内容已有授权。

## GitHub 与 App Store Connect

- 仓库为私有。组织为 GitHub Free，私有仓库使用仓库级 Secrets：`YOUTUBE_API_KEY`、`APP_STORE_CONNECT_API_KEY_ID`、`APP_STORE_CONNECT_ISSUER_ID`、`APP_STORE_CONNECT_API_KEY_BASE64`、`IOS_SIGNING_CERTIFICATE_BASE64`、`IOS_SIGNING_CERTIFICATE_PASSWORD`。
- `.github/workflows/ios.yml` 在 push/PR 执行本地测试、Swift XCTest、iOS 模拟器构建。可信工作流从 Secret 生成忽略提交的 `Config/Local.xcconfig`。
- `.github/workflows/ios-testflight.yml` 可手动选择 `prepare` 或 `release`。准备流程注册/核对 `com.luolihao.newslive`，匹配真实 App Store App ID；签名流程根据发行证书和新 Bundle ID 获取专属描述文件，不复用其他 App 的描述文件。
- 若已有匹配应用记录，准备流程填写并回读三语言名称、副标题。英文名 NewsLive，中文名 NewsLive 新闻直播/新聞直播；副标题“即时新闻，掌握世界每一刻”及繁体对应版本。
- Apple 官方 API 不支持新建 App Store 应用记录。若尚无记录，工作流报告下一步，跳过签名上传。需要在 App Store Connect 新建 `NewsLive`，Bundle ID 选择 `com.luolihao.newslive`，SKU 可用 `newslive-ios`，主语言为 English (U.S.)，之后再次运行 `release`。
- 已配置的 GitHub Secret 不能读回明文。本次组织凭据使用目标仓库公钥加密同步为仓库级凭据；加密任务不输出或下载明文，临时源分支已清理，源项目主分支没有改动。
- 工作流上传命令成功与 Apple 最终处理完成是两个状态。请以实际工作流日志和 App Store Connect 构建状态为准；本流程不提交审核或发布商店版本。

查看 [审核与真机验证说明](docs/审核与真机验证.md)。本工程未签名、未生成 IPA、未提交 App Store，也没有保证审核通过。
