from __future__ import annotations

import re
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
        "你是一个专业的数据分析专家。你会收到用户问题和已执行的查询结果，"
        "需要生成一份结构化的 Markdown 分析报告。\n\n"
        "注意：这些查询结果是经过你（作为数据工程师）多次探索和分析的结果，"
        "包含了原始数据查询和统计分析查询。\n\n"
        "格式要求：\n"
        "## 结论\n1-2 句话总结核心发现\n\n"
        "## 关键指标\n用**粗体数字**列出最重要的指标，"
        "例如 **发布总数：11**、**成功率：0%**\n\n"
        "## 分析\n说明趋势、占比、异常、规律，解释数据背后的含义\n\n"
        "## 数据口径\n说明覆盖的数据范围、时间跨度、过滤条件\n\n"
        "## 建议\n2-3 条可操作的下一步\n\n"
        "规则：\n"
        "- 如果结果是空集，直接说明，不要编造数据\n"
        "- **加粗关键数字**\n"
        "- 控制在 200-500 字\n"
        "- 使用中文，语气客观专业\n"
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

    try:
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
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
        text = f"已完成 {len(units)} 次查询，共返回 {total_rows} 行结果。明细请查看下方数据。"

    return AgentAnswer(
        answer=text,
        key_findings=[f"共 {total_rows} 行结果"] if total_rows > 0 else [],
        evidence=_build_evidence(units),
        caveats=["本次未使用 AI 生成分析，仅展示基础数据。"] if error else [],
        recommendations=[],
        follow_up_questions=[],
    )
