# 历史归档

> 状态：历史材料导航
> 归档日期：2026-08-06

这里保存长期重构过程中形成的设计、计划、审查和工具生成材料。它们用于考古、追溯取舍和理解迁移背景，不是当前实现或发布状态的事实源。

| 目录 | 内容 | 使用方式 |
| --- | --- | --- |
| [`designs/`](./designs/README.md) | 已完成、已取代或未实施的功能设计 | 理解当时目标和候选方案 |
| [`plans/`](./plans/README.md) | 历史实施步骤和完成记录 | 追溯改动顺序，不当作待办 |
| [`reviews/`](./reviews/README.md) | 绑定旧 commit/工作树的审查、验收和整改报告 | 只引用其明确基线的证据 |
| [`generated/`](./generated/README.md) | 外部工具生成的、仍有决策价值的 design specs | 只保留取舍理由，不覆盖人工维护事实 |

归档文档可能出现 LangGraph、Graph/Checkpoint、`engine/agent_runtime`、旧 Artifact payload、Monaco、Playwright、固定端口、遗留启动器或已删除目录。这些术语保留是为了忠实记录历史，不构成兼容要求。

当前信息请返回[文档中心](../README.md)和[架构导航](../architecture/README.md)。

## 当前替代关系索引

| 归档中可能出现的旧主题 | 当前事实源 |
| --- | --- |
| `engine/sql`、Core SQL executor、旧 Result Gateway | [数据、SQL 与结果链](../architecture/data-sql-results.md)；SQL 领域实现归 `dbfox.data` DLC |
| LangGraph、Graph、Checkpoint、`agent_runtime` | [Agent Runtime](../architecture/agent-runtime.md)；当前为显式 RunLoop |
| 旧 Artifact payload、Chart Artifact、正文末尾统一 append | [Artifact、Representation、Visualization 与 Dock](../architecture/artifact-representation-visualization.md) |
| App Shell 拥有 Dock renderer、`dockViewRegistry` | [前端架构](../architecture/frontend.md)；当前 Dock composition 归 `features/dock` |
| Tauri/Rust Host、固定 Sidecar 端口 | [桌面发布与生命周期](../architecture/desktop-release-lifecycle.md)；当前为 Electron Host 动态会话合同 |
| 不受信 DLC sandbox 候选 | [R8A Untrusted Isolation Gate](../architecture/r8-untrusted-isolation-gate.md)；当前结论为 NO-GO / trusted-publisher-only |

仓库根 `.rgignore` 默认排除本目录，避免普通代码定位和 AI 检索把历史材料当成
当前合同。需要考古时使用 `rg --no-ignore <pattern> docs/archive`，并同时核对目标
文档的基线、状态和上表中的当前事实源。
