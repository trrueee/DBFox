"""Domain-neutral progress fingerprints for the Agent Core."""

from engine.agent.progress_guard import ProgressGuard, observation_evidence_signatures


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


def test_rewording_or_advancing_a_plan_without_new_evidence_is_not_progress(db_session, test_resource):
    from engine.agent.plan import PlanStep, PlanStepStatus
    from engine.agent.repositories.plan import PlanRepository
    from engine.agent.repositories.session import SessionRepository
    from engine.models import AgentSession
    from engine.resource import ResourceScopeRef

    db_session.add(AgentSession(id="progress-plan-only", title="Progress"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admitted = sessions.admit(
        session_id="progress-plan-only", content="Create a new result", idempotency_key="progress-plan",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        llm_credential_id="test-credential", api_base=None, model_name="test-model", request_payload={},
    )
    lease = sessions.claim(session_id="progress-plan-only", owner="progress-test")
    assert lease is not None
    assert sessions.promote_next_input(lease=lease) == admitted.run_id
    turn = sessions.start_turn(
        lease=lease, run_id=admitted.run_id, agent_definition_version="test", prompt_version="test",
        prompt_hash="test", context_snapshot={}, context_hash="test", tool_materialization={"tools": []},
        tool_materialization_hash="test", provider="test", model_name="test-model",
    )
    db_session.commit()
    before = ProgressGuard(db_session).fingerprint(admitted.run_id)
    for index, status in enumerate((PlanStepStatus.IN_PROGRESS, PlanStepStatus.COMPLETED)):
        PlanRepository(db_session).update(
            lease=lease, run_id=admitted.run_id, turn_id=str(turn.id), objective=f"Reworded goal {index}",
            steps=[PlanStep(id=f"replacement-{index}", title=f"New wording {index}", status=status)],
            summary=f"Different narrative {index}",
        )
        db_session.commit()
        assert ProgressGuard(db_session).fingerprint(admitted.run_id) == before
