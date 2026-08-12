# DBFox 架构导航

> 文档类型：架构导航
>
> 状态：当前
>
> 最后核验：2026-08-06
>
> 事实源：当前源码、迁移、锁文件、协议测试和绑定目标 commit 的运行证据

架构文档按由外到内的顺序组织。系统上下文和运行容器是稳定视图；只有在确实有帮助时才下钻到组件和代码入口，避免维护与源码重复的类图。

## 1. 系统和约束

1. [系统总览](./system-overview.md)：产品目标、核心不变量、外部系统、部署拓扑、质量属性和事实层级。
2. [Runtime 基础能力 ADR](./runtime-foundation-decisions.md)：Sidecar、单实例、Transport、诊断、SQLite、更新和官方 Tauri 插件决定。
3. [桌面发布、恢复与个性化](./desktop-release-lifecycle.md)：外观偏好、窗口状态、异常退出、代码签名和自动更新链路。

## 2. 运行容器

| 容器 | 文档 | 所有权 |
| --- | --- | --- |
| Tauri/Rust Host | [系统总览](./system-overview.md#3-部署拓扑)、[Runtime ADR](./runtime-foundation-decisions.md) | 进程、窗口、端口、Token、generation、ACL、打包 |
| React WebView | [前端架构](./frontend.md) | 工作区、交互、投影、查询缓存和恢复呈现 |
| FastAPI Sidecar | [后端架构](./backend.md) | API、Agent、工具、数据源、SQL、持久化和事件 |
| SQLite metadata | [后端架构](./backend.md#6-持久化与事务边界) | 迁移、会话、事件、租约、配置和审计事实 |
| 外部数据源 | [数据、SQL 与结果链](./data-sql-results.md) | MySQL、PostgreSQL、SQLite、DuckDB 数据平面 |

如果你理解产品方向但不熟悉 Python 后端实现，请先阅读[后端代码导览](./backend-owner-guide.md)建立整体认识，再进入[后端实现手册](../backend/README.md)逐卷学习启动、鉴权、持久化、数据源、SQL、Agent、工具、记忆、事件、测试和扩展。本页和各主题文档继续作为合同事实源；实现手册是解释层，不建立第二份协议。

## 3. 组件和动态流程

1. [功能和代码索引](./implementation-map.md)：启动、数据源、数据库结构、Agent、审批、SSE、结果、取消和恢复的端到端调用链。
2. [数据、SQL 与结果链](./data-sql-results.md)：连接、Catalog、只读 SQL、安全决策、参数绑定、Artifact 和大结果回源。
3. [Agent Runtime](./agent-runtime.md)：SessionCoordinator、显式 ReAct、状态机、工具、事件和恢复。

## 4. Agent 协议下钻

1. [Runtime Item 协议](./agent-runtime-item-protocol.md)：Provider Items 到耐久 RunItem、事件和前端投影。
2. [工具、当前上下文与记忆边界](./agent-tool-context-memory-contract.md)：数据查询、工具结果和持久记忆如何分工。
3. [历史会话查找合同](./agent-conversation-recall-contract.md)：对话档案、FTS5、检索/读取工具和上下文预算。
4. [错误边界合同](./error-boundary-contract.md)：Provider、Tool、HTTP/SSE、持久化和 UI 的错误可信度。
5. [Agent 产品与运行规范](../specs/agent.md)：用户可见行为、领域词汇和验收场景。

## 5. 当前核心不变量

- Rust Runtime Supervisor 是生产 Sidecar 的唯一生命周期权威；React 不猜测端口、Token 或进程状态。
- FastAPI 对 loopback HTTP/SSE 统一鉴权，公开错误使用固定 catalog 和 RFC 9457 Problem Details。
- SQLite 是会话、事件和调度的耐久事实源；内存只保存有界 wake hints，不是第二队列。
- Agent Harness 使用 provider-neutral 原生 function calling；完成、取消、异常和工具等待具有显式终止语义。
- SQL 使用唯一验证/执行链、参数绑定、只读边界和有界结果；模型上下文不承载完整结果集。
- Artifact 是可解析引用，Observation/Memory 是有界摘要；完整会话通过受控检索回源。
- 事件先持久化再发布，客户端以 cursor/snapshot 恢复，Zustand 不是业务事实源。

## 6. 历史边界

旧 LangGraph/Graph/Checkpoint、`engine/agent_runtime`、旧 RunTrace、`previewRows` 持久化、Monaco、Playwright 和遗留启动器只存在于[历史归档](../archive/README.md)的原始记录中。不得依据这些材料新增兼容层或第二套运行链。
