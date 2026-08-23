# DBFox 后端实现入口

> 文档类型：实现导航
>
> 状态：当前
>
> 最后核验：2026-08-24

当前后端以 `Agent/Workbench Core + Capability DLC` 组织。为避免解释手册与源码形成第二份事实源，本页只维护稳定入口；具体合同、调用链和验证命令由下列当前文档负责。

| 阅读目标 | 当前文档 |
| --- | --- |
| Core/DLC 所有权、Resource authority 与终态边界 | [Agent Core 与 Capability DLC 架构合同](../architecture/agent-core-capability-dlc-contract.md) |
| Python 入口、主要目录、真实 Agent loop 与维护规则 | [Python Engine 代码导览](../architecture/backend-owner-guide.md) |
| Data System DLC、SQL 唯一执行链与结果视图 | [Data、SQL 与结果链](../architecture/data-sql-results.md) |
| Agent Run/Turn、function calling、终态与恢复 | [Agent Runtime](../architecture/agent-runtime.md) |
| Tool、Context、Artifact/Evidence 与 Recall | [工具、当前上下文与记忆边界](../architecture/agent-tool-context-memory-contract.md) |
| 功能到源码、表和测试 | [实现地图](../architecture/implementation-map.md) |
| 产品代码与测试/测评的物理边界 | [测试与测评系统边界](../architecture/verification-system.md) |
| 命令、marker、依赖和提交要求 | [`AGENTS.md`](../../AGENTS.md)、[`CONTRIBUTING.md`](../../CONTRIBUTING.md) |

旧的九卷单体后端手册描述了 Core DataSource、Core SQL 和 Data-scoped Memory 等已退役实现，现归档于 [`docs/archive/backend-manual/`](../archive/backend-manual/)。它们只用于历史追溯，不得作为新增代码的依据。
