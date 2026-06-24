# DBFox Agent Answer, Artifact, and SQL-First Analysis Design

Date: 2026-06-22
Status: Design proposal

## 1. Goal

DBFox Agent should become a professional AI database workspace.

The experience should be:

- During execution, the agent shows a Codex-like working process: narration, tool execution, observations, and next steps.
- After completion, the process collapses automatically.
- The final answer becomes the main visual focus.
- SQL, result tables, charts, and data references are rendered as structured artifacts.
- Analytical conclusions come from precise SQL, not from asking the model to read many raw rows.

Core principle:

> Markdown for narrative, events for process, artifacts for data, references for evidence, SQL for analysis.

---

## 2. Problems Found

### 2.1 Process display feels too much like logs

The current UI already has the right rough structure:

```text
MessageBubble
  RunTracePanel
  Answer Markdown
  ArtifactEvidencePanel
```

But the user-facing process should not look like raw event names.

Instead of:

```text
db.search
sql.validate
agent.run.completed
```

It should say:

```text
我先定位相关数据表。
找到 orders 和 users，我会检查关联字段。
SQL 已通过只读校验，开始执行查询。
查询返回 128 行，我正在整理结论。
```

### 2.2 Agent narration should be stage-based

The agent should speak during execution, but not mechanically on every small step.

Use Stage Narration:

- one short Chinese sentence;
- concrete and task-related;
- describes the current stage, finding, or next step;
- shown in the process panel;
- not repeated in the final answer.

Good examples:

```text
我先定位和“订单增长”相关的表。
找到 orders 和 users，我会检查它们的关联字段。
我会先按日期聚合订单量，而不是直接读取明细。
查询返回 128 行，我正在整理结论和数据口径。
```

Bad examples:

```text
我将进行全面分析。
我会确保结果准确可靠。
基于目前信息我认为有必要进一步探索。
```

### 2.3 Final answer should not be a fixed template

A fixed structure such as:

```text
## 结论
## 关键指标
## 分析
## 数据口径
## 建议
```

is useful for some complex reports, but it should not be mandatory.

Simple questions should get simple answers. Complex questions should get structured analysis. Empty or insufficient results should be explained honestly.

### 2.4 Artifacts need stronger result browsing

Conversation evidence can preview results, but full query results should use a proper result table artifact.

A table preview is not the same as a data workspace.

DBFox needs:

- preview rows in chat;
- open full result table;
- fixed-height scrolling;
- sticky header;
- row and column counts;
- CSV copy/export;
- clear truncated or warning state;
- later: sorting, filtering, search, and virtualization.

### 2.5 The agent should not analyze large raw row sets directly

DBFox should not rely on putting 100 raw rows into the model context and asking the model to infer patterns.

Raw rows are for preview and validation.

Real analysis should be done with SQL:

- aggregate;
- group;
- compare;
- rank;
- calculate ratios;
- inspect distributions;
- drill down;
- validate hypotheses.

---

## 3. SQL-First Agent Work Style

The correct workflow is:

```text
1. Understand the user goal.
2. Search relevant tables and fields.
3. Inspect schema and relationships.
4. Preview a few rows only when useful.
5. Write analytical SQL.
6. Execute the analytical SQL.
7. Read compact analytical results.
8. Drill down with more precise SQL if needed.
9. Produce a grounded answer.
10. Attach SQL, table, chart, and reference artifacts.
```

Bad pattern:

```text
SELECT * FROM orders LIMIT 100;
Then ask the model to read 100 rows and guess the trend.
```

Good pattern:

```sql
SELECT
  DATE(created_at) AS day,
  COUNT(*) AS order_count,
  SUM(amount) AS gmv,
  AVG(amount) AS avg_order_amount
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY day;
```

Then drill down if needed:

```sql
SELECT
  channel,
  COUNT(*) AS order_count,
  SUM(amount) AS gmv
FROM orders
WHERE DATE(created_at) = '2026-06-18'
GROUP BY channel
ORDER BY order_count DESC;
```

Principle:

> Raw rows show examples. SQL produces evidence.

---

## 4. Runtime Process Design

### Running

The process panel is open.

```text
DBFox 正在分析…

● 我先定位和“订单增长”相关的数据表。
  搜索相关表和字段

● 找到 orders 和 users，我会检查它们的关联字段。
  检查表结构：orders、users

● 我会先按日期聚合订单量，而不是直接读取明细。
  执行分析 SQL

● 发现 6 月 12 日后增长明显，我会按渠道继续拆分。
  执行钻取 SQL

● 查询返回 8 个渠道的聚合结果，我正在整理结论。
```

### Completed

The process collapses.

```text
▸ 执行过程 · 6 步 · orders、users · 2 条 SQL · 128 行 · 42ms
```

### Failed

The process remains open and shows:

- failed step;
- reason;
- recovery suggestion;
- available safe alternative.

### Event display mapping

Raw event or tool names should be mapped into product language:

```text
db.observe              -> 浏览数据库结构
db.search               -> 搜索相关表和字段
db.inspect              -> 检查表结构
db.preview              -> 预览样例数据
sql.validate            -> 校验 SQL 安全性
sql.execute_readonly    -> 执行只读查询
chart.suggest           -> 生成图表建议
answer.synthesize       -> 整理最终答案
agent.run.started       -> 开始执行任务
agent.run.completed     -> 任务完成
agent.run.failed        -> 执行失败
```

---

## 5. Final Answer Design

Final answers should use adaptive Markdown.

Rules:

- Simple facts: answer directly in 1-3 sentences.
- Complex analysis: start with the conclusion, then summarize key findings.
- SQL tasks: show SQL and a short explanation.
- Schema tasks: explain tables, fields, relationships, and usage.
- Empty results: explain no match and possible reasons.
- Insufficient evidence: say what cannot be concluded and what query would help.
- Do not repeat the execution process.
- Do not force recommendations.
- Do not invent unsupported facts.
- Prefer analytical SQL results over raw row previews.

Simple answer example:

```text
今天共有 **1,284 个订单**。

口径：按 `orders.created_at` 统计今日订单，排除 `cancelled` 状态。
```

Analytical answer example:

```text
本月订单量整体上升，当前累计订单数为 **12,840**，相比上月同期增长 **18.2%**。

关键变化：

| 指标 | 本月 | 上月同期 | 变化 |
|---|---:|---:|---:|
| 订单数 | 12,840 | 10,862 | +18.2% |
| GMV | 983,200 | 812,400 | +21.0% |
| 新用户订单占比 | 34.6% | 28.1% | +6.5pp |

增长主要集中在 6 月 12 日之后。按渠道拆分后，增长主要来自 paid_search 和 referral。

口径：按 `orders.created_at` 统计，排除 `cancelled` 状态。
```

Insufficient evidence example:

```text
目前不能可靠判断增长原因。

已有查询只能说明订单量在本月中旬后上升，但还没有按渠道、用户类型或活动维度拆分，所以无法判断增长来自投放、自然流量还是老用户复购。

下一步最有价值的是按渠道和新老用户拆分订单量。
```

---

## 6. Rendering Protocol

Separate narrative, process, data, and evidence.

```text
Markdown for narrative.
Events for process.
Artifacts for data.
References for evidence.
```

Recommended event shape:

```ts
type AgentStreamEvent =
  | { type: "progress.narration"; text: string; stage: string }
  | { type: "tool.started"; tool: string; displayName: string; summary?: string }
  | { type: "tool.completed"; tool: string; displayName: string; summary?: string; rowCount?: number; durationMs?: number }
  | { type: "artifact.created"; artifactId: string; artifactType: "sql" | "table" | "chart" }
  | { type: "reference.added"; reference: DataReference }
  | { type: "answer.delta"; delta: string }
  | { type: "answer.completed" };
```

Recommended message rendering:

```text
MessageBubble
  RunTracePanel        // running: open; completed: collapsed
  AnswerMarkdown       // streamed Markdown answer
  DataReferencePanel   // clickable evidence
  ArtifactPanel        // SQL / table / chart
```

---

## 7. Data References

Data references are DBFox's evidence system.

Final answers should show:

```text
数据来源：
[orders] [users] [SQL: 趋势分析] [SQL: 渠道拆分] [结果表] [趋势图]
```

Reference actions:

```text
Table       -> open table structure or preview
Column      -> open table schema and locate field
SQL         -> open SQL artifact
Result      -> open result table artifact
Chart       -> open chart artifact
```

Recommended type:

```ts
type DataReference =
  | { type: "table"; datasourceId: string; schema?: string; table: string; label: string }
  | { type: "column"; datasourceId: string; schema?: string; table: string; column: string; label: string }
  | { type: "sql"; artifactId: string; label: string }
  | { type: "result"; artifactId: string; rowCount?: number; label: string }
  | { type: "chart"; artifactId: string; label: string };
```

MVP should support table, SQL, result, and chart references first.

---

## 8. Artifact Design

### SQL Artifact

Every important SQL query should become an artifact.

It should show:

- purpose;
- SQL text;
- validation status;
- execution status;
- latency;
- returned row count;
- referenced tables;
- actions: copy, open console.

### Result Table Artifact

Real query results should be rendered with a professional table view, not large Markdown tables.

It should support:

- fixed-height scroll area;
- sticky header;
- horizontal scroll;
- row and column counts;
- latency;
- warnings and truncation state;
- CSV copy/export;
- cell copy;
- NULL styling;
- numeric alignment;
- date formatting;
- open full result;
- later sorting, filtering, search, and virtualization.

### Chart Artifact

Charts should link metrics back to source fields.

Example:

```text
GMV      -> SUM(orders.amount)
订单数   -> COUNT(*)
时间轴   -> orders.created_at
```

---

## 9. Table Display Rules

Markdown tables are allowed for small summaries only.

Good uses:

- key metrics;
- Top 5;
- small comparison;
- compact summary.

Limits:

- normally no more than 6 rows;
- normally no more than 4 columns;
- never use Markdown tables for large raw result sets.

Result table display rules:

```text
0 rows:
  show empty state + SQL + metric definition

1-10 rows:
  conversation can show all rows

11-100 rows:
  preview 10 rows + fixed-height scroll / view all

101-500 rows:
  preview 10 rows + strong open-full-result affordance

500+ rows:
  preview 10 rows + virtualized full result view + suggest filtering/export
```

Payload should distinguish:

```text
rowCount      -> total result rows represented
returnedRows  -> rows included in artifact payload
previewRows   -> rows currently rendered in chat
truncated     -> backend stopped returning more data due to limits
```

---

## 10. Implementation Priorities

### P0

1. Replace broad Always Speak behavior with Stage Narration guidance.
2. Add SQL-first analysis guidance to the system prompt.
3. Replace fixed final-answer template with adaptive Markdown answer guidance.
4. Productize RunTracePanel labels.
5. Collapse trace after completion and keep it open on failure.
6. Improve table preview:
   - preview 10 rows;
   - show preview count and total count;
   - add view-all, collapse, or open-full-result action;
   - fixed-height scroll;
   - sticky header.

### P1

1. Add DataReferencePanel.
2. Add references protocol for table, SQL, result, and chart artifacts.
3. Upgrade TableArtifactView into ResultTableView.
4. Show rowCount, returnedRows, latency, truncated, warnings, and notices.
5. Keep CSV copy/export and add cell copy.
6. Make SQL artifacts show purpose, used tables, row count, and latency.
7. Teach the agent to run follow-up analytical SQL after raw preview when needed.

### P2

1. Field-level references.
2. Clickable table and field tokens inside SQL blocks.
3. Chart metrics linked to source fields and aggregation formulas.
4. Virtualized result table for larger results.
5. Result table sorting, filtering, and search.
6. Right-side Inspector for table structure, fields, SQL, and evidence chain.
7. Developer/debug view for raw events and low-level payloads.

---

## 11. Final Design Judgment

DBFox Agent should become:

> A Codex-like, observable database agent that speaks while working, collapses process after completion, writes smart adaptive answers, uses SQL as the primary analysis engine, and presents every conclusion with clickable evidence and high-quality data artifacts.

The three most important principles:

1. Runtime process should be visible, but collapsed after completion.
2. Final answers should be smart Markdown summaries, not fixed templates.
3. Analytical conclusions should come from precise SQL, not from reading many raw rows in model context.
