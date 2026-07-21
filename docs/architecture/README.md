# DBFox 架构文档索引

> 当前事实口径：2026-07-20

建议 AI 或评审者按以下顺序阅读：

1. [当前系统架构](../architecture-design-document.md)：部署、前端、后端、持久化、安全、发布的总事实源。
2. [前端架构](./frontend.md) 与 [后端架构](./backend.md)：两个技术面的状态、边界、性能、安全和测试细节。
3. [功能模块与执行管线](../functional-modules-and-execution-pipelines.md)：模块职责、输入输出、状态变化和故障路径。
4. [Agent Runtime](./agent-runtime.md)：Session、ReAct、工具、计划、记忆、事件和恢复的专题设计。
5. [前后端与 Agent 深度评审](../reviews/frontend-backend-agent-architecture-deep-review.md)：当前设计符合度、开放风险和评审问题。
6. [实施后全局核验](../reviews/architecture-global-verification.md)：修复前证据与实施后权威结论。

以下文档属于历史决策材料，不可覆盖当前事实：

- `docs/designs/` 与 `docs/plans/` 中的旧 LangGraph/Graph/Checkpoint 方案；
- `agent-architecture-review.md` 中的修复前链路分析；
- v1.0.1 对照材料。

识别历史设计的原则：如果文档把 `engine/agent/graph/`、`engine/agent_runtime/`、LangGraph thread/state/checkpoint、Result `previewRows` 或前端旧 RunTrace 作为当前实现，应视为过时描述。
