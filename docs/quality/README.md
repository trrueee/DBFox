# DBFox 质量与发布导航

> 文档类型：质量导航
>
> 状态：当前
>
> 最后核验：2026-08-15

## 当前整改

- [Agent 长任务收尾与证据呈现整改方案](2026-08-15-long-run-evidence-remediation.md)：修复跨 Run Result 引用、硬预算前收尾、受限部分结果和 Evidence/来源呈现。
- [2026-08-14 系统级工程审查整改计划](2026-08-14-system-review-remediation.md)：记录当前 P1/P2 修复设计、验收标准和 P3 反证核验清单。

- [工程质量门禁](./engineering-gates.md)：本地与 CI 的 Python、前端、Rust、迁移、Frozen Sidecar 和依赖策略。
- [Agent 生产评测方法](./agent-evaluation-methodology.md)：分层 Harness、数据集角色、Grader、统计门禁与脱敏 Trace 合同。
- [DBFox AgentBench](./agentbench-implementation.md)：60 场景数据集、评分器校准、真实 RunLoop、故障注入、CLI 和 CI。
- [Agent Harness 设计、优化与评测复盘](./agent-harness-evolution-retrospective.md)：从真实故障、边界合同和关键提交理解当前 Harness 为什么这样设计，以及如何科学评价后续优化。
- [供应链安全](./supply-chain-security.md)：锁文件、依赖审计、提交签名和正式产物来源证明。
- [发布验证矩阵](./release-validation-matrix.md)：平台、Runner、产物和人工验收的证据要求。

质量文档中的“通过”只对注明的 commit、平台、产物和命令有效。未执行的真实 Provider、数据库、安装、签名、公证或 GUI 场景必须明确写为未验证。
