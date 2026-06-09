"""Trajectory evaluator — checks tool-call sequence against expectations."""

from __future__ import annotations

import fnmatch
from typing import Any

from engine.evaluation.schemas import TrajectoryExpectation


def _matches_any(pattern: str, tools: list[str]) -> bool:
    """Check if any tool in tools matches the glob pattern."""
    return any(fnmatch.fnmatch(t, pattern) for t in tools)


def evaluate_trajectory(
    tools_called: list[str],
    expected: TrajectoryExpectation | None,
) -> list[str]:
    """Evaluate tool-call trajectory against expectations.  Returns failure reasons."""
    if expected is None:
        return []

    failures: list[str] = []

    for pattern in expected.must_call:
        if not _matches_any(pattern, tools_called):
            failures.append(f"Expected tool matching '{pattern}' to be called, but it was not. "
                            f"Tools called: {tools_called}")

    for pattern in expected.must_not_call:
        if _matches_any(pattern, tools_called):
            matched = [t for t in tools_called if fnmatch.fnmatch(t, pattern)]
            failures.append(f"Tool matching '{pattern}' was called but should NOT have been: {matched}")

    # must_call_order: check relative ordering
    if expected.must_call_order:
        indices: dict[str, int] = {}
        for pattern in expected.must_call_order:
            for i, tool in enumerate(tools_called):
                if fnmatch.fnmatch(tool, pattern):
                    indices[pattern] = i
                    break
        for i in range(len(expected.must_call_order) - 1):
            a, b = expected.must_call_order[i], expected.must_call_order[i + 1]
            if a in indices and b in indices:
                if indices[a] >= indices[b]:
                    failures.append(
                        f"Expected '{a}' before '{b}', but order was: {tools_called}"
                    )

    return failures
