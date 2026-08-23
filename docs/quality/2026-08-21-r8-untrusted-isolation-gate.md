# R8A Untrusted Isolation Gate 证据

> 文档类型：安全审计与架构 Gate 证据
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 基线：`main@2625ac366113c031149fd226075932ddca0739b2`

## 结论

R8A 已完成，结论是 **NO-GO**。R8B 不启动，DBFox 产品继续只执行用户显式信任的
publisher 所签名代码。签名证明身份与 bytes，用户信任决定是否授予应用级代码权限；
两者都不被描述为 sandbox。

## 仓库反证

| Gate | 当前证据 | 结果 |
|---|---|---|
| Backend filesystem/env/secrets | DLC backend 由 `load_dlc_backend` 导入 Engine，`register_func(host)` 同进程调用；Python 标准库与进程环境可达 | FAIL |
| Backend network/subprocess | manifest capability 只检查注册对象；无 syscall、socket 或 child-process 强制边界 | FAIL |
| Backend crash/resources | 动态 DLC tools 强制 `in_process`；import/register 的 hang、`os._exit` 与内存耗尽会影响 Engine | FAIL |
| Existing worker reuse | worker transport 有 frame/output/deadline/process-tree kill，但 `Popen` 未提供最小 env 或 OS sandbox policy | FAIL |
| Frontend DOM/bridge/token | DLC ESM 在产品 Renderer 原生 import；同 realm 可访问 DOM 与 `window.dbfoxDesktop.engine.getConfig()` 返回的 token | FAIL |
| Frontend network/navigation/crash | CSP/导航限制保护整个产品 Renderer，却未把 DLC 放到独立 origin/session/process；DLC 可阻塞或终止 Renderer | FAIL |
| Asset containment | `dlc-asset:` 只向 active exact digest 提供 bounded、realpath-contained bytes | PASS，但不是代码隔离 |
| Publisher gate | 未信任的真实签名返回 `TRUST_REQUIRED`，v2 unsigned 不能用 developer mode 绕过，restart reverify fail-closed | PASS，且为当前唯一授权模型 |

## 跨平台调查结论

- Windows 需要组合 AppContainer/新 sandbox launcher 与 Job Objects，并严格构造 env、handle、
  filesystem 和 network policy；现有 `subprocess.Popen` 不具备这些保证。
- macOS 真正 privilege separation 需要独立 XPC service 与 App Sandbox entitlements/signing；
  普通 child inheritance 不是独立最小权限 sandbox。当前 Electron/PyInstaller 包无此 service。
- Linux 需要组合 Landlock、seccomp 与 cgroup/namespace 或明确依赖外部容器。seccomp 官方明确
  不是完整 sandbox，Landlock ABI/内核启用状态与 cgroup delegation 不能假定存在。
- Electron 可为独立不可信页面提供 sandboxed Renderer 基础，但现有 React callback API 必须
  同 realm 运行。安全方案必须另建 serializable remote-UI contract，不能把 iframe 当适配层。

因此三平台没有共同闭合，且 macOS/Frontend 需要新的 native service 与平台 primitive，违反
当前 TypeScript + Python 两语言目标和“R8A 不先实现 R8B”的 Gate 规则。

## 本次变更

- 新增正式决策 `docs/architecture/r8-untrusted-isolation-gate.md`，冻结 NO-GO、反例和重开条件。
- 更新 Runtime DLC 主规范与路线图：R8A CLOSED/NO-GO，R8B 未授权。
- 同步当前系统/后端导航中的 Electron Main/Renderer 术语，移除仍把已删除 Rust Host
  写成当前生命周期权威的陈旧表述；历史证据与已标记 superseded 的 ADR 保持原样。
- 收紧 loader/compiler/worker/frontend 注释，明确 namespace、subprocess、transactional staging、
  Electron Renderer sandbox 各自不等于 hostile-code containment。
- 不新增依赖、native helper、compatibility layer、双写、权限 mapper、fallback 或第二运行时契约。

## 现有自动门禁

- `verification/tests/system/test_dlc_package_foundation.py::test_authentic_untrusted_publisher_requires_explicit_trust`
- `verification/tests/system/test_dlc_publisher_trust.py::test_v2_unsigned_package_cannot_use_developer_mode_bypass`
- publisher trust persistence/corruption/restart reverify tests
- Electron security, native sender validation, DLC asset containment, CSP and packaged-host tests

这些门禁证明 trusted path fail-closed；它们不被复用或改名为 untrusted sandbox 测试。

## 本地验证

- package foundation、publisher trust、backend host：77 passed。
- engineering/document governance 与定向 trust/backend 合集：53 passed。
- Frontend DLC Host + CSP：19 passed。
- Electron Main/preload/native/DLC protocol：28 passed。
- Pyflakes 全仓、Mypy 304 个 Python source files、TypeScript test typecheck、ESLint：通过；
  ESLint 仅保留既有 24 条 Fast Refresh warning，无 error。
- `git diff --check`：通过。
