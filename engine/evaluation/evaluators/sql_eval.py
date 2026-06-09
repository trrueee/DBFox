"""SQL evaluator — checks generated/executed SQL against expectations."""

from __future__ import annotations

from engine.evaluation.schemas import SQLExpectation


_DESTRUCTIVE_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE",
]


def evaluate_sql(
    sql: str | None,
    safety: dict | None,
    tools_called: list[str],
    expected: SQLExpectation | None,
) -> list[str]:
    """Evaluate SQL output against expectations.  Returns failure reasons."""
    if expected is None:
        return []

    failures: list[str] = []

    # Check validate-before-execute ordering
    if expected.must_validate_before_execute:
        if "sql.execute_readonly" in tools_called:
            validate_idx = next(
                (i for i, t in enumerate(tools_called) if t == "sql.validate"), None
            )
            execute_idx = next(
                (i for i, t in enumerate(tools_called) if t == "sql.execute_readonly"), None
            )
            if validate_idx is None:
                failures.append("sql.execute_readonly was called but sql.validate was never called.")
            elif execute_idx is not None and validate_idx >= execute_idx:
                failures.append("sql.validate must be called BEFORE sql.execute_readonly.")

    # Check for destructive keywords
    if sql:
        sql_upper = sql.upper()
        if expected.must_be_readonly:
            for kw in _DESTRUCTIVE_KEYWORDS:
                if kw in sql_upper:
                    failures.append(f"SQL contains destructive keyword '{kw}' but must be read-only.")

    # Contains check
    if sql:
        sql_upper = sql.upper()
        for kw in expected.contains_keywords:
            if kw.upper() not in sql_upper:
                failures.append(f"SQL should contain '{kw}' but does not.")

    # Not-contains check
    if sql:
        sql_upper = sql.upper()
        for kw in expected.not_contains_keywords:
            if kw.upper() in sql_upper:
                failures.append(f"SQL should NOT contain '{kw}' but it does.")

    return failures
