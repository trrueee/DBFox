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

        if row_count == 0:
            answer = f"已完成查询，但没有找到符合“{question}”的记录。"
        elif row_count <= 10 and rows:
            answer = f"已完成查询，共返回 {row_count} 行结果；明细请查看下方表格产出物。"
        else:
            lead = facts[0] if facts else f"共返回 {row_count} 行结果。"
            answer = f"{lead}本次问题：{question}"
    elif review_only:
        answer = "已生成并验证 SQL，但本次运行处于仅审阅模式，未执行查询，因此没有结果集。"
        # Do NOT include profile facts — they are misleading when no execution happened
        if result_profile:
            facts = []
    else:
        # No execution happened — the model should not have called answer_synthesize.
        # Return a minimal answer so the UI doesn't show misleading boilerplate.
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
