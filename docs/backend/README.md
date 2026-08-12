# DBFox 后端实现手册

> 文档类型：实现指南
>
> 状态：当前
>
> 适用版本：当前 `engine/` 生产实现
>
> 最后核验：2026-08-10
>
> 读者：项目所有者、后端维护者、Agent/SQL 功能开发者、代码评审者

这套手册用于回答“DBFox 后端实际上怎样工作、出现问题应从哪里开始查、修改时不能破坏什么”。它不是另一份架构规范，也不取代源码、迁移和自动化测试。

## 1. 文档事实层级

遇到冲突时，按以下顺序判断：

1. 当前生产源码、Alembic 迁移和自动化测试；
2. [`docs/architecture/`](../architecture/README.md) 中标记为 Current 的架构与合同；
3. 本目录的实现解释、故障定位和扩展指南；
4. [`docs/archive/`](../archive/README.md) 中的历史材料。

本手册会引用真实文件和 Symbol，但避免复制大段源码。行号可能随实现变化，文件与 Symbol 名才是稳定索引。若实现发生语义变化，必须同时更新对应架构合同、测试和本手册。

## 2. 为什么拆成多卷

DBFox 后端不是单一 Web API，而是四个相互约束的系统：

| 系统 | 主要职责 | 耐久事实源 | 关键边界 |
| --- | --- | --- | --- |
| Runtime/API | 启动、鉴权、请求限制、公开错误、关闭 | 运行时状态 + 配置 | Rust Host 与 FastAPI Sidecar |
| Metadata Control Plane | 配置、凭据引用、会话、事件、租约、审计 | SQLite metadata | SQLAlchemy 事务与 Alembic |
| Data Plane | 外部数据源连接、Catalog、只读 SQL、结果回源 | 外部数据库 + Result Artifact | 安全 SQL 与参数绑定 |
| Agent Harness | 调度、Provider、工具、上下文、记忆、SSE | SQLite Agent 表 | provider-neutral function calling |

把所有内容塞进一个文件会混淆不同事实层级，也不利于查错。因此本目录按“运行容器 → 持久化 → 数据平面 → Agent → 工具 → 记忆/事件 → 测试/扩展”组织。

## 3. 卷册目录

| 卷 | 文档 | 解决的问题 |
| ---: | --- | --- |
| 0 | [后端项目所有者导览](../architecture/backend-owner-guide.md) | 先建立全局心智模型和学习路线 |
| 1 | [Runtime、API、安全与错误](./01-runtime-api-security.md) | Sidecar 如何启动、如何鉴权、错误怎样安全地到达 UI |
| 2 | [持久化、事务与数据模型](./02-persistence-transactions-models.md) | SQLite、Alembic、SQLAlchemy、租约和原子写入怎样协作 |
| 3 | [数据源、凭据、连接与 Catalog](./03-datasource-connectivity-catalog.md) | 凭据怎样保存，连接如何生成、回收，Schema 怎样同步 |
| 4 | [SQL 安全、执行与 Result Artifact](./04-sql-results.md) | SQL 从输入到验证、审批、执行、分页和导出的完整链路 |
| 5 | [Agent Harness 与 Provider](./05-agent-harness-provider.md) | 输入如何成为 Run，Turn 如何循环，完成/取消/失败如何判定 |
| 6 | [工具、策略、审批与 Observation](./06-tools-policy-approval.md) | Function calling 怎样变成受控工具调用，结果如何进入上下文 |
| 7 | [Context、Memory、Recall、事件与恢复](./07-context-memory-events-recovery.md) | 上下文为何不会无限膨胀，历史如何找回，SSE 如何恢复 |
| 8 | [测试、调试、扩展与变更影响](./08-testing-debugging-extension.md) | 怎样验证和定位问题，怎样安全增加功能而不制造第二条链 |
| 9 | [后端源码索引](./09-code-index.md) | 按能力、Symbol、表和测试快速定位代码 |

## 4. 推荐阅读路径

### 4.1 项目所有者第一次系统理解后端

1. 卷 0：先知道四个系统和关键不变量；
2. 卷 1：理解桌面 Host 与 Sidecar 边界；
3. 卷 2：理解为什么 SQLite 是事实源而不是缓存；
4. 卷 3、4：理解数据源和 SQL 数据平面；
5. 卷 5、6、7：完整理解 Agent Harness；
6. 卷 8：学习修改、验证和排障方法；
7. 卷 9：作为日常查找索引。

### 4.2 排查“应用启动但请求失败”

1. 卷 1 的启动时间线；
2. `RuntimeCredentialPolicy` 与 `verify_local_access_token`；
3. `/health` 是否使用当前 generation 的 Token；
4. 全局 Problem Details 是否隐藏了内部异常；
5. 卷 8 的启动与鉴权测试矩阵。

### 4.3 排查“Agent 没回答或工具调用失败”

1. 卷 5 的 Input → Run → Turn 状态机；
2. 卷 6 的工具物化、策略门和 Provider `call_id` 闭环；
3. 卷 7 的 Context 与事件回放；
4. 查看 `AgentRun`、`AgentTurn`、`AgentToolInvocation` 和 `AgentEventRecord`；
5. 运行卷 8 中的 deterministic SQLite Harness。

### 4.4 排查“查到了数据但 AI 看不到完整结果”

这通常不是应把所有行塞回模型。按以下顺序检查：

1. 卷 4：查询是否生成可回源 Result Artifact；
2. 卷 6：工具输出是否只提供有界摘要和 `artifact_id`；
3. `result_inspect` / `result_profile` 是否能按需读取；
4. 卷 7：Observation 是否保留结构性引用，而非复制完整行集；
5. 数据确实需要聚合时，优先让 SQL backend 计算，而不是让模型遍历原始行。

## 5. 核心不变量速查

以下规则是理解全部后端实现的主线：

- Rust Runtime Supervisor 是正式环境 Sidecar 生命周期、端口、Token 和 generation 的唯一权威。
- FastAPI 的所有业务 HTTP/SSE 请求都经过同一 loopback Token 鉴权边界；`/health` 也不是匿名端点。
- SQLite metadata 是控制平面耐久事实源；内存队列、SSE Hub、前端 Store 都只是可重建投影。
- Schema 只由 Alembic 演进；启动不使用 `create_all()`、猜测式 stamp 或静默降级。
- 凭据正文只进入系统凭据库；metadata 只保存引用和业务元数据。
- 外部数据源连接以规范化 `ConnectionProfile` 和 generation 管理，不在 API、工具和 SQL 层分别拼接连接逻辑。
- SQL 必须经过唯一安全链，值使用 driver 参数绑定，不能字符串拼接。
- 大结果保留在 Result Artifact，模型只接收有界 Observation，需要时使用结果工具回源。
- Agent 调度以数据库 Run 为耐久队列；Coordinator 内存只保存有界 wake hint。
- Provider message、tool call、tool output 使用原生 `call_id` 配对；不按 Provider 名称建立兼容映射。
- 完成、失败、取消、等待工具和等待审批是显式状态，不靠字符串内容猜测。
- Context 只装入当前 Turn 必需信息；Memory 是有界派生状态；Conversation Recall 才负责找回较早原文。
- Agent 事件先与业务状态同事务提交，再通知 SSE；客户端以 cursor/snapshot 恢复。
- 内部异常默认不可信；公开错误必须来自固定 catalog 或显式可展示输入错误。

## 6. 术语表

| 术语 | 含义 | 不等同于 |
| --- | --- | --- |
| Metadata database | DBFox 自身的 SQLite 控制平面数据库 | 用户连接的 MySQL/PostgreSQL/SQLite |
| Datasource | 用户配置的外部数据源实体 | 一个永久打开的连接对象 |
| generation | 某个运行时或数据源资源世代，用于拒绝陈旧状态 | 数据库 schema version |
| Session | 一段可持续、多 Run 的对话容器 | 单次模型请求 |
| Input | 用户提交给 Session 的一次耐久输入 | Provider message |
| Run | 消费一个 Input 的一次 Agent 执行 | Turn |
| Turn | 一次 Provider 请求/响应和其工具决策边界 | 整个 Run |
| RunItem | 消息、工具调用、工具输出、状态等规范运行项 | UI 专用 ViewModel |
| Artifact | 可持久引用和回源的数据结果 | 直接塞入上下文的完整结果 |
| Observation | 工具执行后给 Agent 的有界、可信结构化观察 | 原始数据库转储 |
| Memory | 从已完成事实派生的有界会话工作记忆 | 全量聊天记录 |
| Recall | 在授权、预算和范围约束下搜索/读取历史消息 | 自动把全部历史注入 Prompt |
| lease | 防止多个 worker 同时拥有同一 Session 的围栏令牌 | 仅依赖进程内 mutex |

## 7. 手册维护要求

修改后端语义时，按以下检查：

1. 变更是否修改权威合同；如是，先更新 `docs/architecture` 或 `docs/specs`；
2. 本手册中是否有对应运行链、失败路径和源码索引；
3. 数据库模型变化是否有 Alembic 迁移和迁移测试；
4. 边界变化是否有合同测试，而非只测辅助函数；
5. 是否新增了 Adapter、Mapper、fallback 或双轨状态；若有，必须证明它位于真实外部边界并给出退出条件；
6. 是否能从 UI 行为一路追到数据库事实和测试证据；
7. 文档中“已实现”“计划”“未验证”是否明确区分。
