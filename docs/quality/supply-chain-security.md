# 供应链安全与锁文件审计

> 文档类型：安全与质量参考
>
> 状态：当前
>
> 最后核验：2026-08-15
>
> 适用范围：Python、npm、Rust 锁文件与持续集成安全审计

`main`、每个 Pull Request 和每周一 03:17 UTC 的计划任务都会执行
`.github/workflows/ci.yml` 的 `Locked dependency security audit`。该任务只读取提交到
仓库的锁文件；不执行第三方 npm 生命周期脚本，也不会重新解析项目依赖树。

## 门禁范围

| 生态 | 审计输入 | 工具与失败策略 |
| --- | --- | --- |
| Python | `requirements.lock`、`requirements-dev.lock`、`requirements-build.lock` | 下载并 SHA-256 校验 OSV Scanner `v2.3.8`，以 `--no-resolve --data-source=native` 扫描三个已哈希锁定的 requirements 文件；发现已知漏洞即失败。 |
| npm | `desktop/package-lock.json` | `npm audit --package-lock-only --ignore-scripts --audit-level=high`；仅高危或严重漏洞阻断，避免开发工具的低风险通报阻塞交付。 |
| Rust | `desktop/src-tauri/Cargo.lock` | 下载并 SHA-256 校验 RustSec `cargo-audit v0.22.2`，审计已提交的锁文件；已知漏洞阻断，未维护状态和上游 GTK3 技术债会在日志中保留为告警，而不是伪装成漏洞失败。 |

所有下载都使用 HTTPS、固定版本、完整 SHA-256 校验、有限重试与显式超时。CI 的
`GITHUB_TOKEN` 仅有 `contents: read`，且 checkout 不保留凭据。

## 锁文件完整性契约

`engine/tests/test_engineering_contracts.py` 会在离线测试中验证：

- Python lock 中每个固定包条目都带 SHA-256 hash；
- npm lock 使用 lockfile v3，所有第三方包来自 npm 官方 registry 且带 SHA-512 integrity；
- Cargo lock 使用 v4，所有非工作区 crate 来自 crates.io 且带 checksum；
- CI 中的审计器版本、下载 hash、超时和锁文件路径没有被移除。

这层契约不替代在线漏洞数据库，但能阻止无锁、无 hash、Git/本地依赖或未校验下载在
审计之前悄悄进入构建。

## 本地复核

先执行与 CI 相同的锁文件和前端审计：

```powershell
python -m pytest engine/tests/test_engineering_contracts.py -q

Set-Location desktop
npm audit --package-lock-only --ignore-scripts --audit-level=high --registry=https://registry.npmjs.org
```

在 Linux 或对应平台下载并校验 CI 指定的二进制后，按 CI 中的参数运行 OSV Scanner 和
`cargo-audit`。不要使用 `npm audit fix --force`、未校验的 `curl | sh`，或通过
`--ignore`/`--deny` 配置隐藏告警。若必须临时接受一个不可修复的告警，应在单独的安全
决策记录中说明影响范围、到期时间和移除计划，而不是将它静默加入全局忽略列表。

前端依赖事实以 `desktop/package.json` 和 `desktop/package-lock.json` 为准。当前项目不再
依赖 Monaco，也没有为已删除依赖保留全局 npm override。新增或重新引入编辑器、HTML
渲染器等高风险 UI 依赖时，必须先评估其传递依赖、许可证和浏览器攻击面，再运行完整
前端回归、锁文件合同测试和在线 `npm audit`；不得为绕过审计增加无到期条件的 override。

## 作者身份与正式产物来源

MIT License 允许复用和商业使用，因此供应链合同不把“禁止复制”作为目标。项目通过
四层可验证记录区分规范来源和第三方副本：

1. 规范仓库的公开提交图、Pull Request 和 Release 记录保留开发历史；
2. 维护者使用 GitHub 已登记的 SSH、GPG 或 S/MIME 密钥签署后续提交；
3. Windows 发布工作流只接受 `main` 上经 GitHub 验证的源提交，并继续校验
   Authenticode 与 Tauri updater 签名；
4. 工作流使用 GitHub 官方 `actions/attest` 为 MSI、NSIS 和 updater 签名文件生成
   构建来源证明。

用户可以使用 GitHub CLI 验证本地下载文件：

```powershell
gh attestation verify .\DBFox_1.0.3_x64_en-US.msi --repo trrueee/DBFox
```

验证成功只证明该文件由规范仓库的已记录工作流构建，不能替代 Windows 代码签名、
安装态验收或漏洞扫描。旧提交不会通过重写历史补签；启用签名之前的原创时间线继续由
既有公开历史证明。作者和正式来源说明见 [`../../AUTHORS.md`](../../AUTHORS.md)。

## 当前残余风险

Tauri 的 Linux WebKit/GTK3 传递依赖仍会被 RustSec 标记为“未维护”或存在上游
soundness 告警；目前没有与当前 Tauri 2.x 兼容的无破坏性上游替代项。该告警不被忽略，
会显示在审计日志中。未来应优先跟随 Tauri/Wry 对 GTK4 或已维护后端的上游迁移，再评估
是否把对应告警提升为阻断条件。
