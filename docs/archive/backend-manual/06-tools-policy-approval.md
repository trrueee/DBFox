# 卷六：工具、策略、审批与 Observation

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：工具合同、策略、审批、错误和工具观察
>
> 权威合同：[Tool、Context 与 Memory 边界](../architecture/agent-tool-context-memory-contract.md)、[错误边界合同](../architecture/error-boundary-contract.md)
>
> 核心入口：[`engine/tools/`](../../engine/tools/)、[`engine/agent/tool_dispatcher.py`](../../engine/agent/tool_dispatcher.py)、[`engine/policy/`](../../engine/policy/)

## 1. 工具系统解决的问题

工具系统不是“把 Python 函数列表交给模型”。它需要同时保证：

- 模型只看见当前模式允许的工具；
- JSON Schema 与实际 Pydantic 输入一致；
- Provider function call 能耐久恢复；
- 权限、SQL 安全和审批不能靠 Prompt；
- 超时、取消、重试和幂等语义明确；
- 失败结果足够让模型调整，但不泄漏内部秘密；
- 大数据变成 Artifact 引用和有界 Observation；
- UI 可以用 presentation metadata 渲染状态，而不解析工具正文。

## 2. 工具分层

| 层 | 位置 | 职责 |
| --- | --- | --- |
| Tool definition | [`tools/builtin/`](../../engine/tools/builtin/) | 名称、描述、输入/输出 Schema、语义、presentation |
| Registry | [`tools/runtime/registry.py`](../../engine/tools/runtime/registry.py) | 唯一注册、按名称解析 |
| Materialization | [`tools/materialization.py`](../../engine/tools/materialization.py) | 按 AgentDefinition/mode/group 生成当前 Turn 工具集合和 hash |
| Dispatcher | [`agent/tool_dispatcher.py`](../../engine/agent/tool_dispatcher.py) | 持久化调用、审批、执行、恢复、回写 function output |
| Policy | [`policy/gate.py`](../../engine/policy/gate.py) | capability、group、mode、validated SQL、approval 等强制检查 |
| Runtime | [`tools/runtime/runtime.py`](../../engine/tools/runtime/runtime.py) | 严格输入、ToolContext、调用实现、安全错误映射 |
| Executor | [`tools/runtime/executor.py`](../../engine/tools/runtime/executor.py) | timeout、cancel、retry、worker/输出边界 |
| Observation | [`tools/runtime/observation.py`](../../engine/tools/runtime/observation.py) | 有界模型观察与耐久引用 |

层次的目的不是形式化，而是把真实变化轴分开：定义变化、可见性变化、策略变化、执行生命周期变化、Provider 协议变化。

## 3. 当前内置工具

正式注册入口 [`engine/tools/builtin/registry.py`](../../engine/tools/builtin/registry.py) 包括：

### 3.1 控制类

- `request_clarification`：请求用户补充必要信息；
- `update_plan`：更新可见计划，而非暗中改变领域状态。

### 3.2 对话回忆类

- `conversation_search`：在当前授权 Session 中搜索历史；
- `conversation_read`：按消息序列读取明确范围。

### 3.3 Catalog 类

- `catalog_overview`；
- `catalog_refresh`；
- `schema_list`；
- `schema_search`；
- `schema_inspect`。

### 3.4 数据与 SQL 类

- `data_preview`；
- `sql_validate`；
- `sql_execute_readonly`。

### 3.5 结果类

- `result_inspect`；
- `result_profile`；
- `chart_create`。

工具设计刻意把“搜索对象、看结构、预览样本、执行聚合、查看结果”拆成渐进步骤，避免一次调用返回全库内容。

## 4. 定义一个工具时必须表达什么

一个成熟工具定义至少包含：

- 稳定工具名；
- 面向模型的准确描述；
- strict JSON Schema；
- 输入 Pydantic Model；
- 输出合同；
- tool group/capability；
- 是否只读；
- 是否需要 approval；
- 幂等性与 recovery policy；
- timeout/retry；
- 输出字节/行数限制；
- UI presentation metadata；
- 可记录和需脱敏字段；
- 失败代码。

工具描述不能承载唯一安全规则。模型即使忽略描述，PolicyGate 仍必须拒绝越权调用。

## 5. Materialization

`materialize_tools` 在每个 Turn 开始时，根据：

- AgentDefinition；
- 当前 mode；
- tool groups；
- capability；
- 产品策略；
- 可能的 datasource 能力；

形成排序稳定的工具集合和 hash，并写入 AgentTurn。

好处：

- 可以复现模型当时到底看到了什么；
- 工具升级不会篡改历史 Turn；
- 不需要把所有工具永远暴露给模型；
- 测试可验证隐藏工具不会被调用；
- Provider schema 与实际执行 Registry 一致。

## 6. 从 Provider call 到耐久 Invocation

`ToolDispatcher` 的关键步骤：

1. 接收规范 function call：`call_id/name/arguments`；
2. 根据当前 Turn materialization 验证工具存在；
3. 解析严格 JSON；
4. canonicalize input 并计算 hash；
5. 构造 idempotency key；
6. 创建或复用 `AgentToolInvocation`；
7. 写 RunItem/Event；
8. PolicyGate；
9. 若需审批则转 waiting；
10. 否则交给 ToolExecutor；
11. 保存结果引用、Observation、function output；
12. 使用同一 Provider call_id 进入下一 Turn。

先持久化再执行是恢复能力的基础。进程在调用前、调用中、调用后崩溃时，数据库能说明发生到哪一步。

## 7. PolicyGate

[`engine/policy/gate.py`](../../engine/policy/gate.py) 应检查：

- 工具是否属于本 Turn materialization；
- 当前 Agent mode 是否允许；
- capability 是否满足；
- 输入是否通过严格 Schema；
- datasource/session/run 归属；
- SQL 是否有有效 Safety Decision；
- approval 是否存在、未过期且匹配 canonical input；
- 敏感操作是否满足额外产品策略。

Policy 结果要结构化记录到 ToolInvocation，便于解释为何拒绝。不要只保存一段英文字符串。

## 8. Approval

### 8.1 为什么 Approval 是耐久状态

审批可能跨越分钟或应用重启，因此不能只用内存 Promise。完整链路：

1. ToolInvocation 进入 waiting approval；
2. 创建 Approval 记录，绑定 Run、Invocation、input hash、期限和策略；
3. 写 Event 通知 UI；
4. worker 释放，不忙等；
5. 用户批准/拒绝 API 原子更新记录；
6. Coordinator wake Session；
7. Dispatcher 恢复同一 Invocation；
8. Authority 重新验证所有绑定；
9. 执行或形成拒绝 output。

### 8.2 不能复用的批准

以下任一变化都应使批准无效：

- tool name/version；
- canonical input；
- datasource/session/run；
- policy version；
- expiry；
- approval 已消费；
- invocation 已终止。

## 9. ToolExecutor

[`engine/tools/runtime/executor.py`](../../engine/tools/runtime/executor.py) 负责执行生命周期：

- 有界 worker pool；
- 每工具 timeout/deadline；
- cancel signal；
- 明确 retry classifier；
- 可取消 backoff；
- abandoned worker 上限；
- scope lock；
- 输出字节限制；
- attempts 记录。

### 9.1 Retry 分类

可以考虑重试：

- 明确瞬时网络错误；
- 幂等只读调用；
- 工具声明可恢复；
- 未超 budget/deadline。

不得自动重试：

- input/policy/approval 错误；
- 非幂等且结果不明确；
- 用户取消；
- 协议错误；
- datasource generation 已改变；
- 相同失败已触发 ProgressGuard。

### 9.2 Scope lock

某些工具对同一 datasource/result/session 需要串行，Scope lock 应基于稳定资源 identity，而非对象地址。锁只是执行协调，耐久幂等仍由 ToolInvocation 和数据库约束保证。

## 10. ToolContext

[`engine/tools/runtime/context.py`](../../engine/tools/runtime/context.py) 显式传入工具所需授权上下文，例如：

- session/run/turn/invocation ids；
- datasource id/generation；
- deadline/cancel；
- policy/approval authority；
- repositories/services；
- current workspace/selection（若合同允许）。

工具不得从全局变量猜“当前会话”或“当前数据库”。显式上下文让测试、恢复和并发行为确定。

## 11. ToolRuntime 的错误可信度

### 11.1 基本规则

[`engine/tools/runtime/runtime.py`](../../engine/tools/runtime/runtime.py) 捕获内部异常并形成 `ToolResult`。可信度规则与 HTTP 全局边界一致：

- `ToolInputError` 可携带明确允许展示、长度受限的说明；
- 其他 `DBFoxError` 按固定 error code 查公开 catalog；
- 未注册 code 降级为通用工具错误；
- 原始 exception message 只进入脱敏诊断；
- ToolResult、Observation、Provider function output、数据库和 UI 都不能默认信任基类 message。

### 11.2 为什么这条边界特别重要

Tool error 会沿链复制到：

```text
ToolResult
  → Agent Observation
  → Provider function output
  → 下一轮模型上下文
  → AgentEventRecord
  → metadata 持久化
  → UI
```

一次泄漏可能被保存多份并再次发送给外部 Provider。因此要在 ToolRuntime 源头做可信分类，而不是最后在 UI 隐藏。

## 12. ToolResult 与 Observation

### 12.1 ToolResult

ToolResult 描述本次执行事实：

- success/failure；
- stable code；
- safe display summary；
- structured payload；
- artifact/result reference；
- retry/recovery semantics；
- presentation metadata。

### 12.2 Observation

Observation 是给 Agent 下一 Turn 的有界视图。应包含：

- 做了什么；
- 是否成功；
- 关键结构和小样本；
- 行数/列数/统计摘要；
- artifact id；
- 下一步可用动作；
- 安全的失败分类。

不应包含：

- 任意完整大结果；
- secret/DSN/header；
- 内部堆栈；
- 无界 driver repr；
- 与当前问题无关的完整 Catalog；
- 只对 UI 有意义的重复文案。

## 13. Presentation 与业务结果分离

ToolInvocation 的 `presentation_json` 为 UI 提供：

- 显示名称；
- 参数摘要；
- 状态图标；
- 默认折叠；
- 是否可展开 SQL/结果；
- duration/attempts。

UI 不应解析自然语言 ToolResult 判断工具类型和状态。Presentation 也不能反向决定策略或执行。

## 14. 恢复策略

Sidecar 崩溃后，pending/running Invocation 根据 recovery policy 分类：

| 类型 | 恢复 |
| --- | --- |
| 未开始执行 | 可安全重新调度 |
| 幂等只读且能证明未完成 | 可按 budget 重试 |
| 已成功并持久化 output | 复用 output，不再执行 |
| 非幂等且结果不明确 | 不自动重放，形成明确未知结果/人工处理 |
| waiting approval | 恢复等待同一 Approval |
| cancelled | 不恢复执行 |

不能为了“自动恢复体验”而牺牲不重复执行保证。

## 15. 工具设计质量检查

新增工具前问：

1. 这是新的真实能力，还是已有 SQL/Catalog/Result 工具组合就能完成？
2. 是否让模型处理了本应由 backend 计算的大量数据？
3. 输入是否能用严格 JSON Schema 表达？
4. 输出是否有界并可回源？
5. 幂等和恢复语义是什么？
6. 需要 approval 吗，批准绑定哪些字段？
7. error code 是否稳定且安全？
8. 是否需要新依赖，官方/成熟库是否已有实现？
9. 是否引入第二套连接、SQL 或持久化路径？
10. 能否通过 fake + SQLite Harness + 可选真实 Provider 验证完整闭环？

## 16. 常见设计错误

- 工具描述说“只读”，实现却直接执行任意 SQL；
- Provider arguments 未经 strict validation；
- 工具返回完整 10 万行；
- ToolResult 用自然语言混合状态和数据；
- 每个 Provider 各写一套工具 mapper；
- 失败不回 function output，导致模型协议断裂；
- approval 只绑定工具名；
- timeout 后线程仍无限增长；
- retry backoff 不能取消；
- 任意 `DBFoxError.message` 进入模型/UI；
- presentation metadata 承担权限判断；
- 重启后一律重跑所有 running invocation。

## 17. 关键测试

| 合同 | 测试 |
| --- | --- |
| ToolRuntime 安全错误 | [`test_tool_runtime.py`](../../verification/tests/system/test_tool_runtime.py)、[`test_db_tool_error_boundary.py`](../../verification/tests/system/test_db_tool_error_boundary.py) |
| 工具策略门 | [`test_policy_gate.py`](../../verification/tests/agent_core/test_policy_gate.py) |
| 工具物化 | [`test_tool_materialization.py`](../../verification/tests/agent_core/test_tool_materialization.py) |
| Invocation 幂等 | [`test_tool_invocation_repository.py`](../../verification/tests/agent_core/test_tool_invocation_repository.py) |
| 恢复 | [`test_tool_recovery.py`](../../verification/tests/agent_core/test_tool_recovery.py) |
| Approval | [`test_approval_repository.py`](../../verification/tests/agent_core/test_approval_repository.py) |
| 执行权威 | [`test_execution_authority.py`](../../verification/tests/agent_core/test_execution_authority.py) |
| DB tools | [`test_db_tools.py`](../../verification/tests/system/test_dbfox_data_domain_model.py)、[`whitebox/test_db_tools_whitebox.py`](../../verification/tests/system/whitebox/test_db_tools_whitebox.py) |
| 完整 Agent 工具闭环 | [`test_run_loop.py`](../../verification/tests/agent_core/test_run_loop.py)、[`test_real_responses_contract.py`](../../verification/tests/agent_core/test_real_responses_contract.py) |

## 18. 修改检查表

- [ ] 工具复用现有 Registry/Materialization/Dispatcher；
- [ ] Schema strict 且与运行输入模型一致；
- [ ] ToolContext 显式，不读全局当前状态；
- [ ] PolicyGate 强制能力，不靠 Prompt；
- [ ] approval 绑定 canonical input；
- [ ] call_id 和 idempotency key 稳定；
- [ ] retry 只用于明确可恢复类别；
- [ ] backoff/执行可取消且 worker 有界；
- [ ] 错误使用固定公开 catalog；
- [ ] 输出有界，大数据使用 Artifact；
- [ ] Observation 与 UI presentation 分离；
- [ ] 恢复不会自动重放未知结果的非幂等操作。
