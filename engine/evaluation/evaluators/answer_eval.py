"""Answer evaluator — deterministic checks on the final answer.

LLM-as-judge evaluation is done via LangSmith or a separate judge model.
This module provides fast deterministic checks that don't need an LLM.
"""

from __future__ import annotations

from engine.evaluation.schemas import AnswerExpectation


def evaluate_answer(
    answer_text: str | None,
    tools_called: list[str],
    expected: AnswerExpectation | None,
) -> list[str]:
    """Deterministic answer checks.  Returns failure reasons."""
    if expected is None:
        return []

    failures: list[str] = []

    if answer_text is None or not answer_text.strip():
        if expected.must_be_helpful:
            failures.append("Expected a helpful answer but got empty response.")
        return failures

    # Check for disallowed claims about database access
    if expected.must_not_claim_database_access:
        db_claim_patterns = [
            "rows returned", "query returned", "executed and found",
            "the database shows", "查询返回", "查询结果",
        ]
        # Only flag if tools were NOT called — if they were, claiming access is fine
        if not tools_called:
            for pattern in db_claim_patterns:
                if pattern.lower() in answer_text.lower():
                    failures.append(
                        f"Answer claims database access ('{pattern}') but no tools were called."
                    )

    # Phrase checks
    for phrase in expected.expected_phrases:
        if phrase.lower() not in answer_text.lower():
            failures.append(f"Expected answer to contain '{phrase}'.")

    for phrase in expected.forbidden_phrases:
        if phrase.lower() in answer_text.lower():
            failures.append(f"Answer contains forbidden phrase '{phrase}'.")

    return failures
