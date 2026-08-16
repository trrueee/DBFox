"""P2 5.3/5.4 shadow projection service contracts."""

from __future__ import annotations

import json
from engine.agent.memory_projection import (
    project_session_memory,
    rebuild_session_memory,
)
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.json_codec import dumps
from engine.models import (
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    AgentSessionMemory,
    AgentToolInvocation,
    AgentTurn,
)


def _session(db_session, datasource_id: str, session_id: str = "session-v4-proj") -> AgentSession:
    session = AgentSession(
        id=session_id,
        datasource_id=datasource_id,
        title="Memory v4 projection",
    )
    db_session.add(session)
    db_session.flush()
    return session


def _run(
    db_session,
    session_id: str,
    *,
    datasource_id: str,
    run_id: str,
    sequence: int,
    status: str = "completed",
    lease_token: int = 1,
) -> AgentRun:
    run = AgentRun(
        id=run_id,
        session_id=session_id,
        session_sequence=sequence,
        datasource_id=datasource_id,
        datasource_generation=1,
        question="test",
        status=status,
        lease_token=lease_token,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _catalog_search_records(
    db_session,
    *,
    run_id: str,
    session_id: str,
    sequence: int = 1,
    revision: int = 1,
    tool_version: str = "1",
) -> None:
    turn = AgentTurn(
        id=f"turn_{run_id}_{sequence}",
        session_id=session_id,
        run_id=run_id,
        sequence=1,
        status="completed",
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot_json="{}",
        context_hash="context",
        tool_materialization_json="{}",
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    db_session.add(turn)
    db_session.flush()
    invocation = AgentToolInvocation(
        id=f"invocation_{run_id}_{sequence}",
        session_id=session_id,
        run_id=run_id,
        turn_id=turn.id,
        provider_call_id=f"call_{run_id}_{sequence}",
        tool_name="schema_search",
        tool_version=tool_version,
        input_json=dumps({"queries": ["orders"]}),
        input_hash=f"input_{run_id}_{sequence}",
        idempotency_key=f"idem_{run_id}_{sequence}",
        status="succeeded",
        policy_json="{}",
        presentation_json="{}",
        recovery_policy="retry_safe",
    )
    db_session.add(invocation)
    db_session.flush()
    db_session.add(
        AgentObservationRecord(
            id=f"observation_{run_id}_{sequence}",
            session_id=session_id,
            run_id=run_id,
            turn_id=turn.id,
            tool_invocation_id=invocation.id,
            sequence=1,
            status="succeeded",
            model_visible_summary="search",
            model_output_json="{}",
            facts_json=dumps(
                {
                    "catalog_revision": revision,
                    "returned_count": 1,
                    "candidates": [
                        {
                            "type": "table",
                            "schema_name": "main",
                            "table_name": "orders",
                        }
                    ],
                }
            ),
            semantic_capabilities_json="[]",
        )
    )


def test_terminal_run_folds_into_shadow_memory_v4(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id))
    _run(db_session, session.id, datasource_id=str(test_datasource.id), run_id="run-v4-1", sequence=1)
    _catalog_search_records(
        db_session,
        run_id="run-v4-1",
        session_id=session.id,
    )
    db_session.commit()

    outcome = project_session_memory(db_session, session.id, 1)
    db_session.commit()

    assert outcome.projected_through_session_sequence == 1
    assert outcome.projection_lag == 0
    row = db_session.query(AgentSessionMemory).filter_by(session_id=session.id).one()
    assert row.memory_json == "{}"
    payload = json.loads(row.memory_v4_json)
    assert payload["schema_version"] == 4
    projection = next(
        item
        for item in payload["projections"]
        if item["projection_id"] == "dbfox.catalog.working_state"
    )
    assert projection["projected_through_session_sequence"] == 1
    assert len(projection["state"]["objects"]) == 1

    # Idempotent duplicate apply.
    second = project_session_memory(db_session, session.id, 1)
    db_session.commit()
    assert second.projected_through_session_sequence == 1


def test_projection_stops_at_a_sequence_gap(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-gap")
    _run(db_session, session.id, datasource_id=str(test_datasource.id), run_id="run-v4-gap-1", sequence=1)
    _catalog_search_records(
        db_session,
        run_id="run-v4-gap-1",
        session_id=session.id,
    )
    # sequence 2 is missing; sequence 3 is terminal but must not be crossed.
    _run(db_session, session.id, datasource_id=str(test_datasource.id), run_id="run-v4-gap-3", sequence=3)
    db_session.commit()

    outcome = project_session_memory(db_session, session.id, 3)
    db_session.commit()

    assert outcome.projected_through_session_sequence == 1
    row = db_session.query(AgentSessionMemory).filter_by(session_id=session.id).one()
    projection = next(
        item
        for item in json.loads(row.memory_v4_json)["projections"]
        if item["projection_id"] == "dbfox.catalog.working_state"
    )
    assert projection["projected_through_session_sequence"] == 1


def test_projection_contract_error_does_not_block_run_failure(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-fail")
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session.id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="test",
        idempotency_key="memory-v4-fail",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id=session.id, owner="test")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    _catalog_search_records(
        db_session,
        run_id=admission.run_id,
        session_id=session.id,
        tool_version="2",
    )
    db_session.commit()

    RunRepository(db_session).fail(
        lease=lease,
        run_id=admission.run_id,
        error_code="TEST_FAIL",
        message="test failure",
    )
    db_session.commit()

    assert db_session.get(AgentRun, admission.run_id).status == "failed"
    assert (
        db_session.query(AgentSessionMemory)
        .filter_by(session_id=session.id)
        .scalar()
        is None
    )


def test_cancelled_run_still_folds_succeeded_observations(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-cancel")
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session.id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="test",
        idempotency_key="memory-v4-cancel",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id=session.id, owner="test")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    _catalog_search_records(
        db_session,
        run_id=admission.run_id,
        session_id=session.id,
    )
    db_session.commit()

    RunRepository(db_session).cancel(lease=lease, run_id=admission.run_id)
    db_session.commit()

    row = db_session.query(AgentSessionMemory).filter_by(session_id=session.id).one()
    projection = next(
        item
        for item in json.loads(row.memory_v4_json)["projections"]
        if item["projection_id"] == "dbfox.catalog.working_state"
    )
    assert projection["projected_through_session_sequence"] == 1
    assert len(projection["state"]["objects"]) == 1


def test_rebuild_compare_and_strict_match_incremental_shadow(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-rebuild")
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-rebuild-1",
        sequence=1,
    )
    _catalog_search_records(
        db_session,
        run_id="run-v4-rebuild-1",
        session_id=session.id,
    )
    db_session.commit()

    project_session_memory(db_session, session.id, 1)
    db_session.commit()

    compare = rebuild_session_memory(db_session, session.id, mode="compare")
    strict = rebuild_session_memory(db_session, session.id, mode="strict")
    db_session.commit()

    assert compare.complete is True
    assert compare.written is False
    assert compare.matches is True
    assert strict.complete is True
    assert strict.written is False
    assert strict.rebuilt_state_hash == compare.rebuilt_state_hash


def test_rebuild_strict_is_incomplete_on_a_sequence_gap(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-rebuild-gap")
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-rebuild-gap-1",
        sequence=1,
    )
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-rebuild-gap-3",
        sequence=3,
    )
    db_session.commit()

    outcome = rebuild_session_memory(db_session, session.id, mode="strict")
    assert outcome.complete is False
    assert outcome.projected_through_session_sequence == 1
    assert outcome.written is False


def test_rebuild_repair_writes_only_a_complete_candidate(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-repair")
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-repair-1",
        sequence=1,
    )
    _catalog_search_records(
        db_session,
        run_id="run-v4-repair-1",
        session_id=session.id,
    )
    db_session.commit()

    strict = rebuild_session_memory(db_session, session.id, mode="strict")
    repair = rebuild_session_memory(db_session, session.id, mode="repair")
    db_session.commit()

    assert strict.complete is True
    assert repair.complete is True
    assert repair.written is True
    row = db_session.query(AgentSessionMemory).filter_by(session_id=session.id).one()
    payload = json.loads(row.memory_v4_json)
    projection = next(
        item
        for item in payload["projections"]
        if item["projection_id"] == "dbfox.catalog.working_state"
    )
    assert projection["state_hash"] == repair.rebuilt_state_hash
    assert projection["projected_through_session_sequence"] == 1
