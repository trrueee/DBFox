# DBFox Electron 桌面发布、恢复与更新

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-28
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

Main 在创建窗口、启动 Engine 或执行 migration 前调用 Electron 官方
`requestSingleInstanceLock()`。primary instance 拥有窗口和 Sidecar；secondary instance 只触发
`second-instance`，由 primary 恢复、显示并聚焦已有窗口，然后立即退出。第二实例不得启动第二个
Renderer server、Sidecar 或 migration。

内部布局由已有 AppearancePreferences 恢复，Agent/工件由 SQLite 恢复。未确认完成的非幂等操作
不会因桌面恢复而自动重放。

## 开发启动与退出生命周期

`npm run electron:dev` 的启动器只编排真实进程边界，不复制 EngineSupervisor：

```text
构建 Electron Main/Preload + 签名开发 System DLC
  -> spawn Electron with Node IPC
  -> Electron 取得官方 single-instance lock
  -> primary: IPC 回报 ownership
       -> 启动器使用 Vite createServer() 取得 strict 5173 ownership
       -> IPC renderer-ready
       -> Main 创建窗口并启动 EngineSupervisor
  -> secondary: 旧窗口被聚焦，启动器不创建 Vite，直接退出
```

Vite 由启动器通过官方 JavaScript API 直接持有，不再 spawn 一个独立 CLI 后再用 HTTP 探测猜测
所有权。因此旧 5173 server、无关 server 与当前 launcher 不会被误认成“本次 Renderer 已就绪”。

所有正常退出入口使用同一顺序：

```text
窗口关闭 / Ctrl+C / dev parent IPC disconnect / 安装更新
  -> app.quit()
  -> before-quit barrier
  -> EngineSupervisor.stop()
  -> 等待 Engine process tree + stdio close
  -> 清除正常退出 marker
  -> Electron exit
  -> Vite.close()
```

开发启动器发送 graceful shutdown IPC 并等待 8 秒；只有 Electron 无法结算退出时才使用 Windows
`taskkill /T /F` 或 POSIX process-group signal 作为最后收尾。父启动器异常消失时，Electron 监听 IPC
disconnect 并走相同 `app.quit()` 路径。Windows 系统关机/用户注销可能不发 `before-quit`，此时保留
crash marker 是正确的不完整退出事实，下一次启动按恢复流程处理。

## System DLC 包生命周期

生产 System DLC 继续使用发布 manifest 中的 exact `{id, version, digest}` pin；同一 SemVer 出现不同
digest 必须 fail closed，不能以开发便利放宽供应链不变量。

源码开发 bundle 使用确定性的：

```text
<release-version>-dev.<12 hex source fingerprint>
```

指纹覆盖 manifest template 与全部 backend/frontend payload。相同源码和开发签名 key 生成相同版本及
package digest；源码改变就形成新的不可变 prerelease package。Engine 在 Runtime snapshot 激活前选择
新 package，并只移除旧的 `-dev.<fingerprint>` package registry 引用和 content-addressed executable
bytes。`dlcs/data/<dlc-id>`、凭据、Score、Connection、Workspace binding 与用户 enable/disable 状态
均保留。正式 release package 和 rollback history 不由开发清理处理。

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

`electron-builder.yml` 的 System DLC 资源白名单必须与 bundle manifest 同步，当前明确包含
`dbfox.data`、`dbfox.music`、`dbfox.workspace` 三个签名包；工程合同会阻止 manifest 引用已构建但
未进入安装包的 archive。`npm run test:electron-packaged` 启动最终 unpacked Electron 和真实 Frozen
Sidecar，要求 Extension Host `1.0.0` 加载三者的 frontend entrypoint 与 stylesheet：活动
`dlc-asset://` 请求必须全部返回 200，未知 digest 必须返回 403。开发 Host 使用同一 smoke 证明，
不另建 renderer 或 DLC 假实现。

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
electron-updater；开发 Renderer 复用 Vite 官方 `createServer/listen/close`，父子生命周期复用 Node
`child_process` IPC 与 `close` 事件。仅自研产品策略、Sidecar shutdown 排序、异常退出 marker 和窄化
IPC。未采用
Electron core autoUpdater，因为它不覆盖 Linux 且不能生成当前三平台 installer；未采用 Forge，
因为当前仍需额外组合 makers/updater 才能得到同一跨平台合同；未采用自写下载器、更新服务器、
Renderer Node 权限、lockfile/process-name 探测或 IPC-to-Python 代理。

主要新增依赖风险是 builder/updater 供应链和平台签名差异，缓解方式为 package-lock、npm audit、
固定 Actions、三平台打包 smoke 和正式 signer 验证。没有新增双写、业务 mapper 或第二份 runtime truth。

官方依据：

- [Electron Application Packaging](https://www.electronjs.org/docs/latest/tutorial/application-distribution)
- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [Electron app lifecycle and single-instance lock](https://www.electronjs.org/docs/latest/api/app)
- [Node.js child process lifecycle](https://nodejs.org/api/child_process.html)
- [Vite JavaScript API](https://vite.dev/guide/api-javascript.html)
- [electron-builder](https://www.electron.build/)
- [electron-updater](https://www.electron.build/auto-update.html)
- [Windows Code Signing](https://www.electron.build/code-signing-win.html)
- [macOS Code Signing](https://www.electron.build/code-signing-mac.html)
