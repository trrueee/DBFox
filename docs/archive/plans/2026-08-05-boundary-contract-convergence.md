# DBFox 基础设施边界合同收敛实施计划

> **状态：历史归档。** 本文绑定原设计、计划或评审基线，仅用于追溯；当前事实见[架构导航](../../architecture/README.md)。下方原状态只代表当时。

状态：Accepted for implementation
适用分支：`codex/llm-call-interface`
基线提交：`f3dd352b42abf5168fa24e0e32a6b4aeb19c7b62`
最后更新：2026-08-04

## 1. 目标

本计划修复 BC-01～BC-08。它不是基础架构重写，而是将已经存在的 Runtime、Agent、工具、SQL、错误与冻结产物能力收敛到可验证的唯一边界合同。

必须保持：

- Rust RuntimeSupervisor 仍是 Sidecar 生命周期权威；
- OpenAI Responses SDK 仍是当前 provider 的官方协议实现；
- SQLAlchemy Inspector 仍是数据库反射入口；
- SQLGlot 仍是 SQL AST 和只读判断入口；
- Agent Event、RunItem、Observation 和 Artifact 仍是耐久状态；
- RFC 9457 仍是 HTTP 错误合同；
- 不增加 provider 名称分支、兼容 mapper、第二套 Sidecar、第二套 SQL parser 或错误 fallback 链。

## 2. 实施顺序

| 阶段 | 范围 | 前置条件 | 完成门禁 |
| --- | --- | --- | --- |
| S1 | BC-06 公开错误可信边界 | 无 | 任意 DBFoxError 内部文本不能进入 HTTP、Tool、Observation、Provider output、持久化或 UI |
| S2 | BC-07 终止枚举 + BC-03 多 assistant message | S1 | 只有 completed Turn 可完成；commentary/final 不再合并；中断文本不提交 |
| S3 | BC-05 Model setup 错误结算 | S1、S2 | 凭据、Vault、endpoint 和 provider 创建错误具有稳定 Run/Turn 结算 |
| S4 | BC-02 Schema Inspection 错误分类 | S1 | inspect_catalog/inspect_objects 使用同一公开错误合同 |
| S5 | BC-04 SQL 与 EXPLAIN 只读合同 | 无 | Select/With/Union/Intersect/Except 在安全判断上保持一致 |
| S6 | BC-01 Frozen Runtime 合同 | S1～S5 | 正式 Python、依赖、Frozen Sidecar 与功能 smoke 使用同一版本和锁 |
| S7 | BC-08 规范文档同步 | S1～S6 | 文档、类型、迁移、测试与正式产物合同一致 |

每个阶段必须先通过局部测试，再进入下一阶段。禁止通过静默 skip、continue-on-error 或降低鉴权/安全门禁取得绿色结果。

## 3. 权威模型

### 3.1 公开错误

`engine.app.safe_errors` 是唯一公开错误目录。目录项至少包含：

```text
code
public_message
http_status
retryable
problem_type
title
```

普通 `DBFoxError` 只能携带目录中的固定错误码和内部诊断；内部诊断不得序列化。`ToolInputError` 是唯一允许携带动态公开纠正消息的异常，并且消息必须由 DBFox 自己编写，不能来自 `str(exc)`、驱动、Provider 或远端响应。

未注册错误码统一投影为 `INTERNAL_ERROR`。HTTP、ToolResult、Observation、SSE 和 UI 使用同一目录项，不各自维护字符串映射。

### 3.2 Turn 终止

Turn 终止状态是封闭枚举：

```text
completed
incomplete
failed
cancelled
```

只有 `completed` 可以进入完成判断。终止事件必须唯一且位于流末尾；无终止事件是截断，终止后继续出现 Item 是协议错误。

### 3.3 Assistant message

一个 Turn 可以包含零到多个 assistant message。每个消息独立保存：

```text
output_index
stream_item_id
phase: commentary | final_answer | null
status: completed | incomplete
text
```

`phase` 是 Provider 提供的辅助提示，不是完成的必要条件。`commentary` 永不进入最终答案；显式 `final_answer` 优先；没有显式 phase 时，使用正常完成且可展示的消息。工具调用未结算、Turn 非 completed、消息为空或协议不完整时不能完成。

Agent Event/RunItem 保存每个消息的时间线身份；`AgentMessage` 只保存 Run 的最终对话投影；Provider 原始 output 只用于下一轮 continuation，不作为 DBFox 完成判断模型。

### 3.4 SQL

只读判断只有一个入口。EXPLAIN、TrustGate 和执行路径必须复用同一个 SQLGlot AST 判定。安全性与数据库是否支持对应 EXPLAIN 语法是两个独立结论，不能因为某方言不能 EXPLAIN 就把只读 SQL 判为危险。

### 3.5 Frozen Runtime

仓库根目录 `.sidecar-python-version` 是生产 Sidecar 的唯一 Python 版本来源，并同时控制依赖安装、核心合同测试、PyInstaller 构建、runtime manifest 与 Frozen smoke。

源码环境通过不代表 Frozen 产物通过。正式门禁必须执行 Schema reflection、Agent tool、Result Artifact 重载、鉴权和 Token 扫描。

## 4. 阶段设计与验收

### S1 / BC-06：公开错误可信边界

实现：

1. 扩展 `FixedErrorCode` 和固定错误目录；
2. 让 `DBFoxError` 使用固定错误码，原始诊断只留在内部；
3. ToolRuntime 对 `ToolInputError` 使用明确公开消息；
4. ToolRuntime 对其他 `DBFoxError` 只查询固定目录；
5. 未注册 code 降为 `INTERNAL_ERROR`；
6. HTTP、Tool、Observation、SSE 共用 code/message/retryable；
7. 日志只记录 code、异常类型和 keyed fingerprint。

必测：在异常消息中注入唯一 sentinel，验证 HTTP body、ToolResult、Observation、Provider function output、AgentEventRecord、AgentToolInvocation、SSE、UI 和诊断包全部零命中。

回滚：整体回滚本阶段提交；不保留按旧 message 读取的兼容分支。

### S2 / BC-07 + BC-03：Turn 与消息合同

实现：

1. 使用 `TurnTermination` 替换任意字符串 `finish_signal`；
2. FINISH 必须携带枚举，assembler 要求恰好一次合法终止；
3. OpenAI Adapter 按官方事件映射 completed/incomplete/failed/cancelled；
4. `ModelTurnResult` 改为有序 messages；
5. assembler 以 message item ID/output index 独立组装；
6. RunLoop 为每个 message 维护独立 live revision 与耐久 RunItem；
7. Terminalizer 从 eligible messages 产生最终文本；
8. Alembic 删除旧 `draft_text/message_phase/finish_signal`，写入规范 termination；
9. 历史未知 finish 值不猜测为 completed。

必测：无 phase 正常文本、显式 final、commentary+final、多 phase=None、工具调用、中断、取消、incomplete、failed、未知枚举、多轮工具后最终文本、进程恢复和 SSE replay。

回滚：整体回滚代码与 Alembic 迁移；禁止保留新旧字段双读。

### S3 / BC-05：Model setup 错误结算

实现：

1. admission 只验证非秘密偏好与 opaque credential reference；
2. Vault secret 仅在 Provider 边界解析；
3. model factory 进入 Turn 的 try/settle 范围；
4. 配置/Vault/凭据错误使用固定错误码结算 Turn 和 Run；
5. 401/403、配置错误不重试；429/5xx/网络错误受 Provider retry budget 控制；
6. 失败 Run 不复活，用户修复设置后创建新 Run。

必测：未配置凭据、凭据在 admission 后被删除、Vault 不可用、非法 endpoint、401/403、429、超时、取消和恢复。

### S4 / BC-02：Schema Inspection

实现：

1. 保留 SQLAlchemy Inspector；
2. 移除独立 Schema error code 字符串事实源；
3. inspect_catalog/inspect_objects 使用同一分类函数；
4. 数据源、凭据、连接、SSH、TLS、文件路径和未知异常具有稳定 code；
5. 原始 SQLAlchemy/驱动异常只写 fingerprint。

必测：两条入口对相同异常产生相同 code；Frozen MySQL 五表反射；错误不泄漏 DSN/密码；未知异常不可重试。

### S5 / BC-04：SQL/EXPLAIN

实现：

1. 暴露一个“解析单条只读 Query”入口；
2. TrustGate、执行和 EXPLAIN 复用该 AST；
3. 方言 EXPLAIN 能力单独返回，不复制只读白名单；
4. 不使用正则或第二套 parser。

必测：Select、With、Union、Intersect、Except、Subquery、多语句、DML、DDL、危险副作用节点及 MySQL/Postgres/SQLite 差异。

### S6 / BC-01：Frozen Runtime

实现：

1. CI 只保留一个生产 Sidecar Python 版本来源；
2. 相同解释器先运行 Engine 核心合同再构建；
3. runtime manifest 记录 Python、SQLite 和关键 Python 包版本及锁文件哈希；
4. Frozen smoke 使用临时 runtime/data/vault；
5. 执行 health/token、Schema、查询、Artifact、重启重载和最小 Agent 多轮；
6. Windows 发布门禁使用 Frozen Windows Sidecar 对临时 MySQL 验证；
7. macOS/Linux 没有真实 Runner 时明确未验证。

必测：错误 Token 拒绝、正确 Token 通过、旧 Token 失效、正式 bundle 零开发 Token、Frozen Schema/Result/Agent 全链路通过。

### S7 / BC-08：规范同步

更新：

- Agent Runtime 文档；
- Item protocol；
- Provider-neutral Turn ADR；
- Error boundary ADR；
- Release contract；
- OpenAPI/前端生成类型（仅通过正式生成器）。

文档必须明确：phase 可选、termination 必需、多 message 有独立身份、错误文本默认不可信、Frozen 产物必须独立验证。

## 5. 禁止项

- 不按 Provider 名称判断完成；
- 不伪造 `phase=final_answer`；
- 不将未知终止状态映射为 completed；
- 不长期保留 `text/messages` 或 `finish_signal/termination` 双轨；
- 不默认公开 `DBFoxError.message`；
- 不增加第二套错误目录；
- 不自写数据库反射或 SQL parser；
- 不使用全量 hidden-import/collect-submodules 掩盖 PyInstaller 问题；
- 不以源码测试代替正式产物测试；
- 不让测试辅助接口进入 Production。

## 6. 每阶段交付记录

每阶段完成后在 PR/实施报告记录：

```text
阶段：
修改文件：
权威模型：
删除的旧路径：
新增依赖：无/名称与理由
兼容层：无/范围与删除条件
执行命令：
测试结果：
未验证项：
回滚方式：
```

## 7. 实施进度

### S1 / BC-06：完成

- 权威模型：`engine.app.safe_errors` 固定公开目录；仅 `ToolInputError` 允许 DBFox 编写的动态纠正消息。
- 删除的旧路径：ToolRuntime 不再默认公开任意 `DBFoxError.message`。
- 新增依赖：无。
- 兼容层：无。
- 验证：Tool/HTTP 边界定向测试通过；未知错误码降为 `INTERNAL_ERROR`。

### S2 / BC-07 + BC-03：完成

- 权威模型：`TurnTermination` 封闭枚举；每个 assistant output 以 `output_index` 独立持久化。
- 删除的旧路径：`draft_text`、`message_phase`、`finish_signal` 及聚合 draft 双轨。
- 新增依赖：无。
- 兼容层：无；Alembic 只迁移规范终止值，未知旧值不猜测。
- 验证：后端 74 项、前端 10 项定向合同测试通过。

### S3 / BC-05：完成

- 权威模型：配置、Vault、Endpoint 与 Provider 错误均投影到固定公开目录；SDK 原始正文只用于受控诊断指纹。
- 删除的旧路径：model factory 不再位于 Turn settle 的异常边界之外；401/403 不再合并为同一语义；账单/额度 429 不再错误重试。
- 新增依赖：无；复用 OpenAI 官方 SDK 类型化异常、HTTP 状态和结构化 `error.code`。
- 兼容层：无；不按 Provider 名称或报错文本分类。
- 验证：BC-05 定向 35 项、交叉回归 81 项通过；`git diff --check` 通过。当前环境未安装 Ruff，未执行 Ruff。
- 额外闭环：`TurnStreamAssembler` 在消费失败时显式关闭上游迭代器，保证 SDK stream/client 的 `finally` 立即执行。

### S4 / BC-02：完成

- 权威模型：SQLAlchemy Inspector 保持唯一反射入口；`CatalogIntrospector._run_inspection` 是目录和对象检查共享的异常投影边界；错误码来自 `FixedErrorCode`。
- 删除的旧路径：删除独立 `SchemaInspectionErrorCode`；删除根据 `ssh_enabled/ssl_enabled` 猜测失败来源的分类；`inspect_objects` 不再绕过目录检查的分类合同。
- 新增依赖：无；复用 SQLAlchemy Inspector、Python 类型化异常和现有 ConnectionFactory。
- 兼容层：无。
- 验证：Schema/Tool/Connectivity/Tunnel 定向与交叉回归 109 项通过，随后源头类型回归 54 项通过；DSN/密码 sentinel 在公开异常和日志中零命中。
- 失败来源：凭据、SSH、TLS 使用 `DataSourceConnectionError` 的窄化子类型；普通网络错误不冒充 SSH/TLS；SQLite/DuckDB 文件错误按已知方言投影；未知异常降为 `SCHEMA_INSPECTION_FAILED`。

### S5 / BC-04：完成

- 权威模型：`engine.sql.readonly_query.parse_single_readonly_query` 是单条、无副作用 Query 的唯一解析合同；SQLGlot AST 是唯一语法事实源。
- 删除的旧路径：删除 EXPLAIN 的 Select/Union 私有白名单、SafetyService 的重复解析、TrustGate 的二次解析，以及按 SQL 字符串前缀决定 dry-run 的路径。
- 副作用边界：除 DML/DDL、锁和文件导出 AST 外，统一拒绝 PostgreSQL `nextval/setval`、advisory lock 以及 MySQL user lock 等会改变持久或会话状态的函数。
- 新增依赖：无；复用 SQLGlot、SQLAlchemy ConnectionFactory 和各数据库官方 EXPLAIN 能力。
- 兼容层：无；Guardrail、Safety、EXPLAIN 和 SQL-backed view 直接使用同一合同。
- 验证：146 项相关测试通过；SQLite 真实 `EXPLAIN QUERY PLAN` 覆盖 SELECT、WITH、UNION、INTERSECT、EXCEPT；嵌套 DELETE、多语句、行锁、文件导出与状态函数均被拒绝。
- 官方依据：PostgreSQL 官方说明 `nextval/setval` 改变序列状态且不回滚、advisory lock 改变会话/事务锁状态；MySQL 官方说明 `GET_LOCK/RELEASE_LOCK` 操作 server-level user lock。

### S6 / BC-01：完成

- 权威模型：`.sidecar-python-version` 固定生产 Python `3.14.6`；`requirements-build.lock` 固定发布依赖；runtime manifest schema 2 绑定解释器、锁文件 SHA-256、关键包版本、SQLite 来源和 Sidecar 哈希。
- 删除的旧路径：CI 不再维护第二份 `SIDECAR_PYTHON_VERSION`；ORM 不再给所有数据源注入 MySQL `3306`；数据源响应不再把可空网络字段映射为空字符串；Frozen 产物不再只验证 health。
- 新增依赖：无；复用 `actions/setup-python` 的 `python-version-file`、uv 精确同步、PyInstaller hidden-import 和现有正式 API。
- 兼容层：无。SQLGlot 官方实现通过 `importlib` 动态加载方言，因此仅声明 DBFox 支持的 `mysql/postgres/sqlite` 三个 hidden imports，没有全量收集方言或运行时 fallback。
- 数据库迁移：`12ab34cd56ef` 允许 SQLite 文件型数据源的 host/port/username 为 NULL；网络默认端口仍只由 `ConnectionProfile` 按方言生成。
- 验证：45 项 SQLite API/迁移/初始化测试、57 项构建和 SQL 合同测试通过；临时空库完整升级至 head 且 `alembic check` 无差异；Windows x64 64 MB Frozen Sidecar 构建成功。
- Frozen smoke：真实可执行文件完成 health、正确/错误/旧 Token、SQLite 数据源创建、Schema sync、只读 SQL、Result Artifact 分页、同会话两次耐久 Run 以及进程重启后的数据和历史重载，结果 `status=ok`、`durable_turns=2`。
- 已确认并修复的产物专属缺陷：SQLGlot 方言动态导入未被 PyInstaller 捕获，导致 Frozen Console SQL 返回 `POLICY_PARSE_ERROR`；显式打包三个受支持方言后真实 smoke 通过。
- 平台边界：本轮真实构建与运行证据仅覆盖 Windows x64；macOS/Linux 仍需各自 Runner 验证，不从 Windows 结果推断通过。

### S7 / BC-08：完成

- 规范同步：更新 Agent Runtime、RunItem 协议、公开错误合同、工程质量门禁和跨平台发布矩阵；明确 phase 可选、termination 必需、多 message 独立、错误文本默认不可信以及 Frozen 证据的平台边界。
- 类型同步：通过 `npm run generate:api` 从 FastAPI OpenAPI 重新生成前端 SDK/Zod；RunItem 判别联合要求显式 `type`，SQLite 网络字段保持真实 nullable，不手改生成文件。
- 后端验证：全量 `941 passed, 2 skipped`；最终 Agent/Conversation/OpenAPI/TrustGate/Icon 定向回归 `169 passed, 1 skipped`。
- 前端验证：Vitest `69 files / 292 tests`、ESLint、设计令牌合同、测试 TypeScript、生产构建、开发 Token 扫描和 bundle budget 全部通过。
- Rust 验证：`cargo fmt --check`、Clippy `-D warnings`、`cargo test --locked`（21 项）全部通过。
- Python 静态验证：compileall、pyflakes、mypy（248 个 source files）和 `git diff --check` 通过。
- 附带收敛：旧 TrustGate 测试直接迁移至唯一 `guardrail_check_with_ast` 合同，没有恢复兼容别名；Windows ICO 所有声明帧同时满足透明安全边距与高画布占用。
- 未验证：opt-in 真实 Responses 合同未提供外部凭据，按设计未运行；macOS/Linux 未在本地真实构建或运行。
