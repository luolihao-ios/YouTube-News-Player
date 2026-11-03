# GitHub 私有仓库与 App Store Connect 工作流计划

**目标：** 在 `luolihao-ios/YouTube-News-Player` 保存项目，使用仓库级凭据进行 GitHub macOS 编译、签名和 App Store Connect 上传；必要时创建 NewsLive 应用记录并填写名称和副标题。

**架构：** 保留原生项目。CI 读取 Secret 生成忽略提交的本机配置；签名流程从 Apple API 获取与新 Bundle ID 对应的描述文件。Apple API 能注册 Bundle ID，但新增 App Store 应用记录须通过 App Store Connect 网页完成。

## 约束与决定
- 仓库必须私有，仓库名使用 GitHub 支持的 `YouTube-News-Player`。
- 组织当前为 GitHub Free，私有仓库不能读取组织级密钥。用户选择仓库级配置；通过临时分支把组织已有凭据用目标仓库公钥加密传递，源主分支不改，明文不下载、不输出。
- YouTube Key 作为仓库 Secret，不进入 Git 历史。
- 新应用 Bundle ID 采用 `com.luolihao.newslive`，应用名 NewsLive；不误用其他 App 的描述文件。
- TestFlight 上传与正式提交审核分开；不因为上传而发布商店版本。TestFlight 不强制尚未发布的隐私/支援网址；正式提交配置检查仍要求两者。
- 用户明确不要求轮询等待 GitHub 出包；进入纯构建等待阶段即可报告实际状态。

## 任务
- [x] 确认组织和现有工作流，创建私有仓库。
- [x] 加密同步 Apple 凭据与本机 YouTube Key 至仓库 Secrets。
- [x] 先写发布配置、Apple 注册/资料管理测试，再实现脚本；16项本地测试通过。
- [x] 配置 macOS CI 和可手动触发的签名上传流程，完成本地回归、密钥检查及独立代码审查。
- [x] 提交推送项目并触发构建、Apple 准备流程；初始源码提交 `016ee25`，发布工作流 `41601779524` 已启动。
- [ ] 必要时在 App Store Connect 新建 NewsLive，回读名称和副标题；记录真实上传状态。

## 网页操作阻塞

Windows Computer Use 在绑定 Chrome 页面时因无法可靠识别当前浏览器 URL 而停止，未执行任何 App Store Connect 网页操作。不能继续使用网页自动化或绕过该限制。若 Apple API 查询不到应用记录，仍需用户在 App Store Connect 网页手动创建一次；工作流不会虚构 App ID 或宣称已经创建。

## Apple API 实际回读

准备任务成功，Bundle ID `com.luolihao.newslive` 已注册，对应 Apple Bundle 资源 ID `976224PM7U`。回读 `record_ready=false`、`app_id=null`，因此没有填写商店名称或副标题，也没有上传 IPA。需要在网页新建 NewsLive，选择该 Bundle ID，SKU `newslive-ios`，主语言 English (U.S.)。当前等待 GitHub macOS 验证构建；按用户要求不继续轮询等包。
