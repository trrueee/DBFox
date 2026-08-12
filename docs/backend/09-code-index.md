# 卷九：后端源码索引

> 文档类型：代码索引
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：`engine/` 生产入口、数据模型和关键测试
>
> 用法：按“用户动作 → 领域入口 → 状态所有者 → 测试”定位；不要只凭文件名猜职责。

## 1. 顶层入口

| 能力 | 生产入口 | 关键测试 |
| --- | --- | --- |
| FastAPI/生命周期/鉴权 | [`engine/main.py`](../../engine/main.py) | [`test_startup.py`](../../engine/tests/test_startup.py)、[`test_api_security_contracts.py`](../../engine/tests/test_api_security_contracts.py) |
| metadata Engine/Alembic | [`engine/db.py`](../../engine/db.py) | [`test_db_init.py`](../../engine/tests/test_db_init.py)、[`test_migrations.py`](../../engine/tests/test_migrations.py) |
| ORM | [`engine/models.py`](../../engine/models.py) | Repository/迁移测试 |
| Runtime Token | [`engine/engine_runtime/credentials.py`](../../engine/engine_runtime/credentials.py) | [`test_runtime_credentials.py`](../../engine/tests/test_runtime_credentials.py) |
| Public errors | [`engine/app/safe_errors.py`](../../engine/app/safe_errors.py)、[`engine/problem_details.py`](../../engine/problem_details.py) | [`test_global_error_boundary.py`](../../engine/tests/test_global_error_boundary.py) |

## 2. API 路由

| 用户动作 | 模块 |
| --- | --- |
| 数据源 CRUD | [`api/datasources/crud.py`](../../engine/api/datasources/crud.py) |
| 数据源健康 | [`api/datasources/health.py`](../../engine/api/datasources/health.py) |
| metadata/schema | [`api/datasources/metadata.py`](../../engine/api/datasources/metadata.py)、[`schema.py`](../../engine/api/datasources/schema.py) |
| 查询 | [`api/query.py`](../../engine/api/query.py) |
| 创建/读取对话 | [`api/conversations.py`](../../engine/api/conversations.py)、[`conversation_queries.py`](../../engine/api/conversation_queries.py) |
| 输入/取消/审批命令 | [`api/conversation_commands.py`](../../engine/api/conversation_commands.py) |
| SSE | [`api/conversation_stream.py`](../../engine/api/conversation_stream.py) |
| Agent Result | [`api/agent_results.py`](../../engine/api/agent_results.py) |
| 凭据 | [`api/credentials.py`](../../engine/api/credentials.py) |
| 备份 | [`api/backup.py`](../../engine/api/backup.py) |
| 诊断 | [`api/diagnostics.py`](../../engine/api/diagnostics.py) |
| 测试数据 | [`api/test_data.py`](../../engine/api/test_data.py) |

## 3. 数据库与安全

| Symbol/能力 | 文件 |
| --- | --- |
| `build_metadata_engine` / `initialize_metadata_database` | [`db.py`](../../engine/db.py) |
| SQLite migration mutex | [`migrations/sqlite_mutex.py`](../../engine/migrations/sqlite_mutex.py) |
| Agent short write transaction | [`agent/repositories/write_transaction.py`](../../engine/agent/repositories/write_transaction.py) |
| CredentialVault | [`security/credential_vault.py`](../../engine/security/credential_vault.py) |
| CredentialLeaseSaga | [`security/credential_lease.py`](../../engine/security/credential_lease.py) |
| Security audit | [`security/audit.py`](../../engine/security/audit.py) |
| Runtime reset | [`security/runtime_reset.py`](../../engine/security/runtime_reset.py) |
| Error redaction | [`policy/redactor.py`](../../engine/policy/redactor.py) |
| Error sanitizer | [`policy/error_sanitizer.py`](../../engine/policy/error_sanitizer.py) |
| Sensitivity | [`policy/sensitivity.py`](../../engine/policy/sensitivity.py) |

## 4. 连接与 Catalog

| Symbol/能力 | 文件 |
| --- | --- |
| ConnectionProfile | [`connectivity/profile.py`](../../engine/connectivity/profile.py) |
| ConnectionFactory | [`connectivity/factory.py`](../../engine/connectivity/factory.py) |
| DatasourceResourceLifecycle | [`connectivity/lifecycle.py`](../../engine/connectivity/lifecycle.py) |
| pool resources | [`connectivity/_pools.py`](../../engine/connectivity/_pools.py)、[`resources.py`](../../engine/connectivity/resources.py) |
| tunnel | [`tunnel.py`](../../engine/tunnel.py) |
| Authoritative Inventory | [`environment/authoritative_inventory.py`](../../engine/environment/authoritative_inventory.py) |
| Catalog introspection | [`environment/catalog_introspector.py`](../../engine/environment/catalog_introspector.py) |
| SchemaCatalogSync | [`environment/schema_catalog_sync.py`](../../engine/environment/schema_catalog_sync.py) |
| ER diagram | [`environment/er_diagram.py`](../../engine/environment/er_diagram.py) |

## 5. SQL

| 能力 | 文件 |
| --- | --- |
| Parser | [`sql/parser.py`](../../engine/sql/parser.py) |
| Dialect context | [`sql/dialect_context.py`](../../engine/sql/dialect_context.py) |
| Dialects | [`sql/dialect/`](../../engine/sql/dialect/) |
| Safety service | [`sql/safety/service.py`](../../engine/sql/safety/service.py) |
| Bound parameters | [`sql/bound_parameters.py`](../../engine/sql/bound_parameters.py) |
| Guardrail | [`sql/guardrail.py`](../../engine/sql/guardrail.py) |
| Trust gate | [`sql/trust_gate.py`](../../engine/sql/trust_gate.py) |
| Readonly | [`sql/readonly_query.py`](../../engine/sql/readonly_query.py) |
| Permission probes | [`sql/permissions/`](../../engine/sql/permissions/) |
| Executor | [`sql/executor.py`](../../engine/sql/executor.py) |
| Streaming executor/export | [`sql/execution/`](../../engine/sql/execution/) |
| Row serializer | [`sql/row_serializer.py`](../../engine/sql/row_serializer.py) |
| Result limits | [`sql/result_limits.py`](../../engine/sql/result_limits.py) |
| ResultViewService | [`sql/result_view/service.py`](../../engine/sql/result_view/service.py) |
| SQL-backed view | [`sql/sql_backed_view.py`](../../engine/sql/sql_backed_view.py) |

## 6. Agent 调度与循环

| Symbol | 文件 | 作用 |
| --- | --- | --- |
| SessionCoordinator | [`agent/coordinator.py`](../../engine/agent/coordinator.py) | 有界调度、lease、heartbeat、DB 扫描 |
| RunLoop | [`agent/loop.py`](../../engine/agent/loop.py) | 多 Turn 状态机 |
| AgentDefinition | [`agent/definition.py`](../../engine/agent/definition.py) | 工具组、预算、版本和模式 |
| PromptAssembler | [`agent/prompt.py`](../../engine/agent/prompt.py) | Prompt 组装 |
| CompletionPolicy | [`agent/completion.py`](../../engine/agent/completion.py) | complete/continue/repair/fail |
| Terminalizer | [`agent/terminalizer.py`](../../engine/agent/terminalizer.py) | 原子终态 |
| RunControl | [`agent/control.py`](../../engine/agent/control.py) | cancel/control |
| ProgressGuard | [`agent/progress_guard.py`](../../engine/agent/progress_guard.py) | 无进展停止 |
| WorkingState | [`agent/working_state.py`](../../engine/agent/working_state.py) | 当前运行工作状态 |
| Plan | [`agent/plan.py`](../../engine/agent/plan.py) | 计划领域逻辑 |
| OpenAIModelAdapter | [`agent/providers/openai.py`](../../engine/agent/providers/openai.py) | Responses 外部协议边界 |

## 7. Agent Repository

| Repository | 文件 | 聚合 |
| --- | --- | --- |
| SessionRepository | [`agent/repositories/session.py`](../../engine/agent/repositories/session.py) | admit、claim、messages、lease |
| RunRepository | [`agent/repositories/run.py`](../../engine/agent/repositories/run.py) | Run/Turn/终态/Memory |
| ToolInvocationRepository | [`agent/repositories/tool.py`](../../engine/agent/repositories/tool.py) | function call 生命周期 |
| EventRepository | [`agent/repositories/events.py`](../../engine/agent/repositories/events.py) | sequence、RunItem、Event、compact |
| ApprovalRepository | [`agent/repositories/approval.py`](../../engine/agent/repositories/approval.py) | 审批 |
| ArtifactRepository | [`agent/repositories/artifact.py`](../../engine/agent/repositories/artifact.py) | Artifact |
| EvidenceRepository | [`agent/repositories/evidence.py`](../../engine/agent/repositories/evidence.py) | Evidence |
| PlanRepository | [`agent/repositories/plan.py`](../../engine/agent/repositories/plan.py) | 计划 |
| QuestionRepository | [`agent/repositories/question.py`](../../engine/agent/repositories/question.py) | 澄清问题 |

## 8. 工具

| 能力 | 文件 |
| --- | --- |
| Built-in registry | [`tools/builtin/registry.py`](../../engine/tools/builtin/registry.py) |
| Catalog tools | [`tools/builtin/catalog.py`](../../engine/tools/builtin/catalog.py) |
| Conversation tools | [`tools/builtin/conversation.py`](../../engine/tools/builtin/conversation.py) |
| Query tools | [`tools/builtin/query.py`](../../engine/tools/builtin/query.py) |
| Result tools | [`tools/builtin/results.py`](../../engine/tools/builtin/results.py) |
| Control tools | [`tools/builtin/control.py`](../../engine/tools/builtin/control.py) |
| Materialization | [`tools/materialization.py`](../../engine/tools/materialization.py) |
| Tool registry | [`tools/runtime/registry.py`](../../engine/tools/runtime/registry.py) |
| ToolRuntime | [`tools/runtime/runtime.py`](../../engine/tools/runtime/runtime.py) |
| ToolExecutor | [`tools/runtime/executor.py`](../../engine/tools/runtime/executor.py) |
| ToolContext | [`tools/runtime/context.py`](../../engine/tools/runtime/context.py) |
| ToolResult | [`tools/runtime/result.py`](../../engine/tools/runtime/result.py) |
| Observation | [`tools/runtime/observation.py`](../../engine/tools/runtime/observation.py) |
| ToolDispatcher | [`agent/tool_dispatcher.py`](../../engine/agent/tool_dispatcher.py) |

## 9. Context、记忆与事件

| Symbol/能力 | 文件 |
| --- | --- |
| ContextAssembler | [`agent/context.py`](../../engine/agent/context.py) |
| ContextBudget | [`agent/context_budget.py`](../../engine/agent/context_budget.py) |
| ConversationRecallService | [`agent/conversation_recall.py`](../../engine/agent/conversation_recall.py) |
| Search index | [`persistence/search_index.py`](../../engine/persistence/search_index.py) |
| RunItem protocol | [`agent/run_item.py`](../../engine/agent/run_item.py) |
| Event domain/live hub | [`agent/events.py`](../../engine/agent/events.py) |
| Projection | [`agent/projection.py`](../../engine/agent/projection.py) |
| SSE API | [`api/conversation_stream.py`](../../engine/api/conversation_stream.py) |
| Evidence | [`agent/evidence.py`](../../engine/agent/evidence.py) |
| Artifact | [`agent/artifact.py`](../../engine/agent/artifact.py) |

## 10. 快速调用链索引

### 10.1 启动

`main.lifespan → initialize_metadata_database → CredentialLeaseSaga.reconcile → SessionCoordinator.start`

### 10.2 提交对话

`conversation command → SessionRepository.admit → commit → coordinator.wake → claim → RunLoop.execute`

### 10.3 模型 Turn

`RunLoop._prepare_turn → ContextAssembler.build → materialize_tools → PromptAssembler → OpenAIModelAdapter → CompletionPolicy/ToolDispatcher`

### 10.4 工具

`function_call → AgentToolInvocation → PolicyGate → ApprovalAuthority → ToolExecutor → ToolRuntime → ToolResult/Observation → function_output`

### 10.5 SQL

`sql_execute_readonly → SqlSafetyService → ApprovalAuthority → ConnectionFactory → executor → Result Artifact → result tools`

### 10.6 完成

`CompletionPolicy → Terminalizer → RunRepository.complete → Message/Evidence/Memory/Event → commit → after_commit publish`

### 10.7 SSE 恢复

`conversation_stream → subscribe live → replay from cursor → snapshot on floor gap → live bounded queue`

## 11. 测试目录地图

- [`engine/tests/`](../../engine/tests/)：API、数据库、连接、SQL、安全、发布边界；
- [`engine/agent/tests/`](../../engine/agent/tests/)：Harness、Provider、工具、上下文、记忆、Repository；
- [`engine/agent/tests/harness/`](../../engine/agent/tests/harness/)：确定性完整场景；
- [`engine/tests/whitebox/`](../../engine/tests/whitebox/)：对安全细节的白盒验证；
- [`engine/tests/fixtures/`](../../engine/tests/fixtures/)：SQL golden 等受控 fixture。

## 12. 搜索建议

有 `.codegraph/` 时优先使用：

```powershell
codegraph explore "SessionRepository.admit to RunLoop.execute call path"
codegraph node SessionCoordinator
```

精确文本再使用：

```powershell
rg -n "class AgentToolInvocation|def complete|after_commit" engine
rg -n "ERROR_CODE|ToolInputError" engine tests
```

先找调用链，再读局部实现；不要从文件名横向扫完整仓库后凭印象改架构。
