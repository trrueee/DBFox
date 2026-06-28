from __future__ import annotations

import re
from typing import Any, Callable

from engine.agent_core.types import AgentAnswer, AnswerEvidence


def synthesize_agent_answer(
    question: str,
    *,
    analysis_units: list[dict[str, Any]],
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    error: str | None = None,
    emit_answer_delta: Callable[[str], None] | None = None,
) -> AgentAnswer:
    """Generate a structured answer from collected analysis units via LLM.

    This is the SINGLE entry point for answer generation.  No hardcoded
    templates — every answer goes through the same LLM prompt path.
    The agent is expected to have already written analytical SQL to
    explore the data; this function synthesises those findings.
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

    import os
    has_credentials = bool(
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("DBFOX_LLM_API_KEY")
    )

    if not (has_credentials or os.environ.get("DBFOX_TESTING") == "1"):
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
        "你是一个专业的数据分析专家。你会收到用户问题和已经执行的查询结果，"
        "需要生成自适应 Markdown 答案。\n\n"
        "注意：这些查询结果是经过数据工程式探索和分析得到的结果，"
        "可能包含原始样例查询、统计分析查询、钻取查询和图表建议。\n\n"
        "答案规则：\n"
        "- 简单事实：直接用 1-3 句话回答。\n"
        "- 复杂分析：先给结论，再概括关键发现。\n"
        "- SQL 任务：给出 SQL 和简短说明。\n"
        "- Schema 任务：解释表、字段、关系和使用方式。\n"
        "- 空结果：明确说明没有匹配数据，并给出可能原因。\n"
        "- 证据不足：明确说不能可靠判断，并说明最有价值的下一步查询。\n"
        "- 不要强制使用固定章节，不要强制给建议。\n"
        "- 不要重复执行过程，不要编造没有查询支持的事实。\n"
        "- 小型汇总可以用 Markdown 表；大型原始结果不要写成 Markdown 表。\n"
        "- 优先基于聚合、分组、对比、排名、比例等分析 SQL 结果下结论。\n"
        "- 使用中文，关键数字可加粗，语气客观专业。\n"
    )

    user_parts = [f"用户问题: {question}\n"]
    units = [u for u in analysis_units if not u.get("is_empty")]
    if not units:
        units = analysis_units  # fallback to all units if every one is empty

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

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    if emit_answer_delta is not None:
        try:
            chunks: list[str] = []
            for chunk in model.stream(messages):
                text = _chunk_content_text(chunk)
                if text:
                    emit_answer_delta(text)
                    chunks.append(text)
            report_text = "".join(chunks).strip()
            if report_text:
                key_findings = _extract_key_findings(report_text)
                evidence = _build_evidence(units)
                caveats = _collect_caveats(units, error)

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

    try:
        response = model.invoke(messages)
        if response and response.content:
            report_text = response.content.strip()

            key_findings = _extract_key_findings(report_text)
            evidence = _build_evidence(units)
            caveats = _collect_caveats(units, error)

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _chunk_content_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


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
    matches = re.findall(r'\*\*(.+?)\*\*', text)
    return [m.strip() for m in matches if len(m.strip()) > 3]


def _build_evidence(units: list[dict[str, Any]]) -> list[AnswerEvidence]:
    """Build evidence list from analysis units."""
    total_rows = 0
    for u in units:
        exec_data = u.get("execution") or {}
        total_rows += int(exec_data.get("rowCount", 0))

    evidence: list[AnswerEvidence] = []
    if len(units) == 1:
        evidence.append(AnswerEvidence(
            artifact_id="result_view",
            label="查询行数",
            value=total_rows,
        ))
    else:
        evidence.append(AnswerEvidence(
            artifact_id="result_view",
            label="查询次数",
            value=len(units),
        ))
        if total_rows > 0:
            evidence.append(AnswerEvidence(
                artifact_id="result_view",
                label="合计行数",
                value=total_rows,
            ))
    return evidence


def _collect_caveats(
    units: list[dict[str, Any]],
    error: str | None,
) -> list[str]:
    caveats: list[str] = []
    for u in units:
        if u.get("is_empty"):
            caveats.append("部分查询未返回结果")
            break
        if u.get("is_truncated"):
            caveats.append("部分结果被截断")
    if error:
        caveats.append(f"运行中有非致命错误: {error}")
    return caveats


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
        text = f"已完成查询，共返回 {total_rows} 行结果。明细请查看下方数据。"
    key_findings = _fallback_key_findings(units, total_rows)

    return AgentAnswer(
        answer=text,
        key_findings=key_findings,
        evidence=_build_evidence(units),
        caveats=["本次未使用 AI 生成分析，仅展示基础数据。"] if error else [],
        recommendations=[],
        follow_up_questions=[],
    )


def _fallback_key_findings(
    units: list[dict[str, Any]],
    total_rows: int,
) -> list[str]:
    if total_rows <= 0:
        return []

    findings: list[str] = []
    first_unit = units[0] if units else {}
    exec_data = first_unit.get("execution") or {}
    columns = exec_data.get("columns") or []
    rows = exec_data.get("rows") or []

    if len(columns) >= 2 and isinstance(rows, list) and rows:
        label_col = str(columns[0])
        value_col = str(columns[1])
        best_label = ""
        best_value: float | None = None
        for row in rows:
            if isinstance(row, dict):
                label = str(row.get(label_col) or "")
                raw_value = row.get(value_col)
            elif isinstance(row, list) and len(row) >= 2:
                label = str(row[0] or "")
                raw_value = row[1]
            else:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if best_value is None or value > best_value:
                best_label = label
                best_value = value
        if best_label and best_value is not None:
            findings.append(f"{best_label} {_metric_leader_phrase(value_col)}。")

    if not findings:
        findings.append(f"共 {total_rows} 行结果")
    return findings


def _metric_leader_phrase(column: str) -> str:
    normalized = column.lower()
    if "usage" in normalized or "use" in normalized:
        return "使用次数最高"
    if "amount" in normalized or "gmv" in normalized or "revenue" in normalized or "sales" in normalized:
        return "金额最高"
    if "count" in normalized or "total" in normalized or "num" in normalized:
        return "数量最高"
    return "数值最高"
