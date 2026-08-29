# DBFox 架构导航

> 文档类型：架构导航
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 事实源：当前源码、迁移、锁文件、协议测试和绑定目标 commit 的运行证据

架构文档按由外到内的顺序组织。系统上下文和运行容器是稳定视图；只有在确实有帮助时才下钻到组件和代码入口，避免维护与源码重复的类图。

## 1. 系统和约束

1. [系统总览](./system-overview.md)：产品目标、核心不变量、外部系统、部署拓扑、质量属性和事实层级。
2. [R7 Electron Host Cutover](../quality/2026-08-21-r7-electron-host-cutover.md)：当前 Sidecar、原生能力、DLC protocol、更新和发布边界。
3. [R8A Untrusted Isolation Gate](./r8-untrusted-isolation-gate.md)：三平台 backend/frontend 隔离调查、NO-GO 结论与 trusted-publisher-only 边界。
4. [桌面发布、恢复与个性化](./desktop-release-lifecycle.md)：外观偏好、窗口状态、异常退出、代码签名和自动更新链路。
5. [测试与测评系统边界](./verification-system.md)：产品代码与 verification 的物理隔离、真实链路、Core/DLC/Bench 分类和 CI 门禁。

## 2. 当前架构合同

1. [Agent Core 与 Capability DLC 架构合同](./agent-core-capability-dlc-contract.md)：Project、Conversation intent、Run authority、ResourceKey、System DLC 与 Workbench composition 的权威边界。
2. [Artifact、Representation、可视化与 Dock 架构](./artifact-representation-visualization.md)：当前 AI 编排、SQL Backend、多视图、Visualization DLC 与 Dock 边界。
3. [Runtime Extension Contracts](./runtime-extension-contracts.md)：Backend Extension Manifest、Invocation Context、Capability Grant、Effect、Semantic 和 Completion Rule。
4. [Runtime Extension 安全与兼容规范](./runtime-extension-security-compatibility.md)：trusted publisher、Filesystem/Network/Process/Secret、Artifact envelope 和 wire compatibility。
5. [前端架构](./frontend.md)：Host-owned Workbench、资源树、Conversation composer、Dock 与 DLC contribution。
6. [测试与测评系统边界](./verification-system.md)：与产品物理分离但驱动真实 Runtime loop 的验证架构。

已完成的分阶段迁移方案和 Memory v4 候选设计只保留在 [`docs/archive/designs/`](../archive/designs/)；它们不是当前实现合同，也不得成为新增兼容路径的依据。

## 3. 运行容器

| 容器 | 文档 | 所有权 |
| --- | --- | --- |
| Electron/TypeScript Host | [系统总览](./system-overview.md#3-部署拓扑)、[R7 Cutover](../quality/2026-08-21-r7-electron-host-cutover.md) | 进程、窗口、端口、Token、generation、IPC、打包 |
| React Renderer | [前端架构](./frontend.md) | 工作区、交互、投影、查询缓存和恢复呈现 |
| FastAPI Sidecar | [后端架构](./backend.md) | API、Agent Core、工具运行时、DLC Host、持久化和事件 |
| SQLite metadata | [后端架构](./backend.md#6-持久化与事务边界) | 迁移、会话、事件、租约、配置和审计事实 |
| 外部数据源 | [数据、SQL 与结果链](./data-sql-results.md) | MySQL、PostgreSQL、SQLite、DuckDB 数据平面 |

如果你理解产品方向但不熟悉 Python 后端实现，请先阅读[后端代码导览](./backend-owner-guide.md)建立整体认识，再进入[后端实现手册](../backend/README.md)逐卷学习启动、鉴权、持久化、数据源、SQL、Agent、工具、记忆、事件、测试和扩展。本页和各主题文档继续作为合同事实源；实现手册是解释层，不建立第二份协议。

## 4. 组件和动态流程

1. [功能和代码索引](./implementation-map.md)：启动、数据源、数据库结构、Agent、审批、SSE、结果、取消和恢复的端到端调用链。
2. [数据、SQL 与结果链](./data-sql-results.md)：连接、Catalog、只读 SQL、安全决策、参数绑定、Artifact 和大结果回源。
3. [Agent Runtime](./agent-runtime.md)：SessionCoordinator、显式 ReAct、状态机、工具、事件和恢复。

## 5. Agent 协议下钻

1. [Runtime Item 协议](./agent-runtime-item-protocol.md)：Provider Items 到耐久 RunItem、事件和前端投影。
2. [工具、当前上下文与记忆边界](./agent-tool-context-memory-contract.md)：通用 Context、Artifact/Evidence、工具结果和历史召回如何分工。
3. [历史会话查找合同](./agent-conversation-recall-contract.md)：对话档案、FTS5、检索/读取工具和上下文预算。
4. [错误边界合同](./error-boundary-contract.md)：Provider、Tool、HTTP/SSE、持久化和 UI 的错误可信度。
5. [Agent 产品与运行规范](../specs/agent.md)：用户可见行为、领域词汇和验收场景。

## 6. 当前核心不变量

- Electron Main 的 `EngineSupervisor` 是生产 Sidecar 的唯一生命周期权威；React 不猜测端口、Token 或进程状态。
- Runtime DLC 是 trusted-publisher-only 的应用级代码扩展；manifest permissions、subprocess、module namespace、CSP 或 Renderer sandbox 均不被描述为不可信代码 sandbox。
- FastAPI 对 loopback HTTP/SSE 统一鉴权，公开错误使用固定 catalog 和 RFC 9457 Problem Details。
- SQLite 是会话、事件和调度的耐久事实源；内存只保存有界 wake hints，不是第二队列。
- Agent Harness 使用 provider-neutral 原生 function calling；完成、取消、异常和工具等待具有显式终止语义。
- Data DLC 的 SQL 使用唯一验证/执行链、参数绑定、只读边界和有界结果；Core 不理解 SQL 语义。
- Artifact 是可解析引用，Observation/Memory 是有界投影；完整会话通过受控检索回源。
- 事件先持久化再发布，客户端以 cursor/snapshot 恢复，Zustand 不是业务事实源。

## 7. 历史边界

旧 LangGraph/Graph/Checkpoint、`engine/agent_runtime`、旧 RunTrace、`previewRows` 持久化、Monaco、Playwright 和遗留启动器只存在于[历史归档](../archive/README.md)的原始记录中。不得依据这些材料新增兼容层或第二套运行链。
