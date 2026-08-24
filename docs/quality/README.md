# DBFox 质量与发布导航

> 文档类型：质量导航
>
> 状态：当前
>
> 最后核验：2026-08-24

## 当前整改

- [Agent Core、Capability DLC 与 Workbench 深度质量评审](./2026-08-22-agent-core-dlc-workbench-review.md)：记录 Resource authority、多同类资源、Project/Data/Workspace 边界，以及 Dock、Sidebar、Composer 的证据、复用决策和安全施工顺序。
- [Agent 长任务收尾与证据呈现整改方案](2026-08-15-long-run-evidence-remediation.md)：修复跨 Run Result 引用、硬预算前收尾、受限部分结果和 Evidence/来源呈现。
- [2026-08-14 系统级工程审查整改计划](2026-08-14-system-review-remediation.md)：记录当前 P1/P2 修复设计、验收标准和 P3 反证核验清单。

- [工程质量门禁](./engineering-gates.md)：本地与 CI 的 Python、前端、Electron Host、迁移、Frozen Sidecar 和依赖策略。
- [技术调研、方案复用与架构克制](./technical-investigation-and-reuse.md)：实现前先调查、复用优先、避免堆叠中间层、兼容层可退出和决策依据要求。
- [R5.2 GitHub DLC 数据迁移证据](./2026-08-21-r5-github-data-migration.md)：一次性导入、失败保留、幂等重放，以及迁移后 DLC SQLite 唯一读写权威。
- [R5.3 GitHub Core 运行图移除证据](./2026-08-21-r5-github-core-removal.md)：删除静态 API、ORM、运行时与前端组合，同时保留历史 Alembic 升级能力。
- [R5.4 GitHub 完整外置 Conformance 证据](./2026-08-21-r5-github-conformance.md)：真实 `dbfox.github` 包的 absence、restart activation/deactivation、数据与 ToolAttempt 身份保留，以及三平台 frozen release 合同。
- [R6 Side-by-Side Update / Rollback 证据](./2026-08-21-r6-side-by-side-update-rollback.md)：多 digest/version registry、显式选择与 rollback、数据不回滚、旧版本清理，以及三平台 packaged release 合同。
- [R7.0 Electron Host Cutover 决策与迁移证据](./2026-08-21-r7-electron-host-cutover.md)：只替换 Desktop Host、保持 Renderer→Python HTTP/SSE、分阶段迁移 supervisor/native/DLC/release 并最终删除 Rust/Tauri。
- [R7.1 DLC SDK / CLI / Conformance 证据](./2026-08-21-r7-dlc-sdk-cli.md)：共享 Host verifier/canonical rules、确定性 build/sign、安全 key generation、公开 Frontend types 与三平台 CLI 自举门禁。
- [R8A Untrusted Isolation Gate 证据](./2026-08-21-r8-untrusted-isolation-gate.md)：逐平台核验 backend/frontend 权限、反证当前同进程/同 Renderer 边界，并正式记录 trusted-publisher-only 的 NO-GO 结论。
- [P2 Memory v4 Cutover Gate 本地证据与限制](../archive/reviews/2026-08-16-p2-memory-v4-cutover-evidence.md)：已归档的旧开关式候选实现证据，不代表当前 Runtime 仍提供该开关。
- [P2 Memory v4 DeepSeek 真实 Provider 调查与修复记录](../archive/reviews/2026-08-17-memory-v4-projection-deepseek-investigation.md)：已归档的 projection 故障调查；当前评测不得把已删除开关当作 A/B 变化轴。
- [Agent 生产评测方法](./agent-evaluation-methodology.md)：分层 Harness、数据集角色、Grader、统计门禁与脱敏 Trace 合同。
- [DBFox Benchmark System](./benchmark-system.md)：Core/Capability/Composition 分层、60 场景 Data suite、真实 RunLoop、评分器校准、CLI 和 CI。
- [Agent Harness 设计、优化与评测复盘](../archive/reviews/agent-harness-evolution-retrospective.md)：历史演进背景；当前合同以架构文档和 verification system 为准。
- [供应链安全](./supply-chain-security.md)：锁文件、依赖审计、提交签名和正式产物来源证明。
- [发布验证矩阵](./release-validation-matrix.md)：平台、Runner、产物和人工验收的证据要求。

质量文档中的“通过”只对注明的 commit、平台、产物和命令有效。未执行的真实 Provider、数据库、安装、签名、公证或 GUI 场景必须明确写为未验证。
