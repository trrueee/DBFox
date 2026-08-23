# 供应链安全与锁文件审计

> 文档类型：安全与质量参考
>
> 状态：当前
>
> 最后核验：2026-08-22
>
> 适用范围：Python、npm 锁文件与持续集成安全审计

`main`、每个 Pull Request 和每周一 03:17 UTC 的计划任务都会执行
`.github/workflows/ci.yml` 的 `Locked dependency security audit`。该任务只读取提交到
仓库的锁文件；不执行第三方 npm 生命周期脚本，也不会重新解析项目依赖树。

## 门禁范围

| 生态 | 审计输入 | 工具与失败策略 |
| --- | --- | --- |
| Python | `requirements.lock`、`requirements-dev.lock`、`requirements-build.lock` | 下载并 SHA-256 校验 OSV Scanner `v2.3.8`，以 `--no-resolve --data-source=native` 扫描三个已哈希锁定的 requirements 文件；发现已知漏洞即失败。仅允许 `osv-scanner.toml` 中带理由和到期时间的已审查例外。 |
| npm | `desktop/package-lock.json` | `npm audit --package-lock-only --ignore-scripts --audit-level=high`；仅高危或严重漏洞阻断，避免开发工具的低风险通报阻塞交付。 |

所有下载都使用 HTTPS、固定版本、完整 SHA-256 校验、有限重试与显式超时。CI 的
`GITHUB_TOKEN` 仅有 `contents: read`，且 checkout 不保留凭据。

## 锁文件完整性契约

`engine/tests/test_engineering_contracts.py` 会在离线测试中验证：

- Python lock 中每个固定包条目都带 SHA-256 hash；
- npm lock 使用 lockfile v3，所有第三方包来自 npm 官方 registry 且带 SHA-512 integrity；
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

在 Linux 或对应平台下载并校验 CI 指定的二进制后，按 CI 中的参数运行 OSV Scanner。
不要使用 `npm audit fix --force`、未校验的 `curl | sh`，或无理由、无
期限的全局忽略。若必须临时接受一个不可修复的告警，必须在根目录
`osv-scanner.toml` 中逐项记录公告 ID、影响判断、到期时间和上游移除条件；CI 显式加载
该配置，过期例外重新成为阻断项。

## 当前 Python 漏洞例外

`PYSEC-2026-2858` / `GHSA-r374-rxx8-8654` 影响 Paramiko 4.0.0 及以前版本，公告评级
为低危，且截至 2026-08-15 没有已发布的修复版本。DBFox 只作为客户端连接用户明确
配置的数据库 SSH 跳板，不提供 SSH 服务端；这会降低暴露面，但并未从实现上删除
Paramiko 的 SHA-1 代码路径，因此仍按残余风险接受至 2026-11-15。例外只针对该公告，
不忽略 Paramiko 包的其他漏洞。上游发布包含 `paramiko/paramiko@a448945` 的版本后，
必须删除例外、升级约束并重新生成三份锁文件。

`GHSA-g6cj-pr64-35w5` 影响 `cryptography` 44.0.0 至 49.x，官方修复版为 50.0.0。
DBFox 不直接使用该库，而是由 Paramiko 传递引入，因此通过标准 `constraints.txt` 将三套
依赖解析共同限制到 `cryptography>=50.0.0,<51.0.0`，避免为了安全版本约束重新制造一项
虚假的直接运行时依赖。

前端依赖事实以 `desktop/package.json` 和 `desktop/package-lock.json` 为准，并使用
`packageManager: npm@10.9.3` 与 CI 的 Node 22.18.0 工具链保持一致。`@emnapi/core` 和
`@emnapi/runtime` 是跨平台 Vite/Rolldown WASM 构建路径声明的必需 peer；将它们列为
开发依赖，是为了让 Windows 生成的 lockfile 也完整描述 Linux Runner 所需的依赖图，
它们不是桌面应用运行时能力。

`@hey-api/json-schema-ref-parser@1.4.4` 把 `js-yaml` 固定在受
`GHSA-52cp-r559-cp3m` 和 `GHSA-5p4m-2wfm-xmqj` 影响的 4.2.0，因此仅在该真实上游边界
使用 npm 官方 `overrides` 机制提升到修复版 4.3.1。`brace-expansion` 则通过正常的
传递依赖更新提升到修复版 5.0.9，不建立 override。上游解除精确版本限制后，应删除
`js-yaml` override 并重新生成锁文件。当前项目不再依赖 Monaco，也不为已删除依赖保留
全局 override。新增或重新引入编辑器、HTML 渲染器等高风险 UI 依赖时，必须先评估其
传递依赖、许可证和浏览器攻击面，再运行完整前端回归、锁文件合同测试和在线
`npm audit`；不得为绕过审计增加无明确上游退出条件的 override。

## 作者身份与正式产物来源

MIT License 允许复用和商业使用，因此供应链合同不把“禁止复制”作为目标。项目通过
四层可验证记录区分规范来源和第三方副本：

1. 规范仓库的公开提交图、Pull Request 和 Release 记录保留开发历史；
2. 维护者使用 GitHub 已登记的 SSH、GPG 或 S/MIME 密钥签署后续提交；
3. Windows 发布工作流只接受 `main` 上经 GitHub 验证的源提交，并继续校验
   Authenticode 与 Electron 更新 metadata 的签名边界；
4. 工作流使用 GitHub 官方 `actions/attest` 为 MSI、NSIS 和更新文件生成
   构建来源证明。

用户可以使用 GitHub CLI 验证本地下载文件：

```powershell
gh attestation verify .\DBFox_1.0.3_x64_en-US.msi --repo trrueee/DBFox
```

验证成功只证明该文件由规范仓库的已记录工作流构建，不能替代 Windows 代码签名、
安装态验收或漏洞扫描。旧提交不会通过重写历史补签；启用签名之前的原创时间线继续由
既有公开历史证明。作者和正式来源说明见 [`../../AUTHORS.md`](../../AUTHORS.md)。

## 官方 System DLC 信任根

`dbfox.data` 与 `dbfox.workspace` 使用同一条 `.dbfox-dlc` verifier/registry/snapshot 生命周期，
不从源码目录直载。正式构建的 Ed25519 私钥只以文件路径进入隔离构建进程；构建器生成确定性
包，并把 publisher 公钥及每个包的 exact digest 烘焙进 Frozen Sidecar。Electron Resources
中的相邻 JSON 或包名不能扩大信任：启动只接受 Sidecar 内嵌的 ID、版本、文件名和 SHA-256，
随后仍重新验证包签名。用户禁用状态跨启动保留；应用升级选择新的内嵌 digest，但不会静默重新
启用已被用户禁用的 capability。

当前 Data package 已进入同一签名安装链，但在 SQL、Result、Backup/Restore 执行族完成迁移前
默认禁用；Workspace 默认启用。这个迁移门槛由 bundle manifest 的 `default_enabled` 明示，
不是运行时 fallback 或双写。Data 完整 cutover 后必须删除 legacy Data composition 开关，并将
Data pin 改为默认启用。

## 当前残余风险

Electron/Chromium 显著扩大 npm 依赖体积和发布物体积，因此必须保持锁文件、在线 audit、版本更新、
代码签名和 packaged smoke。删除第三语言依赖图降低了工具链数量，但不替代 Chromium 安全更新。
