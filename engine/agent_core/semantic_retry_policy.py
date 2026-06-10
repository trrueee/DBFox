from __future__ import annotations

import json
from typing import Any

from engine.agent_core.semantic_contract import QueryContract
from engine.agent_core.sql_semantic_verifier import SemanticViolation
from engine.sql.compiler import SQLProjectionConstraintVerifier


HIGH_CONFIDENCE_RETRYABLE_CODES = frozenset({
    "having_missing",
    "group_by_missing",
    "having_count_missing",
    "antijoin_outer_join",
    "antijoin_not_equal_or_null",
    "antijoin_missing",
    "setlogic_contradictory_and",
    "projection_select_star",
    "distinct_missing",
    "projection_extra_columns",
    "projection_missing_requested_column",
    "projection_duplicate_alias",
})

PROJECTION_RETRY_CODES = frozenset({
    "projection_extra_columns",
    "projection_missing_requested_column",
    "projection_duplicate_alias",
    "projection_select_star",
    "projection_extra_count",
})


def should_retry_semantic(
    contract: QueryContract,
    violations: list[SemanticViolation],
    has_api_key: str | None,
) -> bool:
    if not has_api_key:
        return False
    if contract.confidence < 0.7:
        return False
    return any(
        violation.code in HIGH_CONFIDENCE_RETRYABLE_CODES
        for violation in violations
        if violation.severity == "retryable"
    )


def accept_semantic_retry(
    original_violations: list[Any],
    retry_violations: list[Any],
    contract: QueryContract,
    *,
    original_sql: str = "",
    retry_sql: str = "",
) -> bool:
    if contract.confidence < 0.7:
        return False

    orig_score = semantic_violation_severity_score(original_violations)
    retry_score = semantic_violation_severity_score(retry_violations)
    orig_codes = {violation_code(item) for item in original_violations}
    retry_high_codes = {
        violation_code(item)
        for item in retry_violations
        if violation_severity(item) == "retryable"
    }

    new_retryable_non_proj = (retry_high_codes - orig_codes) - PROJECTION_RETRY_CODES
    if new_retryable_non_proj:
        return False

    orig_proj_codes = orig_codes & PROJECTION_RETRY_CODES
    if orig_proj_codes and original_sql and retry_sql:
        if not SQLProjectionConstraintVerifier().validate_retry(original_sql, retry_sql, contract):
            return False
        return projection_violation_score(retry_violations) < projection_violation_score(original_violations)

    return retry_score < orig_score


def semantic_retry_prompt(
    *,
    question: str,
    schema_context: dict[str, Any],
    contract: QueryContract,
    previous_sql: str,
    violations: list[SemanticViolation],
) -> str:
    schema_text = str(schema_context.get("schema_context") or "")
    schema_block = f"\nSchema context:\n{schema_text[:12000]}\n" if schema_text else ""
    guidance = semantic_retry_guidance(violations)
    guidance_block = f"\nCorrection rules:\n{guidance}\n" if guidance else ""
    return (
        "Previous SQL violated the semantic contract.\n\n"
        f"Original question:\n{question}\n"
        f"{schema_block}\n"
        "SQL_CONTRACT:\n"
        f"{json.dumps(contract.to_dict(), ensure_ascii=False, indent=2)}\n\n"
        "Previous SQL:\n"
        f"{previous_sql}\n\n"
        "Violations:\n"
        f"{json.dumps(semantic_violation_payload(violations), ensure_ascii=False, indent=2)}\n\n"
        f"{guidance_block}"
        "Regenerate one MySQL SELECT query that satisfies the contract. Return SQL only."
    )


def semantic_retry_guidance(violations: list[SemanticViolation]) -> str:
    codes = {violation.code for violation in violations}
    rules: list[str] = []
    if codes & {"group_by_missing", "having_missing", "having_count_missing", "having_threshold_mismatch"}:
        rules.append(
            "- For related-row thresholds, select only the requested entity columns, GROUP BY them, and put COUNT(...) comparison in HAVING."
        )
    if "projection_select_star" in codes:
        rules.append("- Replace SELECT * with explicit requested columns from SQL_CONTRACT.")
    if codes & {"projection_extra_columns", "projection_missing_requested_column", "projection_duplicate_alias", "projection_extra_count"}:
        rules.append(
            "- Fix ONLY the SELECT list. Do not change FROM. Do not change JOIN. "
            "Do not change WHERE. Do not change GROUP BY. Do not change HAVING. "
            "Do not change ORDER BY. Do not change LIMIT. "
            "Remove unrequested columns. Keep only columns explicitly requested by the question. "
            "If the question asks for an ID (e.g. pet id), return only that requested ID column, "
            "not all columns of the joined entity. "
            "Remove duplicate aliases for the same underlying column (keep one). "
            "Preserve DISTINCT if present in the original SQL or required by SQL_CONTRACT."
        )
    if "distinct_missing" in codes:
        rules.append("- Use SELECT DISTINCT for explicitly distinct/different/unique results.")
    if codes & {"antijoin_not_equal_or_null", "antijoin_outer_join", "antijoin_missing"}:
        rules.append(
            "- For absence/never/no-related-record questions, use a correlated NOT EXISTS subquery. "
            "Do NOT use LEFT JOIN patterns (neither `WHERE col <> value OR col IS NULL` nor "
            "`LEFT JOIN ... AND col = value WHERE key IS NULL`) — both fail when a subject "
            "has both matching and non-matching related rows. Only NOT EXISTS guarantees "
            "correct anti-join semantics for value-qualified conditions."
        )
    if codes & {"setlogic_contradictory_and", "setlogic_missing"}:
        rules.append(
            "- For shared/both/intersection semantics, use EXISTS subqueries or a self-join with DISTINCT; do not combine mutually exclusive predicates in one row scope, and prefer this over INTERSECT."
        )
    return "\n".join(rules)


def semantic_violation_payload(violations: list[SemanticViolation]) -> list[dict[str, Any]]:
    return [violation.to_dict() for violation in violations]


def has_retryable_semantic_violations(violations: list[SemanticViolation]) -> bool:
    return any(violation.severity == "retryable" for violation in violations)


def semantic_violation_severity_score(violations: list[Any]) -> int:
    score = 0
    for item in violations:
        severity = violation_severity(item)
        if severity == "blocking":
            score += 100
        elif severity == "retryable":
            score += 10
        else:
            score += 1
    return score


def projection_violation_score(violations: list[Any]) -> int:
    score = 0
    for item in violations:
        if violation_code(item) not in PROJECTION_RETRY_CODES:
            continue
        score += 10 if violation_severity(item) == "retryable" else 1
    return score


def violation_code(item: Any) -> str:
    return str(item.get("code") if isinstance(item, dict) else item.code)


def violation_severity(item: Any) -> str:
    return str(item.get("severity") if isinstance(item, dict) else item.severity)
