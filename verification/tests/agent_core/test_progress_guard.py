"""Domain-neutral progress fingerprints for the Agent Core."""

from engine.agent.progress_guard import observation_evidence_signatures


def _signatures(tool: str, facts: dict, *, status: str = "succeeded") -> set[str]:
    return observation_evidence_signatures(
        tool_name=tool,
        status=status,
        facts=facts,
        error_code="",
    )


def test_same_evidence_ignores_volatile_timestamps_and_ids():
    first = _signatures("verification_read", {"value": 1, "createdAt": "a", "item_id": "one"})
    second = _signatures("verification_read", {"value": 1, "createdAt": "b", "item_id": "two"})
    assert first == second


def test_changed_domain_fact_is_progress():
    assert _signatures("verification_read", {"value": 1}) != _signatures(
        "verification_read", {"value": 2}
    )


def test_failure_status_and_code_are_part_of_progress_identity():
    succeeded = _signatures("verification_read", {"value": 1})
    failed = observation_evidence_signatures(
        tool_name="verification_read",
        status="failed",
        facts={"value": 1},
        error_code="VERIFICATION_FAILED",
    )
    assert succeeded != failed
