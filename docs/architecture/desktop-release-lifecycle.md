# DBFox Electron 桌面发布、恢复与更新

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 当前正式发布范围：Windows x64；macOS/Linux 为跨平台 release-contract

## 所有权边界

| 状态或能力 | 唯一事实来源 | 禁止路径 |
|---|---|---|
| 主题、字体、密度和内部面板 | Renderer `AppearancePreferences` | Engine、诊断包 |
| 原生窗口和上次异常退出 | Electron Main / session marker | React 业务状态、SQL、Token |
| Agent、Run、工具和工件 | Python/SQLite | Electron IPC |
| Engine token、generation、process handle | Electron Main `EngineSupervisor` | Renderer localStorage、双 supervisor |
| 更新检查、下载和安装 | Main 中锁定的 `electron-updater` | Renderer URL、任意 feed、Python 代理 |
| Windows 发布者身份 | Authenticode 与系统证书链 | 仓库、日志、应用 metadata 参数 |

Renderer 继续通过 HTTP/SSE 直连 Python。Electron IPC 只覆盖窗口、文件、诊断、更新、
Engine lifecycle 和其他真实 OS 能力，不成为新的业务 API。

## 窗口与异常退出

`BrowserWindow` 默认隐藏，加载完成后再显示；`sandbox: true`、`contextIsolation: true`、
`nodeIntegration: false` 为硬门。Main 在 userData 下创建 `session-active-v1`，正常退出或更新安装前
删除。marker 只表达上次是否正常退出，不包含窗口内容、SQL、会话、Token 或凭据。

内部布局由已有 AppearancePreferences 恢复，Agent/工件由 SQLite 恢复。未确认完成的非幂等操作
不会因桌面恢复而自动重放。

## 打包合同

`electron-builder 26.15.3` 负责 Windows NSIS、macOS DMG/ZIP 和 Linux AppImage，Electron 固定为
43.4.1。构建先生成 React/Vite 与完全 bundle 的 Main/Preload，再复制到无依赖的 `electron-app`
staging；最终 ASAR 不包含仓库 `node_modules`、源码或开发配置。官方 Electron fuses 禁止 RunAsNode、
`NODE_OPTIONS` 和 CLI inspect，启用 ASAR integrity 并只从 ASAR 加载应用。

Frozen Sidecar 固定安装为 `resources/sidecar/dbfox-engine[.exe]`。Main 每次启动前校验 schema 3
artifact manifest、精确文件名和 SHA-256。`build_sidecar.py` 使用 Python `platform` 显式映射目标，
不再调用 Rust。平台代码签名会改变可执行文件字节，因此正式发布必须遵循：

```text
构建并 probe Sidecar
  -> 使用 OS 官方 signer 签 Sidecar
  -> --refresh-artifact-manifest 重绑最终 SHA-256
  -> builder 复制但不二次修改 Sidecar
  -> 签名并封装 Electron App/Installer
```

Windows 流程已经自动执行该顺序。未来 macOS 正式发布必须先以 Developer ID 签 Sidecar并刷新
manifest，再由 builder 签整个 App、notarize DMG/ZIP；缺任一步都不能发布。

## 应用更新

`electron-updater 6.8.9` 只在 packaged Windows/macOS 构建中启用，Linux 明确交给系统包管理器或
发行包。更新只由用户手动触发，不做后台自动下载：

```text
用户检查
  -> Main 使用编译进应用的 GitHub provider
  -> 只接受 stable 且高于当前版本
  -> UI 展示版本与说明
  -> 用户确认
  -> updater 下载并校验 metadata SHA-512
  -> Windows 验证固定 publisher Authenticode / macOS 验证签名身份
  -> Main 停止 Sidecar、清 crash marker
  -> quitAndInstall
```

`autoDownload`、`autoInstallOnAppQuit`、prerelease、downgrade 与 web installer 均关闭。Renderer
不能提供 feed、URL、版本或文件路径；下载/验签失败时不会停止当前 Engine。只有下载成功后才进入
受控 shutdown，若安装调用同步失败则重启 Engine。

Windows `latest.yml` 的 SHA-512 负责下载完整性，Authenticode publisher 负责发布者身份，GitHub
Actions provenance 负责构建来源；三者互不替代。正式工作流只从 `main` 手工触发，要求 PFX，创建
未公开 Draft Release，并验证最终 NSIS、unpacked Host、Sidecar 的同一证书、manifest/hash、更新
metadata、packaged Host smoke、静默首次安装和卸载。缺少凭据直接失败。

## 发布与回滚

- 普通三平台 contract 不持有签名私钥，不得把其 unsigned artifact 当作正式发行物；
- Windows 当前是唯一正式自动签名发布；macOS 要等 Developer ID/notarization 工作流闭合；
- Linux 不伪造应用内代码签名更新，使用系统包管理器或明确下载的新发行包；
- 客户端不允许降级。回滚以更高补丁版本发布修复，不静默替换已检查的 artifact；
- 草稿验证失败时保留证据、删除失败候选后从源码重新构建，不能修改已签名 artifact 补洞。

## 复用决策

采用 Electron 官方 BrowserWindow/protocol/fuses、安全指南，采用成熟的 electron-builder 与
electron-updater；仅自研产品策略、Sidecar shutdown 排序、异常退出 marker 和窄化 IPC。未采用
Electron core autoUpdater，因为它不覆盖 Linux 且不能生成当前三平台 installer；未采用 Forge，
因为当前仍需额外组合 makers/updater 才能得到同一跨平台合同；未采用自写下载器、更新服务器、
Renderer Node 权限或 IPC-to-Python 代理。

主要新增依赖风险是 builder/updater 供应链和平台签名差异，缓解方式为 package-lock、npm audit、
固定 Actions、三平台打包 smoke 和正式 signer 验证。没有新增双写、业务 mapper 或第二份 runtime truth。

官方依据：

- [Electron Application Packaging](https://www.electronjs.org/docs/latest/tutorial/application-distribution)
- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [electron-builder](https://www.electron.build/)
- [electron-updater](https://www.electron.build/auto-update.html)
- [Windows Code Signing](https://www.electron.build/code-signing-win.html)
- [macOS Code Signing](https://www.electron.build/code-signing-mac.html)
