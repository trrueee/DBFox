# R5.4 GitHub 完整外置 Conformance 证据

> 文档类型：质量证据 / 跨平台发布合同
>
> 状态：当前
>
> 最后核验：2026-08-21

## 结论

`dbfox.github` 是普通签名 DLC，而不是 Core 内建域。R5.4 将其真实 source tree 打包后，
通过与通用 `acme.echo` 相同的 lifecycle 与 frozen-sidecar 路径验证：无包时能力缺席、安装
默认禁用、enable 后必须重启、active digest 精确匹配、disable 后必须重启、inactive 后可
卸载，且 DLC-owned SQLite 与历史 ToolAttempt 的 owner/digest 身份保持不变。

只有本 work package 的常规 CI 与 Linux、Windows、macOS `workflow_dispatch` release
contract 全绿后，R5 才允许合并并宣告关闭。

## 复用与设计决策

- 复用 `DlcPackageService`、`ContributionCompiler`、typed operation endpoint、active
  projection 和现有 packaged sidecar restart harness；未增加 GitHub primitive、静态 router、
  product branch 或第二套 E2E runner。
- 保留 R4.3 `acme.echo` 流程，并在同一真实进程、同两次受控重启中追加 `dbfox.github`，
  避免用 mock snapshot 代替 frozen runtime truth。
- fixture builder 只增加可执行 CLI 入口，仍从仓库唯一 `dlcs/dbfox.github` source tree 构建，
  继续使用明确标注的 test-only deterministic key；不引入生产私钥。
- R5.2 历史迁移可能在安装前建立空 `state.sqlite3`，所以“不执行扩展代码”的证明比较
  inspect/trust/install/enable 前后的文件 digest，并同时断言 operation 不可用；不把“文件
  已存在”错误等同于包已执行。
- 未新增依赖、兼容层、映射层、fallback、双写或迁移债务。

## 自动证明

### Python conformance

- 默认产品 snapshot 没有 `dbfox.github` owner、resolver、operation 或 active identity。
- 安装后 registry 为 `desired_enabled=false`，重新 compile 仍无 GitHub capability，且未建立
  package-owned state。
- enable 前的旧 snapshot 保持 absence；restart compile 后只激活签名包的 exact digest，
  并恢复三个 tools、`github.repository`、artifact contract 与六个 operations。
- disable 后旧 snapshot 仍代表 current active truth；restart compile 后贡献全部消失。
- inactive uninstall 删除 executable bytes，保留 `data/dbfox.github/state.sqlite3`。
- 已持久化 `AgentToolInvocation` 继续保存 `owner_id=dbfox.github` 与原 package digest。

### Frozen sidecar release evidence

每个平台产出的 `reports/dlc-packaged-e2e-<host-tuple>.json` 必须同时包含原 R4.3
`packaged_dlc` 与 R5.4 `packaged_github_dlc`。后者固定证明：

- `absent_without_package`
- `install_execution_blocked`
- `install_disabled`
- `enable_restart_active_exact_digest`
- `backend_operation=ok`
- `frontend_contributions=ok`
- `disable_restart_absent`
- `executable_bytes_removed`
- `data_retained`

## 本地证据与限制

- Windows x64：fresh PyInstaller sidecar build 与完整 authenticated smoke 通过；报告 target 为
  `x86_64-pc-windows-msvc`，通用包和 GitHub 包两组 lifecycle 均为 `status=ok`。
- Python package/lifecycle/ToolAttempt retention 与 sidecar contract tests：41 passed。
- ESLint、frontend test typecheck、Python compile/Pyflakes/Mypy 由 PR 常规门禁复核。
- Linux/macOS 只接受 GitHub Actions release-contract artifacts；本地 Windows 结果不能替代
  这两个平台的证据。
