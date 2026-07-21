# 供应链安全与锁文件审计

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

当前 `monaco-editor 0.55.1` 把 `dompurify` 精确固定在存在已知 XSS 公告的旧版本，
而上游稳定版尚未发布可用的 Monaco 修复。`desktop/package.json` 因此以 npm override
固定 `dompurify 3.4.12`，并由工程契约测试确认 lockfile 与该 override 一致。升级 Monaco
时必须重新运行完整的前端测试和 `npm audit`，再决定是否可以移除 override。

## 当前残余风险

Tauri 的 Linux WebKit/GTK3 传递依赖仍会被 RustSec 标记为“未维护”或存在上游
soundness 告警；目前没有与当前 Tauri 2.x 兼容的无破坏性上游替代项。该告警不被忽略，
会显示在审计日志中。未来应优先跟随 Tauri/Wry 对 GTK4 或已维护后端的上游迁移，再评估
是否把对应告警提升为阻断条件。
