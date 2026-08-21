# R7.0 Electron Host Cutover 决策与迁移证据

> 文档类型：平台决策 / 迁移门禁
>
> 状态：已接受
>
> 最后核验：2026-08-21

## 决定

DBFox 的目标桌面架构收敛为 **Electron + React/TypeScript + Python Engine**。迁移只替换
Desktop Host，不重写 FastAPI、Agent、SQL、数据库连接、SQLite 持久化或 DLC Engine
contracts。Renderer 继续通过 HTTP/SSE 直连 Python；Electron IPC 只承载窗口、文件、Engine
lifecycle、更新、诊断和其他真实 OS 边界，不代理业务 API。

Electron 现在是唯一生产 Host。旧 Host 源码、依赖、工具链、CI job 和临时 runtime selector 已在
R7.0d 原子删除；一次进程只有一个 supervisor、一个 token/generation 和一份 active runtime truth。

## 调研与复用

- CodeGraph 和源码审计确认 Rust 边界为 11 个文件、约 3355 行，集中承担 sidecar supervisor、
  token/health handshake、crash recovery、DLC asset protocol、文件能力、诊断、更新和窗口。
- React 对 Tauri 的直接依赖集中在少量 desktop integration modules，Python HTTP/SSE 和 DLC
  backend contracts 不依赖 Rust，适合替换 Host 而非重写 Engine。
- 采用 Electron 官方 `BrowserWindow`、sandbox、`contextIsolation`、`contextBridge`、`ipcMain`
  和 custom protocol primitives。官方安全指南要求 renderer sandbox、禁用 Node integration、
  限制导航/新窗口、逐消息暴露 preload API并验证 IPC sender；这些作为硬门而非建议。
- Electron `utilityProcess` 仍提供 Node 环境，不等同 R8 backend sandbox，因此本迁移不声称解决
  不可信 DLC 隔离。R8A 将在 cutover 后单独评估 OS containment 与 adversarial escape tests。
- 复用现有 Vite/TypeScript 构建，不引入 electron-vite、Forge、业务 IPC mapper 或第二套 Engine
  协议。Electron 43.4.1 的 Node 要求与仓库 Node 22 contract 匹配。
- R7.0b 复用 Electron 官方 `dialog`、`shell`、`protocol.handle` 和 Node `fs`/`dns`/`https`，没有
  自建文件 picker、URL parser 或网络栈。诊断 ZIP 采用现有生态中纯 TypeScript、无 native addon、MIT
  的 `fflate 0.8.2`；锁文件固定解析结果且 npm 官方 registry audit 为 0 vulnerabilities。
- 未采用 Renderer Node 权限、通用 IPC、Renderer 直接读包目录、Electron IPC 代理 Python API，或把
  `iframe`/`utilityProcess` 宣称为 sandbox。`desktopHost.ts` 现在只是 Electron preload 的窄化边界，
  不再选择旧 Host，也没有双写、mapper 或第二份 active runtime truth。
- R7.0c 调研 Electron 官方 packaging/autoUpdater、Forge 与 electron-builder。Electron core 明确要求
  第三方 packaging，内建 autoUpdater 只覆盖 Windows/macOS；Forge 仍需组合 makers 与更新方案。
  因此固定 `electron-builder 26.15.3` + `electron-updater 6.8.9`，直接复用 NSIS、DMG/ZIP、AppImage、
  extraResources、ASAR/fuses、代码签名和 `latest*.yml`，不自写下载/验签/installer。
- Linux 明确使用系统包管理器，不以 AppImage updater 冒充三平台同质签名边界；Windows/macOS 只在
  packaged build 启用代码签名通道。Renderer 无权提供 feed/URL，禁止 prerelease、downgrade、web
  installer、自动下载和退出时自动安装。

官方依据：

- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [Context Isolation](https://www.electronjs.org/docs/latest/tutorial/context-isolation)
- [Process Sandboxing](https://www.electronjs.org/docs/latest/tutorial/sandbox)
- [IPC](https://www.electronjs.org/docs/latest/tutorial/ipc)
- [Custom Protocol](https://www.electronjs.org/docs/latest/api/protocol/)
- [Application Packaging](https://www.electronjs.org/docs/latest/tutorial/application-distribution)
- [electron-builder](https://www.electron.build/)
- [electron-updater](https://www.electron.build/auto-update.html)

## 分阶段门禁

1. **R7.0a — Engine Host**：新增纯 TypeScript `EngineSupervisor`、Node child-process adapter、
   sandboxed preload 和窄化 engine IPC；真实 Python smoke 证明启动、鉴权、restart token/generation
   轮换与 shutdown。
2. **R7.0b — Native/DLC Boundary**：迁文件/目录、外链、窗口、诊断、crash marker 与严格
   `dlc-asset` protocol；Renderer 不获得 Node、通用 IPC 或任意路径能力。
3. **R7.0c — Package/Update/Release**：选择并固定 Electron packaging/updater，建立 Windows、
   macOS、Linux 安装态 release contracts；Frozen Python Sidecar 格式不在此阶段重写。
4. **R7.0d — Atomic Removal**：Electron 成为唯一发布 Host 后删除 `src-tauri`、Cargo/Rust 工具链、
   Tauri npm dependencies、Rust CI 与 release scripts，并移除短期 host selector。

## R7.0a 安全和状态合同

- Main 是 Engine process handle、token、generation 与 crash-loop 状态的唯一权威；Renderer 只读
  config/status 并请求显式 restart。
- 32-byte 随机 token 每次启动轮换；握手必须匹配 protocol、server identity 和 required
  capabilities，health 必须在 64 KiB 上限内通过本地 token 认证后才发布 config。
- 意外退出立即撤销旧 config，最多在 60 秒内恢复三次；第四次 fail-closed。手动 restart 停止旧
  process tree、清空 crash budget 并等待新一代 Ready。
- BrowserWindow 强制 `sandbox: true`、`contextIsolation: true`、`nodeIntegration: false`，拒绝新窗口
  和非 renderer origin 导航；preload 不暴露 `ipcRenderer` 或通用 `send/invoke`。

## R7.0b 原生与 DLC 边界合同

- 文件夹选择通过 Electron 官方 `dialog` 完成；Main 持有有界、严格 schema、原子替换的授权根记录。
  每次列目录或读文件都重新 `realpath` 并校验 canonical containment，目录最多返回 600 项，文本预览
  最多 1 MiB，DLC picker 只接受实际存在的 `.dbfox-dlc` 单文件。
- `dlc-asset` 使用 Electron 官方 `protocol.handle`，且只信任当前 Python runtime activation
  projection 中带 frontend entrypoint 的 exact digest。Engine 状态离开 Ready 时立即清空 authority；投影
  超过 64 KiB、schema/digest 非法、路径逃逸、symlink 逃逸或资源超过 20 MiB 均 fail-closed。
- 外部图片仍执行 HTTPS/443、无凭据、DNS 后 public-IP pin、手动有界 redirect、媒体类型与 magic
  signature 双校验、20 MiB/20 秒/最多两个并发下载及原子落盘；Renderer 不取得网络或文件句柄。
- diagnostics 只接收两份有界快照，递归执行敏感键和文本凭据脱敏，并仅收集有界的 DBFox Host/
  Sidecar regular logs。ZIP 采用锁定的 `fflate 0.8.2`；没有引入第二份诊断模型或业务 IPC。
- 窗口、文件、外链、诊断、crash marker 与 lifecycle 均通过固定 preload 方法暴露。Main 对每次 IPC
  同时验证 renderer origin、sender WebContents 和主窗口身份；真实 Electron smoke 额外证明未知/未激活
  digest 的 `dlc-asset` 请求返回 403。

## R7.0d 原子删除结果

- `desktopHost.ts` 直接要求 Electron preload bridge，缺失时 fail-closed；不存在旧 Host fallback。
- 删除旧 Host 源码、Cargo lock/toolchain、npm 依赖、构建脚本、CI job、Dependabot 生态和 release 配置。
- 平台图标迁入 `desktop/build-resources/`，由 Electron packaging 单一消费。
- Engine 只接受 `dbfox-app://localhost` 桌面 origin；旧 origins 不保留兼容路径。
- 生产项目收敛为 TypeScript/Electron + Python，不新增协议转换、双重 SSOT 或迁移兼容层。

## R7.0c 打包、更新与发布合同

- packaged Renderer 由 `dbfox-app://localhost` 提供，协议只允许固定 host、无 credentials/query/hash、
  规范化的 containment、10 MiB 资源上限、明确 MIME、CSP、COOP、nosniff 与 immutable asset cache；
  CSP 不含 `unsafe-eval`，业务网络仍只开放本地 Engine。
- staging app 不声明运行依赖；Main 将 updater 完整 bundle，最终 ASAR 只包含 dist、Main/Preload 与
  package metadata。Electron fuses 禁止 RunAsNode、NODE_OPTIONS 和 inspect，启用 cookie encryption、
  ASAR integrity 和 only-load-from-ASAR。
- Sidecar 固定为 `resources/sidecar/dbfox-engine[.exe]`。Main 每次 launch 前校验 manifest schema、
  exact filename 和 SHA-256。`build_sidecar.py` 使用显式 OS/arch 映射，不再依赖 `rustc`。
- `dbfox-app://localhost` 是冻结 Engine 的唯一正式桌面 origin，不通过代理或 null origin 放宽。
  未知 host、attacker origin 与未激活 DLC digest 继续 403。
- 更新检查保留 exact pending result，下载成功后才停止 Sidecar；下载/验签失败保持当前进程可用。
  Windows 使用 publisher Authenticode，macOS 要求 Developer ID/notarization，Linux 明确 system-managed。
- 平台 signer 会改变 Sidecar 字节。正式流程先签 Sidecar、再调用受限 manifest refresh 重绑 hash，
  builder 不得二次修改它；随后签 Host/installer。Windows 正式工作流验证同一证书、metadata、packaged
  smoke、NSIS 静默安装/卸载与 provenance，且只创建 Draft Release。
- CI `release-platform-contract` 和普通 PR 门禁均已收敛为 Python + Node + Electron。
