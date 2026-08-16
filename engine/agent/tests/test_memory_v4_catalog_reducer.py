"""P2 5.2 contracts for the typed Memory v4 Catalog reducer."""

from __future__ import annotations

from typing import Any

import pytest

from engine.agent.memory_v4 import (
    MAX_CATALOG_OBJECTS,
    MAX_PRIOR_DIGEST_OBJECTS,
    MAX_CATALOG_SEARCHES,
    CatalogObjectKey,
    CatalogObjectState,
    CatalogProjectionScope,
    CatalogWorkingState,
    UnsupportedCatalogInput,
    build_catalog_projection_envelope,
    canonical_state_hash,
    catalog_contract_fingerprint,
    empty_session_memory_v4,
    fold_catalog,
    select_prior_catalog_objects,
)
from engine.agent.observation import Observation, ObservationStatus
from engine.agent.tool import ToolInvocation, ToolInvocationStatus
from engine.tools.runtime.base import ToolRecoveryPolicy


def _invocation(
    tool_name: str,
    *,
    version: str = "1",
    authorized_input: dict[str, Any] | None = None,
    sequence: int = 1,
) -> ToolInvocation:
    return ToolInvocation(
        id=f"invocation_{tool_name}_{sequence}",
        session_id="session-memory-v4",
        run_id="run-memory-v4",
        turn_id="turn-memory-v4",
        provider_call_id=f"call_{tool_name}_{sequence}",
        tool_name=tool_name,
        tool_version=version,
        authorized_input=authorized_input or {},
        authorized_input_hash=f"input-{tool_name}-{sequence}",
        idempotency_key=f"idem-{tool_name}-{sequence}",
        status=ToolInvocationStatus.SUCCEEDED,
        recovery_policy=ToolRecoveryPolicy.RETRY_SAFE,
    )


def _observation(
    tool_name: str,
    *,
    facts: dict[str, Any] | None = None,
    status: ObservationStatus = ObservationStatus.SUCCEEDED,
    sequence: int = 1,
) -> Observation:
    return Observation(
        id=f"observation_{tool_name}_{sequence}",
        session_id="session-memory-v4",
        run_id="run-memory-v4",
        turn_id="turn-memory-v4",
        tool_invocation_id=f"invocation_{tool_name}_{sequence}",
        tool_name=tool_name,
        tool_version="1",
        status=status,
        model_visible_summary="summary",
        model_output="{}",
        facts=facts or {},
        sequence=sequence,
    )


def _scope(revision: int = 1) -> CatalogProjectionScope:
    return CatalogProjectionScope(
        datasource_id="datasource-memory-v4",
        datasource_generation=1,
        catalog_revision=revision,
    )


def _search_pair(
    sequence: int,
    *,
    candidates: list[dict[str, Any]] | None = None,
    revision: int = 1,
) -> tuple[ToolInvocation, Observation]:
    candidates = candidates or [
        {
            "type": "table",
            "schema_name": "main",
            "table_name": "orders",
            "column_name": None,
        }
    ]
    invocation = _invocation(
        "schema_search",
        authorized_input={"queries": ["orders"]},
        sequence=sequence,
    )
    observation = _observation(
        "schema_search",
        facts={
            "catalog_revision": revision,
            "returned_count": len(candidates),
            "candidates": candidates,
        },
        sequence=sequence,
    )
    return invocation, observation


def test_search_then_inspect_folds_footprint_and_object_state() -> None:
    state = CatalogWorkingState()
    scope = _scope()

    search_invocation, search_observation = _search_pair(
        1,
        candidates=[
            {
                "type": "column",
                "schema_name": "main",
                "table_name": "orders",
                "column_name": "customer_id",
            }
        ],
    )
    folded = fold_catalog(
        state,
        scope=scope,
        source_sequence=1,
        invocation=search_invocation,
        observation=search_observation,
    )

    assert len(folded.state.searches) == 1
    assert len(folded.state.objects) == 1
    assert folded.state.objects[0].key == CatalogObjectKey(
        kind="column",
        schema_name="main",
        table_name="orders",
        column_name="customer_id",
    )
    assert folded.state.objects[0].last_inspected_observation_id is None

    inspect_invocation = _invocation("schema_inspect", sequence=2)
    inspect_observation = _observation(
        "schema_inspect",
        facts={
            "catalog_revision": 1,
            "inspections": [
                {
                    "target": "orders.customer_id",
                    "details": {
                        "object_type": "column",
                        "schema_name": "main",
                        "table": "orders",
                        "name": "customer_id",
                    },
                }
            ],
        },
        sequence=2,
    )
    folded = fold_catalog(
        folded.state,
        scope=folded.scope,
        source_sequence=2,
        invocation=inspect_invocation,
        observation=inspect_observation,
    )

    assert folded.state.objects[0].last_inspected_observation_id == (
        inspect_observation.id
    )
    assert folded.state.objects[0].last_source_sequence == 2


def test_revision_transition_resets_revision_scoped_state() -> None:
    state = CatalogWorkingState()
    scope = _scope(revision=1)
    search_invocation, search_observation = _search_pair(1)
    folded = fold_catalog(
        state,
        scope=scope,
        source_sequence=1,
        invocation=search_invocation,
        observation=search_observation,
    )
    assert len(folded.state.objects) == 1

    refreshed = _observation(
        "catalog_refresh",
        facts={"catalog_revision": 2, "status": "ready"},
        sequence=2,
    )
    folded = fold_catalog(
        folded.state,
        scope=folded.scope,
        source_sequence=2,
        invocation=_invocation("catalog_refresh", sequence=2),
        observation=refreshed,
    )

    assert folded.scope.catalog_revision == 2
    assert folded.state.objects == ()
    assert folded.state.searches == ()
    assert folded.state.orientation is not None
    assert folded.state.orientation.last_refresh_observation_id == refreshed.id


def test_non_catalog_and_non_succeeded_observations_are_ignored() -> None:
    state = CatalogWorkingState()
    scope = _scope()
    folded = fold_catalog(
        state,
        scope=scope,
        source_sequence=1,
        invocation=_invocation("sql_validate"),
        observation=_observation(
            "sql_validate",
            facts={"catalog_revision": 1},
        ),
    )
    assert folded.state == state

    search_invocation, failed_observation = _search_pair(1)
    failed_observation = failed_observation.model_copy(
        update={"status": ObservationStatus.FAILED}
    )
    folded = fold_catalog(
        state,
        scope=scope,
        source_sequence=1,
        invocation=search_invocation,
        observation=failed_observation,
    )
    assert folded.state == state


def test_unknown_tool_version_rejects_instead_of_guessing() -> None:
    with pytest.raises(UnsupportedCatalogInput):
        fold_catalog(
            CatalogWorkingState(),
            scope=_scope(),
            source_sequence=1,
            invocation=_invocation("schema_search", version="2"),
            observation=_search_pair(1)[1],
        )


def test_missing_catalog_revision_fact_rejects() -> None:
    search_invocation, search_observation = _search_pair(1)
    search_observation = search_observation.model_copy(
        update={"facts": {"candidates": [], "returned_count": 0}}
    )
    with pytest.raises(ValueError, match="catalog_revision"):
        fold_catalog(
            CatalogWorkingState(),
            scope=_scope(),
            source_sequence=1,
            invocation=search_invocation,
            observation=search_observation,
        )


def test_incremental_and_rebuild_use_the_same_fold_function() -> None:
    records: list[tuple[int, ToolInvocation, Observation]] = []
    for index in range(1, 6):
        invocation, observation = _search_pair(index)
        records.append((index, invocation, observation))
    inspect_invocation = _invocation("schema_inspect", sequence=6)
    inspect_observation = _observation(
        "schema_inspect",
        facts={
            "catalog_revision": 1,
            "inspections": [
                {
                    "target": "orders",
                    "details": {
                        "object_type": "table",
                        "schema_name": "main",
                        "name": "orders",
                    },
                }
            ],
        },
        sequence=6,
    )
    records.append((6, inspect_invocation, inspect_observation))

    incremental_state = CatalogWorkingState()
    incremental_scope = _scope()
    for source_sequence, invocation, observation in records:
        folded = fold_catalog(
            incremental_state,
            scope=incremental_scope,
            source_sequence=source_sequence,
            invocation=invocation,
            observation=observation,
        )
        incremental_state = folded.state
        incremental_scope = folded.scope

    rebuilt_state = CatalogWorkingState()
    rebuilt_scope = _scope()
    for source_sequence, invocation, observation in records:
        folded = fold_catalog(
            rebuilt_state,
            scope=rebuilt_scope,
            source_sequence=source_sequence,
            invocation=invocation,
            observation=observation,
        )
        rebuilt_state = folded.state
        rebuilt_scope = folded.scope

    assert incremental_state == rebuilt_state
    assert incremental_scope == rebuilt_scope
    assert canonical_state_hash(incremental_state) == canonical_state_hash(rebuilt_state)


def test_bounds_are_deterministic_and_bounded() -> None:
    state = CatalogWorkingState()
    scope = _scope()
    for sequence in range(1, MAX_CATALOG_OBJECTS + 6):
        invocation, observation = _search_pair(
            sequence,
            candidates=[
                {
                    "type": "table",
                    "schema_name": "main",
                    "table_name": f"table_{sequence:02d}",
                }
            ],
        )
        folded = fold_catalog(
            state,
            scope=scope,
            source_sequence=sequence,
            invocation=invocation,
            observation=observation,
        )
        state, scope = folded.state, folded.scope

    assert len(state.searches) == MAX_CATALOG_SEARCHES
    assert len(state.objects) == MAX_CATALOG_OBJECTS
    assert state.objects == tuple(
        sorted(state.objects, key=lambda item: item.key.canonical_tuple)
    )


def test_projection_envelope_and_memory_state_are_typed_and_hashable() -> None:
    state = CatalogWorkingState()
    scope = _scope()
    envelope = build_catalog_projection_envelope(
        scope=scope,
        state=state,
        projected_through_session_sequence=0,
    )
    memory = empty_session_memory_v4()

    assert memory.schema_version == 4
    assert memory.core.referenced_artifact_ids == ()
    assert envelope.projection_id == "dbfox.catalog.working_state"
    assert envelope.contract_fingerprint == catalog_contract_fingerprint()
    assert envelope.state_hash == canonical_state_hash(state)
    assert len(envelope.state_hash) == 64


def test_prior_search_hit_only_promotes_its_own_candidate_keys() -> None:
    orders = CatalogObjectKey(
        kind="table",
        schema_name="main",
        table_name="orders",
    )
    states = [CatalogObjectState(
        key=orders,
        first_seen_observation_id="obs_orders",
        last_seen_observation_id="obs_orders",
        last_source_sequence=0,
        catalog_revision=1,
    )]
    for index in range(1, MAX_PRIOR_DIGEST_OBJECTS + 1):
        key = CatalogObjectKey(
            kind="table",
            schema_name="main",
            table_name=f"other_{index:02d}",
        )
        states.append(CatalogObjectState(
            key=key,
            first_seen_observation_id=f"obs_{key.table_name}",
            last_seen_observation_id=f"obs_{key.table_name}",
            last_source_sequence=index,
            catalog_revision=1,
        ))
    from engine.agent.memory_v4 import SearchFootprint

    state = CatalogWorkingState(
        objects=tuple(states),
        searches=(
            SearchFootprint(
                invocation_id="inv_orders",
                observation_id="obs_search_orders",
                input_hash="input-orders",
                queries=("orders",),
                candidate_keys=(orders,),
                returned_count=1,
                catalog_revision=1,
                source_sequence=1,
            ),
        ),
    )

    selected = select_prior_catalog_objects(
        state,
        current_request="请分析 orders 的汇总",
    )
    assert len(selected) == MAX_PRIOR_DIGEST_OBJECTS
    assert selected[0].key.table_name == "orders"


def test_prior_object_selection_prefers_explicit_request_identity() -> None:
    keys = []
    for index in range(MAX_PRIOR_DIGEST_OBJECTS + 2):
        keys.append(
            CatalogObjectKey(
                kind="table",
                schema_name="main",
                table_name=f"table_{index:02d}",
            )
        )
    states = tuple(
        CatalogObjectState(
            key=key,
            first_seen_observation_id=f"obs_{key.table_name}",
            last_seen_observation_id=f"obs_{key.table_name}",
            last_source_sequence=index,
            catalog_revision=1,
        )
        for index, key in enumerate(keys)
    )
    state = CatalogWorkingState(objects=states)
    selected = select_prior_catalog_objects(
        state,
        current_request="请查看 main.table_09 的字段",
    )
    assert len(selected) == MAX_PRIOR_DIGEST_OBJECTS
    assert selected[0].key.table_name == "table_09"
