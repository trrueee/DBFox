# 卷四：SQL 安全、执行与 Result Artifact

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：SQL 校验、审批、参数绑定、执行、分页和结果制品
>
> 权威合同：[数据、SQL 与结果链](../architecture/data-sql-results.md)
>
> 核心入口：[`engine/sql/`](../../engine/sql/)、[`engine/tools/db/sql_execution.py`](../../engine/tools/db/sql_execution.py)、[`engine/sql/result_view/`](../../engine/sql/result_view/)

## 1. 设计目标

DBFox 的 SQL 链要同时满足：

- 模型可以完成真实数据分析；
- 默认只读且不能靠关键词拦截；
- SQL 值不通过字符串拼接；
- 查询规模受限；
- 大结果不塞满模型上下文；
- 结果可分页、统计、画图、导出和引用；
- 每个结论可追溯到实际执行结果；
- 数据源差异由 dialect 层表达，而不是散落条件分支。

核心思想是“让数据库计算，让 Agent 选择和解释”。模型负责提出查询意图和逐步分析，SQL backend 负责过滤、聚合、排序和限制。

## 2. 完整链路

```text
User/Agent SQL intent
  → strict tool/API input
  → DialectContext
  → parse to AST
  → statement/read-only classification
  → schema/policy/limit checks
  → bound parameter validation
  → SqlSafetyDecision
  → optional approval authority
  → ConnectionFactory checkout(current generation)
  → driver execution with parameters
  → bounded row serialization
  → Result Artifact + source fingerprint
  → small Tool Observation
  → result_inspect/profile/chart/export on demand
```

每个箭头都是合同边界。不能直接从工具参数跳到 `connection.execute(raw_sql)`。

## 3. DialectContext

[`engine/sql/dialect_context.py`](../../engine/sql/dialect_context.py) 将 datasource dialect、标识符规则、能力和安全实现绑定在一起。

不同数据库的差异包括：

- 标识符引用；
- LIMIT/OFFSET；
- 参数占位符；
- EXPLAIN；
- system catalog；
- 只读事务能力；
- 函数和类型；
- driver result 类型。

这些差异应该通过正式 dialect 实现表达：

- [`dialect/mysql.py`](../../engine/sql/dialect/mysql.py)
- [`dialect/postgres.py`](../../engine/sql/dialect/postgres.py)
- [`dialect/sqlite.py`](../../engine/sql/dialect/sqlite.py)
- [`dialect/duckdb.py`](../../engine/sql/dialect/duckdb.py)

禁止在上层根据字符串 `if datasource_type == ...` 复制一套 SQL 安全链。

## 4. 解析与只读判断

### 4.1 为什么不能只检查前缀

`sql.strip().lower().startswith("select")` 无法可靠处理：

- CTE 内写操作；
- 多 statement；
- 注释和混淆；
- `SELECT ... INTO`；
- 数据库特有副作用函数；
- PRAGMA/ATTACH/COPY；
- 通过可写视图或过程调用产生副作用。

DBFox 通过 parser/AST、dialect permission probes、guardrail 和 trust gate 组合判断。

相关实现：

- [`dlcs/dbfox_data/backend/sql/parser.py`](../../dlcs/dbfox_data/backend/sql/parser.py)
- [`dlcs/dbfox_data/backend/sql/guardrail.py`](../../dlcs/dbfox_data/backend/sql/guardrail.py)
- [`dlcs/dbfox_data/backend/sql/readonly_query.py`](../../dlcs/dbfox_data/backend/sql/readonly_query.py)
- [`dlcs/dbfox_data/backend/sql/permissions/`](../../dlcs/dbfox_data/backend/sql/permissions/)
- [`dlcs/dbfox_data/backend/sql/trust_gate.py`](../../dlcs/dbfox_data/backend/sql/trust_gate.py)
- [`dlcs/dbfox_data/backend/sql/dry_run_contracts.py`](../../dlcs/dbfox_data/backend/sql/dry_run_contracts.py)

### 4.2 `SqlSafetyService`

[`engine/sql/safety/service.py`](../../engine/sql/safety/service.py) 是统一决策入口。它形成结构化决定，而非只返回布尔值：

- SQL 是否解析成功；
- 是否单 statement；
- 是否属于允许的 read-only 类别；
- 是否存在 blocker；
- 是否需要确认/审批；
- 可执行的 safe SQL；
- 参数合同；
- 结果限制/超时；
- 稳定拒绝原因。

执行器必须消费这份决定，不能自己重新解释原始 SQL。

## 5. 参数绑定

### 5.1 值和结构必须分开

SQL 中两类动态内容：

- **值**：用户 id、日期、搜索词，应使用 driver 参数绑定；
- **结构**：表名、列名、排序方向，不能当普通 value bind，必须来自已验证 AST/Catalog/枚举。

正确示意：

```python
sql = "SELECT * FROM orders WHERE tenant_id = :tenant_id"
parameters = {"tenant_id": tenant_id}
```

错误示意：

```python
sql = f"SELECT * FROM orders WHERE tenant_id = '{tenant_id}'"
```

### 5.2 Bound Parameter 合同

[`dlcs/dbfox_data/backend/sql/bound_parameters.py`](../../dlcs/dbfox_data/backend/sql/bound_parameters.py) 负责参数名称、类型、序列化和 driver 适配。目标：

- Provider/工具传入 JSON 兼容值；
- 后端校验必需/多余参数；
- 不在日志输出敏感值；
- 参数 hash 可用于审计/幂等，但不能反推 secret；
- dialect 层转换 placeholder，不由 Agent 猜测；
- 日期、decimal、bytes 等类型有明确行为。

### 5.3 AST/Schema 投影血缘脱敏

从 AST 或 Catalog 形成的 projection 可能携带列名、别名和表达式。敏感性不能只看最终展示列名；需要保留来源血缘：

```text
source table/column
  → AST expression
  → projection alias
  → Result column
  → Artifact/Observation/UI
```

脱敏策略应根据权威 schema 分类和投影血缘决定，防止 `password AS harmless_name` 绕过。实现不能用一张随意字符串映射表代替 AST 关系。

## 6. 执行前审批

`sql_validate` 与 `sql_execute_readonly` 是不同动作：

- validate 只产生安全决定；
- execute 必须携带/重建与当前输入匹配的决定；
- 需要审批时由 `ApprovalAuthority` 验证当前 approval 与 canonical input/hash；
- approval 不能只绑定工具名，否则参数变化后可复用旧批准；
- 过期、拒绝或不同 Run 的 approval 无效。

相关入口：[`engine/policy/authority.py`](../../engine/policy/authority.py)、[`engine/policy/confirmation.py`](../../engine/policy/confirmation.py)、[`engine/tools/db/sql_execution.py`](../../engine/tools/db/sql_execution.py)。

## 7. 连接与执行

### 7.1 `sql_execute_readonly`

正式工具路径：

1. 接收严格输入；
2. 取得当前 ToolContext 和 datasource generation；
3. 调用 Safety Service；
4. 检查 blockers/`can_execute`；
5. 经过 ApprovalAuthority；
6. 使用 safe SQL 和 bound parameters；
7. 通过正式 ConnectionFactory/Lifecycle checkout；
8. 执行有超时、行数和字节上限的只读查询；
9. 生成 Artifact 和有界 Observation。

Agent Tool 不应有第二套“快捷执行”逻辑。

### 7.2 Native read-only 防线

在支持的平台上，应同时使用数据库/driver 的只读能力，例如只读事务、权限探测或 SQLite 只读 URI。AST 判断与 native read-only 是纵深防御，不互相替代。

### 7.3 超时与取消

需要区分：

- 用户取消；
- deadline 到期；
- driver timeout；
- 连接失效；
- 查询已在服务端完成但客户端响应丢失。

只读查询可在明确幂等和恢复策略下重试，但不能形成无限 retry loop。ToolExecutor 的取消与 SQL driver 取消能力也要分别记录。

## 8. 行序列化与边界

[`dlcs/dbfox_data/backend/sql/row_serializer.py`](../../dlcs/dbfox_data/backend/sql/row_serializer.py) 把 driver 特有值转换为稳定 JSON 表示，需处理：

- `Decimal`；
- datetime/date/time；
- bytes/blob；
- UUID；
- JSON；
- NaN/Infinity；
- driver 特有对象；
- 超长文本；
- NULL。

序列化不应隐式丢失类型信息，也不能无界读取 BLOB。用于 UI 的 preview 和用于 Artifact 的数据应共享一致合同。

## 9. Result Artifact

### 9.1 为什么需要 Artifact

数据库查询可能返回百万行，而 Provider 上下文只有有限 token。错误做法是：

- 把完整 rows 写入 ToolResult；
- 再写入 Agent Event；
- 再写入 Memory；
- 再随每个 Turn 发送给 Provider。

正确做法：

- 完整/可回源结果留在数据平面；
- 持久化稳定 `artifact_id`、source fingerprint、SQL/参数摘要、列 schema、行数/采样等；
- Tool Observation 只含足够决定下一步的有界摘要；
- 模型用 `result_inspect` 分页查看、`result_profile` 在 backend 计算统计、`chart_create` 建图；
- 最终回答引用 Artifact/Evidence。

### 9.2 Reference-only 语义

Artifact 应尽量是“引用 + 可验证来源”，而不是复制所有结果行到 metadata。回源时必须验证：

- Artifact 属于当前授权 Session/datasource；
- source fingerprint/generation 仍满足合同；
- derived SQL 仍通过 Safety；
- 页码、页大小、导出上限受控；
- 已删除/过期 Artifact 返回稳定错误。

## 10. `ResultViewService`

[`engine/sql/result_view/service.py`](../../engine/sql/result_view/service.py) 提供统一结果读取能力：

- `page`：分页；
- `count`：受控计数；
- `table`：表格投影；
- `chart`：图表数据；
- `export`：流式导出；
- 验证来源和 derived SQL；
- 应用结果大小、时间和敏感字段规则。

结果 API、Agent 工具和导出功能应复用它，而不是各自重新执行原 SQL。

## 11. 工具如何让 AI 看数据而不爆上下文

推荐分析模式：

1. Catalog 搜索定位相关表；
2. inspect 只看必要字段和关系；
3. preview 少量样本确认语义；
4. 让 SQL 做过滤、join、group by、窗口函数、排序；
5. execute 生成 Artifact；
6. result_profile 计算分布/空值/范围；
7. result_inspect 只读取回答所需页；
8. 必要时发起更小的后续 SQL；
9. 最终用 Evidence 引用结果。

当结果太多时，模型不需要“看完每一行”。应通过 SQL 计算可验证指标，并在必要时抽样检查。

## 12. 常见失败与定位

### 12.1 `result_inspect` 找不到 Artifact

检查：

- Tool 输出的 `artifact_id` 是否真实持久化；
- Session/datasource 授权范围；
- Artifact 状态/过期；
- result tool input Schema；
- 是否把展示用临时 id 当成 durable artifact id。

### 12.2 SQL validate 成功但 execute 被拒

可能原因：

- 参数在两步间变化；
- approval 不匹配 canonical hash；
- datasource generation 变化；
- 执行时 native permission probe 失败；
- Safety decision 过期或不完整。

### 12.3 查询成功但回答没有数据

检查：

- ToolResult 是否有 `artifact_id` 和有界摘要；
- Observation 是否成为后续 Turn context；
- 完成策略是否在工具返回前提前结束；
- Context Budget 是否错误丢弃最新观察；
- Final answer Evidence 是否引用已观察 Artifact。

### 12.4 数据预览 0 行

0 行是合法结果，不等于工具失败。工具合同必须区分：

- success + zero rows；
- invalid input；
- policy rejected；
- execution failed；
- result unavailable。

## 13. 关键测试

| 合同 | 测试 |
| --- | --- |
| 参数绑定 | [`test_bound_parameters.py`](../../engine/tests/test_bound_parameters.py) |
| SQL safety | [`test_sql_safety_service.py`](../../engine/tests/test_sql_safety_service.py) |
| Guardrail | [`test_guardrail.py`](../../engine/tests/test_guardrail.py)、[`test_guardrail_bypass.py`](../../engine/tests/test_guardrail_bypass.py) |
| Native readonly | [`test_native_readonly_execution.py`](../../engine/tests/test_native_readonly_execution.py) |
| 只读查询合同 | [`test_readonly_query_contract.py`](../../engine/tests/test_readonly_query_contract.py) |
| 执行器 | [`test_executor.py`](../../engine/tests/test_executor.py) |
| 结果边界 | [`test_sql_result_boundaries.py`](../../engine/tests/test_sql_result_boundaries.py) |
| ResultView | [`test_result_view_service.py`](../../engine/tests/test_result_view_service.py) |
| 安全 preview | [`test_safe_preview.py`](../../engine/tests/test_safe_preview.py) |
| CSV/流式 deadline | [`test_csv_export.py`](../../engine/tests/test_csv_export.py)、[`test_streaming_export_deadline.py`](../../engine/tests/test_streaming_export_deadline.py) |
| DB tools | [`test_db_tools.py`](../../engine/tests/test_db_tools.py) |

## 14. 修改检查表

- [ ] 所有执行都消费统一 Safety Decision；
- [ ] 值使用 driver 参数绑定；
- [ ] 结构字段来自 AST/Catalog/枚举验证；
- [ ] 不按 SQL 前缀判断只读；
- [ ] approval 绑定 canonical 输入；
- [ ] 执行走正式 ConnectionFactory generation；
- [ ] 行数、字节、时间均有界；
- [ ] 大结果保留为 Artifact，不复制进 Prompt/Memory；
- [ ] 0 行与失败明确区分；
- [ ] Result 回源验证授权、来源和 derived SQL。
