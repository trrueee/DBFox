# DBFox 桌面发布、恢复与个性化

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-10
>
> 适用范围：桌面外观、窗口恢复、异常退出、签名和自动更新
>
> 当前正式发布范围：Windows x64

本文说明桌面外观偏好、窗口恢复、异常退出检测、代码签名和应用更新如何协作。它不把 CI 配置当作已经取得的证书或发布证据；macOS/Linux 仍需各自的真实签名、安装和运行验证。

## 1. 所有权边界

| 状态 | 唯一事实来源 | 不允许进入 |
|---|---|---|
| 主题、字体、密度、表格与内部面板 | `ThemeProvider` 的版本化 `AppearancePreferences` | 数据库、Agent 上下文、诊断包 |
| 原生窗口位置、尺寸、最大化状态 | 官方 `tauri-plugin-window-state` | React localStorage、自定义坐标 mapper |
| Agent 会话、Run、工具和工件 | SQLite 耐久存储 | 窗口状态或外观导出 |
| 上次是否异常退出 | Rust 的存在性 session marker | SQL、对话正文、Token、凭据 |
| 更新检查、下载、签名验证与安装 | 官方 `tauri-plugin-updater` | WebView 任意 URL 下载、自定义安装器 |
| Windows 发布者身份 | Authenticode 证书与系统证书存储 | 仓库、安装包资源、日志 |

当前界面不存在独立底部面板。外观设置因此保存真实存在的数据源侧栏宽度和 Agent 右侧工件面板宽度，不创建无消费者的“底部面板高度”。若未来引入正式底部面板，应由该组件消费新的规范字段并补迁移测试。

## 2. 外观与工作区

`desktop/src/lib/appearance.ts` 是唯一偏好 schema。它使用封闭枚举和有界数值，拒绝未知字段、任意 CSS 值和版本不匹配的导入文件。导出 JSON 只包含该 schema 中的外观字段，因此结构上不可能包含 Token、API Key、数据源密码、DSN、SQL、会话或日志。

- 密度统一投影到工具栏、按钮和主要间距 token；
- UI、数据、代码分别选择本机字体栈，未安装首选字体时使用 CSS 字体栈自然回退；
- Agent 与 SQL/代码行高独立；
- 数据表控制默认行高、网格线、斑马纹、NULL 呈现和默认主键冻结；
- 高对比度和减少动效同时支持显式选择与系统媒体查询；
- 系统 DPI 由 Windows、Tauri 和 WebView 处理，不使用 CSS `zoom` 二次缩放；
- React 可调面板把用户拖拽结果写回同一偏好文档，不维护第二份 layout localStorage。

## 3. 窗口与异常退出恢复

原生窗口在 `tauri.conf.json` 中以 `visible: false` 创建，官方 Window State 插件在首次显示前恢复几何状态，避免窗口先出现在默认位置再跳动。WebView 没有 Window State 写权限，因为当前无需从 JavaScript 调用插件命令。

Rust Host 启动时在应用数据目录创建 `session-active-v1`。正常关闭、窗口销毁和 Windows 更新安装前都会删除该 marker；下一次启动只根据 marker 是否仍存在报告“上次异常退出”。marker 不保存窗口内容或业务数据。恢复范围如下：

1. 原生窗口几何由 Window State 恢复；
2. 内部面板和外观由 AppearancePreferences 恢复；
3. Agent、工具和工件继续从数据库耐久事实恢复；
4. 不保存或自动重放未确认完成的非幂等操作。

## 4. 自动更新链路

```text
发布通道验收完成后，由产品入口触发检查
  -> Rust 确认编译期公钥存在
  -> 官方 Updater 读取固定 HTTPS latest.json
  -> 默认 semver 比较（不降级）
  -> UI 展示版本、说明和安装确认
  -> 用户确认安装
  -> 官方 Updater 下载
  -> minisign 公钥验证更新包
  -> Rust 停止 Sidecar、清除 session marker、执行 Tauri cleanup
  -> Windows 被动安装并重新启动应用
```

更新端点固定为 GitHub Release 的 `latest.json`，前端不能传 URL、目标平台或签名。Release 构建从官方插件配置 `desktop/src-tauri/tauri.conf.json` 的 `plugins.updater` 读取唯一一份端点与公钥。私钥只允许由 CI 的 `TAURI_SIGNING_PRIVATE_KEY` Secret 提供。官方 Updater 的签名校验不能关闭，失败时不存在旧下载器、HTTP、跳过验证或手工 fallback。

当前产品入口暂不开放自动更新：设置侧栏、命令面板和启动后台任务都不会触发更新检查。Rust/Tauri 更新边界和候选页面代码保留用于发布验收；只有在 GitHub Release 清单、minisign、Windows Authenticode、安装/升级/回滚场景全部取得真实证据后，才能重新加入公开设置导航。开发构建不得用不可操作的占位页面冒充已交付功能。

自动更新指“自动检查、用户确认安装”，不做无人值守的自动下载安装。原因是 DBFox 可能有正在运行的查询、Agent Run 和数据库交互；未经用户确认退出会损害可解释性。若未来需要强制安全更新，必须新增独立 ADR，定义截止时间、运行中任务处理和回滚策略。

## 5. 两类签名不可混用

1. **Tauri updater minisign**：证明更新清单引用的包由 DBFox 更新密钥签发，阻止更新通道投毒。
2. **Windows Authenticode**：证明 MSI/NSIS 的发布者身份，供 SmartScreen、系统属性和企业策略验证。

二者缺一不可。`windows-signed-release.yml` 是仅允许从 `main` 手工触发的 Release environment 工作流，要求四组外部配置：

- Secret：`TAURI_SIGNING_PRIVATE_KEY`；
- 可选有密码的 updater 私钥 Secret：`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`；
- Secrets：`WINDOWS_CERTIFICATE_BASE64`、`WINDOWS_CERTIFICATE_PASSWORD`。

工作流导入 PFX 到临时 Runner 的当前用户证书库，使用 Tauri 官方打包和 `tauri-action`，只创建 **Draft Release**。随后验证 MSI/NSIS Authenticode、Frozen Sidecar、manifest 和 updater `.sig`，并使用 Windows Installer 的静默标准参数验证 MSI 首次安装、从最近已发布 MSI 覆盖升级以及卸载；没有已发布前序版本时，报告会明确标记首次版本的升级场景不适用。NSIS 的交互安装/卸载仍属于人工候选验收。任何凭据缺失都会在构建前失败。

## 6. 发布与回滚

- 普通 CI 和每周跨平台合同不持有发布私钥，也不生成可发布更新；
- 当前正式工作流只覆盖 Windows x64；macOS 签名/公证、Gatekeeper 与 Linux 动态依赖/安装未验证；
- Updater 默认只接受高于当前版本的 semver；回滚应发布新的更高修复版本，不通过客户端允许降级；
- 草稿 Release 验证失败时不得发布，删除草稿和对应候选 tag 后修复源码重新构建；
- 已发布版本出现问题时停止发布清单指向、准备更高补丁版本，并保留旧版本人工下载与证据，不轮换或复用已泄漏私钥。

## 7. 采用与未采用方案

采用官方 Window State、Updater、Tauri bundler、tauri-action、Windows 证书存储和 Authenticode。DBFox 自研部分仅保留产品边界：何时检查、何时征求安装确认、Sidecar 停止、异常退出 marker 和安全 UI 文案。

未采用 Electron 风格自定义更新服务器、自写下载/验签/解压、前端直连任意 URL、双更新通道、坐标 localStorage、CSS 缩放和包含凭据的整份应用设置导出。这些方案要么重复平台能力，要么扩大供应链与隐私边界。

官方依据：

- [Tauri Window State](https://v2.tauri.app/plugin/window-state/)
- [Tauri Updater](https://v2.tauri.app/plugin/updater/)
- [Tauri Windows Code Signing](https://v2.tauri.app/distribute/sign/windows/)
- [Tauri GitHub Pipelines](https://v2.tauri.app/distribute/pipelines/github/)
