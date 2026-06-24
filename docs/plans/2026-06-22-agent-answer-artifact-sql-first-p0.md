# Agent Answer Artifact SQL-First P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the P0 behavior from `docs/designs/2026-06-22-agent-answer-artifact-and-sql-first.md`: stage-based narration, SQL-first analysis guidance, adaptive final answers, productized trace labels, and stronger table result browsing.

**Architecture:** Keep the existing backend event and artifact contracts. Update prompt/synthesis guidance on the backend, then improve frontend rendering by mapping raw runtime events to product language and making table artifacts behave like result previews with metadata, fixed scrolling, sticky headers, and CSV actions.

**Tech Stack:** Python 3.12, pytest, React 19, TypeScript, Vitest, Testing Library, lucide-react.

---

## File Structure

- Modify `engine/agent/model/system_prompt.py`: replace broad "Always speak" with stage narration rules and strengthen SQL-first analysis guidance.
- Modify `engine/tests/test_analysis_flow.py`: assert the new prompt contract.
- Modify `engine/agent_core/answer.py`: replace mandatory report sections with adaptive Markdown answer guidance.
- Modify `engine/agent/tests/test_answer_synthesis.py`: assert the LLM prompt asks for adaptive answers and not a fixed template.
- Modify `desktop/src/features/conversation/workspace/RunTracePanel.tsx`: map raw runtime event/tool names into user-facing Chinese labels, summarize completed runs, and keep failure traces open.
- Modify `desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx`: verify labels, collapse/open behavior, and summary text.
- Modify `desktop/src/types/agentArtifact.ts`: expose optional result table metadata already present in payloads.
- Modify `desktop/src/features/workspace/agentBridge.ts`: map row count, returned rows, latency, SQL, truncated state, and warnings into table artifacts.
- Modify `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`: add fixed-height scrolling, sticky header, row/column counts, preview/full affordance, truncation/warning display, NULL and numeric styling, CSV copy/export, and cell copy.
- Add `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`: verify table metadata and actions.

## Task 1: Backend Prompt Contract

- [ ] **Step 1: Write/update prompt tests**

Update `engine/tests/test_analysis_flow.py::TestSystemPrompt.test_prompt_requires_text_with_tool_calls` so it expects stage narration:

```python
from engine.agent.model.system_prompt import SYSTEM_PROMPT

assert "Stage Narration" in SYSTEM_PROMPT
assert "one short Chinese sentence" in SYSTEM_PROMPT
assert "Do not narrate every tiny internal step" in SYSTEM_PROMPT
assert "Never send an empty message" in SYSTEM_PROMPT
assert "Always speak" not in SYSTEM_PROMPT
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
python -m pytest engine/tests/test_analysis_flow.py::TestSystemPrompt -q
```

Expected before implementation: failure because the prompt still contains "Always speak" and does not contain the full Stage Narration contract.

- [ ] **Step 3: Update `SYSTEM_PROMPT`**

Replace the broad "Always speak" paragraph with a `## Stage Narration` section:

```text
## Stage Narration

When you call tools, include one short Chinese sentence that explains the current stage, finding, or next step.

Good narration is concrete and task-related:
- "我先定位和订单增长相关的数据表。"
- "找到 orders 和 users，我会检查它们的关联字段。"
- "我会先按日期聚合订单量，而不是直接读取大量明细。"

Do not narrate every tiny internal step. Do not repeat process narration in the final answer.
Never send an empty message with only tool calls.
```

Strengthen the query-result section with SQL-first wording:

```text
Raw rows are examples for validation. Analytical conclusions must come from SQL that aggregates, groups, compares, ranks, computes ratios, inspects distributions, or drills down.
```

- [ ] **Step 4: Re-run prompt tests**

Run:

```bash
python -m pytest engine/tests/test_analysis_flow.py::TestSystemPrompt -q
```

Expected after implementation: pass.

## Task 2: Adaptive Answer Synthesis

- [ ] **Step 1: Update answer synthesis tests**

In `engine/agent/tests/test_answer_synthesis.py`, keep the existing LLM invocation test and inspect the system prompt passed to the mocked model:

```python
messages = mock_model.invoke.call_args.args[0]
system_content = messages[0].content
assert "自适应 Markdown" in system_content
assert "不要强制使用固定章节" in system_content
assert "## 结论" not in system_content
assert "## 建议" not in system_content
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
python -m pytest engine/agent/tests/test_answer_synthesis.py -q
```

Expected before implementation: failure because the current prompt still mandates fixed sections.

- [ ] **Step 3: Update `synthesize_agent_answer` prompt**

Modify `engine/agent_core/answer.py` so the LLM system prompt says:

```text
你是一个专业的数据分析专家。你会收到用户问题和已经执行的查询结果，需要生成自适应 Markdown 答案。

答案规则：
- 简单事实：直接用 1-3 句话回答。
- 复杂分析：先给结论，再概括关键发现。
- SQL 任务：给出 SQL 和简短说明。
- Schema 任务：解释表、字段、关系和使用方式。
- 空结果：明确说明没有匹配数据，并给出可能原因。
- 证据不足：明确说不能可靠判断，并说明最有价值的下一步查询。
- 不要强制使用固定章节，不要强制给建议。
- 不要重复执行过程，不要编造没有查询支持的事实。
- 小型汇总可以用 Markdown 表；大型原始结果不要写成 Markdown 表。
- 优先基于聚合、分组、对比、排名、比例等分析 SQL 结果下结论。
- 使用中文，关键数字可加粗，语气客观专业。
```

- [ ] **Step 4: Re-run answer tests**

Run:

```bash
python -m pytest engine/agent/tests/test_answer_synthesis.py engine/tests/test_agent_answer.py -q
```

Expected after implementation: pass.

## Task 3: Productized Run Trace Panel

- [ ] **Step 1: Update trace tests**

Update `desktop/src/features/conversation/workspace/__tests__/RunTracePanel.test.tsx` to verify:

```tsx
expect(screen.getByText("执行过程 · 1 步 · 1 条 SQL · 128 行 · 42ms")).toBeTruthy();
expect(screen.getByText("执行只读查询")).toBeTruthy();
expect(screen.getByText("查询返回 128 行，正在整理结论。")).toBeTruthy();
expect(container.querySelector("details")?.hasAttribute("open")).toBe(false);
```

Add a failure test:

```tsx
expect(container.querySelector("details")?.hasAttribute("open")).toBe(true);
expect(screen.getByText("执行失败")).toBeTruthy();
expect(screen.getByText("SQL 语法错误")).toBeTruthy();
```

- [ ] **Step 2: Run focused failing frontend test**

Run:

```bash
npm --prefix desktop test -- RunTracePanel.test.tsx
```

Expected before implementation: failure because raw `sql.execute_readonly` is displayed and completed summary is generic.

- [ ] **Step 3: Implement label and summary helpers**

In `RunTracePanel.tsx`, add helpers that:

```ts
const TOOL_LABELS: Record<string, string> = {
  "db.observe": "浏览数据库结构",
  "db.search": "搜索相关表和字段",
  "db.inspect": "检查表结构",
  "db.preview": "预览样例数据",
  "sql.validate": "校验 SQL 安全性",
  "sql.execute_readonly": "执行只读查询",
  "chart.suggest": "生成图表建议",
  "answer.synthesize": "整理最终答案",
};
```

The completed summary should count visible events, SQL executions, row counts, and latency from `event.step` fields.

- [ ] **Step 4: Re-run trace tests**

Run:

```bash
npm --prefix desktop test -- RunTracePanel.test.tsx
```

Expected after implementation: pass.

## Task 4: Result Table Artifact View

- [ ] **Step 1: Add table view tests**

Create `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx` with tests that render a table artifact containing `rowCount`, `returnedRows`, `latencyMs`, `truncated`, `warnings`, numeric cells, and `NULL`.

Assert:

```tsx
expect(screen.getByText("预览 10 / 共 128 行")).toBeTruthy();
expect(screen.getByText("3 列")).toBeTruthy();
expect(screen.getByText("42ms")).toBeTruthy();
expect(screen.getByText("结果已截断")).toBeTruthy();
expect(screen.getByText("NULL")).toBeTruthy();
```

- [ ] **Step 2: Run focused failing frontend test**

Run:

```bash
npm --prefix desktop test -- TableArtifactView.test.tsx
```

Expected before implementation: failure because the current table view lacks metadata and warning display.

- [ ] **Step 3: Extend table artifact type and bridge**

Add optional fields to `desktop/src/types/agentArtifact.ts`:

```ts
rowCount?: number;
returnedRows?: number;
latencyMs?: number;
sql?: string;
truncated?: boolean;
warnings?: string[];
```

Map these fields in `desktop/src/features/workspace/agentBridge.ts` from payload keys `rowCount`, `returnedRows`, `latencyMs`, `sql`, `truncated`, `warnings`, and `notices`.

- [ ] **Step 4: Implement the result table UI**

Update `TableArtifactView.tsx` to:

- render only the first 10 rows in the default preview;
- show `预览 N / 共 M 行`, column count, and latency;
- use a fixed-height scroll region with sticky headers;
- preserve CSV copy/export for all available artifact rows;
- add a cell copy button behavior by clicking a cell;
- style `NULL` and numeric values distinctly.

- [ ] **Step 5: Re-run table tests**

Run:

```bash
npm --prefix desktop test -- TableArtifactView.test.tsx
```

Expected after implementation: pass.

## Task 5: Focused Verification

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
python -m pytest engine/tests/test_analysis_flow.py::TestSystemPrompt engine/agent/tests/test_answer_synthesis.py engine/tests/test_agent_answer.py -q
```

Expected: all pass.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
npm --prefix desktop test -- RunTracePanel.test.tsx TableArtifactView.test.tsx
```

Expected: all pass.

- [ ] **Step 3: Run TypeScript check if focused tests pass**

Run:

```bash
npm --prefix desktop run build
```

Expected: TypeScript build completes.

## Self-Review

- Spec coverage: P0 items 1-6 are covered. P1/P2 are intentionally out of scope for this plan.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: table metadata names match backend payload names and frontend artifact type extensions.
- Commit policy: this plan omits automatic commit steps because the user asked to develop, not to create commits.
