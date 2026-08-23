# P2 Memory v4 DeepSeek 真实 Provider 调查与修复记录

> 文档类型：质量证据 / 问题定位
>
> 状态：历史
>
> 最后核验：2026-08-17
>
> 适用范围：Memory v4 Catalog projection、`DBFOX_MEMORY_V4_CONTEXT`、DeepSeek AgentBench 后测

## 1. 结论

在 DeepSeek 真实 Provider AgentBench 运行中，控制台反复出现：

```text
code=agent_memory_save_projection type=MemoryProjectionError fingerprint=...
```

这不是无害日志。它说明 `project_session_memory` 在 terminal boundary fail-soft，`agent_session_memories.memory_v4_json` 没有被写入。因此即使设置了 `DBFOX_MEMORY_V4_CONTEXT=1`，后续 Run 也拿不到 prior Catalog projection；此前的 v3/v4 对比实际不是有效的 v4 context A/B。

已定位并修复根因，补了回归测试。**v4 默认仍未切换**，因为修复后的完整候选运行被主动中止，尚未得到新的 `compare` 结论。

## 2. 运行环境

- Provider：DeepSeek Responses API
- API base：`https://api.deepseek.com`
- Model：`deepseek-v4-flash`
- 凭据：仅通过 `DBFOX_REAL_LLM_API_KEY` 环境变量注入，未写入文件或 Git
- Dataset：`verification/bench/agentbench/datasets/regression-v1.json`，60 cases
- Repetitions：1（为控制 DeepSeek 成本，未使用默认 3）
- Memory flag：每个 Python 进程启动前设置 `DBFOX_MEMORY_V4_CONTEXT`

## 3. 已完成的运行与结果

| 运行 | 结果 | 备注 |
|---|---:|---|
| v4=0 smoke，`sql-count-orders` | pass | 仍出现 projection warning |
| v4=1 smoke，`sql-count-orders` | pass | 仍出现 projection warning |
| v4=0 baseline，60 cases | 36/60 passed，1 safety veto，0 unscored | 完整完成 |
| v4=1 candidate，60 cases | 36/60 passed，0 safety veto，0 unscored | 修复前完整完成 |
| `verification.bench.agentbench compare` | failed | 仅 `no_case_regression` 失败 |
| v4=1 fixed smoke，`sql-count-orders` | pass | projection warning 消失 |
| v4=1 fixed candidate | 未完成 | 用户主动中止于 15/60 |

修复前对比：

```text
same_dataset=true
no_safety_veto=true
candidate_has_scored_trials=true
no_new_infrastructure_failures=true
no_case_regression=false
success_rate=true
median_tokens=true
p90_latency=true
duplicate_tool_ratio=true
failed_tool_ratio=true
```

修复前 baseline 稳定通过、candidate 回退的 case：

```text
large-top-ten
multi-payment-coverage
recovery-preview-then-query
recovery-schema-before-sql
uncertainty-empty-result
```

修复前 candidate 由 fail 转 pass 的 case：

```text
memory-user-correction
recovery-empty-filter
recovery-missing-column
recovery-no-progress
security-delete-rollback
```

这些 pass/fail 变化受单次重复的模型噪声影响很大；在 projection 实际未写入时，不能当作 v4 语义回归证据。

## 4. 根因

### 4.1 症状

保留元数据目录后直接检查：

```text
agent_session_memories.memory_v4_json = NULL
```

直接重放 `project_session_memory` 得到：

```text
MemoryProjectionError
Catalog projection could not reduce a terminal Run
```

### 4.2 真实错误

逐条 fold canonical Invocation/Observation：

```text
tool=schema_inspect
tool_version=sha256:4ef4eb98...
observation_status=succeeded
failure=UnsupportedCatalogInput
message=Unsupported schema_inspect contract version
       'sha256:4ef4eb98...' for Catalog projection
```

### 4.3 原因

`engine/tools/materialization.py` 将 `MaterializedTool.version` 定义为完整可执行工具合同的 content hash：

```python
version=f"sha256:{_canonical_digest(contract_payload)}"
```

`engine/agent/repositories/tool.py` 把它原样写入 `AgentToolInvocation.tool_version`。

而 `engine/agent/memory_v4.py` 的 Catalog reducer 只接受声明语义版本：

```python
SUPPORTED_CATALOG_TOOLS = {
    "catalog_overview": frozenset({"1"}),
    "catalog_refresh": frozenset({"1"}),
    "schema_list": frozenset({"1"}),
    "schema_search": frozenset({"1"}),
    "schema_inspect": frozenset({"1"}),
}
```

因此所有真实 Catalog Tool 都被判定为未知版本，投影整体 fail-soft。

## 5. 修复

修改 `fold_catalog`，同时接受：

- 声明语义版本，例如 `"1"`；
- 材料化内容地址版本，例如 `"sha256:<digest>"`。

并在 `catalog_contract_fingerprint` 中加入：

```python
"tool_version_scheme": "declared_or_content_hash"
```

这会让旧的、按纯语义版本解释的 projection fingerprint 失效；当前生产环境本来就没有成功写入的旧 projection，因此不会引入迁移债务。

新增测试：

```text
verification/tests/agent_core/test_memory_v4_catalog_reducer.py
::test_materialized_content_hash_tool_version_is_supported
```

## 6. 验证

相关确定性测试：

```powershell
python -m pytest verification/tests/agent_core/test_memory_v4_catalog_reducer.py `
  verification/tests/agent_core/test_memory_projection.py `
  verification/tests/agent_core/test_context_memory_v4.py -q
```

结果：

```text
22 passed
```

保留元数据目录中重放 `project_session_memory`：

```text
OUTCOME 1 0 <state_hash>
```

随后 `memory_v4_json` 已写入，projection 包含一个 Catalog object：

```json
{
  "objects": [
    {
      "key": {"kind": "table", "schema_name": "", "table_name": "orders"},
      "last_inspected_observation_id": "...",
      "last_source_sequence": 1
    }
  ]
}
```

修复后 `deepseek-smoke-v4-fixed` 运行不再出现 `agent_memory_save_projection` warning。

## 7. 当前状态与下一步

- `DBFOX_MEMORY_V4_CONTEXT` 仍保持默认关闭。
- 修复后的 v4 full candidate 未完成，不能据此 cutover。
- 下一步按顺序：
  1. 完整运行 v3 baseline 与 v4 fixed candidate，同一 dataset/cases/repetitions；
  2. `python -m verification.bench.agentbench compare` 全部通过；
  3. 再执行受控默认切换，并更新本目录证据；
  4. 继续 P9/P10 与剩余能力接入。

DeepSeek key 不写入 Git、日志或报告；所有真实 Provider 运行均使用环境变量一次性注入。
