# Agent State Contract & AI Schema Linking — 全栈设计

Date: 2026-06-16
Status: approved for implementation planning

## Context

本轮修复了三个 Bug，暴露出两条系统性问题：

1. **工具调用状态清理不统一**：`db.query` 失败重试成功后，后端 `state["error"]` 未清零导致进度循环，前端同名工具复用卡片时旧 `TrustGate Error` 未清除，出现"成功 Output + 红色 ERROR"混叠。
2. **搜索硬编码别名不可扩展**：`_BOOTSTRAP_SYNONYMS` 写死 21 组中英对照，新业务领域（小红书、功能、使用、频率）每次都要手动补，且 `audit_logs` 等无关表会被带偏。

这两个问题分别催生了 Track 1 和 Track 2。

## Overall Architecture

两条并行轨道，共享工具注册层和 `ToolObservation` 结构：

```
┌─ Track 1: 全栈状态契约 ─────────────────────────────┐
│                                                      │
│  backend: ToolStateContract → databinding.py          │
│  frontend: merge_strategy → agentTimeline.ts          │
│  audit: all registered tools                          │
│                                                      │
├─ Track 2: AI Schema Linking Index ───────────────────┤
│                                                      │
│  offline: refresh_catalog → LLM 富化 → search_docs    │
│  online:  db.search → FTS/BM25 → 统一打分             │
│  clean:   删除 _BOOTSTRAP_SYNONYMS                    │
│                                                      │
└─ 共享: 工具注册层 / ToolObservation 结构 ────────────┘
```

## Design Principles

1. **离线重 AI，在线轻检索** — LLM 只在 `refresh_catalog` 运行，`db.search` 零 API 调用
2. **追求准，不追求语义发散** — 目标是 schema linking，不是开放式语义召回
3. **一套召回，一套打分** — 不做关键词/向量双路径
4. **所有命中都要可解释** — 搜索结果必须携带 `reasons`
5. **声明式清理，不手写** — 工具注册时声明状态契约，系统自动执行
6. **不改交互体验** — 思考过程→结果→折叠、多轮对话保持不变

---

## Track 1: 全栈状态契约

### 1.1 问题定义

当前 `databinding.py` 的状态管理存在三个问题：

- **手写清理不一致**：`_apply_db_query` 手动设 `"error": None, **RESET_SELF_HEALING`，但其他工具（`db.preview`、`db.search`、`db.inspect`）没有对应的成功清理逻辑
- **失败路径与成功路径无隔离**：`_apply_failed_telemetry` 写入的 `error` / `last_error_telemetry` / `last_failed_tool_call` 在后续成功时没有统一清理入口
- **前端 `upsertToolStep`** 的 error 字段在重试成功时有条件保留旧值（line 129: `stringValue(step.error) || previous?.error || null`）

### 1.2 方案：声明式 ToolStateContract

#### 1.2.1 数据结构

```python
# engine/agent_core/tool_contract.py (新文件)

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class ToolStateContract:
    tool_name: str
    on_success_clear: tuple[str, ...]   # 成功时强制设为 None
    on_success_reset: tuple[str, ...]   # 成功时用预设值复位
    merge_strategy: str                 # "reuse" | "new" | "always_new"
    emit_artifact: bool                 # 是否产生 artifact
```

#### 1.2.2 契约注册表

```python
# engine/agent_core/tool_registry.py 或 tool_contract.py

RESET_ERROR = ("error",)
RESET_SELF_HEALING = ("last_error_telemetry", "last_failed_tool_call")
RESET_ALL_ERROR_STATE = RESET_ERROR + RESET_SELF_HEALING

TOOL_CONTRACTS: dict[str, ToolStateContract] = {
    # ── 数据库操作 ──
    "db.query": ToolStateContract(
        tool_name="db.query",
        on_success_clear=RESET_ALL_ERROR_STATE,
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=True,
    ),
    "db.preview": ToolStateContract(
        tool_name="db.preview",
        on_success_clear=RESET_ALL_ERROR_STATE,
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=True,
    ),
    "db.inspect": ToolStateContract(
        tool_name="db.inspect",
        on_success_clear=RESET_ALL_ERROR_STATE,
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),
    "db.search": ToolStateContract(
        tool_name="db.search",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "db.observe": ToolStateContract(
        tool_name="db.observe",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "db.remember": ToolStateContract(
        tool_name="db.remember",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),

    # ── Schema 操作 ──
    "schema.list_tables": ToolStateContract(
        tool_name="schema.list_tables",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "schema.describe_table": ToolStateContract(
        tool_name="schema.describe_table",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "schema.refresh_catalog": ToolStateContract(
        tool_name="schema.refresh_catalog",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),

    # ── 语义/记忆 ──
    "semantic.resolve": ToolStateContract(
        tool_name="semantic.resolve",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "memory.search": ToolStateContract(
        tool_name="memory.search",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "memory.write": ToolStateContract(
        tool_name="memory.write",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=False,
    ),

    # ── 分析/合成 ──
    "environment.get_profile": ToolStateContract(
        tool_name="environment.get_profile",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="reuse",
        emit_artifact=False,
    ),
    "result.profile": ToolStateContract(
        tool_name="result.profile",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=True,
    ),
    "chart.suggest": ToolStateContract(
        tool_name="chart.suggest",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=True,
    ),
    "answer.synthesize": ToolStateContract(
        tool_name="answer.synthesize",
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="always_new",
        emit_artifact=True,
    ),
}

# workspace.* 族走独立路由，但也可显式注册
def _workspace_contract(tool_name: str) -> ToolStateContract:
    return ToolStateContract(
        tool_name=tool_name,
        on_success_clear=(),
        on_success_reset=(),
        merge_strategy="new",
        emit_artifact=True,
    )
```

#### 1.2.3 执行层改造

`apply_tool_result_to_state` 改为契约驱动：

```python
# engine/agent_core/databinding.py (改造)

def apply_tool_result_to_state(
    *,
    state: dict[str, Any],
    tool_name: str,
    observation: ToolObservation,
) -> dict[str, Any]:
    contract = TOOL_CONTRACTS.get(tool_name)
    if contract is None:
        # workspace.* 或未注册工具 → 默认 safe contract
        if tool_name.startswith("workspace."):
            contract = _workspace_contract(tool_name)
        else:
            contract = ToolStateContract(
                tool_name=tool_name,
                on_success_clear=(),
                on_success_reset=(),
                merge_strategy="reuse",
                emit_artifact=False,
            )

    output = observation.output or {}
    update: dict[str, Any] = {
        "tool_results": [observation.model_dump(mode="json")],
        "trace_events": [
            {
                "type": "tool.completed",
                "payload": {
                    "tool_name": tool_name,
                    "observation_name": observation.name,
                    "status": observation.status,
                },
            }
        ],
        "_merge_strategy": contract.merge_strategy,
    }

    # ── 失败路径 ──
    if observation.status == "failed":
        _apply_failed_telemetry(state, tool_name, observation, output, update)
        return update

    # ── 成功路径：先执行契约清理 ──
    for key in contract.on_success_clear:
        update[key] = None
    for key in contract.on_success_reset:
        # RESET_SELF_HEALING 等预设值，可根据 key 映射
        update[key] = None

    # ── 再执行工具特定的 state handler ──
    handler = TOOL_STATE_APPLIERS.get(tool_name)
    if handler is not None:
        tool_update = handler(state, output, observation)
    elif tool_name.startswith("workspace."):
        tool_update = _apply_workspace_prefix(state, output, observation)
    else:
        tool_update = {}

    extra_trace = tool_update.pop("_trace", None)
    if isinstance(extra_trace, list):
        update["trace_events"].extend(extra_trace)
    update.update(tool_update)

    # ── artifact ──
    if contract.emit_artifact:
        update["artifacts"] = [_artifact_event(tool_name, output)]

    return update
```

**关键变化：** 删除了 `_apply_db_query` 中手写的 `"error": None, **RESET_SELF_HEALING`，交给契约层统一处理。

#### 1.2.4 删除手写清理

`_apply_db_query` 中删除手动清理行，只保留业务逻辑：

```python
# Before (当前)
def _apply_db_query(state, output, _obs):
    execution = dict(output)
    execution["success"] = output.get("status") == "success"
    execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
    execution["latencyMs"] = output.get("latencyMs", output.get("execution_time_ms", 0))
    update: dict[str, Any] = {
        "execution": execution,
        "error": None,          # ← 删除，由契约层处理
        **RESET_SELF_HEALING,    # ← 删除，由契约层处理
    }
    if output.get("safe_sql"):
        update["sql"] = output.get("safe_sql")
    return update

# After
def _apply_db_query(state, output, _obs):
    execution = dict(output)
    execution["success"] = output.get("status") == "success"
    execution["rowCount"] = output.get("rowCount", output.get("returned_rows", 0))
    execution["latencyMs"] = output.get("latencyMs", output.get("execution_time_ms", 0))
    update: dict[str, Any] = {"execution": execution}
    if output.get("safe_sql"):
        update["sql"] = output.get("safe_sql")
    return update
```

### 1.3 前端联动

#### 1.3.1 类型扩展

```typescript
// desktop/src/lib/api/types.ts

export interface AgentStep {
  // ... existing fields
  merge_strategy?: "reuse" | "new" | "always_new";
}
```

`merge_strategy` 从 SSE 事件的 `_merge_strategy` 字段映射到 `AgentStep`。

#### 1.3.2 agentTimeline.ts 改造

```typescript
// desktop/src/features/workspace/agentTimeline.ts

function upsertToolStep(
  current: AgentTimelineItem[],
  event: AgentRuntimeEvent,
): AgentTimelineItem[] {
  const step = event.step || {};
  const toolName = stringValue(step.tool_name) || stringValue(step.name) || "tool";
  const stepName = stringValue(step.name);
  const isCompleted = event.type === "agent.step.completed";
  const strategy = step.merge_strategy || "reuse";

  // Id 策略
  let id: string;
  if (strategy === "always_new" || strategy === "new") {
    id = toolEventId(toolName, event.sequence);
  } else {
    // reuse: 找不到同名 running 卡片才新建
    id = isCompleted
      ? findLatestRunningToolId(current, toolName, stepName) || toolEventId(toolName, event.sequence)
      : toolEventId(toolName, event.sequence);
  }

  const previous = current.find((item) => item.id === id);
  const input = recordValue(step.input) ?? previous?.input ?? null;
  const output = recordValue(step.output) ?? previous?.output ?? null;

  // 核心修复: success + reuse 强制清零 error
  const stepStatus = isCompleted ? statusValue(step.status, "success") : "running";
  const error = isCompleted && strategy === "reuse" && stepStatus === "success"
    ? null
    : stringValue(step.error) || previous?.error || null;

  const content = isCompleted
    ? toolStepSummary(toolName, output, error)
    : previous?.content;

  return upsertById(current, {
    id,
    kind: "tool",
    title: toolName,
    subtitle: stepName,
    status: stepStatus,
    toolName,
    content,
    input,
    output,
    error,
    latencyMs: numberValue(step.latency_ms) ?? previous?.latencyMs ?? null,
  });
}
```

**关键变化 (line 129 附近):**
- `error` 现在检查 `strategy === "reuse"`：可复用卡片时，success 强制 null
- `strategy === "new"` 的工具（如 `db.inspect`）：每次新卡片，不会混入旧 error
- 这与现有 `error = isCompleted ? stringValue(step.error) || null : stringValue(step.error) || previous?.error || null` 不同：核心是 `strategy === "reuse" && stepStatus === "success" → null`

### 1.4 A 类打磨清单

逐工具审查状态清理死角：

| 工具 | 当前状态 | 行动 |
|------|---------|------|
| `db.query` | 已手动修复，但手写清理在 handler 内部 | 移除手写，改契约驱动 |
| `db.preview` | 有 `_execution_failed`，成功路径无清理 | 加契约 `on_success_clear=RESET_ALL_ERROR_STATE` |
| `db.inspect` | 失败抛异常，未走 `_apply_failed_telemetry` | 审查异常路径，确认 `_execution_failed` 已正确处理 |
| `db.search` | 无失败清理 | 加契约 |
| `db.observe` | 无失败清理 | 加契约 |
| `db.remember` | 无失败清理 | 加契约 |
| `schema.*` | 无状态写入，安全 | 确认即可 |
| `workspace.*` | 走 `_apply_workspace_prefix`，写 `status: "completed"` | 确认重试场景不残留 |
| `answer.synthesize` | 成功写 answer | 确认不覆盖 error |
| `result.profile` / `chart.suggest` | 新接入 | 加契约 |

`_apply_failed_telemetry` 的 retryable 判断与契约没有冲突：失败路径和成功路径走不同分支 (`observation.status == "failed"` vs `"success"`)，泾渭分明。

---

## Track 2: AI Schema Linking Index

### 2.1 目标

> 不是"向量召回"，而是让用户自然语言 query 稳定、准确、可解释地对齐到正确的表和字段。

核心能力：
1. LLM 生成表/字段业务描述
2. LLM 生成 `business_terms` / `semantic_tags` / `aliases`
3. 构建 `schema_search_docs` 可搜索文档表
4. 构建 SQLite FTS5 全文索引
5. 在线 alias expand + FTS/BM25 召回
6. 单套 `total_score` 排序
7. 返回命中原因
8. 支持增量刷新
9. 删除 `_BOOTSTRAP_SYNONYMS` 硬编码
10. embedding 仅作为未来可选增强，不进入默认主路径

### 2.2 架构

```
schema.refresh_catalog(ai_enrich=True)
  ├─ 1. 增量检测 (schema_hash 对比)
  ├─ 2. 批处理 LLM 调用 (每批 50 表，1 次 LLM)
  ├─ 3. 写入 catalog 新字段
  ├─ 4. 重建 schema_search_docs
  ├─ 5. 重建 FTS5 索引
  └─ 6. 清理孤儿行 (源库已删除的表)

db.search(query)
  ├─ query normalize (去噪 + jieba 分词)
  ├─ alias expand (SemanticAlias 表 + AI 生成的 aliases)
  ├─ FTS/BM25 召回 (schema_search_docs)
  ├─ field-aware scoring → total_score
  ├─ table-column grouping
  └─ explainable result (含 reasons)
```

### 2.3 降级路径

```python
def db_search(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    docs_exist = (
        ctx.db.query(SchemaSearchDoc)
        .filter(SchemaSearchDoc.datasource_id == ctx.request.datasource_id)
        .first()
        is not None
    )

    if not docs_exist:
        # 降级: 纯关键词匹配 (无 AI 语义标签)
        return _fallback_keyword_search(ctx, args)

    return _fts_search(ctx, args)
```

首次 AI 富化完成后自动切换到 FTS 路径，降级路径只在富化前起作用。

### 2.4 数据库 Schema 变更

#### 2.4.1 Catalog 扩展字段

```sql
-- SchemaTable 新增
ALTER TABLE schema_tables ADD COLUMN ai_description TEXT;
ALTER TABLE schema_tables ADD COLUMN semantic_tags TEXT;      -- JSON array
ALTER TABLE schema_tables ADD COLUMN business_terms TEXT;     -- JSON array
ALTER TABLE schema_tables ADD COLUMN aliases TEXT;            -- JSON array
ALTER TABLE schema_tables ADD COLUMN table_role TEXT;         -- fact / dim / bridge / log / agg
ALTER TABLE schema_tables ADD COLUMN grain TEXT;              -- 表粒度
ALTER TABLE schema_tables ADD COLUMN subject_area TEXT;       -- user / order / content / traffic
ALTER TABLE schema_tables ADD COLUMN ai_confidence REAL;      -- 0-1
ALTER TABLE schema_tables ADD COLUMN ai_enriched_at TEXT;     -- ISO datetime
ALTER TABLE schema_tables ADD COLUMN schema_hash TEXT;        -- 结构 hash，增量检测用

-- SchemaColumn 新增
ALTER TABLE schema_columns ADD COLUMN ai_description TEXT;
ALTER TABLE schema_columns ADD COLUMN semantic_tags TEXT;     -- JSON array
ALTER TABLE schema_columns ADD COLUMN business_terms TEXT;    -- JSON array
ALTER TABLE schema_columns ADD COLUMN aliases TEXT;           -- JSON array (feature_id -> feat_id)
ALTER TABLE schema_columns ADD COLUMN column_role TEXT;       -- dimension / measure / time / id / status
ALTER TABLE schema_columns ADD COLUMN metric_type TEXT;       -- count / amount / rate / duration
ALTER TABLE schema_columns ADD COLUMN is_pii INTEGER DEFAULT 0;
ALTER TABLE schema_columns ADD COLUMN ai_confidence REAL;
ALTER TABLE schema_columns ADD COLUMN ai_enriched_at TEXT;
```

核心字段：`ai_description`、`semantic_tags`、`business_terms`、`aliases`、`grain`、`column_role`、`metric_type`。它们直接决定搜索准确度。

#### 2.4.2 搜索文档表（新表）

```sql
CREATE TABLE schema_search_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datasource_id TEXT NOT NULL,

    entity_type TEXT NOT NULL,       -- 'table' / 'column'
    entity_id TEXT NOT NULL,         -- SchemaTable.id / SchemaColumn.id

    table_name TEXT,
    column_name TEXT,

    name TEXT NOT NULL,
    ai_description TEXT,
    semantic_tags TEXT,
    business_terms TEXT,
    aliases TEXT,

    table_role TEXT,
    column_role TEXT,
    metric_type TEXT,
    grain TEXT,
    subject_area TEXT,

    column_summary TEXT,             -- 所属表的所有列名
    relation_summary TEXT,           -- FK 关系描述

    search_text TEXT NOT NULL,       -- FTS 索引主字段
    ai_confidence REAL,

    updated_at TEXT NOT NULL,

    FOREIGN KEY (datasource_id) REFERENCES data_sources(id)
);

CREATE INDEX idx_search_docs_ds ON schema_search_docs(datasource_id, entity_type);
CREATE INDEX idx_search_docs_table ON schema_search_docs(datasource_id, table_name);
```

#### 2.4.3 FTS5 全文索引

```sql
CREATE VIRTUAL TABLE schema_search_fts USING fts5(
    name,
    ai_description,
    semantic_tags,
    business_terms,
    aliases,
    column_summary,
    relation_summary,
    search_text,
    content='schema_search_docs',
    content_rowid='id'
);
```

**中文分词方案：** `search_text` 写入前用 jieba 分词，中文字间插入空格。FTS5 默认 tokenizer 按空白切分，经过 jieba 预处理后，`小红书功能使用频率` 变为 `小红书 功能 使用 频率`，`功能使用` 可命中。

### 2.5 search_text 拼接规则

#### 表级 search_text

```
表名: xhs_feature_usage_daily
业务描述: 小红书功能使用频率日统计表，记录用户每日对各功能模块的使用次数、使用时长和活跃情况
语义标签: 小红书 功能使用 用户行为 频率统计
业务术语: 小红书 使用频率 功能模块 用户活跃
别名: xhs redbook 小红书 feature_usage frequency [经 jieba 分词]
表角色: 聚合表
表粒度: 按用户、功能、日期聚合
字段: user_id 用户ID feature_id 功能模块 usage_count 使用次数 duration 使用时长 dt 日期 [经 jieba]
关系: user_id 关联用户表
```

#### 列级 search_text

```
字段名: usage_count
所属表: xhs_feature_usage_daily
字段描述: 功能使用次数
语义标签: 使用次数 频率 功能使用 [经 jieba]
业务术语: 功能使用频率 使用次数
字段角色: 指标
指标类型: count
```

### 2.6 LLM 调用设计

#### 2.6.1 批处理策略

```
每批 50 张表
每批 1 次 LLM 调用 (含全部列上下文)
embedding 批量编码 (若 AI_SEARCH_VECTOR_ENABLED=False 则跳过)
失败批次自动重试，最多 3 次
按 schema_hash 做增量，表结构未变则跳过
批间间隔 200ms
```

**上下文收集（给 LLM 的输入）：**

- 表名、列名、列类型、注释、主键/外键关系
- 少量采样数据（前 3-5 行，经过 redaction）
- 关联表的名字

#### 2.6.2 LLM 输出格式

```json
{
  "tables": [
    {
      "name": "xhs_feature_usage_daily",
      "ai_description": "小红书功能使用频率日统计表，记录用户每日对各功能模块的使用次数、使用时长和活跃情况",
      "semantic_tags": ["小红书", "功能使用", "用户行为", "频率统计"],
      "business_terms": ["小红书", "功能使用", "使用频率", "活跃功能", "用户行为"],
      "aliases": ["xhs", "redbook", "小红书", "feature_usage"],
      "table_role": "agg",
      "grain": "按用户、功能、日期聚合",
      "subject_area": "user_behavior",
      "ai_confidence": 0.92,
      "columns": [
        {
          "name": "feature_id",
          "ai_description": "功能模块 ID",
          "semantic_tags": ["功能", "模块"],
          "business_terms": ["功能模块", "产品功能"],
          "aliases": ["feat_id", "feature"],
          "column_role": "dimension",
          "metric_type": null,
          "ai_confidence": 0.9
        },
        {
          "name": "usage_count",
          "ai_description": "功能使用次数",
          "semantic_tags": ["使用次数", "频率"],
          "business_terms": ["功能使用频率", "使用次数"],
          "aliases": ["cnt", "count", "frequency"],
          "column_role": "measure",
          "metric_type": "count",
          "ai_confidence": 0.95
        },
        {
          "name": "duration",
          "ai_description": "功能使用时长（秒）",
          "semantic_tags": ["使用时长", "时长"],
          "business_terms": ["使用时", "停留时长"],
          "aliases": ["dur", "time_spent"],
          "column_role": "measure",
          "metric_type": "duration",
          "ai_confidence": 0.93
        },
        {
          "name": "dt",
          "ai_description": "统计日期",
          "semantic_tags": ["日期", "时间"],
          "business_terms": ["统计日期", "报表日期"],
          "aliases": ["date", "stat_date"],
          "column_role": "time",
          "metric_type": null,
          "ai_confidence": 0.98
        }
      ]
    }
  ]
}
```

### 2.7 在线搜索流程

一条链路到底：

```
query
  → normalize (去冗余空白、标点规范化)
  → jieba 分词 + 英文 tokenize
  → alias expand (SemanticAlias + AI aliases)
  → FTS5 召回 (schema_search_fts, recall_limit=300)
  → field-aware scoring → total_score
  → table-column grouping (列结果归属到表)
  → 排序 + 截断 (limit=20)
  → 附加 reason 信息
```

#### 2.7.1 分词

```python
import jieba
import re

def tokenize_query(query: str) -> list[str]:
    tokens: list[str] = []
    # 英文/数字 token
    eng_tokens = re.findall(r"[A-Za-z0-9_]+", query)
    tokens.extend(t for t in eng_tokens if len(t) >= 2)

    # 中文 jieba 分词
    chinese = re.sub(r"[A-Za-z0-9_]+", " ", query)
    tokens.extend(t for t in jieba.lcut(chinese) if len(t.strip()) >= 1)

    return list(dict.fromkeys(tokens))  # 去重保序
```

#### 2.7.2 Alias Expand

```python
def expand_aliases(tokens: list[str], datasource_id: str, db: Session) -> list[str]:
    """扩展 token 为同义别名列表。
    来源: SemanticAlias 表 (用户手动) + AI 生成的 aliases 字段。
    """
    expanded = list(tokens)
    for token in tokens:
        # 查 SemanticAlias
        aliases = (
            db.query(SemanticAlias.alias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target == token,
            )
            .all()
        )
        expanded.extend(a[0] for a in aliases if a[0].strip())
    return list(dict.fromkeys(expanded))
```

#### 2.7.3 FTS 查询构建

```python
def build_fts_query(tokens: list[str], expanded_terms: list[str]) -> str:
    """构建 FTS5 查询字符串。
    精确别名用 "..." 包裹，分词 token 用 OR 连接。
    """
    # 精确别名
    exact_parts = [f'"{t}"' for t in expanded_terms if len(t) >= 2]
    # OR 匹配
    token_parts = [t for t in tokens if len(t) >= 2]

    parts = exact_parts + token_parts
    return " OR ".join(parts)
```

### 2.8 total_score 公式

```
total_score =
    exact_alias_match        × 0.25
  + business_term_match      × 0.25
  + field_name_match         × 0.20
  + ai_description_match     × 0.15
  + structure_boost          × 0.10
  + usage_boost              × 0.05
```

| 因子 | 含义 | 计算方式 |
|------|------|---------|
| `exact_alias_match` | 精确别名命中（小红书 → xhs） | 0 或 1 |
| `business_term_match` | 业务术语命中的覆盖比 | 命中术语数 / 总术语数 |
| `field_name_match` | 字段名/列名命中 | 命中字段数 / 有意义的 token 数 |
| `ai_description_match` | AI 描述中的 BM25 命中 | FTS5 score 归一化 |
| `structure_boost` | 结构加分（FK 关联、时间字段、指标字段） | 0–1 区间 |
| `usage_boost` | 使用频率加分（历史命中、收藏） | 0–1 区间 |

**排序优先级（同分时的 tiebreaker）：**

```
精确表名/字段名命中
  > exact alias 命中
  > business_terms 命中
  > semantic_tags 命中
  > ai_description 命中
  > 普通 search_text 命中
  > FK 扩展命中
```

### 2.9 返回结果格式

```json
{
  "query": "小红书功能使用频率",
  "results": [
    {
      "type": "table",
      "name": "xhs_feature_usage_daily",
      "table_name": "xhs_feature_usage_daily",
      "score": 91.5,
      "ai_description": "小红书功能使用频率日统计表...",
      "semantic_tags": ["小红书", "功能使用", "用户行为", "频率统计"],
      "table_role": "agg",
      "matched_columns": [
        {
          "name": "usage_count",
          "reason": "命中业务词：使用频率、使用次数"
        },
        {
          "name": "duration",
          "reason": "命中业务词：使用时长"
        },
        {
          "name": "dt",
          "reason": "时间粒度字段"
        }
      ],
      "reasons": [
        "别名命中：小红书 → xhs",
        "业务词命中：功能使用、使用频率",
        "字段命中：usage_count、duration",
        "表粒度匹配：按用户、功能、日期聚合"
      ],
      "short_comment": "小红书功能使用频率日统计表",
      "tags": ["user_behavior", "analytics"],
      "columns": ["user_id", "feature_id", "usage_count", "duration", "dt"]
    }
  ],
  "total_matches": 3
}
```

### 2.10 增量刷新

```python
def refresh_catalog(ai_enrich: bool = True):
    tables = load_catalog_tables()
    ds_id = current_datasource_id()

    # 1. 增量检测
    changed = [
        t for t in tables
        if _compute_schema_hash(t) != t.schema_hash
    ]

    if not changed:
        return {"ai_enriched": False, "reason": "no changes"}

    # 2. 批处理 LLM
    for batch in chunked(changed, AI_LLM_TABLE_BATCH):
        context = build_table_context(batch)
        ai_result = llm_enrich_schema(context)       # 1 次 LLM
        validate_ai_result(ai_result)
        write_ai_metadata(batch, ai_result)
        rebuild_search_docs(batch, ai_result)         # search_docs + FTS
        update_schema_hash(batch)
        sleep(AI_LLM_BATCH_INTERVAL_MS / 1000)

    # 3. 清理孤儿行 (源库已 DROP 的表)
    _clean_orphan_search_docs(ds_id)

    return {"ai_enriched": True, "enriched_count": len(changed)}


def _clean_orphan_search_docs(db: Session, datasource_id: str):
    """删除 schema_search_docs 中不在 catalog 里的表。"""
    db.execute(
        "DELETE FROM schema_search_docs "
        "WHERE datasource_id = :ds_id "
        "  AND entity_type = 'table' "
        "  AND table_name NOT IN ("
        "    SELECT table_name FROM schema_tables WHERE data_source_id = :ds_id"
        ")",
        {"ds_id": datasource_id},
    )
    db.execute(
        "DELETE FROM schema_search_docs "
        "WHERE datasource_id = :ds_id "
        "  AND entity_type = 'column' "
        "  AND table_name NOT IN ("
        "    SELECT table_name FROM schema_tables WHERE data_source_id = :ds_id"
        ")",
        {"ds_id": datasource_id},
    )
    db.commit()
```

增量检测的核心是 `schema_hash`：表结构（列名+类型+注释）的 hash，表结构不变则跳过。

### 2.11 干净切换 Bootstrap

迁移步骤：

```sql
-- 1. 删除 bootstrap 别名
DELETE FROM semantic_aliases WHERE description = 'Bootstrapped default';

-- 2. 新增 catalog 字段 (2.4.1)
ALTER TABLE schema_tables ADD COLUMN ai_description TEXT;
-- ... (其余 ALTER TABLE)

-- 3. 新建搜索文档表 (2.4.2)
CREATE TABLE IF NOT EXISTS schema_search_docs (...);

-- 4. 新建 FTS5 索引 (2.4.3)
CREATE VIRTUAL TABLE IF NOT EXISTS schema_search_fts USING fts5(...);
```

代码删除：

```text
engine/tools/db_tools.py:
  - 删除 _BOOTSTRAP_SYNONYMS 常量 (line 42-63)
  - 删除 _bootstrap_synonyms() 函数 (line 1610-1621)
  - 删除 _expanded_terms() 中 bootstrap fallback 逻辑 (line 519-523)
  - _load_synonyms() 不再做 bootstrap 检查，空库返回 {}
  - SemanticAlias 查询条件移除 target_type == 'synonym' 中的 bootstrap 项
```

### 2.12 Embedding 策略

**第一版默认关闭：**

```python
AI_SEARCH_VECTOR_ENABLED = False
```

embedding 仅用于离线阶段的 LLM 辅助（聚类、表相似度发现等可选增强），不进入在线搜索主路径。

原因:
- schema search 的核心目标是精准 schema linking，不是开放式语义文本召回
- AI 富化后的 `ai_description`、`business_terms`、`aliases` 和 `semantic_tags` 已覆盖主要业务语义
- embedding 在线调用引入延迟 (100-300ms) 和成本

未来如加 embedding 增强，只用于：
1. 离线相似表发现
2. 重复表检测
3. 表聚类
4. 标签质量检查
5. 长尾 query 分析

### 2.13 配置项

```python
# engine/config.py

AI_ENRICH_ENABLED = True

# LLM
AI_LLM_PROVIDER = "aliyun"
AI_LLM_MODEL = "qwen-plus"
AI_LLM_TABLE_BATCH = 50
AI_LLM_MAX_RETRIES = 3
AI_LLM_BATCH_INTERVAL_MS = 200

# Search
AI_SCHEMA_LINKING_ENABLED = True
AI_SEARCH_USE_FTS = True
AI_SEARCH_LIMIT = 20
AI_SEARCH_RECALL_LIMIT = 300

# Embedding (optional, default off)
AI_SEARCH_VECTOR_ENABLED = False
AI_SEARCH_VECTOR_PROVIDER = "aliyun"
AI_SEARCH_VECTOR_MODEL = "text-embedding-v3"
AI_SEARCH_VECTOR_DIM = 1024
```

---

## Implementation Order

### Phase 1: Track 1 — State Contract (Foundation)

1. 新建 `engine/agent_core/tool_contract.py`
2. 为所有现有工具定义 `ToolStateContract`
3. 改造 `databinding.py` 的 `apply_tool_result_to_state`
4. 删除 `_apply_db_query` 中的手写清理
5. 前端 `agentTimeline.ts` 消费 `merge_strategy`
6. 前端 `types.ts` 扩展 `AgentStep`
7. 逐工具审查 A 类清单

### Phase 2: Track 2 — AI Schema Linking

1. 数据库迁移 (`schema_tables` / `schema_columns` 新字段)
2. 新建 `schema_search_docs` 表 + FTS5 索引
3. 实现 `engine/ai_index.py` (LLM 调用封装)
4. 改造 `schema.refresh_catalog` (AI 富化阶段)
5. 改造 `db.search` (FTS 路径 + 降级路径)
6. 实现 `_clean_orphan_search_docs`
7. 删除 `_BOOTSTRAP_SYNONYMS` 相关代码

### Phase 3: Test Coverage

1. `test_tool_contract.py` — 每个工具的契约验证
2. `test_agent_timeline.ts` — 前端 merge_strategy 行为
3. `test_ai_index.py` — LLM 输出验证 + 增量检测
4. `test_db_search_fts.py` — FTS 搜索准确度

---

## Non-Goals

- 不引入独立向量数据库 (Pinecone/Milvus)
- 不在 db.search 在线路径中调用 LLM
- 不在 db.search 在线路径中调用 embedding API
- 不改变前端时间线交互 (折叠/展开/思考过程)
- 不改变现有的 ToolObservation SSE 传输协议结构
- 不重构 `SemanticAlias` 表 schema（只加 source 字段区分来源）
