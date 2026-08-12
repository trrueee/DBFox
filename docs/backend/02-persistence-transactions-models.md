# 卷二：持久化、事务与数据模型

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：本地 SQLite、Alembic、SQLAlchemy、事务、租约和数据模型
>
> 权威合同：[后端架构](../architecture/backend.md)、[Agent Runtime](../architecture/agent-runtime.md)
>
> 核心入口：[`engine/db.py`](../../engine/db.py)、[`engine/models.py`](../../engine/models.py)、[`engine/migrations/`](../../engine/migrations/)、[`engine/agent/repositories/`](../../engine/agent/repositories/)

## 1. 两类数据库必须先分清

DBFox 同时接触两类数据库：

| 数据库 | 用途 | 写权限 | 典型内容 |
| --- | --- | --- | --- |
| metadata SQLite | DBFox 自身控制平面 | DBFox 可写 | 数据源配置、凭据引用、Agent Session/Run/Event、审计、备份记录 |
| 外部 datasource | 用户要分析的数据 | 默认只读 | 用户业务表和视图 |

`engine/db.py` 管理的是前者。`engine/connectivity` 和 `engine/sql` 管理的是后者。把两条连接链混用会破坏安全、事务和生命周期边界。

## 2. metadata engine 的创建

`engine.db.build_metadata_engine` 建立 SQLAlchemy Engine 和 Session factory。SQLite 关键配置包括：

- `check_same_thread=False`：允许受控 worker 跨线程取得各自 Session；
- 连接超时和 `busy_timeout`：给短期写竞争一个有限等待窗口；
- `PRAGMA foreign_keys=ON`：保证外键约束；
- `PRAGMA journal_mode=WAL`：允许读写更合理并发；
- `PRAGMA synchronous=NORMAL`：在 WAL 模式下平衡耐久性和性能；
- `PRAGMA secure_delete=ON`：减少删除敏感 metadata 后的残留；
- 每个连接都配置 PRAGMA，而不是只在启动连接上执行一次。

### 2.1 WAL 不等于无并发约束

WAL 允许多个 reader 与一个 writer 更好共存，但 SQLite 仍是单 writer。DBFox 因此采用：

- 短事务；
- 重要聚合写入前 `BEGIN IMMEDIATE`；
- Session lease fencing；
- 有界 Coordinator worker；
- 先在事务外完成网络/模型/工具耗时工作，再用短事务落库；
- 不在数据库事务中等待 Provider 或外部数据源。

## 3. Schema 演进与启动核验

### 3.1 唯一路径是 Alembic

`engine.db.initialize_metadata_database` 的目标是把空库或旧库升级到当前 head，并验证结果。禁止的旁路包括：

- `Base.metadata.create_all()` 代替迁移；
- 因表“看起来存在”而猜测 stamp；
- 迁移失败后静默继续启动；
- 在业务代码里临时 `ALTER TABLE`；
- 为测试建立与生产不同的 schema 初始化器。

### 3.2 迁移互斥

[`engine/migrations/sqlite_mutex.py`](../../engine/migrations/sqlite_mutex.py) 为 SQLite 迁移提供进程间互斥，避免两个进程同时改 metadata schema。它降低迁移竞争，不等于应用单实例，也不保护运行期全部业务写入。

### 3.3 迁移验证

迁移测试应证明：

1. 空数据库可升级到唯一 head；
2. 支持的历史状态可升级；
3. 索引、唯一约束、外键和触发器确实存在；
4. FTS 等 SQLite 特性经过修复/核验；
5. 不存在多个 Alembic heads；
6. ORM 与实际 schema 一致。

对应入口：[`engine/tests/test_migrations.py`](../../engine/tests/test_migrations.py)、[`engine/tests/test_unique_migration.py`](../../engine/tests/test_unique_migration.py)、[`engine/tests/test_fts_migration_repair.py`](../../engine/tests/test_fts_migration_repair.py)。

## 4. SQLAlchemy Session 所有权

### 4.1 基本规则

- 一个 SQLAlchemy Session 只服务一个同步工作单元；
- 不在多个 worker/thread 间共享同一 Session；
- Repository 接收 Session，负责聚合读写，但通常不擅自提交；
- API、Coordinator 或 Terminalizer 等工作单元边界决定 commit/rollback；
- 网络请求、Provider 流和长查询不应持有 metadata 写事务。

### 4.2 为什么 Repository 不到处 commit

一个业务动作常常同时写：

- Run 状态；
- Message 状态；
- RunItem；
- Evidence/Artifact 引用；
- Event；
- Memory 派生状态。

如果每个 Repository 自行 commit，用户可能看到“Run 已完成但 final message 没写入”或“事件已广播但事实被回滚”。由上层工作单元统一提交才能保持原子性。

## 5. SQLite 写入围栏：`begin_agent_write`

[`engine/agent/repositories/write_transaction.py`](../../engine/agent/repositories/write_transaction.py) 提供 `begin_agent_write`：

- SQLite 且当前没有活跃事务时发出短 `BEGIN IMMEDIATE`；
- 非 SQLite 或已有事务时不重复开启；
- 目的是在“先读聚合状态，再基于版本写入”之前抢占 writer，避免两个 writer 都读到旧状态；
- 它不是全局锁，也不能包围 Provider/工具网络调用。

适合使用的操作：claim lease、消费输入、完成 Run、取消、审批状态迁移、事件 sequence 增长等。

## 6. Agent 聚合的数据模型

以下字段不是完整 ORM 定义，而是理解状态机所需的分组。

### 6.1 `AgentSession`

`AgentSession` 是对话和调度聚合根，主要承担：

- 业务身份：`id`、`datasource_id`、`title`；
- 输入顺序：`input_sequence`；
- 事件顺序：`event_sequence`、`event_floor_sequence`；
- 调度租约：`lease_owner`、`lease_token`、`lease_expires_at`；
- 上下文世代：`context_epoch`；
- 消息顺序：`message_sequence`；
- 当前选择：`selected_artifact_id`；
- 生命周期：archive/delete/timestamps。

它不保存一个巨大 JSON 聊天数组。Messages、Runs、Memory 和 Events 使用规范表关联。

### 6.2 `AgentMessage`

保存用户和 assistant 的规范可展示消息：

- `role`；
- `content`；
- `status`；
- Session 内单调 `sequence`；
- 创建/完成时间。

只有完成的 assistant 消息才能作为后续历史。Provider 的 reasoning、工具调用和临时状态不应伪装成最终 assistant message。

### 6.3 `AgentMessageSearchDoc`

这是 Conversation Recall 的派生搜索投影：

- 关联 canonical message；
- 保存受控 `search_text`；
- 支持 FTS5 或确定性回退；
- 可重建，不是消息事实源；
- 迁移和测试保证索引合同。

### 6.4 `AgentSessionMemory`

每个 Session 一份有界 `memory_json`，用于保存经过筛选的：

- 最近已完成 Run 摘要；
- Evidence 引用；
- working set；
- 与当前 datasource generation 兼容的信息。

它不是完整聊天记录，也不应保存原始大结果。

### 6.5 `AgentRun`

一个 Input 对应一次耐久执行。字段可分为：

- 归属：session/input/parent；
- 数据边界：datasource id + connection generation；
- 模型配置：credential 引用、API base、model；
- 消息关联：user/assistant message id；
- 状态与并发：status/version/lease_token/execution id/current turn；
- 请求与结果：request/result JSON；
- 取消：cancel requested/reason/time；
- 预算账本：token、cost、provider retry、repair；
- 等待态：current step、waiting approval；
- 诊断：response/context summary/error code/public message；
- timestamps。

Run 不应把 Provider SDK 对象原样 pickle。只持久化规范化、版本可控的协议字段。

### 6.6 `AgentTurn`

每次 Provider 往返一条 Turn，保存可复现证据：

- sequence/attempt/status；
- Agent definition、prompt version/hash；
- Context snapshot/hash；
- Tool materialization/hash；
- provider/model；
- reasoning summary；
- tool calls、response items、usage；
- provider-neutral termination；
- error code/public message；
- timestamps。

Turn 是定位“模型看到什么工具、为何完成/继续”的关键记录。

### 6.7 `AgentToolInvocation`

每个原生 function call 对应一条耐久调用：

- `provider_call_id`：保持 Provider 协议配对；
- tool name/version；
- canonical input JSON/hash；
- idempotency key；
- status/attempts；
- policy 和 presentation；
- approval id；
- recovery policy；
- result reference；
- error code/public message。

`turn_id + provider_call_id` 和 idempotency key 的唯一性约束防止重放制造第二次业务调用。

### 6.8 RunItem、Event、Evidence、Artifact

- RunItem：运行过程的规范项目投影；
- Event：用于 cursor replay 的顺序事件；
- Evidence：最终回答中可验证主张的来源关系；
- Artifact：大结果或可回源结果的耐久引用。

它们职责不同，不能用一个“万能 JSON 日志表”代替。

## 7. Session lease 与 fencing token

### 7.1 `SessionRepository.claim`

claim 在写事务中：

1. 锁定/读取 Session；
2. 若另一 owner 的 lease 未过期，则拒绝；
3. 新 owner 或过期接管时递增 `lease_token`；
4. 写入 owner 与 expiry；
5. 返回包含 fencing token 的 `SessionLease`。

### 7.2 为什么只存 owner 不够

旧 worker 可能经历长暂停，在 lease 过期后恢复。如果只检查 owner 名称，它可能覆盖新 worker。单调递增的 `lease_token` 让每次状态写入都能证明“我仍属于当前世代”。

### 7.3 heartbeat 与接管

Coordinator 为活跃执行续租。若进程崩溃，heartbeat 停止，lease 到期后另一 worker 可以从数据库恢复。恢复依赖持久化 Run/Invocation 状态，而不是内存 continuation。

## 8. 原子完成事务

`Terminalizer.complete` 最终进入 `RunRepository.complete`，其工作单元应原子包含：

1. 校验当前 lease；
2. 拒绝已终止或已取消 Run；
3. 写/关联 Evidence；
4. 将 assistant message 标记 completed 并写最终内容；
5. 将 Input 标记 consumed；
6. 将 Run 标记 completed，写结果与终止元数据；
7. 更新选择状态；
8. 派生并写 Memory；
9. 写 `RUN_ITEM_COMPLETED`、`RUN_COMPLETED` 等 Event；
10. 由上层一次 commit。

任何一步失败都 rollback。SSE 不能先看到一个尚未提交的完成事件。

## 9. 提交后事件通知

`EventRepository.append_locked` 在同一事务内：

1. 增长 Session `event_sequence`；
2. upsert canonical RunItem；
3. 校验 event payload；
4. 插入 Event；
5. 根据保留窗口 compact；
6. 在 SQLAlchemy Session `info` 中登记待通知项。

SQLAlchemy `after_commit` listener 才把通知发布到内存 Live Hub；`after_rollback` 清除待通知项。

这保证：

- 事件永远指向已提交事实；
- 进程在 commit 后、publish 前崩溃时，客户端仍可从数据库 replay；
- 内存发布失败不会丢掉耐久事件；
- rollback 不会产生幽灵 UI 更新。

## 10. 事件压缩与 replay floor

事件表不会无限增长。压缩时：

- 保留最近窗口；
- 删除 floor 之前事件；
- 推进 `event_floor_sequence`；
- 客户端 cursor 早于 floor 时不能伪装成连续 replay；
- API 应要求重新取 snapshot，再从新 cursor 继续。

floor 是协议字段，不是内部清理细节。

## 11. Credential Lease Saga 的持久化意义

系统凭据库和 SQLite 无法参与同一数据库事务，因此凭据创建/更新采用 Saga：

1. metadata 记录意图/lease；
2. 对系统凭据库执行写入；
3. metadata claim/commit；
4. 失败时释放或留给启动 reconciliation；
5. startup 清理未完成操作。

这不是普通 Agent Session lease。两者同名“lease”但解决不同问题：前者协调跨资源提交，后者协调 worker 所有权。

## 12. 常见反模式

- 在 `async` API 中共享一个全局 SQLAlchemy Session；
- Repository 内部随意 `commit()`；
- 在持有 `BEGIN IMMEDIATE` 时请求 Provider；
- 用内存锁替代跨进程 lease；
- 更新 Run 后异步“稍后补事件”；
- 从 Event 反推唯一业务状态，而不是读取 canonical 表；
- 手工修改 ORM 后忘记 Alembic；
- 迁移失败时 `create_all()` 兜底；
- 把 Memory 当消息归档；
- 把 ToolInvocation 结果正文无限写入同一 JSON。

## 13. 关键测试

| 合同 | 测试 |
| --- | --- |
| metadata 初始化和 PRAGMA | [`test_db_init.py`](../../engine/tests/test_db_init.py) |
| 启动/迁移生命周期 | [`test_db_init_lifecycle.py`](../../engine/tests/test_db_init_lifecycle.py) |
| Alembic 单头与升级 | [`test_migrations.py`](../../engine/tests/test_migrations.py) |
| Session admit/claim/lease | [`test_session_repository.py`](../../engine/agent/tests/test_session_repository.py) |
| Coordinator 接管 | [`test_session_coordinator.py`](../../engine/agent/tests/test_session_coordinator.py) |
| 终态原子性 | [`test_terminal_transaction.py`](../../engine/agent/tests/test_terminal_transaction.py) |
| ToolInvocation 幂等 | [`test_tool_invocation_repository.py`](../../engine/agent/tests/test_tool_invocation_repository.py) |
| 事件合同 | [`test_event_contracts.py`](../../engine/agent/tests/test_event_contracts.py) |
| SSE 背压/回放 | [`test_conversation_stream_backpressure.py`](../../engine/tests/test_conversation_stream_backpressure.py) |
| 确定性 SQLite 场景 | [`harness/test_sqlite_scenarios.py`](../../engine/agent/tests/harness/test_sqlite_scenarios.py) |

## 14. 修改检查表

- [ ] schema 变化有 Alembic 迁移且仍只有一个 head；
- [ ] 新写操作明确了事务 owner；
- [ ] Repository 未在中间状态自行 commit；
- [ ] SQLite 竞争路径使用短事务并有 busy/lease 测试；
- [ ] 状态写入校验当前 fencing token；
- [ ] Event 与 canonical 状态同事务；
- [ ] publish 发生在 commit 后；
- [ ] rollback 不会留下通知；
- [ ] 派生索引/Memory 可重建；
- [ ] 没有把 metadata Session 传给外部 datasource 执行链。
