from __future__ import annotations

from typing import Any

from engine.agent_core.recommendations import recommendation_texts
from engine.agent_core.types import AgentAnswer, AnswerEvidence, FollowUpSuggestion, ResultProfile


def synthesize_agent_answer(
    question: str,
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: ResultProfile | None,
    suggestions: list[FollowUpSuggestion] | None = None,
    error: str | None = None,
    *,
    analysis_units: list[dict[str, Any]] | None = None,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> AgentAnswer:
    if error:
        return AgentAnswer(
            answer=f"未能完成分析：{error}",
            key_findings=[],
            evidence=_base_evidence(sql=sql, safety=safety, execution=execution, result_profile=result_profile),
            caveats=["本次运行未成功完成，因此没有生成业务结论。"],
            recommendations=recommendation_texts(suggestions or []),
            follow_up_questions=[suggestion.question for suggestion in (suggestions or [])],
        )

    # ── Multi-unit report composition (P2) ──────────────────────────
    units = analysis_units or []
    non_empty = [u for u in units if not u.get("is_empty")]
    if len(non_empty) >= 2:
        try:
            report = _compose_multi_unit_report(
                question=question,
                units=non_empty,
                model_name=model_name,
                api_key=api_key,
                api_base=api_base,
            )
            if report:
                return AgentAnswer(
                    answer=report.get("summary", ""),
                    key_findings=report.get("key_findings", [])[:8],
                    evidence=_multi_unit_evidence(non_empty, sql, safety),
                    caveats=report.get("caveats", [])[:5],
                    recommendations=report.get("recommendations", []),
                    follow_up_questions=report.get("follow_up_questions", []),
                )
        except Exception:
            pass  # Fall through to single-unit path

    execution_success = bool((execution or {}).get("success"))
    review_only = bool(safety and safety.get("can_execute") and not execution_success and execution and execution.get("reason"))
    facts: list[str] = []

    if execution_success:
        row_count = int(execution.get("rowCount") or 0)
        columns = list(execution.get("columns") or [])
        rows = list(execution.get("rows") or [])
        facts = list(result_profile.notable_facts if result_profile else [])

        analysis = None
        try:
            import os
            has_credentials = bool(
                api_key
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("QWEN_API_KEY")
                or os.environ.get("DBFOX_LLM_API_KEY")
            )
            if has_credentials or os.environ.get("DBFOX_TESTING") == "1":
                from engine.llm import get_chat_model
                from langchain_core.messages import HumanMessage, SystemMessage

                model = get_chat_model(
                    model_name=model_name,
                    api_key=api_key,
                    api_base=api_base,
                    temperature=0.3,
                )

                preview_text = ""
                if rows:
                    preview_text = _format_result_preview(columns, rows[:30])

                notable_facts_str = "\n".join(f"- {f}" for f in result_profile.notable_facts) if result_profile and result_profile.notable_facts else "无"
                anomalies_str = "\n".join(f"- {a}" for a in result_profile.anomalies) if result_profile and result_profile.anomalies else "无"
                limitations_str = "\n".join(f"- {l}" for l in result_profile.limitations) if result_profile and result_profile.limitations else "无"

                system_prompt = (
                    "你是一个专业的数据分析专家，能够根据用户的查询问题和执行出的数据库结果数据，生成专业、有深度的商业/业务分析结论。"
                    "请使用中文进行回答。使用 Markdown 格式组织内容："
                    "**加粗关键数字和发现**，用列表列出要点，必要时用小标题分节。"
                    "直接针对用户的问题进行深入的数据洞察，指出趋势、占比、异常、极值或有商业价值的规律，"
                    "不要只是简单地重复数据行数或做敷衍的回答。"
                    "控制在 200 到 500 字以内，语气客观、专业且精准。"
                )

                user_content = (
                    f"用户问题: {question}\n"
                    f"执行的 SQL: {sql}\n"
                    f"结果集列名: {columns}\n"
                    f"结果集行数: {row_count}\n"
                    f"结果集预览 (最多显示前30行):\n{preview_text}\n\n"
                    f"数据统计特征 (由系统计算):\n"
                    f"显著事实:\n{notable_facts_str}\n"
                    f"异常值/异常模式:\n{anomalies_str}\n"
                    f"数据限制或偏差提示:\n{limitations_str}\n\n"
                    f"请基于以上信息，生成深入的业务洞察和分析结论。"
                )

                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_content),
                ]
                response = model.invoke(messages)
                if response and response.content:
                    analysis = response.content.strip()
        except Exception:
            analysis = None

        if analysis:
            answer = analysis
        else:
            if row_count == 0:
                answer = f"已完成查询，但没有找到符合“{question}”的记录。"
            elif row_count <= 10 and rows:
                answer = f"已完成查询，共返回 {row_count} 行结果；明细请查看下方表格产出物。"
            else:
                lead = facts[0] if facts else f"共返回 {row_count} 行结果。"
                answer = f"{lead}本次问题：{question}"
    elif review_only:
        answer = "已生成并验证 SQL，但本次运行处于仅审阅模式，未执行查询，因此没有结果集。"
        if result_profile:
            facts = []
    else:
        answer = ""
        facts = []

    caveats = list(result_profile.limitations if result_profile else [])
    if safety and safety.get("messages"):
        caveats.extend(str(message) for message in safety.get("messages", [])[:3])
    if result_profile and result_profile.anomalies and execution_success:
        facts.extend(result_profile.anomalies[:2])

    return AgentAnswer(
        answer=answer,
        key_findings=facts[:5],
        evidence=_base_evidence(sql=sql, safety=safety, execution=execution, result_profile=result_profile),
        caveats=_dedupe(caveats)[:5],
        recommendations=recommendation_texts(suggestions or []),
        follow_up_questions=[suggestion.question for suggestion in (suggestions or [])],
    )


def _base_evidence(
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: ResultProfile | None,
) -> list[AnswerEvidence]:
    evidence: list[AnswerEvidence] = []
    execution_data = execution or {}
    execution_success = bool(execution_data.get("success"))
    if execution_success:
        evidence.append(
            AnswerEvidence(
                artifact_id="result_table",
                label="查询行数",
                value=execution_data.get("rowCount", len(execution_data.get("rows", []) or [])),
            )
        )
    if result_profile:
        if execution_success:
            evidence.append(
                AnswerEvidence(
                    artifact_id="result_profile",
                    label="结果画像",
                    value=f"已分析 {result_profile.row_count} 行",
                )
            )
        else:
            # execution skipped or failed — report truthfully, not misleading row counts
            evidence.append(
                AnswerEvidence(
                    artifact_id="result_profile",
                    label="结果画像",
                    value="未执行查询，没有可分析的结果集",
                )
            )
    if sql:
        evidence.append(AnswerEvidence(artifact_id="sql_candidate", label="SQL", value="已验证"))
    if safety:
        evidence.append(
            AnswerEvidence(
                artifact_id="safety_report",
                label="安全检查",
                value="通过" if safety.get("can_execute") else "已阻止",
            )
        )
    return evidence


def _format_result_preview(columns: list[str], rows: list[list[Any]]) -> str:
    """Format a small result set as a readable text table for the answer."""
    if not columns or not rows:
        return "(no data)"

    lines: list[str] = []
    # Header
    header = " | ".join(str(c) for c in columns[:8])
    lines.append(header)
    lines.append("-" * len(header))
    # Rows (max 10)
    for row in rows[:10]:
        if isinstance(row, dict):
            cells = [str(row.get(column, ""))[:80] for column in columns]
        else:
            cells = [str(cell)[:80] for cell in (row if isinstance(row, list) else [row])]
        # Pad to column count
        while len(cells) < len(columns):
            cells.append("")
        lines.append(" | ".join(cells[:8]))

    return "\n".join(lines)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _compose_multi_unit_report(
    *,
    question: str,
    units: list[dict[str, Any]],
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> dict[str, Any] | None:
    """Compose a structured report from multiple analysis units via LLM."""
    import os

    has_credentials = bool(
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("QWEN_API_KEY")
        or os.environ.get("DBFOX_LLM_API_KEY")
    )
    if not (has_credentials or os.environ.get("DBFOX_TESTING") == "1"):
        return None

    from engine.llm import get_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage

    # Build unit summaries for the prompt
    unit_summaries: list[str] = []
    for i, u in enumerate(units):
        sql_short = (u.get("sql") or "")[:200]
        rows_count = u.get("execution", {}).get("rowCount", 0)
        columns = u.get("execution", {}).get("columns", [])
        rows = u.get("execution", {}).get("rows", [])
        is_empty = rows_count == 0
        profile = u.get("profile") or {}
        chart = u.get("chart") or {}

        unit_text = (
            f"### Query {i + 1}\n"
            f"- SQL: {sql_short}\n"
            f"- Columns: {columns}\n"
            f"- Row count: {rows_count}\n"
            f"- Empty: {is_empty}\n"
        )
        if profile:
            facts = profile.get("notable_facts") or []
            anomalies = profile.get("anomalies") or []
            if facts:
                unit_text += f"- Notable facts: {'; '.join(facts[:5])}\n"
            if anomalies:
                unit_text += f"- Anomalies: {'; '.join(anomalies[:3])}\n"
        if chart:
            unit_text += f"- Chart type: {chart.get('type')}, dimensions: {chart.get('x')} vs {chart.get('y')}\n"
        # Preview first 3 rows
        if rows:
            preview = _format_result_preview(columns, rows[:3])
            unit_text += f"- Data preview:\n{preview}\n"
        unit_summaries.append(unit_text)

    units_text = "\n".join(unit_summaries)

    system_prompt = (
        "你是一个专业的数据分析报告撰写专家。你会收到多个查询结果，"
        "需要将它们整合成一份结构化、易读的业务分析报告。\n\n"
        "格式要求：使用 Markdown 输出，包含以下章节：\n"
        "## 结论\n1-2句话总结核心发现\n\n"
        "## 关键指标\n用**粗体数字**列出最重要的指标，如 **发布总数：11**、**成功率：0%**\n\n"
        "## 维度分析\n如果多次查询覆盖不同维度，说明它们之间的关系和分布特征\n\n"
        "## 数据口径\n说明分析覆盖的数据范围、时间跨度、过滤条件\n\n"
        "## 建议\n基于发现给出 2-3 条可操作的下一步建议\n\n"
        "语气客观、专业，使用中文。每个章节控制在 2-5 行。"
    )

    user_content = (
        f"用户问题: {question}\n\n"
        f"共执行了 {len(units)} 次查询，结果如下:\n\n"
        f"{units_text}\n\n"
        "请基于以上所有查询结果，用 Markdown 格式撰写综合分析报告。"
    )

    try:
        model = get_chat_model(
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            temperature=0.3,
        )
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
        if not response or not response.content:
            return None

        report_text = response.content.strip()

        # Extract key findings from profiles
        all_facts: list[str] = []
        for u in units:
            profile = u.get("profile") or {}
            for f in (profile.get("notable_facts") or []):
                all_facts.append(str(f))

        # Collect caveats
        caveats: list[str] = []
        for u in units:
            if u.get("is_empty"):
                caveats.append(f"Query '{u.get('sql', '')[:60]}...' returned no rows")
            if u.get("is_truncated"):
                caveats.append("Some results were truncated")
            profile = u.get("profile") or {}
            for lim in (profile.get("limitations") or []):
                caveats.append(str(lim))
            for anom in (profile.get("anomalies") or []):
                caveats.append(str(anom))

        return {
            "summary": report_text,
            "key_findings": _dedupe(all_facts),
            "caveats": _dedupe(caveats),
            "recommendations": [],
            "follow_up_questions": [],
        }
    except Exception:
        return None


def _multi_unit_evidence(
    units: list[dict[str, Any]],
    sql: str | None,
    safety: dict[str, Any] | None,
) -> list[AnswerEvidence]:
    """Build evidence list referencing all analysis units."""
    evidence: list[AnswerEvidence] = []
    total_rows = 0
    total_empty = 0
    for u in units:
        exec_data = u.get("execution") or {}
        total_rows += int(exec_data.get("rowCount", 0))
        if exec_data.get("rowCount", 0) == 0:
            total_empty += 1

    evidence.append(
        AnswerEvidence(
            artifact_id="result_table",
            label="查询次数",
            value=len(units),
        )
    )
    if total_rows > 0:
        evidence.append(
            AnswerEvidence(
                artifact_id="result_table",
                label="合计行数",
                value=total_rows,
            )
        )
    if total_empty > 0:
        evidence.append(
            AnswerEvidence(
                artifact_id="result_table",
                label="空结果查询",
                value=total_empty,
            )
        )
    if sql:
        evidence.append(AnswerEvidence(artifact_id="sql_candidate", label="SQL", value="已验证"))
    if safety:
        evidence.append(
            AnswerEvidence(
                artifact_id="safety_report",
                label="安全检查",
                value="通过" if safety.get("can_execute") else "已阻止",
            )
        )
    return evidence
