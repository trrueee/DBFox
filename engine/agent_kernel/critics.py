from __future__ import annotations

from typing import Any

from engine.agent_kernel.state import KernelState, latest_user_message
from engine.agent_kernel.reference_resolver import _preview

DATA_CLAIM_WORDS = (
    "returned",
    "rows",
    "records",
    "decreased",
    "increased",
    "highest",
    "lowest",
    "total",
    "average",
    "sum",
    "返回",
    "行",
    "记录",
    "下降",
    "增长",
    "最高",
    "最低",
    "总计",
    "平均",
)

AGGREGATE_FUNCTION_TOKENS = ("sum(", "count(", "avg(", "min(", "max(")
RANKING_QUESTION_TOKENS = ("top", "最高", "最大", "排名", "前")
MONTH_BUCKET_QUESTION_TOKENS = ("month", "monthly", "按月", "每月", "月份")
MONTH_SQL_TOKENS = ("month", "strftime", "date_trunc", "%y-%m", "%m")


def critique_sql(state: KernelState) -> dict[str, Any]:
    """Lightweight SQL Critic that runs after SQL generation and before validation."""
    sql = str(state.get("sql") or "").strip()
    query_plan = state.get("query_plan") if isinstance(state.get("query_plan"), dict) else {}
    question = latest_user_message(state).strip().lower()
    last_tool = str(state.get("last_tool_name") or "")
    issues: list[str] = []
    suggestions: list[str] = []

    if not sql:
        return {
            "status": "not_applicable",
            "needs_revision": False,
            "summary": "No SQL candidate is available yet.",
            "issues": [],
            "suggestions": [],
        }
    if last_tool and last_tool not in {"sql.generate", "sql.revise"}:
        return {
            "status": "not_applicable",
            "needs_revision": False,
            "summary": "SQL Critic only runs immediately after SQL generation or revision.",
            "issues": [],
            "suggestions": [],
        }

    lowered_sql = sql.lower()
    if ";" in sql.rstrip(";"):
        issues.append("SQL appears to contain multiple statements.")
        suggestions.append("Return exactly one read-only SELECT statement.")
    if not lowered_sql.lstrip().startswith("select") and "with" not in lowered_sql[:20]:
        issues.append("SQL is not a SELECT/CTE query.")
        suggestions.append("Rewrite as a read-only SELECT query.")

    candidate_tables = [str(table).lower() for table in query_plan.get("candidate_tables", []) if isinstance(table, str)]
    if candidate_tables and not any(table in lowered_sql for table in candidate_tables):
        issues.append("SQL does not appear to use any candidate table from the QueryPlan.")
        suggestions.append(f"Use one of the planned candidate tables: {', '.join(candidate_tables[:5])}.")

    metrics = query_plan.get("metrics") if isinstance(query_plan.get("metrics"), list) else []
    dimensions = query_plan.get("dimensions") if isinstance(query_plan.get("dimensions"), list) else []

    if metrics and not any(func in lowered_sql for func in AGGREGATE_FUNCTION_TOKENS):
        issues.append("QueryPlan expects metrics, but SQL has no obvious aggregate expression.")
        suggestions.append("Add the required aggregate expression for the planned metric.")

    if (
        dimensions
        and any(func in lowered_sql for func in AGGREGATE_FUNCTION_TOKENS)
        and "group by" not in lowered_sql
    ):
        issues.append("QueryPlan includes dimensions with aggregate metrics, but SQL has no GROUP BY.")
        suggestions.append("Group by the planned dimension columns.")

    if any(token in question for token in RANKING_QUESTION_TOKENS) and "order by" not in lowered_sql:
        issues.append("The question asks for ranking/top values, but SQL has no ORDER BY.")
        suggestions.append("Add ORDER BY on the relevant metric and a LIMIT.")

    if any(token in question for token in MONTH_BUCKET_QUESTION_TOKENS) and not any(token in lowered_sql for token in MONTH_SQL_TOKENS):
        issues.append("The question asks for monthly analysis, but SQL has no visible month bucketing.")
        suggestions.append("Add month-level date bucketing.")

    if "limit" not in lowered_sql and not any(func in lowered_sql for func in AGGREGATE_FUNCTION_TOKENS):
        suggestions.append("Consider adding a LIMIT for exploratory row-returning queries.")

    needs_revision = bool(issues)
    return {
        "status": "needs_revision" if needs_revision else "passed",
        "needs_revision": needs_revision,
        "summary": "SQL Critic found issues before validation." if needs_revision else "SQL Critic found no blocking issues before validation.",
        "issues": issues,
        "suggestions": suggestions,
    }


def critique_answer(state: KernelState) -> dict[str, Any]:
    """Final answer guardrail that prevents unsupported data claims."""
    answer = state.get("answer") or state.get("final_answer") or {}
    answer_text = str(answer.get("answer") if isinstance(answer, dict) else answer or "")
    lowered = answer_text.lower()
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    execution_success = execution.get("success") is True
    execution_reason = str(execution.get("reason") or "").lower()
    execution_skipped = bool((not execution_success and execution_reason and ("skip" in execution_reason or "execute=false" in execution_reason)) or (state.get("execute") is False and not execution_success))
    data_claim_detected = any(word in lowered for word in DATA_CLAIM_WORDS)
    has_result_evidence = execution_success or bool(state.get("result_profile"))
    issues: list[str] = []

    if execution_skipped and data_claim_detected:
        issues.append("Answer appears to make data-result claims even though execution was skipped.")
    elif not has_result_evidence and data_claim_detected:
        issues.append("Answer appears to make data-result claims without execution or result-profile evidence.")
    if not answer_text and state.get("error"):
        issues.append("Answer is empty while the run has an error that should be explained.")

    needs_correction = bool(issues)
    return {
        "status": "needs_correction" if needs_correction else "passed",
        "needs_correction": needs_correction,
        "summary": "Answer Critic found unsupported claims." if needs_correction else "Answer Critic found no blocking issue.",
        "issues": issues,
        "execution_success": execution_success,
        "execution_skipped": execution_skipped,
        "has_result_evidence": has_result_evidence,
        "data_claim_detected": data_claim_detected,
    }


def corrected_answer(answer: Any, critique: dict[str, Any]) -> dict[str, Any]:
    answer_dict = dict(answer) if isinstance(answer, dict) else {"answer": str(answer or "")}
    original = str(answer_dict.get("answer") or "").strip()
    correction = "Execution evidence is not available for this response, so any data-result conclusion should be treated as unsupported until the query is executed."
    if critique.get("execution_skipped"):
        correction = "Execution was disabled or skipped for this run, so no result set was retrieved and I cannot make data-result claims."
    answer_dict["answer"] = f"{original}\n\n{correction}" if original else correction
    caveats = answer_dict.get("caveats") if isinstance(answer_dict.get("caveats"), list) else []
    caveats = [*caveats, *[str(issue) for issue in critique.get("issues", [])]]
    answer_dict["caveats"] = caveats
    return answer_dict
