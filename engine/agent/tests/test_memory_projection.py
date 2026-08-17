"""P2 5.3/5.4 shadow projection service contracts."""

from __future__ import annotations

import json
import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.context import ContextAssembler
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.memory_projection import (
    project_session_memory,
    rebuild_session_memory,
)
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.prompt import PromptAssembler
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.json_codec import dumps
from engine.models import (
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    AgentSessionMemory,
    AgentToolInvocation,
    AgentTurn,
)
from engine.tools.runtime import ToolRegistry


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
    datasource_generation: int = 1,
) -> AgentRun:
    run = AgentRun(
        id=run_id,
        session_id=session_id,
        session_sequence=sequence,
        datasource_id=datasource_id,
        datasource_generation=datasource_generation,
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
    declared_version: str = "1",
    contract_hash: str = "sha256:1",
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
        declared_version=declared_version,
        contract_hash=contract_hash,
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


def test_resource_generation_transition_resets_catalog_working_state(
    db_session,
    test_datasource,
) -> None:
    session = _session(db_session, str(test_datasource.id), session_id="session-v4-generation")
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-generation-1",
        sequence=1,
        datasource_generation=1,
    )
    _catalog_search_records(
        db_session,
        run_id="run-v4-generation-1",
        session_id=session.id,
        revision=1,
    )
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-generation-2",
        sequence=2,
        datasource_generation=2,
    )
    db_session.commit()

    outcome = project_session_memory(db_session, session.id, 2)
    db_session.commit()

    assert outcome.projected_through_session_sequence == 2
    row = db_session.query(AgentSessionMemory).filter_by(session_id=session.id).one()
    projection = next(
        item
        for item in json.loads(row.memory_v4_json)["projections"]
        if item["projection_id"] == "dbfox.catalog.working_state"
    )
    assert projection["scope"] == {
        "datasource_id": str(test_datasource.id),
        "datasource_generation": 2,
        "catalog_revision": 0,
    }
    assert projection["state"]["objects"] == []
    assert projection["state"]["searches"] == []

    compare = rebuild_session_memory(db_session, session.id, mode="compare")
    assert compare.complete is True
    assert compare.matches is True


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
        declared_version="2",
        contract_hash="sha256:2",
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

    repair = rebuild_session_memory(db_session, session.id, mode="repair")
    assert repair.complete is False
    assert repair.written is False
    assert (
        db_session.query(AgentSessionMemory)
        .filter_by(session_id=session.id)
        .scalar()
        is None
    )


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


@pytest.mark.parametrize("terminal_status", ("failed", "cancelled"))
def test_unsuccessful_run_projection_is_consumed_by_the_next_run_context(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    """Prove the complete durable projection -> later Context handoff."""

    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    session = _session(
        db_session,
        str(test_datasource.id),
        session_id=f"session-v4-{terminal_status}-to-context",
    )
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id=f"run-v4-{terminal_status}-to-context-1",
        sequence=1,
        status=terminal_status,
    )
    _catalog_search_records(
        db_session,
        run_id=f"run-v4-{terminal_status}-to-context-1",
        session_id=session.id,
        revision=7,
    )
    test_datasource.catalog_revision = 7
    session.input_sequence = 1
    session.message_sequence = 2
    admitted = SessionRepository(db_session).admit(
        session_id=session.id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="继续使用已经确认的订单表。",
        idempotency_key=f"v4-{terminal_status}-to-context-2",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()

    outcome = project_session_memory(db_session, session.id, 1)
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(admitted.run_id)
    working = snapshot.session_memory["SESSION_WORKING_STATE"]
    prompt = PromptAssembler().assemble(
        definition=AgentDefinition(),
        context=snapshot,
    )

    assert outcome.projected_through_session_sequence == 1
    assert working["selected_count"] == 1
    assert working["objects"][0]["key"]["table_name"] == "orders"
    assert working["objects"][0]["source_observation_id"] == (
        f"observation_run-v4-{terminal_status}-to-context-1_1"
    )
    assert any(
        segment["role"] == "user"
        and "SESSION_WORKING_STATE" in str(segment["content"])
        and "orders" in str(segment["content"])
        for segment in prompt.messages
    )


def test_generation_transition_removes_projected_objects_from_later_context(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    session = _session(
        db_session,
        str(test_datasource.id),
        session_id="session-v4-generation-context",
    )
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-generation-context-1",
        sequence=1,
        datasource_generation=1,
    )
    _catalog_search_records(
        db_session,
        run_id="run-v4-generation-context-1",
        session_id=session.id,
        revision=4,
    )
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-generation-context-2",
        sequence=2,
        datasource_generation=2,
        status="completed",
    )
    session.input_sequence = 2
    session.message_sequence = 4
    admitted = SessionRepository(db_session).admit(
        session_id=session.id,
        datasource_id=str(test_datasource.id),
        datasource_generation=2,
        content="数据库连接已切换，请继续。",
        idempotency_key="v4-generation-context-2",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()

    project_session_memory(db_session, session.id, 2)
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(admitted.run_id)

    assert snapshot.session_memory["freshness"]["resource_fence"] == "matched"
    assert snapshot.session_memory["SESSION_WORKING_STATE"]["objects"] == []
    assert "orders" not in json.dumps(snapshot.session_memory)


class _ScriptedPriorSchemaConsumer:
    """A deterministic Provider that can only use the constructed Prompt."""

    def __init__(self) -> None:
        self.prompt_checked = False

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        assert tools == []
        rendered = "\n".join(str(message.get("content") or "") for message in messages)
        assert '<dbfox_context source="session_memory">' in rendered
        assert '"table_name":"orders"' in rendered
        self.prompt_checked = True
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_START,
            item_id="answer",
            revision=1,
            output_index=0,
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_DELTA,
            item_id="answer",
            revision=2,
            content="已复用前一运行确认的 orders 表结构。",
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_END,
            item_id="answer",
            revision=3,
            output_index=0,
            message_status="completed",
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
            item_id="answer",
            revision=4,
            output_index=0,
            model_output_item={
                "type": "message",
                "role": "assistant",
                "content": "已复用前一运行确认的 orders 表结构。",
            },
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


def test_scripted_continuation_consumes_memory_without_rediscovery(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B-layer proof: a later Run receives Memory through the real RunLoop Prompt."""

    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    session = _session(
        db_session,
        str(test_datasource.id),
        session_id="session-v4-scripted-continuation",
    )
    _run(
        db_session,
        session.id,
        datasource_id=str(test_datasource.id),
        run_id="run-v4-scripted-continuation-1",
        sequence=1,
        status="failed",
    )
    _catalog_search_records(
        db_session,
        run_id="run-v4-scripted-continuation-1",
        session_id=session.id,
    )
    test_datasource.catalog_revision = 1
    session.input_sequence = 1
    session.message_sequence = 2
    admitted = SessionRepository(db_session).admit(
        session_id=session.id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="继续使用 orders 表完成分析。",
        idempotency_key="v4-scripted-continuation-2",
        llm_credential_id="credential",
        api_base=None,
        model_name="scripted",
        request_payload={},
    )
    db_session.commit()
    project_session_memory(db_session, session.id, 1)
    db_session.commit()
    sessions = SessionRepository(db_session)
    lease = sessions.claim(session_id=session.id, owner="memory-v4-scripted")
    assert lease is not None
    assert sessions.promote_next_input(lease=lease) == admitted.run_id
    db_session.commit()

    provider = _ScriptedPriorSchemaConsumer()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: provider,
        registry=ToolRegistry(),
        definition=AgentDefinition(allowed_tool_groups=()),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admitted.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admitted.run_id)
    assert provider.prompt_checked is True
    assert run is not None and run.status == "completed"
    assert db_session.query(AgentToolInvocation).filter_by(run_id=admitted.run_id).count() == 0
