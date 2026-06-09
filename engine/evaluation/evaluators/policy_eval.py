"""Policy evaluator — checks PolicyGate decisions against expectations."""

from __future__ import annotations

import fnmatch
from typing import Any

from engine.evaluation.schemas import PolicyExpectation


def evaluate_policy(
    blocked_tools: list[str],
    approval_tools: list[str],
    sql_executed: bool,
    expected: PolicyExpectation | None,
) -> list[str]:
    """Evaluate policy behavior against expectations.  Returns failure reasons."""
    if expected is None:
        return []

    failures: list[str] = []

    for pattern in expected.must_block:
        if not any(fnmatch.fnmatch(t, pattern) for t in blocked_tools):
            failures.append(f"Expected policy to block '{pattern}', but it was not blocked.")

    for pattern in expected.must_require_approval:
        if not any(fnmatch.fnmatch(t, pattern) for t in approval_tools):
            failures.append(f"Expected policy to require approval for '{pattern}', but it did not.")

    if expected.must_not_execute_sql and sql_executed:
        failures.append("SQL was executed but policy should have prevented it.")

    return failures
