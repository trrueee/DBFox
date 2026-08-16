"""P2 5.5 context rehydration from Memory v4 behind the feature flag."""

from __future__ import annotations

import json
from importlib import reload

import pytest

from engine.agent.context import ContextAssembler
from engine.agent.memory_v4 import (
    CatalogObjectKey,
    CatalogObjectState,
    CatalogProjectionScope,
    CatalogWorkingState,
    build_catalog_projection_envelope,
)
from engine.agent.repositories.session import SessionRepository
from engine.json_codec import canonical_dumps
from engine.models import (
    AgentObservationRecord,
    AgentSession,
    AgentSessionMemory,
    AgentToolInvocation,
    AgentTurn,
)


def test_memory_v4_context_flag_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DBFOX_MEMORY_V4_CONTEXT", raising=False)
    from engine.agent import context as context_module

    reload(context_module)
    assert context_module.MEMORY_V4_CONTEXT_ENABLED is False


def _seed_v4_context(
    db_session,
    test_datasource,
    *,
    generation: int = 2,
    revision: int = 0,
) -> str:
    session_id = "session-v4-context"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Memory v4 context",
        )
    )
    db_session.flush()
    admission = SessionRepository(db_session).admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=generation,
        content="现在有哪些订单字段？",
        idempotency_key="v4-context",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    turn = AgentTurn(
        id="turn-v4-context",
        session_id=session_id,
        run_id=admission.run_id,
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
        id="invocation-v4-context",
        session_id=session_id,
        run_id=admission.run_id,
        turn_id=turn.id,
        provider_call_id="call-v4-context",
        tool_name="schema_inspect",
        tool_version="1",
        input_json=json.dumps({"targets": ["orders"]}),
        input_hash="input-v4-context",
        idempotency_key="idem-v4-context",
        status="succeeded",
        policy_json="{}",
        presentation_json="{}",
        recovery_policy="retry_safe",
    )
    db_session.add(invocation)
    db_session.flush()
    db_session.add(
        AgentObservationRecord(
            id="observation-v4-context",
            session_id=session_id,
            run_id=admission.run_id,
            turn_id=turn.id,
            tool_invocation_id=invocation.id,
            sequence=1,
            status="succeeded",
            model_visible_summary="inspect",
            model_output_json="{}",
            facts_json=json.dumps(
                {
                    "catalog_revision": revision,
                    "inspections": [
                        {
                            "target": "orders",
                            "details": {
                                "object_type": "table",
                                "schema_name": "main",
                                "name": "orders",
                                "primary_key": ["id"],
                                "columns": [
                                    {"name": "id"},
                                    {"name": "customer_id"},
                                ],
                                "foreign_keys_out": [
                                    {
                                        "references": {
                                            "schema_name": "main",
                                            "table": "customers",
                                            "column": "id",
                                        }
                                    }
                                ],
                            },
                        }
                    ],
                }
            ),
        )
    )
    scope = CatalogProjectionScope(
        datasource_id=str(test_datasource.id),
        datasource_generation=generation,
        catalog_revision=revision,
    )
    key = CatalogObjectKey(
        kind="table",
        schema_name="main",
        table_name="orders",
    )
    state = CatalogWorkingState(
        objects=(
            CatalogObjectState(
                key=key,
                first_seen_observation_id="observation-v4-context",
                last_seen_observation_id="observation-v4-context",
                last_inspected_observation_id="observation-v4-context",
                last_source_sequence=1,
                catalog_revision=revision,
            ),
        )
    )
    envelope = build_catalog_projection_envelope(
        scope=scope,
        state=state,
        projected_through_session_sequence=1,
    )
    payload = {
        "schema_version": 4,
        "core_policy_version": 1,
        "core": {
            "referenced_artifact_ids": [],
            "runtime_evidence_references": [],
            "advisory_open_questions": [],
        },
        "projections": [envelope.model_dump(mode="json")],
    }
    db_session.add(
        AgentSessionMemory(
            id="memory-v4-context-row",
            session_id=session_id,
            datasource_id=str(test_datasource.id),
            memory_json="{}",
            memory_v4_json=canonical_dumps(payload),
        )
    )
    db_session.commit()
    return admission.run_id


def test_v4_context_rehydrates_bounded_prior_objects(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    run_id = _seed_v4_context(db_session, test_datasource)

    snapshot = ContextAssembler(db_session).build(run_id)

    assert snapshot.session_memory["version"] == 4
    working = snapshot.session_memory["SESSION_WORKING_STATE"]
    assert working["selected_count"] == 1
    assert working["objects"][0]["key"]["table_name"] == "orders"
    assert working["objects"][0]["key_columns"] == ["id", "customer_id"]
    assert working["objects"][0]["primary_key"] == ["id"]
    assert working["objects"][0]["related_objects"] == ["main.customers.id"]
    assert working["objects"][0]["source_observation_id"] == "observation-v4-context"
    assert snapshot.session_memory["SESSION_EVIDENCE_INDEX"] == {
        "referenced_artifact_ids": [],
        "runtime_evidence_references": [],
    }
    assert snapshot.session_memory["freshness"]["resource_fence"] == "matched"


def test_v4_context_omits_stale_resource_fence(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    run_id = _seed_v4_context(db_session, test_datasource, generation=1, revision=0)
    row = db_session.query(AgentSessionMemory).filter_by(
        session_id="session-v4-context"
    ).one()
    payload = json.loads(row.memory_v4_json)
    payload["projections"][0]["scope"]["datasource_generation"] = 99
    row.memory_v4_json = canonical_dumps(payload)
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(run_id)

    assert snapshot.session_memory == {}
    source = next(
        item
        for item in snapshot.sources
        if item.kind == "session_memory"
    )
    assert "outside the current resource fence" in source.reason
