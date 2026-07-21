# DBFox 代码审查与整改记录

> 状态：Phase 1–3 代码实施完成并进入最终严格回归；真实数据库、外部服务与安装包验收待发布环境执行
> 审查基线：2026-07-11 的全仓 CodeGraph 审查（620 个文件、主要入口和核心调用链）
> 整改原则：以长期正确的边界和可验证的状态机为目标；不保留会降低安全性或一致性的兼容路径；历史运行态可按版本化迁移/重置处理。

## 1. 项目与审查范围

DBFox 是 local-first 的 AI 数据库桌面工作台。Tauri 负责桌面宿主和 Python sidecar，React/TypeScript 提供 UI，FastAPI/SQLAlchemy/Alembic 提供本地服务和元数据存储，Agent 基于 LangGraph，连接 MySQL、PostgreSQL、SQLite 与 DuckDB。

审查覆盖以下关键边界：

- sidecar 启动、loopback 鉴权、桌面 CSP 与外链行为；
- LLM 凭据、LangGraph checkpoint、LangSmith 和日志；
- 数据源、SSH/TLS、Schema 探查与 catalog 同步；
- SQL guardrail、只读执行、导出、备份/恢复；
- Agent 事件、审批、取消、checkpoint 和会话持久化；
- Alembic、SQLite 完整性、运行时路径、依赖、测试和 CI。

审查没有对真实生产数据库、真实 SSH 堡垒机或外部 LLM 发起调用；此类集成结论在本记录中均应视为“待真实环境验证”。

## 2. 原始风险结论与整改状态

| 优先级 | 风险 | 原始位置 | 整改状态 | 长期处理方向 |
| --- | --- | --- | --- | --- |
| P0 | LLM API Key 写入 checkpoint、浏览器/私有配置链路 | `engine/agent/app/request_context.py`、`engine/agent_core/checkpointer.py`、`desktop/src/lib/llmConfig.ts` | 已完成 | OS Credential Vault 仅存 secret；业务与 checkpoint 只携带 opaque credential ID；旧运行态版本化清除 |
| P0 | 原地逻辑恢复可能使目标处于半恢复状态 | `engine/backup.py`、`engine/schemas/backup.py`、`engine/api/backup.py` | 已完成 | 创建独立 MySQL 目标、校验恢复结果、按 datasource generation CAS 原子切换；失败删除隔离目标并保留原连接 |
| P1 | 采集失败被误当权威空 Schema，可能删除 catalog | `engine/environment/schema_introspector.py`、`schema_catalog_sync.py` | Phase 1 已处理 | 只允许完整的 authority snapshot 执行删除；采集失败保留原 catalog |
| P1 | SSH/TLS 路径分叉、隧道失败可直连 | 数据源、Schema、inspect、tunnel、SQL 路径 | 已完成 | `ConnectionProfile` + `ConnectionFactory` 是唯一连接边界；SSH 配置时 fail closed |
| P1 | 自定义 LLM `api_base` 可造成 SSRF/明文传输 | `engine/llm/config.py`、provider | 已完成 OpenAI-compatible 主链路；LangSmith 自定义 endpoint 的 SDK 传输仍待外部验证 | 远程仅 HTTPS，loopback HTTP 显式允许；解析后拒绝私网并将实际 TCP 连接固定到已准入 IP，保留原 Host/SNI |
| P0 | Agent 事件可能先于 run 落库，持久化失败后仍向 SSE 发事件 | `engine/agent/app/service.py`、`persistence_coordinator.py` | 已完成，legacy runtime 已删除 | 新 `agent_runtime` 使用 run 状态机、事务 outbox 和提交后 replay |
| P0 | Approval/取消/完成无 CAS，可能重复恢复或取消被完成覆盖 | `engine/agent_core/persistence/*`、`engine/api/agent.py` | 已完成 | 版本化条件更新、审批原子 consume、run-local cancel token 和 terminal state 不可逆 |
| P1 | 每次运行创建 checkpointer，checkpoint 无保留策略且状态过大 | `engine/agent_core/checkpointer.py` | 已完成 | lifespan 所有权、run-specific namespace、显式关闭；TTL、终态 run 数量和磁盘容量三重上限，并清理投影载荷 |
| P1 | SQL “只读”只靠 AST，结果截断语义不可靠 | executor/dialects/serializer | 已完成代码整改 | 原生只读事务 + 最小权限；hard cap、额外行探测和独立截断标志 |
| P1 | CSV export 绕开 timeout/cancel/audit | `engine/sql/execution/streaming_executor.py` | 已完成 | 导出复用执行 deadline、取消注册和受控流式写入 |
| P1 | 前端 SSE parser、定向取消、数据源切换存在竞态 | conversation/datasource stores | 已完成 | run ID 定向取消、持久 outbox replay、stateful SSE parser、datasource generation fencing |
| P2 | `create_all`/stamp 与 Alembic 漂移，SQLite FK 未强制 | `engine/db.py`、migrations | Phase 1 已处理 | Alembic 成为唯一 schema source；新库只 upgrade + verify；SQLite 启用 FK、WAL、secure delete |
| P2 | CSV 公式注入、日志/诊断长期明文、无轮转 | export/redactor/diagnostics | 已完成代码整改 | 统一安全输出策略、数据分类、保留期和轮转上限 |
| P1 | 依赖未锁定，CI 未覆盖完整后端/Rust/打包 | requirements、CI、build | 已完成仓库门禁；安装包 smoke 待目标环境执行 | hash lock、固定 Action SHA、Python/Node/Rust 审计和质量门禁 |
| P2 | 会话/事件未分页，Schema map N+1，前端主包和缓存无预算 | persistence/environment/desktop | 已完成本阶段整改 | cursor pagination、批量加载、LRU、路由级拆包与体积预算 |

### 2.1 凭据与仓库历史处置记录

- 当前工作树曾发现一个被忽略的本地 `.env.e2e`，其中含明文 LLM 凭据；它不在 Git index、没有构建引用，已删除，当前工作树只保留不含 secret 的 `.env.example`。
- 历史测试文件中曾存在密钥形态的固定字符串；无法仅凭字符串形态判断它是否曾是有效凭据，因此本文不将其表述为“已确认密钥泄露”。相关文件与 checkpoint 产物已从可达 branch/tag 历史中移除并强制更新远端 refs。
- 当前工作树、Git index 与重写后的可达历史扫描均无该形态命中。GitHub 旧 PR refs/cache 的服务端清理已提交支持请求，属于托管平台侧的残留处置，不影响当前构建产物。
- 不在本文、提交信息、日志或测试输出中记录明文 key、其片段或可逆编码。

### 2.2 Git 历史清除执行记录

1. 在独立镜像仓库中删除历史测试文件和 checkpoint 产物，不在包含业务改动的工作树中重写。
2. 扫描重写后的 branch/tag 后 force-push；旧 clone 不得继续向远端推送，当前开发 clone 的 push URL 已禁用。
3. GitHub Support 已收到旧 PR refs/cache 清理请求；在平台确认前，仅把这部分标记为“托管平台缓存待清理”。

## 3. 已落实的整改（以测试和迁移为准）

### 3.1 凭据与运行期数据边界

- 移除 LangSmith 本地 `.env`/sidecar 环境变量回退，LLM/LangSmith 凭据必须来自 credential vault。
- 删除私有运行目录中的历史明文 LangSmith 配置，并将运行时根目录固定到用户私有应用数据目录；无法创建私有目录时 fail closed，绝不回退到仓库目录。
- `.env` 改为严格的非敏感调优白名单，而非按变量名猜测密钥的 deny-list；Provider key、数据库 URL、运行时路径、token 和安全绕过开关只能由受控父进程或 credential vault 提供。
- SPIDER/Qwen 基准和真实 LLM E2E 均不再接收 `--api-key`、`QWEN_API_KEY` 或 `DBFOX_LLM_API_KEY`；它们只接收 OS credential vault 中已有的 opaque credential ID。
- 引入版本化运行态重置：清理 checkpoint、旧 sidecar 配置、旧备份和本地敏感运行态；保留的元数据会清除 credential 引用并标记为需要重新授权。
- LLM telemetry migration 删除 `prompt_text`、`response_text`、`error_message` 等可携带明文内容的字段，保留不可逆的 HMAC request fingerprint 与固定错误码。
- 删除不再被生产代码引用的本地 AES 凭据层，凭据边界统一到 OS credential vault。（以实际删除提交和回归测试为完成条件。）

### 3.2 本地元数据库和迁移

- `engine/db.py` 不再使用 `Base.metadata.create_all`、表名猜测或无条件 stamp；新库经 Alembic `upgrade` 后验证版本、表、索引和 FK。
- SQLite 启用 `foreign_keys`、WAL/busy timeout 和 secure delete；增加 FTS 修复迁移和环境/数据源外键环消除迁移。
- 确认令牌从进程内/临时 SQLite 存储切换为迁移管理的数据表，并通过条件删除实现一次性消费。
- 测试运行时强制使用临时私有目录，禁止测试启动时清理真实 AppData 或工作区。

### 3.3 数据源、Schema 与执行安全

- 引入 secret-free 的 `ConnectionProfile` 和 `ConnectionFactory`；TLS/SSH/凭据 ID 进入明确的 profile，secret 只在 vault 解析后的短作用域中使用。
- 网络 driver 与连接池 creator 已移入 `engine.connectivity` 私有实现；SQL 层不再保留可绕过 `ConnectionFactory` 的 MySQL/PostgreSQL 直连入口。
- Schema introspection 只在完整读取成功后产生 `AuthoritativeInventory`；采集失败产生 typed error，catalog 同步不会删除既有记录。
- SQL 公共读路径使用数据库原生只读事务：MySQL `START TRANSACTION READ ONLY`，PostgreSQL `BEGIN READ ONLY` + local timeout，SQLite 强制只读连接。
- 增加 DuckDB 的显式依赖、打包 hidden import 与连接/profile 支持。（以所有调用路径收口到工厂为完成条件。）

### 3.4 备份/恢复

- 移除 `allow_fallback`、Python simple SQL export/import 和 API body/query 兼容入口。
- `POST /backups/{id}/restore` 要求调用方提交期望的 datasource generation 和精确确认文本；先校验备份 checksum，再创建全新隔离数据库并通过受控绝对路径 `mysql` 客户端恢复。
- 恢复完成后通过 `information_schema` 校验隔离目标，并以 `WHERE connection_generation = :expected` 的 CAS 更新数据库名与 generation；冲突或失败时删除隔离目标，原数据库和元数据保持不变。
- `restore_operations` 持久记录成功/失败、目标名、期望与切换后的 generation；旧数据库不会在切换事务中删除，保留回滚窗口。
- 备份仅使用由受控父进程设置的绝对 `DBFOX_MYSQL_CLIENT_DIR` 下的非链接 `mysqldump`；子进程仅接收 `MYSQL_PWD`、`PATH` 和 locale，dump 通过私有 staging 文件原子发布。
- 备份记录只保存私有 `backups/` 根下的 canonical relative path；绝对路径、遍历路径、链接和非普通文件一律隐藏或拒绝，失败时删除部分文件并清空 `file_path`。

### 3.5 桌面安全基线

- 移除禁用 SmartScreen 和全局 proxy bypass 的 Tauri 参数。
- CSP 限制网络到应用自身和 loopback engine；移除远程字体加载。
- 外链只允许显式用户操作打开绝对 HTTPS URL，并使用 `noopener,noreferrer`。

## 4. 分阶段执行计划

### Phase 1：安全、持久化与连接基础

实施状态：代码与本地回归完成。

目标是消除已确认的 secret、迁移和数据损坏风险，并建立唯一可信的运行期/连接边界。

完成标准：

1. 扫描不到已知 sentinel secret、生产 plaintext LLM telemetry 字段、或 `.env`/sidecar 注入路径。
2. 仅 Alembic 可创建和升级 metadata 数据库，fresh upgrade 与 `alembic check` 一致。
3. Schema 失败不能改变 catalog；SSH/TLS 数据源不能偷偷直连。
4. 备份/恢复不存在 fallback，失败不会留下可恢复的半成品。
5. 所有生产连接路径通过 `ConnectionFactory`，并覆盖 SQLite/MySQL/PostgreSQL/DuckDB。

### Phase 2：Agent durable runtime

实施状态：完成。旧 `engine.agent.runtime`、`engine.agent.app` 和 `engine.agent_core.persistence` 运行时已删除；原有 LangGraph 图、节点、工具、记忆与业务决策逻辑保留并接入 v2 生命周期。

目标是取代 legacy coordinator/event store 的“尽力写入”模型，建立可重放、可取消、可幂等恢复的 durable run。

设计约束：

1. `create_run` 与 sequence 1 的 `agent.run.started` outbox 在同一事务提交后才对 SSE 可见。
2. 所有 run transition 都是 `UPDATE ... WHERE version = :expected AND status IN (...)`；无行数即冲突，terminal state 不可逆。
3. approval 与 `waiting_approval -> running` 在单事务内消费，绑定 checkpoint ID/version/expiry，并只能成功一次。
4. 每个 run 使用自己的 checkpoint namespace/thread ID；checkpointer 是 lifespan 资源，具备关闭与 retention。
5. cancel 先持久化条件状态和 outbox，再通过 run 的 execution ID 调用真实 QueryRegistry/运行 token；完成不得覆盖 cancelling/cancelled。
6. SSE 只能 replay 已提交 outbox，并支持 `after_sequence`；answer delta 必须可回放或明确采用受控合并策略。

### Phase 3：可观测性、工程化、性能与 UI 一致性

实施状态：代码与本地 Python/Node/Rust 门禁完成；真实外部服务和安装包 smoke 不属于本地确定性回归，仍需发布环境验收。

目标是让安全边界持续可验证，并为长期数据量和发布流程设置上限。

- 统一 URL/SSRF policy、日志/SQL/CSV 安全输出、日志轮转和 retention；
- 将导出接入 deadline/cancel/audit；收敛 SQL limit/row/column/byte 语义；
- 增加会话/事件分页、Schema 批量查询、checkpoint/preview LRU；
- 完成可靠的 SSE parser、按 run 的前端取消、datasource generation；
- lockfile/SBOM/依赖审计、GitHub Actions 最小权限、Python/Rust/desktop/sidecar/installer 全链路门禁；
- LangSmith 可从人工/API 负反馈导入确定性回归 case；模型自产反馈不会自动进入基准集；
- LangGraph SQLite checkpoint 具备 30 天 TTL、500 个终态 run 和 512 MiB 默认容量上限，均可通过非敏感环境变量收紧；
- 生命周期异步化并报告 sidecar 启动状态，继续收紧 CSP（移除 inline script/style 前先完成 UI 改造）。

## 5. 验收与发布门禁

每个阶段结束前至少应执行：

```powershell
python -m pytest engine/tests engine/agent/tests engine/evaluation/tests
python -m alembic check
python -m mypy --no-warn-unused-configs --follow-imports=skip engine build_sidecar.py
cd desktop; npm test; npm run lint; npm run build
cd desktop/src-tauri; cargo fmt --check; cargo clippy --locked -- -D warnings; cargo test --locked
```

此外必须包含以下故障注入：密钥 sentinel 全目录扫描、Schema 网络/TLS/SSH 失败、并发 approval resume、cancel 与 finalize 竞争、断开 SSE 后 `after_sequence` replay、原生客户端缺失、fresh Alembic upgrade，以及打包桌面端启动 smoke。

## 6. 最终本地验收结果（2026-07-13）

- Python 全量确定性回归：`1143 passed, 2 skipped`，并以 `-W error` 执行，零 warning、零失败。此前的 325/332 条 warning 根因（Starlette 测试客户端依赖、SQLite datetime adapter、资源句柄和 LangGraph 运行时注解）已逐项修复。
- 前端：Vitest `77 files / 426 tests` 全部通过；ESLint 零错误、零 warning；生产构建与 bundle budget 通过。
- Rust（MSVC）：`cargo fmt --check`、`cargo clippy --locked --all-targets -- -D warnings` 通过；`cargo test --locked` 9 项通过。
- 数据库：唯一 Alembic head/current 均为 `c1d2e3f4a5b6`；`alembic check` 报告无新增迁移操作。
- Python 构建与类型：`compileall` 通过；CI mypy 覆盖 `engine` 与 `build_sidecar.py`，本地检查 291 个源文件零问题。
- 安全静态证据：当前工作树未发现高置信 API key 形态；仅保留 `.env.example`；生产代码无旧 Agent runtime 导入、无直接 LLM key 环境变量解析、无生产 `unsafe-inline`。
- 仓库已使用 Python 3.12 `.venv` 从 `requirements-dev.lock --require-hashes` 安装，`pip check` 无冲突；共享 Anaconda 全局环境不再作为开发、测试或发布判断依据。

## 7. 剩余发布阻断项与待验证风险

以下事项需要仓库管理员、凭据所有者或真实发布环境，不能由当前工作树内的代码修改代替：

1. 在真实 MySQL 上验证 `mysqldump`/`mysql`、大备份、权限不足、校验失败、generation 冲突以及切换后的连接池刷新；本地自动化测试使用故障注入，没有连接生产数据库。
2. 在真实 PostgreSQL、SSH/TLS、DuckDB 和外部 LLM 环境执行故障注入与权限最小化验证。
3. 用正式 MSVC/Tauri 发布环境执行 sidecar + 安装包 smoke、多实例启动、升级和卸载验证。
4. 等待 GitHub Support 确认旧 PR refs/cache 的平台侧清理；这不是当前 branch/tag 或构建产物的阻断项。
5. LangSmith 自定义 endpoint 由第三方 SDK 建立最终连接；当前已做 URL 准入，但其 DNS 解析/重绑定行为需结合 SDK 版本做真实网络验证。
6. `cargo audit` 的 GTK/glib 传递依赖仍有 RustSec unsound/unmaintained 警告；桌面依赖升级时持续跟踪并在上游可迁移时移除该链路。
