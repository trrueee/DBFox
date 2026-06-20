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
                    "请使用中文进行回答。你的回答应该直接针对用户的问题进行深入的数据洞察，指出趋势、占比、异常、极值或有商业价值的规律，而不要只是简单地重复数据行数或做敷衍的回答。"
                    "不要包含 markdown 格式的标题（如 #, ##）或 metadata，控制在 150 到 400 字以内，保持语气客观、专业且精准。"
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
