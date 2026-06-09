"""Artifact evaluator — checks generated artifacts against expectations."""

from __future__ import annotations

from engine.evaluation.schemas import ArtifactExpectation


def evaluate_artifacts(
    artifact_types: list[str],
    artifact_count: int,
    expected: ArtifactExpectation | None,
) -> list[str]:
    """Evaluate artifacts against expectations.  Returns failure reasons."""
    if expected is None:
        return []

    failures: list[str] = []

    for atype in expected.must_include_types:
        if atype not in artifact_types:
            failures.append(f"Expected artifact type '{atype}' but not found. "
                            f"Produced: {artifact_types}")

    for atype in expected.must_not_include_types:
        if atype in artifact_types:
            failures.append(f"Artifact type '{atype}' was produced but should NOT have been.")

    if expected.min_artifact_count is not None:
        if artifact_count < expected.min_artifact_count:
            failures.append(
                f"Expected at least {expected.min_artifact_count} artifacts, got {artifact_count}."
            )

    return failures
