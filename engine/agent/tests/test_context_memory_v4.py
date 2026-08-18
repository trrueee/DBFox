"""P2 5.5 context rehydration from Memory v4 behind the feature flag."""

from __future__ import annotations

import json

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


@pytest.mark.parametrize(
    ("value", "enabled"),
    ((None, True), ("1", True), ("0", False)),
)
def test_memory_v4_context_flag_defaults_on_with_explicit_v3_rollback(
    value: str | None, enabled: bool
) -> None:
    from engine.agent import context as context_module

    assert context_module._memory_v4_context_enabled(value) is enabled


def test_memory_v4_context_flag_rejects_invalid_value() -> None:
    from engine.agent import context as context_module

    with pytest.raises(ValueError, match="DBFOX_MEMORY_V4_CONTEXT"):
        context_module._memory_v4_context_enabled("enabled")


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
        declared_version="1",
        contract_hash="sha256:1",
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


def test_explicit_v3_rollback_does_not_inject_v4_working_state(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", False)
    run_id = _seed_v4_context(db_session, test_datasource)

    snapshot = ContextAssembler(db_session).build(run_id)

    assert snapshot.session_memory.get("version") != 4
    assert "SESSION_WORKING_STATE" not in snapshot.session_memory


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("datasource_generation", 99),
        ("catalog_revision", 99),
        ("datasource_id", "other-datasource"),
    ),
)
def test_v4_context_omits_stale_resource_fence(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: int | str,
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    run_id = _seed_v4_context(db_session, test_datasource, generation=1, revision=0)
    row = db_session.query(AgentSessionMemory).filter_by(
        session_id="session-v4-context"
    ).one()
    payload = json.loads(row.memory_v4_json)
    payload["projections"][0]["scope"][field] = value
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


@pytest.mark.parametrize(
    ("corruption", "expected_reason"),
    (
        ("invalid_json", "invalid Memory v4 projection contract"),
        ("invalid_typed_state", "Catalog projection envelope does not match typed scope/state"),
        ("fingerprint_mismatch", "missing or incompatible Catalog projection"),
    ),
)
def test_v4_context_safely_omits_corrupted_persisted_memory(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
    expected_reason: str,
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    run_id = _seed_v4_context(db_session, test_datasource)
    row = db_session.query(AgentSessionMemory).filter_by(
        session_id="session-v4-context"
    ).one()
    if corruption == "invalid_json":
        row.memory_v4_json = "{not-json"
    else:
        payload = json.loads(row.memory_v4_json)
        if corruption == "invalid_typed_state":
            payload["projections"][0]["state"] = {"objects": "not-a-list"}
        else:
            payload["projections"][0]["contract_fingerprint"] = "sha256:stale"
        row.memory_v4_json = canonical_dumps(payload)
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(run_id)

    assert snapshot.session_memory == {}
    source = next(item for item in snapshot.sources if item.kind == "session_memory")
    assert source.included is False
    assert source.reason == expected_reason
