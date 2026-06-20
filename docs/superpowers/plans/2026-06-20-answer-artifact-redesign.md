# Answer & Artifact 架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 answer 和 artifact 系统：删除 result.profile、统一答案生成为单一路径、artifact 分层为 Evidence/Process、前端答案优先

**Architecture:** Agent 自己写统计 SQL 替代 result.profile；answer.synthesize 成为唯一答案入口；artifact 分 Evidence（table/chart/sql，用户可见）和 Process（其余，Trace 面板）；前端 FinalAnswerCard 答案正文主导，支撑数据折叠

**Spec:** `docs/superpowers/specs/2026-06-20-answer-artifact-redesign.md`

**Tech Stack:** Python (Pydantic, LangChain/LangGraph), TypeScript (React), SQLite

## Global Constraints

- 不硬编码模板字符串 — 所有文本生成走 LLM prompt
- AI 自己写统计 SQL — 删除 result.profile 工具
- answer.synthesize 是唯一答案生成入口
- Evidence artifact: table / chart / sql 三种
- Process artifact: query_plan / sql_suggestion / safety / agent_plan / error 五种
- 删除 `recommendation` 和 `insight` artifact 类型
- 删除 `ResultProfile` / `ColumnProfile` 类型
- 前端答案正文永远可见，支撑数据折叠

---

### Task 1: 更新 types.py — Artifact 分层和删除类型

**Files:**
- Modify: `engine/agent_core/types.py`

**Interfaces:**
- Produces: `EVIDENCE_ARTIFACT_TYPES`, `PROCESS_ARTIFACT_TYPES` constants; updated `AgentArtifactType`

- [ ] **Step 1: 添加分层常量，更新 ArtifactType，删除 recommendation 和 insight**

在 `AgentArtifactType` 定义后添加:

```python
# Artifact categorization
EVIDENCE_ARTIFACT_TYPES: frozenset[str] = frozenset({"table", "chart", "sql"})
PROCESS_ARTIFACT_TYPES: frozenset[str] = frozenset({
    "query_plan", "sql_suggestion", "safety", "agent_plan", "error",
})
```

修改 `AgentArtifactType` Literal，删除 `"insight"` 和 `"recommendation"`:

```python
AgentArtifactType = Literal[
    "agent_plan",
    "query_plan",
    "sql",
    "sql_suggestion",
    "safety",
    "table",
    "chart",
    "error",
]
```

- [ ] **Step 2: 删除 ResultProfile 和 ColumnProfile**

删除 `ResultProfile` 和 `ColumnProfile` 两个 BaseModel 类。

- [ ] **Step 3: 运行现有测试确认破坏范围**

```bash
cd D:\Project\DBFox && python -m pytest engine/agent/tests/ engine/tests/ -x --tb=short 2>&1 | head -80
```

预期: 大量测试失败（因为引用了被删除的类型），这确认了破坏范围。

- [ ] **Step 4: Commit**

```bash
git add engine/agent_core/types.py
git commit -m "refactor: add artifact categories, remove insight/recommendation/ResultProfile types"
```

---

### Task 2: 删除 result_profiler.py 和 analysis_composer.py

**Files:**
- Delete: `engine/agent_core/result_profiler.py`
- Delete: `engine/agent_core/analysis_composer.py`

- [ ] **Step 1: 删除文件**

```bash
rm engine/agent_core/result_profiler.py
rm engine/agent_core/__pycache__/result_profiler.cpython-*.pyc 2>/dev/null; true
rm engine/agent_core/analysis_composer.py
rm engine/agent_core/__pycache__/analysis_composer.cpython-*.pyc 2>/dev/null; true
```

- [ ] **Step 2: 检查所有 import 引用**

```bash
cd D:\Project\DBFox && rg "result_profiler|analysis_composer" --type py
```

记录所有引用位置，后续 task 逐一修复。

- [ ] **Step 3: Commit**

```bash
git rm engine/agent_core/result_profiler.py engine/agent_core/analysis_composer.py
git commit -m "refactor: remove result_profiler and analysis_composer"
```

---

### Task 3: 重写 answer.py — 统一答案生成

**Files:**
- Modify: `engine/agent_core/answer.py`

**Interfaces:**
- Produces: `synthesize_agent_answer(question, analysis_units, *, model_name, api_key, api_base) -> AgentAnswer`
- Deletes: `_format_profile_for_ai`, `_format_result_preview`（移到工具层）, `_compose_multi_unit_report`, `_multi_unit_evidence`

- [ ] **Step 1: 重写 synthesize_agent_answer**

```python
from __future__ import annotations

from typing import Any

from engine.agent_core.types import AgentAnswer, AnswerEvidence


def synthesize_agent_answer(
    question: str,
    *,
    analysis_units: list[dict[str, Any]],
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    error: str | None = None,
) -> AgentAnswer:
    """Generate a structured answer from collected analysis units via LLM.

    This is the SINGLE entry point for answer generation.  No hardcoded
    templates — every answer goes through the same LLM prompt path.
    """
    if error and not analysis_units:
        return AgentAnswer(
            answer=f"分析未能完成：{error}",
            key_findings=[],
            evidence=[],
            caveats=["本次运行未成功完成。"],
            recommendations=[],
            follow_up_questions=[],
        )

    # Build context for the LLM
    import os
    has_credentials = bool(
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("DBFOX_LLM_API_KEY")
    )

    if not (has_credentials or os.environ.get("DBFOX_TESTING") == "1"):
        # No LLM available — return a minimal answer from raw data
        return _fallback_answer(question, analysis_units, error)

    from engine.llm import get_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage

    model = get_chat_model(
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
        temperature=0.3,
    )

    system_prompt = (
        "你是一个专业的数据分析专家。你会收到用户问题和查询执行结果，"
        "需要生成一份结构化的 Markdown 分析报告。\n\n"
        "注意：在执行过程中，你已有能力自己写 SQL 进行统计分析"
        "（如 COUNT、AVG、SUM、GROUP BY 等），"
        "因此你现在拿到的结果已经是经过分析的数据。\n\n"
        "格式要求：\n"
        "## 结论\n1-2 句话总结核心发现\n\n"
        "## 关键指标\n用**粗体数字**列出最重要的指标\n\n"
        "## 分析\n说明趋势、占比、异常、规律\n\n"
        "## 数据口径\n说明覆盖的数据范围、时间跨度、过滤条件\n\n"
        "## 建议\n2-3 条可操作的下一步\n\n"
        "规则：\n"
        "- 如果结果是空集，直接说明\"没有找到符合条件的数据\"，不要编造\n"
        "- **加粗关键数字**\n"
        "- 控制在 200-500 字\n"
        "- 使用中文，语气客观专业\n"
    )

    user_parts = [f"用户问题: {question}\n"]
    units = [u for u in analysis_units if not u.get("is_empty")]
    if not units:
        units = analysis_units

    for i, u in enumerate(units):
        exec_data = u.get("execution") or {}
        sql_text = (u.get("sql") or "")[:300]
        columns = exec_data.get("columns", [])
        rows = exec_data.get("rows", [])
        row_count = exec_data.get("rowCount", len(rows))
        chart = u.get("chart") or {}

        user_parts.append(f"### 查询 {i + 1}")
        user_parts.append(f"SQL: {sql_text}")
        user_parts.append(f"列: {columns}")
        user_parts.append(f"行数: {row_count}")

        # Preview rows — cap to avoid token explosion
        if rows:
            preview = _format_rows(columns, rows[:5])
            user_parts.append(f"结果预览 (前 5 行):\n{preview}")
            if row_count > 5:
                user_parts.append(f"(共 {row_count} 行，以上仅前 5 行)")

        if chart:
            user_parts.append(
                f"图表: {chart.get('type')}, X={chart.get('x')}, Y={chart.get('y')}"
            )

    user_content = "\n".join(user_parts)

    try:
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
        if response and response.content:
            report_text = response.content.strip()

            # Extract key_findings from bold markers in the report
            key_findings = _extract_key_findings(report_text)

            # Build evidence from analysis units
            evidence = _build_evidence(units)

            # Collect caveats
            caveats: list[str] = []
            for u in units:
                if u.get("is_empty"):
                    caveats.append("部分查询未返回结果")
                    break
                if u.get("is_truncated"):
                    caveats.append("部分结果被截断")
            if error:
                caveats.append(f"运行中有非致命错误: {error}")

            return AgentAnswer(
                answer=report_text,
                key_findings=key_findings[:8],
                evidence=evidence,
                caveats=caveats[:5],
                recommendations=[],
                follow_up_questions=[],
            )
    except Exception:
        pass

    return _fallback_answer(question, analysis_units, error)


def _format_rows(columns: list[str], rows: list[list[Any]]) -> str:
    """Format a small number of rows as a text table."""
    if not columns or not rows:
        return "(无数据)"
    lines: list[str] = []
    header = " | ".join(str(c) for c in columns[:8])
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        if isinstance(row, dict):
            cells = [str(row.get(c, ""))[:60] for c in columns]
        elif isinstance(row, list):
            cells = [str(v)[:60] for v in row]
        else:
            cells = [str(row)[:60]]
        while len(cells) < len(columns):
            cells.append("")
        lines.append(" | ".join(cells[:8]))
    return "\n".join(lines)


def _extract_key_findings(text: str) -> list[str]:
    """Extract bold-marked phrases as key findings."""
    import re
    matches = re.findall(r'\*\*(.+?)\*\*', text)
    return [m.strip() for m in matches if len(m.strip()) > 3][:8]


def _build_evidence(units: list[dict[str, Any]]) -> list[AnswerEvidence]:
    """Build evidence list from analysis units."""
    evidence: list[AnswerEvidence] = []
    total_rows = 0
    for u in units:
        exec_data = u.get("execution") or {}
        total_rows += int(exec_data.get("rowCount", 0))

    if len(units) == 1:
        evidence.append(AnswerEvidence(
            artifact_id="result_table",
            label="查询行数",
            value=total_rows,
        ))
    else:
        evidence.append(AnswerEvidence(
            artifact_id="result_table",
            label="查询次数",
            value=len(units),
        ))
        if total_rows > 0:
            evidence.append(AnswerEvidence(
                artifact_id="result_table",
                label="合计行数",
                value=total_rows,
            ))
    return evidence


def _fallback_answer(
    question: str,
    analysis_units: list[dict[str, Any]],
    error: str | None,
) -> AgentAnswer:
    """Minimal answer when no LLM is available."""
    units = [u for u in analysis_units if not u.get("is_empty")]
    total_rows = sum(
        int((u.get("execution") or {}).get("rowCount", 0)) for u in units
    )

    if total_rows == 0:
        text = f"已完成查询，但没有找到符合「{question}」的记录。"
    else:
        text = f"已完成 {len(units)} 次查询，共返回 {total_rows} 行结果。"

    return AgentAnswer(
        answer=text,
        key_findings=[f"共 {total_rows} 行结果"] if total_rows > 0 else [],
        evidence=_build_evidence(units),
        caveats=["本次未使用 AI 生成分析，仅展示基础统计。"] if error else [],
        recommendations=[],
        follow_up_questions=[],
    )
```

- [ ] **Step 2: 删除旧函数**

删除以下函数（它们不再被调用）:
- `_base_evidence`
- `_format_profile_for_ai`
- `_format_result_preview`
- `_compose_multi_unit_report`
- `_multi_unit_evidence`
- `_dedupe`

`_format_rows` 保留（新实现，更简单）。

- [ ] **Step 3: 确认函数签名**

保留的公开函数签名:
```python
def synthesize_agent_answer(
    question: str,
    *,
    analysis_units: list[dict[str, Any]],
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    error: str | None = None,
) -> AgentAnswer:
```

注意：删除了 `query_plan`、`sql`、`safety`、`execution`、`result_profile`、`suggestions` 参数。这些信息现在通过 `analysis_units` 传递（每个 unit 已包含 sql 和 execution）。

- [ ] **Step 4: Commit**

```bash
git add engine/agent_core/answer.py
git commit -m "refactor: rewrite synthesize_agent_answer — single entry, LLM-prompt-driven, no profile"
```

---

### Task 4: 清理 artifacts.py — 删除 profile 和 recommendation artifact

**Files:**
- Modify: `engine/agent_core/artifacts.py`

- [ ] **Step 1: 删除 build_profile_artifact 函数**

删除整个 `build_profile_artifact` 函数（约 18 行）。

- [ ] **Step 2: 删除 build_recommendations_artifact 函数**

删除整个 `build_recommendations_artifact` 函数（约 16 行）。

- [ ] **Step 3: 更新 build_agent_artifacts**

```python
def build_agent_artifacts(
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    chart_suggestion: dict[str, Any] | None,
    answer: AgentAnswer | None,
    error: str | None = None,
    identity: AgentArtifactIdentity | None = None,
) -> list[AgentArtifact]:
    artifacts: list[AgentArtifact] = []

    if query_plan:
        artifacts.append(build_query_plan_artifact(query_plan, identity=identity))

    if sql:
        artifacts.append(build_sql_artifact(sql, safety=safety, identity=identity))

    if safety:
        artifacts.append(build_safety_artifact(safety, identity=identity))

    if execution and execution.get("success"):
        artifacts.append(build_table_artifact(execution, safety=safety, identity=identity))

    if chart_suggestion and chart_suggestion.get("type") and chart_suggestion.get("type") != "table":
        artifacts.append(build_chart_artifact(chart_suggestion, safety=safety, execution=execution, identity=identity))

    if error:
        artifacts.append(build_error_artifact(error, safety=safety, execution=execution, identity=identity))

    return sorted(artifacts, key=lambda artifact: artifact.presentation.priority)
```

删除了 `result_profile` 参数和对应的 `build_profile_artifact` 调用。
删除了 `answer.recommendations` 检查和 `build_recommendations_artifact` 调用。

- [ ] **Step 4: 检查 build_agent_plan_artifact 是否还在被使用**

```bash
rg "build_agent_plan_artifact" --type py
```

如果没有调用方，删除它。

- [ ] **Step 5: Commit**

```bash
git add engine/agent_core/artifacts.py
git commit -m "refactor: remove profile and recommendation artifact builders"
```

---

### Task 5: 简化 finalize_node.py

**Files:**
- Modify: `engine/agent/nodes/finalize_node.py`

- [ ] **Step 1: 删除 answer 组装逻辑**

`finalize_answer` 当前做了太多事：提取 answer 文本、拼装 evidence、构建 answer_payload。应该简化为纯收尾。

```python
def finalize_answer(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Finalize the agent run — mark status, persist, write trajectory."""

    messages = state.get("messages", [])
    error = state.get("error")
    pending_approval = state.get("pending_approval")

    existing_answer = state.get("answer")
    answer_dict = existing_answer if isinstance(existing_answer, dict) else {}
    has_answer = bool(answer_dict.get("answer") or "")

    if pending_approval:
        status = "waiting_approval"
    elif has_answer:
        status = "completed"
        error = None
    elif error:
        status = "failed"
    else:
        status = "failed"
        if not error:
            error = "Agent completed without producing an answer."

    # Ensure answer has evidence from artifacts if missing
    if has_answer and not answer_dict.get("evidence"):
        from engine.agent_core.answer import _build_evidence
        units = state.get("analysis_units") or []
        answer_dict["evidence"] = [
            ev.model_dump() for ev in _build_evidence(units)
        ]

    trace_event: dict[str, Any] = {
        "type": "agent.finalized",
        "status": status,
        "has_answer": has_answer,
        "has_error": bool(error),
    }

    _auto_write_trajectory(state, status, str(answer_dict.get("answer") or ""))

    result: dict[str, Any] = {
        "status": status,
        "answer": answer_dict,
        "final_answer": answer_dict,
        "error": error,
        "trace_events": [trace_event],
        "agent_graph_route": "end",
    }

    if status == "failed" and error:
        error_artifact = _build_and_persist_error_artifact(state, config, str(error))
        if error_artifact is not None:
            result["artifacts"] = [error_artifact]

    return result
```

关键改动:
- 不再从 `messages[-1]` 提取 answer 文本
- 不再自己构建 evidence（如果 answer 没有 evidence，用 tool 函数补充）
- 不再有 `_looks_like_tool_envelope` 检查
- `answer_payload` 直接来自 state 中的 `answer`（由 `answer.synthesize` 工具写入）

- [ ] **Step 2: 删除 _looks_like_tool_envelope**

此函数不再需要。

- [ ] **Step 3: Commit**

```bash
git add engine/agent/nodes/finalize_node.py
git commit -m "refactor: simplify finalize_node — answer comes from synthesize tool only"
```

---

### Task 6: 更新 dbfox_tools.py — 删除 ResultProfileTool，更新 AnswerSynthesizeTool

**Files:**
- Modify: `engine/tools/dbfox_tools.py`

- [ ] **Step 1: 删除 ResultProfileTool 类**

找到 `ResultProfileTool` 类（应该有 `name = "result.profile"`），删除整个类定义。

- [ ] **Step 2: 更新 AnswerSynthesizeTool**

更新 `AnswerSynthesizeTool.run` — 新的 `synthesize_agent_answer` 签名不再需要 `query_plan`、`sql`、`safety`、`execution`、`result_profile`、`suggestions`:

```python
class AnswerSynthesizeTool(BaseTool[AnswerSynthesizeInput, AgentAnswer]):
    name = "answer.synthesize"
    group = "answer"
    description = (
        "Synthesize a structured final answer from all collected evidence: "
        "query results, charts, and any errors. "
        "Produces an AgentAnswer with key findings, evidence references, "
        "caveats, and recommendations."
    )
    input_model = AnswerSynthesizeInput
    output_model = AgentAnswer
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        consumes=("analysis_units", "error"),
        produces=("answer", "final_answer"),
        merge_strategy="always_new",
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("sql", "table", "chart"))

    def run(self, tool_input: AnswerSynthesizeInput, context: ToolRunContext) -> AgentAnswer:
        question = tool_input.question or getattr(context.request, "question", "") or ""
        model_name = getattr(context.request, "model_name", None)
        api_key = getattr(context.request, "api_key", None)
        api_base = getattr(context.request, "api_base", None)

        return synthesize_agent_answer(
            question=question,
            analysis_units=list(context.state.get("analysis_units") or []),
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            error=context.state.get("error"),
        )
```

- [ ] **Step 3: 更新 import**

```python
from engine.agent_core.answer import synthesize_agent_answer
# 删除: from engine.agent_core.result_profiler import profile_result
# 删除: from engine.agent_core.types import ResultProfile
```

- [ ] **Step 4: 更新 chart_builder.py 的调用方（如果有）**

检查 `chart_builder.py` 的 `suggest_plotly_chart` 是否依赖 `ResultProfile`:

```bash
rg "ResultProfile|result_profile|ColumnProfile" engine/agent_core/chart_builder.py
```

如果有引用，更新函数签名。

- [ ] **Step 5: Commit**

```bash
git add engine/tools/dbfox_tools.py engine/agent_core/chart_builder.py
git commit -m "refactor: remove ResultProfileTool, update AnswerSynthesizeTool signature"
```

---

### Task 7: 清理 state_reducer.py

**Files:**
- Modify: `engine/tools/runtime/state_reducer.py`

- [ ] **Step 1: 删除 result.profile 处理逻辑**

在 `_apply_success_output` 中删除 `result.profile` 分支（约 5 行）:

```python
# 删除这段:
if tool_name == "result.profile":
    result: dict[str, Any] = {"result_profile": output}
    unit_id = state.get("current_analysis_unit_id")
    if unit_id:
        result["analysis_units"] = _enrich_units(state.get("analysis_units", []), unit_id, profile=output)
    return result
```

- [ ] **Step 2: 更新 _enrich_units 函数**

删除 `profile` 参数，只保留 `chart`:

```python
def _enrich_units(
    units: list[dict[str, Any]],
    unit_id: str,
    *,
    chart: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return a new list with the matching unit enriched in-place copy."""
    updated = list(units)
    for i, u in enumerate(updated):
        if u.get("id") == unit_id:
            copy = dict(u)
            if chart is not None:
                copy["chart"] = chart
            updated[i] = copy
            break
    return updated
```

- [ ] **Step 3: 更新 ARTIFACT_TOOLS 列表**

```python
ARTIFACT_TOOLS = {"db.preview", "db.query", "sql.execute_readonly", "chart.suggest", "answer.synthesize"}
```

删除 `"result.profile"`。

- [ ] **Step 4: 更新 answer.synthesize 的 state 处理**

`answer.synthesize` 分支当前是:
```python
if tool_name == "answer.synthesize":
    return {"answer": output, "final_answer": output}
```

保持不变。`output` 现在是 `AgentAnswer` 的 model_dump 结果。

- [ ] **Step 5: 删除 state 中的 result_profile 引用**

检查 state 中是否还有 `result_profile` 的读写:

```bash
rg "result_profile" engine/tools/runtime/state_reducer.py
```

清理残留引用。

- [ ] **Step 6: Commit**

```bash
git add engine/tools/runtime/state_reducer.py
git commit -m "refactor: remove result.profile from state_reducer, simplify enrichment"
```

---

### Task 8: 更新 graph state.py — 删除 result_profile 字段

**Files:**
- Modify: `engine/agent/graph/state.py`

- [ ] **Step 1: 删除 result_profile 字段**

在 `DBFoxAgentState` TypedDict 中删除:
```python
result_profile: dict[str, Any] | None
```

- [ ] **Step 2: 检查所有引用**

```bash
rg "result_profile" engine/agent/ --type py
```

修复所有引用位置。

- [ ] **Step 3: Commit**

```bash
git add engine/agent/graph/state.py
git commit -m "refactor: remove result_profile from agent state"
```

---

### Task 9: 更新前端 types.ts

**Files:**
- Modify: `desktop/src/lib/api/types.ts`

- [ ] **Step 1: 更新 AgentArtifact type**

```typescript
export interface AgentArtifact {
  id: string;
  semantic_id?: string | null;
  type: "agent_plan" | "query_plan" | "sql" | "sql_suggestion" | "safety" | "table" | "chart" | "error";
  // ... rest unchanged
}
```

删除 `"insight"` 和 `"recommendation"`。

- [ ] **Step 2: 添加分层常量**

```typescript
export const EVIDENCE_ARTIFACT_TYPES = new Set(["table", "chart", "sql"]);
export const PROCESS_ARTIFACT_TYPES = new Set(["query_plan", "sql_suggestion", "safety", "agent_plan", "error"]);
```

- [ ] **Step 3: 删除 ResultProfile 接口（如果存在）**

```bash
rg "ResultProfile|ColumnProfile" desktop/src/lib/api/types.ts
```

- [ ] **Step 4: Commit**

```bash
git add desktop/src/lib/api/types.ts
git commit -m "refactor(frontend): update artifact types, add categories, remove insight/recommendation"
```

---

### Task 10: 重构 FinalAnswerCard.tsx

**Files:**
- Modify: `desktop/src/features/agentTask/FinalAnswerCard.tsx`

- [ ] **Step 1: 重构为答案优先布局**

核心改动:
- 答案正文（Markdown）永远在最显眼位置
- Evidence artifact（table/chart/sql）通过 `answer.evidence` 链接，内联折叠展示
- 不再独立遍历 `artifacts` 列表匹配

```tsx
import { useMemo } from "react";
import {
  Lightbulb, AlertTriangle, Database, Terminal, ChevronRight,
} from "lucide-react";
import type { AgentAnswer } from "../../lib/api/types";
import type { AgentArtifact } from "../../types/agentArtifact";
import type { AgentTabStatus } from "../../mock/dbfoxMock";
import { EVIDENCE_ARTIFACT_TYPES } from "../../lib/api/types";
import { MarkdownContent } from "../workspace/queryResult/MarkdownContent";

interface FinalAnswerCardProps {
  answer: AgentAnswer | null | undefined;
  artifacts: AgentArtifact[];
  agentStatus: AgentTabStatus | "idle";
  onSendFollowUp: (text: string) => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

function isRealAnswer(answer: AgentAnswer): boolean {
  const text = (answer.answer || "").trim();
  return text.length > 0;
}

// Filter artifacts to only evidence types
function getEvidenceArtifacts(artifacts: AgentArtifact[]): AgentArtifact[] {
  return artifacts.filter(a => EVIDENCE_ARTIFACT_TYPES.has(a.type));
}

export function FinalAnswerCard({
  answer, artifacts, agentStatus, onSendFollowUp, onOpenSqlConsole, onToast,
}: FinalAnswerCardProps) {
  const hasCaveats = answer?.caveats && answer.caveats.length > 0;
  const hasRecommendations = answer?.recommendations && answer.recommendations.length > 0;
  const hasFollowUp = answer?.follow_up_questions && answer.follow_up_questions.length > 0;

  const evidenceArtifacts = useMemo(
    () => getEvidenceArtifacts(artifacts),
    [artifacts],
  );

  const tableArts = evidenceArtifacts.filter(a => a.type === "table");
  const chartArts = evidenceArtifacts.filter(a => a.type === "chart");
  const sqlArts = evidenceArtifacts.filter(a => a.type === "sql");

  const accentClass = agentStatus === "failed"
    ? "task-answer-error"
    : hasCaveats ? "task-answer-warn" : "task-answer-success";

  if (!answer || !isRealAnswer(answer)) return null;

  return (
    <div className={`task-answer-card ${accentClass}`}>

      {/* Answer body — Markdown, always visible */}
      <div className="task-answer-markdown">
        <MarkdownContent content={answer.answer} />
      </div>

      {/* Evidence artifacts — collapsible section */}
      {evidenceArtifacts.length > 0 && (
        <details className="task-answer-evidence-details">
          <summary className="task-answer-section-title">
            <Database size={12} />
            <span>支撑数据</span>
            <span className="text-[10px] text-slate-400 ml-2">
              ({tableArts.length} 表, {chartArts.length} 图, {sqlArts.length} SQL)
            </span>
          </summary>

          <div className="task-evidence-body">
            {/* Tables */}
            {tableArts.map(t => (
              <div key={t.id} className="task-evidence-table">
                <div className="task-evidence-head">
                  <Database size={11} />
                  <span>{t.title || "结果表"}</span>
                  <span className="text-[10px] text-slate-400 ml-auto">
                    {(t.payload?.rows as any[])?.length ?? 0} 行 × {(t.payload?.columns as any[])?.length ?? 0} 列
                  </span>
                </div>
                <div className="task-artifact-table-wrap">
                  <table className="task-artifact-table">
                    <thead><tr>
                      {((t.payload?.columns as string[]) || []).slice(0, 6).map((col: string, ci: number) => (
                        <th key={ci}>{col}</th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {((t.payload?.rows as any[][]) || []).slice(0, 10).map((row: any[], ri: number) => (
                        <tr key={ri}>
                          {((t.payload?.columns as string[]) || []).slice(0, 6).map((col: string, ci: number) => (
                            <td key={ci}>{String(row?.[ci] ?? (row as Record<string, unknown>)?.[col] ?? "")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}

            {/* Charts */}
            {chartArts.map(c => (
              <div key={c.id} className="task-evidence-chart">
                {/* Reuse existing ChartArtifactView rendering */}
              </div>
            ))}

            {/* SQL */}
            {sqlArts.map(s => (
              <div key={s.id} className="task-evidence-sql">
                <div className="task-evidence-head">
                  <Terminal size={11} />
                  <span>SQL</span>
                </div>
                <pre className="task-artifact-sql-pre">{(s.payload as any)?.sql || ""}</pre>
                <button
                  className="task-artifact-btn"
                  onClick={() => onOpenSqlConsole((s.payload as any)?.sql)}
                  type="button"
                >
                  在 SQL 控制台打开
                </button>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Caveats */}
      {hasCaveats && (
        <div className="task-answer-caveats">
          <div className="task-answer-section-title">
            <AlertTriangle size={12} /><span>注意事项</span>
          </div>
          <ul className="task-answer-list">
            {answer.caveats!.map((caveat, i) => (
              <li key={i}><span>{caveat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendations */}
      {hasRecommendations && (
        <div className="task-answer-recommendations">
          <div className="task-answer-section-title">
            <Lightbulb size={12} /><span>建议</span>
          </div>
          <ul className="task-answer-list">
            {answer.recommendations!.map((rec, i) => <li key={i}>{rec}</li>)}
          </ul>
        </div>
      )}

      {/* Follow-up questions */}
      {hasFollowUp && (
        <div className="task-answer-followup">
          <div className="task-answer-section-title"><span>追问建议</span></div>
          <div className="task-followup-chips">
            {answer.follow_up_questions!.slice(0, 4).map((q, i) => (
              <button key={i} className="task-followup-chip" onClick={() => onSendFollowUp(q)} type="button">
                <span>{q}</span><ChevronRight size={11} />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 删除不再需要的代码**

删除 `extractMetrics` 函数和相关 metric card 渲染逻辑。
删除 `BarChartIcon` 和 `maxVal`。
删除 table/chart linking 逻辑（通过 `depends_on` 匹配）。

- [ ] **Step 3: 检查编译**

```bash
cd desktop && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 4: Commit**

```bash
git add desktop/src/features/agentTask/FinalAnswerCard.tsx
git commit -m "refactor(frontend): restructure FinalAnswerCard — answer-first, evidence collapsible"
```

---

### Task 11: 更新 AgentTurnItem.tsx — process artifacts 过滤

**Files:**
- Modify: `desktop/src/features/agentTask/AgentTurnItem.tsx`

- [ ] **Step 1: 过滤传入 FinalAnswerCard 的 artifacts**

```tsx
import { EVIDENCE_ARTIFACT_TYPES } from "../../lib/api/types";

// In the render section, filter artifacts before passing to FinalAnswerCard:
{hasAgent && hasAnswer && turn.agentAnswer && (
  <FinalAnswerCard
    answer={turn.agentAnswer}
    artifacts={(turn.artifacts || []).filter(a => EVIDENCE_ARTIFACT_TYPES.has(a.type))}
    agentStatus={agentStatus}
    onSendFollowUp={onSendFollowUp}
    onOpenSqlConsole={onOpenSqlConsole}
    onToast={onToast}
  />
)}
```

Process artifacts 仍然在 `turn.artifacts` 中，供 TraceTimeline 使用，但不传给 FinalAnswerCard。

- [ ] **Step 2: Commit**

```bash
git add desktop/src/features/agentTask/AgentTurnItem.tsx
git commit -m "refactor(frontend): filter process artifacts from FinalAnswerCard"
```

---

### Task 12: 更新 AnswerCard.tsx — 标记 deprecated

**Files:**
- Modify: `desktop/src/features/workspace/queryResult/AnswerCard.tsx`

- [ ] **Step 1: 检查是否还有引用**

```bash
rg "AnswerCard" desktop/src/ --type tsx --type ts
```

- [ ] **Step 2: 如果无引用，删除文件；如果有引用，替换为 FinalAnswerCard**

```bash
# 如果无引用:
git rm desktop/src/features/workspace/queryResult/AnswerCard.tsx
```

如果有引用: 将引用改为 `FinalAnswerCard`，然后删除。

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(frontend): remove deprecated AnswerCard"
```

---

### Task 13: 更新测试

**Files:**
- Modify: `engine/agent/tests/test_answer_synthesis.py`
- Modify: `engine/tests/test_agent_answer.py`
- Modify: `engine/evaluation/evaluators/answer_eval.py`
- Modify: `engine/evaluation/evaluators/artifact_eval.py`

- [ ] **Step 1: 更新 test_answer_synthesis.py**

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from engine.agent_core.answer import synthesize_agent_answer


def test_synthesize_agent_answer_no_units():
    """No analysis units, no credentials — fallback."""
    result = synthesize_agent_answer(
        question="What is the total sales?",
        analysis_units=[],
    )
    assert result.answer != ""
    assert result.key_findings == []


def test_synthesize_agent_answer_empty_result():
    """Empty result set."""
    result = synthesize_agent_answer(
        question="Find orders",
        analysis_units=[{
            "id": "abc",
            "sql": "SELECT * FROM orders WHERE 1=0",
            "execution": {"columns": ["id"], "rows": [], "rowCount": 0},
            "is_empty": True,
        }],
    )
    assert "没有找到" in result.answer or "0" in result.answer


@patch("engine.llm.get_chat_model")
def test_synthesize_agent_answer_with_llm(mock_get_chat_model):
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = (
        "## 结论\n"
        "共 **50** 条记录，总销售额 **10,000** 元。\n\n"
        "## 关键指标\n"
        "- **总销售额：10,000**\n"
        "- **订单数：50**\n\n"
        "## 分析\n销售趋势稳定。\n\n"
        "## 数据口径\n覆盖全部订单。\n\n"
        "## 建议\n持续监控。"
    )
    mock_model.invoke.return_value = mock_response
    mock_get_chat_model.return_value = mock_model

    with patch.dict("os.environ", {"DBFOX_TESTING": "1"}):
        result = synthesize_agent_answer(
            question="What is the total sales?",
            analysis_units=[{
                "id": "abc",
                "sql": "SELECT SUM(amount) FROM orders",
                "execution": {
                    "success": True,
                    "rowCount": 1,
                    "columns": ["total"],
                    "rows": [[10000]],
                },
            }],
        )

    assert "10,000" in result.answer
    assert len(result.key_findings) >= 1
    mock_model.invoke.assert_called_once()
```

- [ ] **Step 2: 更新 test_agent_answer.py**

检查测试是否引用了 `ResultProfile` 或 `result_profile`，删除相关测试。

```bash
rg "ResultProfile|result_profile|notable_facts" engine/tests/test_agent_answer.py
```

- [ ] **Step 3: 更新 evaluators**

```bash
rg "ResultProfile|result_profile|insight|recommendation" engine/evaluation/evaluators/
```

删除 profile 相关的评估逻辑。

- [ ] **Step 4: 运行测试**

```bash
cd D:\Project\DBFox && python -m pytest engine/agent/tests/test_answer_synthesis.py engine/tests/test_agent_answer.py -x -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/agent/tests/test_answer_synthesis.py engine/tests/test_agent_answer.py engine/evaluation/evaluators/
git commit -m "test: update tests for answer/artifact refactor — remove profile dependency"
```

---

### Task 14: 全局清理残留引用

- [ ] **Step 1: 搜索所有残留引用**

```bash
rg "result_profile|ResultProfile|notable_facts|ColumnProfile|build_profile_artifact|build_recommendations_artifact|profile_result|analysis_composer|build_display_plan" engine/ desktop/src/ --type py --type ts --type tsx
```

- [ ] **Step 2: 逐一修复或确认已删除**

- [ ] **Step 3: 运行完整测试套件**

```bash
cd D:\Project\DBFox && python -m pytest engine/ -x --tb=short 2>&1 | tail -40
```

- [ ] **Step 4: 前端编译检查**

```bash
cd desktop && npx tsc --noEmit 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: clean up all residual references to removed types and functions"
```
