# DBFox Electron 发布验证矩阵

> 文档类型：发布参考
>
> 状态：当前
>
> 最后核验：2026-08-21

门禁配置不等于平台已经通过。每次 work package 必须绑定 commit、workflow run、job、artifact 和
验证摘要；Windows 结果不得外推到 macOS/Linux。

| 自动合同 | Windows 2025 | macOS 14 arm64 | Ubuntu 24.04 |
|---|---:|---:|---:|
| 固定 Python/Node lock 安装 | 必须 | 必须 | 必须 |
| PyInstaller Sidecar + manifest/hash | 必须 | 必须 | 必须 |
| DLC packaged lifecycle smoke | 必须 | 必须 | 必须 |
| React/Vite + Electron Main/Preload | 必须 | 必须 | 必须 |
| Electron installer | NSIS | DMG + ZIP | AppImage |
| Packaged Electron/Preload/Engine smoke | 必须 | 必须 | 必须（xvfb） |
| 未激活 DLC asset 403 | 必须 | 必须 | 必须 |
| 最终 app tree/Sidecar probe/secret scan | 必须 | 必须 | 必须 |
| 正式平台签名 | Authenticode 自动门 | Developer ID/notarization 待正式门 | 系统包管理器策略 |
| 安装/卸载 | 签名候选自动 | 发布候选 | 发布候选 |

## 自动工作流

`ci.yml` 的 `release-platform-contract` 只在 schedule 或 `workflow_dispatch` 运行。它在三平台重建
Sidecar，执行 runtime/DLC smoke，生成 Electron installer，启动 packaged Electron，并上传
`reports/`、最终 manifest 和 `desktop/release-electron/**`。普通 PR 与 release contract 都只安装
Python/Node 依赖，不包含第三语言构建路径。

`windows-signed-release.yml` 是当前唯一正式发布工作流，只允许从 `main` 手工触发。它要求
`WINDOWS_CERTIFICATE_BASE64` 与 `WINDOWS_CERTIFICATE_PASSWORD`，先签 Sidecar并刷新 hash，再由
electron-builder 签 Host/NSIS、生成 `latest.yml` 和未公开 Draft Release。随后验证：

- installer、安装态 Host 与 Sidecar 的 Authenticode signer；
- artifact manifest、Sidecar exact hash/runtime/release contracts；
- `latest.yml` SHA-512 与 app-update publisher policy；
- packaged Electron preload/Engine/asset 403 smoke；
- NSIS 静默首次安装、版本、安装态签名和卸载；
- GitHub artifact attestation。

缺少凭据、签名、metadata 或证据均失败，不生成“临时未签名正式版”。

## Sidecar 与 DLC 合同

生产解释器来自 `.sidecar-python-version`，依赖来自 `requirements-build.lock`。manifest schema 3
绑定解释器/锁/源码/SQLite provenance、target triplet、release contracts、固定 filename 和最终
SHA-256。签名改变二进制后必须显式 refresh，builder 不允许二次修改 Sidecar。

Frozen smoke 必须验证鉴权、Schema、只读查询、Result Artifact、durable run、restart reload，并通过
真实 lifecycle API 驱动签名的 `acme.echo`：tampered 拒绝、安装不执行、disabled、enable/restart
exact digest、backend/frontend contribution、disable/restart 消失，以及 inactive uninstall 保留 data。

## 尚需人工候选证据

正式候选还需保存 OS 安装包 hash、签名/公证、首次启动、sleep/resume、Sidecar crash、端口重占、
Keyring、MySQL/PostgreSQL/SQLite 连接取消、SSH/TLS 路径。macOS 在 Developer ID/notarization 和
Gatekeeper 真实工作流闭合前不能标记正式可发布；Linux 应记录目标发行版依赖和包管理器升级路径。

供应链继续由 lockfile、依赖治理和 CycloneDX 门禁覆盖；不存在无消费者的第三语言流程。
