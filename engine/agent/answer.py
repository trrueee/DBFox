from __future__ import annotations

from typing import Any

from engine.agent.recommendations import recommendation_texts
from engine.agent.types import AgentAnswer, AnswerEvidence, FollowUpSuggestion, ResultProfile


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
            answer=f"I could not complete the analysis because: {error}",
            key_findings=[],
            evidence=_base_evidence(sql=sql, safety=safety, execution=execution, result_profile=result_profile),
            caveats=["No business conclusion was produced because the run did not complete successfully."],
            recommendations=recommendation_texts(suggestions or []),
            follow_up_questions=[suggestion.question for suggestion in (suggestions or [])],
        )

    execution_success = bool((execution or {}).get("success"))
    review_only = bool(safety and safety.get("can_execute") and not execution_success and execution and execution.get("reason"))
    facts: list[str] = []

    if execution_success:
        facts = list(result_profile.notable_facts if result_profile else [])
        lead = facts[0] if facts else "The query completed and returned data for the requested analysis."
        answer = f"{lead} I treated the returned rows as evidence for the question: {question}"
    elif review_only:
        answer = "I generated and validated the SQL, but execution was disabled for this review-only run. No result set was retrieved."
        # Do NOT include profile facts — they are misleading when no execution happened
        if result_profile:
            facts = []
    else:
        answer = "I do not have a successful result set to analyze yet."
        if result_profile and result_profile.detected_patterns and "execution_skipped" not in result_profile.detected_patterns:
            facts = list(result_profile.notable_facts if result_profile else [])

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


_SKIPPED_EXECUTION_SAFE_ANSWER = (
    "I generated and validated the SQL, but execution was disabled "
    "for this review-only run, so no result set was retrieved. "
    "I cannot make data-result claims until the query is executed."
)

_MISLEADING_DATA_CLAIMS = [
    "returned zero", "no rows returned", "no students",
    "executed successfully", "query executed successfully",
    "returned 0 rows", "returned no rows", "0 rows",
    "there are no students", "no data was returned",
]


def sanitize_answer_for_skipped_execution(
    answer: AgentAnswer | None,
    execution: dict[str, Any] | None,
    *,
    sql: str | None = None,
    safety: dict[str, Any] | None = None,
) -> AgentAnswer | None:
    """Deterministic sanitizer: when execution was skipped/disabled, replace
    any data-result claims with a safe no-execution message.

    This is a hard post-check — it does NOT rely on LLM prompt compliance.
    """
    if answer is None:
        return answer
    execution_success = bool((execution or {}).get("success"))
    if execution_success:
        return answer

    # Detect review-only / skipped-execution scenarios broadly:
    # 1. explicit execute=false in execution reason, or
    # 2. sql validated but no successful execution (review-only pattern)
    reason = str((execution or {}).get("reason", "")).lower()
    explicitly_skipped = "execute=false" in reason or "skipped" in reason
    review_only_pattern = bool(sql and (safety or {}).get("can_execute") and not execution_success)
    if not explicitly_skipped and not review_only_pattern:
        return answer

    text = answer.answer.lower()
    needs_sanitize = any(marker.lower() in text for marker in _MISLEADING_DATA_CLAIMS)
    if not needs_sanitize:
        return answer

    return AgentAnswer(
        answer=_SKIPPED_EXECUTION_SAFE_ANSWER,
        key_findings=[],
        evidence=answer.evidence,
        caveats=_dedupe(["Execution was skipped; no result set is available."] + list(answer.caveats)),
        recommendations=answer.recommendations,
        follow_up_questions=answer.follow_up_questions,
    )


def _base_evidence(
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: ResultProfile | None,
) -> list[AnswerEvidence]:
    evidence: list[AnswerEvidence] = []
    execution_success = bool(execution and execution.get("success"))
    if execution_success:
        evidence.append(
            AnswerEvidence(
                artifact_id="result_table",
                label="Rows returned",
                value=execution.get("rowCount", len(execution.get("rows", []) or [])),
            )
        )
    if result_profile:
        if execution_success:
            evidence.append(
                AnswerEvidence(
                    artifact_id="result_profile",
                    label="Result profile",
                    value=f"{result_profile.row_count} rows profiled",
                )
            )
        else:
            # execution skipped or failed — report truthfully, not misleading row counts
            evidence.append(
                AnswerEvidence(
                    artifact_id="result_profile",
                    label="Result profile",
                    value="execution was skipped; no result set available",
                )
            )
    if sql:
        evidence.append(AnswerEvidence(artifact_id="sql_candidate", label="SQL", value="validated candidate"))
    if safety:
        evidence.append(
            AnswerEvidence(
                artifact_id="safety_report",
                label="Safety",
                value="passed" if safety.get("can_execute") else "blocked",
            )
        )
    return evidence


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
