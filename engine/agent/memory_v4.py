"""Typed, bounded, rebuildable Session Memory v4 models and Catalog reducer.

Memory v4 is a derived projection of canonical durable records. This module
contains only the deterministic, pure projection contract; repositories decide
when to persist it. It must never read wall-clock time, live datasources, the
Prompt, or the model provider.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from engine.agent.observation import Observation, ObservationStatus
from engine.agent.tool import ToolInvocation
from engine.json_codec import canonical_dumps

CATALOG_PROJECTION_ID = "dbfox.catalog.working_state"
CATALOG_PROJECTION_SCHEMA_VERSION = 1
MEMORY_V4_SCHEMA_VERSION: Literal[4] = 4
CORE_POLICY_VERSION = 1

MAX_CATALOG_SEARCHES = 12
MAX_CATALOG_OBJECTS = 32
MAX_PRIOR_DIGEST_OBJECTS = 8
MAX_PRIOR_DIGEST_COLUMNS = 12
MAX_PRIOR_RELATED_OBJECTS = 8
MAX_PRIOR_DIGEST_BYTES = 16 * 1024

# P0 supports exactly the built-in Catalog contracts at their current versions.
# Unknown versions must fail the projection attempt rather than guess.
SUPPORTED_CATALOG_TOOLS: dict[str, frozenset[str]] = {
    "catalog_overview": frozenset({"1"}),
    "catalog_refresh": frozenset({"1"}),
    "schema_list": frozenset({"1"}),
    "schema_search": frozenset({"1"}),
    "schema_inspect": frozenset({"1"}),
}


class CatalogProjectionError(ValueError):
    """The current input cannot be reduced without guessing."""


class UnsupportedCatalogInput(CatalogProjectionError):
    pass


class CatalogObjectKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["table", "column"]
    schema_name: str
    table_name: str
    column_name: str = ""

    @model_validator(mode="after")
    def validate_column_target(self) -> "CatalogObjectKey":
        if self.kind == "table" and self.column_name:
            raise ValueError("table key must not carry a column_name")
        if self.kind == "column" and not self.column_name:
            raise ValueError("column key requires a column_name")
        if not self.table_name:
            raise ValueError("Catalog object key requires a table_name")
        return self

    @property
    def canonical_tuple(self) -> tuple[str, str, str, str]:
        return (self.kind, self.schema_name, self.table_name, self.column_name)


class CatalogProjectionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    datasource_id: str
    datasource_generation: int = Field(ge=0)
    catalog_revision: int = Field(ge=0)


class CatalogOrientation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    last_overview_observation_id: str | None = None
    last_refresh_observation_id: str | None = None
    last_source_sequence: int = Field(ge=0)
    catalog_revision: int = Field(ge=0)


class SearchFootprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invocation_id: str
    observation_id: str
    input_hash: str
    queries: tuple[str, ...]
    candidate_keys: tuple[CatalogObjectKey, ...]
    returned_count: int = Field(ge=0)
    catalog_revision: int = Field(ge=0)
    source_sequence: int = Field(ge=0)


class CatalogObjectState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: CatalogObjectKey
    first_seen_observation_id: str
    last_seen_observation_id: str
    last_inspected_observation_id: str | None = None
    last_source_sequence: int = Field(ge=0)
    catalog_revision: int = Field(ge=0)


class CatalogWorkingState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    orientation: CatalogOrientation | None = None
    searches: tuple[SearchFootprint, ...] = ()
    objects: tuple[CatalogObjectState, ...] = ()


class CatalogFoldResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: CatalogWorkingState
    scope: CatalogProjectionScope


class SessionMemoryCore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    referenced_artifact_ids: tuple[str, ...] = ()
    runtime_evidence_references: tuple[str, ...] = ()
    advisory_open_questions: tuple[str, ...] = ()


class SessionProjectionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    extension_id: str
    projection_id: str
    schema_version: int
    contract_fingerprint: str
    projected_through_session_sequence: int = Field(ge=0)
    state_hash: str
    scope: dict[str, JsonValue]
    state: dict[str, JsonValue]


class SessionMemoryStateV4(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[4] = 4
    core_policy_version: int
    core: SessionMemoryCore
    projections: tuple[SessionProjectionEnvelope, ...] = ()


def canonical_state_hash(value: BaseModel) -> str:
    """Return a deterministic content hash for one typed projection value."""

    return hashlib.sha256(
        canonical_dumps(value.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()


def select_prior_catalog_objects(
    state: CatalogWorkingState,
    *,
    current_request: str,
) -> tuple[CatalogObjectState, ...]:
    """Deterministic first-version prior Observation selection.

    No LLM/embedding is used. The current request can only promote an object
    by an explicit identity or prior search-query hit; otherwise inspected and
    most-recently-seen objects win, with the canonical key as tie-breaker.
    """

    request = current_request.casefold()
    hit_keys = {
        candidate.canonical_tuple
        for footprint in state.searches
        if any(query.casefold() in request for query in footprint.queries)
        for candidate in footprint.candidate_keys
    }

    def request_rank(item: CatalogObjectState) -> tuple[int, int, int, tuple[str, str, str, str]]:
        identity_terms = [
            item.key.table_name,
            (
                f"{item.key.schema_name}.{item.key.table_name}"
                if item.key.schema_name
                else item.key.table_name
            ),
        ]
        if item.key.kind == "column":
            identity_terms.append(item.key.column_name)
            identity_terms.append(f"{item.key.table_name}.{item.key.column_name}")
        explicit_identity = any(
            term.casefold() in request for term in identity_terms
        )
        search_hit = item.key.canonical_tuple in hit_keys
        inspected = 0 if item.last_inspected_observation_id is not None else 1
        return (
            0 if explicit_identity or search_hit else 1,
            inspected,
            -item.last_source_sequence,
            item.key.canonical_tuple,
        )

    ranked = sorted(state.objects, key=request_rank)
    return tuple(ranked[:MAX_PRIOR_DIGEST_OBJECTS])


def catalog_contract_fingerprint() -> str:
    """Fingerprint only inputs that change Catalog projection interpretation.

    Presentation, Tool titles and unrelated Extensions are deliberately absent.
    The Catalog projector interprets ToolInvocation.declared_version, while
    exact execution compatibility is owned by the frozen contract hash.
    """

    payload = {
        "projection_id": CATALOG_PROJECTION_ID,
        "schema_version": CATALOG_PROJECTION_SCHEMA_VERSION,
        "core_policy_version": CORE_POLICY_VERSION,
        "tool_identity": "declared_version",
        "eligible_tools": {
            name: sorted(versions) for name, versions in SUPPORTED_CATALOG_TOOLS.items()
        },
        "bounds": {
            "searches": MAX_CATALOG_SEARCHES,
            "objects": MAX_CATALOG_OBJECTS,
        },
    }
    return hashlib.sha256(
        canonical_dumps(payload).encode("utf-8")
    ).hexdigest()


def empty_session_memory_v4() -> SessionMemoryStateV4:
    return SessionMemoryStateV4(
        core_policy_version=CORE_POLICY_VERSION,
        core=SessionMemoryCore(),
    )


def build_catalog_projection_envelope(
    *,
    scope: CatalogProjectionScope,
    state: CatalogWorkingState,
    projected_through_session_sequence: int,
) -> SessionProjectionEnvelope:
    return SessionProjectionEnvelope(
        extension_id="dbfox.data",
        projection_id=CATALOG_PROJECTION_ID,
        schema_version=CATALOG_PROJECTION_SCHEMA_VERSION,
        contract_fingerprint=catalog_contract_fingerprint(),
        projected_through_session_sequence=projected_through_session_sequence,
        state_hash=canonical_state_hash(state),
        scope=scope.model_dump(mode="json"),
        state=state.model_dump(mode="json"),
    )


def fold_catalog(
    state: CatalogWorkingState,
    *,
    scope: CatalogProjectionScope,
    source_sequence: int,
    invocation: ToolInvocation,
    observation: Observation,
) -> CatalogFoldResult:
    """Fold one canonical invocation/observation pair.

    Incremental terminal fold, lag catch-up and full rebuild must all call this
    same pure function with different record windows.
    """

    if observation.status is not ObservationStatus.SUCCEEDED:
        return CatalogFoldResult(state=state, scope=scope)
    versions = SUPPORTED_CATALOG_TOOLS.get(invocation.tool_name)
    if versions is None:
        return CatalogFoldResult(state=state, scope=scope)
    if invocation.declared_version not in versions:
        raise UnsupportedCatalogInput(
            f"Unsupported {invocation.tool_name} contract version "
            f"{invocation.declared_version!r} for Catalog projection"
        )

    revision = _required_observation_revision(observation)
    current_scope = scope
    if scope.catalog_revision != revision:
        current_scope = scope.model_copy(update={"catalog_revision": revision})
        state = CatalogWorkingState()

    if invocation.tool_name == "catalog_overview":
        return CatalogFoldResult(
            state=_fold_overview(
                state, current_scope, source_sequence, observation
            ),
            scope=current_scope,
        )
    if invocation.tool_name == "catalog_refresh":
        return CatalogFoldResult(
            state=_fold_refresh(
                state, current_scope, source_sequence, observation
            ),
            scope=current_scope,
        )
    if invocation.tool_name == "schema_list":
        return CatalogFoldResult(
            state=_fold_schema_list(
                state, current_scope, source_sequence, observation
            ),
            scope=current_scope,
        )
    if invocation.tool_name == "schema_search":
        return CatalogFoldResult(
            state=_fold_schema_search(
                state, current_scope, source_sequence, invocation, observation
            ),
            scope=current_scope,
        )
    return CatalogFoldResult(
        state=_fold_schema_inspect(
            state, current_scope, source_sequence, observation
        ),
        scope=current_scope,
    )


def _required_observation_revision(observation: Observation) -> int:
    facts = observation.facts or {}
    value = facts.get("catalog_revision")
    if isinstance(value, bool) or not isinstance(value, int):
        raise CatalogProjectionError(
            "Catalog Observation is missing a valid catalog_revision fact"
        )
    if value < 0:
        raise CatalogProjectionError("Catalog Observation has a negative catalog_revision")
    return value


def _fold_overview(
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
    source_sequence: int,
    observation: Observation,
) -> CatalogWorkingState:
    orientation = CatalogOrientation(
        last_overview_observation_id=observation.id,
        last_source_sequence=source_sequence,
        catalog_revision=scope.catalog_revision,
    )
    return state.model_copy(update={"orientation": orientation})


def _fold_refresh(
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
    source_sequence: int,
    observation: Observation,
) -> CatalogWorkingState:
    orientation = CatalogOrientation(
        last_overview_observation_id=(
            state.orientation.last_overview_observation_id
            if state.orientation is not None
            else None
        ),
        last_refresh_observation_id=observation.id,
        last_source_sequence=source_sequence,
        catalog_revision=scope.catalog_revision,
    )
    return state.model_copy(update={"orientation": orientation})


def _fold_schema_list(
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
    source_sequence: int,
    observation: Observation,
) -> CatalogWorkingState:
    tables = observation.facts.get("tables")
    if not isinstance(tables, list):
        raise CatalogProjectionError("schema_list Observation is missing tables facts")
    object_updates: dict[tuple[str, str, str, str], CatalogObjectState] = {
        item.key.canonical_tuple: item for item in state.objects
    }
    for table in tables:
        if not isinstance(table, dict):
            raise CatalogProjectionError("schema_list table fact is not an object")
        key = CatalogObjectKey(
            kind="table",
            schema_name=str(table.get("schema_name") or ""),
            table_name=str(table.get("table_name") or ""),
        )
        object_updates[key.canonical_tuple] = _upsert_seen_object(
            object_updates.get(key.canonical_tuple),
            key=key,
            observation_id=observation.id,
            source_sequence=source_sequence,
            revision=scope.catalog_revision,
        )
    return state.model_copy(
        update={
            "objects": _bounded_objects(
                tuple(
                    sorted(
                        object_updates.values(),
                        key=lambda item: item.key.canonical_tuple,
                    )
                )
            )
        }
    )


def _fold_schema_search(
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
    source_sequence: int,
    invocation: ToolInvocation,
    observation: Observation,
) -> CatalogWorkingState:
    raw_queries = invocation.authorized_input.get("queries")
    if not isinstance(raw_queries, list) or not all(
        isinstance(query, str) for query in raw_queries
    ):
        raise CatalogProjectionError("schema_search authorized input is missing queries")
    queries = tuple(query for query in raw_queries if query)
    if not queries:
        raise CatalogProjectionError("schema_search authorized input has no queries")

    raw_candidates = observation.facts.get("candidates")
    if not isinstance(raw_candidates, list):
        raise CatalogProjectionError("schema_search Observation is missing candidates")
    candidate_keys = tuple(
        _candidate_key(candidate) for candidate in raw_candidates
    )
    returned_count = int(observation.facts.get("returned_count", len(candidate_keys)))

    footprint = SearchFootprint(
        invocation_id=invocation.id,
        observation_id=observation.id,
        input_hash=invocation.authorized_input_hash,
        queries=queries,
        candidate_keys=candidate_keys,
        returned_count=returned_count,
        catalog_revision=scope.catalog_revision,
        source_sequence=source_sequence,
    )

    object_updates: dict[tuple[str, str, str, str], CatalogObjectState] = {
        item.key.canonical_tuple: item for item in state.objects
    }
    for key in candidate_keys:
        object_updates[key.canonical_tuple] = _upsert_seen_object(
            object_updates.get(key.canonical_tuple),
            key=key,
            observation_id=observation.id,
            source_sequence=source_sequence,
            revision=scope.catalog_revision,
        )

    searches = _bounded_searches((*state.searches, footprint))
    objects = _bounded_objects(
        tuple(
            sorted(
                object_updates.values(),
                key=lambda item: item.key.canonical_tuple,
            )
        )
    )
    return state.model_copy(update={"searches": searches, "objects": objects})


def _fold_schema_inspect(
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
    source_sequence: int,
    observation: Observation,
) -> CatalogWorkingState:
    inspections = observation.facts.get("inspections")
    if not isinstance(inspections, list):
        raise CatalogProjectionError("schema_inspect Observation is missing inspections")
    object_updates: dict[tuple[str, str, str, str], CatalogObjectState] = {
        item.key.canonical_tuple: item for item in state.objects
    }
    for inspection in inspections:
        if not isinstance(inspection, dict):
            raise CatalogProjectionError("schema_inspect fact is not an object")
        key = _inspection_key(inspection)
        existing = object_updates.get(key.canonical_tuple)
        if existing is None:
            existing = CatalogObjectState(
                key=key,
                first_seen_observation_id=observation.id,
                last_seen_observation_id=observation.id,
                last_source_sequence=source_sequence,
                catalog_revision=scope.catalog_revision,
            )
        object_updates[key.canonical_tuple] = existing.model_copy(
            update={
                "last_seen_observation_id": observation.id,
                "last_inspected_observation_id": observation.id,
                "last_source_sequence": max(
                    source_sequence, existing.last_source_sequence
                ),
                "catalog_revision": scope.catalog_revision,
            }
        )
    return state.model_copy(
        update={
            "objects": _bounded_objects(
                tuple(
                    sorted(
                        object_updates.values(),
                        key=lambda item: item.key.canonical_tuple,
                    )
                )
            )
        }
    )


def _candidate_key(candidate: Any) -> CatalogObjectKey:
    if not isinstance(candidate, dict):
        raise CatalogProjectionError("schema_search candidate is not an object")
    kind = str(candidate.get("type") or "")
    if kind == "table":
        return CatalogObjectKey(
            kind="table",
            schema_name=str(candidate.get("schema_name") or ""),
            table_name=str(candidate.get("table_name") or ""),
        )
    if kind == "column":
        return CatalogObjectKey(
            kind="column",
            schema_name=str(candidate.get("schema_name") or ""),
            table_name=str(candidate.get("table_name") or ""),
            column_name=str(candidate.get("column_name") or ""),
        )
    raise CatalogProjectionError(f"Unknown schema_search candidate kind: {kind!r}")


def _inspection_key(inspection: dict[str, Any]) -> CatalogObjectKey:
    details = inspection.get("details")
    if not isinstance(details, dict):
        raise CatalogProjectionError("schema_inspect fact is missing details")
    object_type = str(details.get("object_type") or "")
    if object_type == "table":
        return CatalogObjectKey(
            kind="table",
            schema_name=str(details.get("schema_name") or ""),
            table_name=str(details.get("name") or inspection.get("target") or ""),
        )
    if object_type == "column":
        return CatalogObjectKey(
            kind="column",
            schema_name=str(details.get("schema_name") or ""),
            table_name=str(details.get("table") or ""),
            column_name=str(details.get("name") or ""),
        )
    raise CatalogProjectionError(
        f"Unknown schema_inspect object_type: {object_type!r}"
    )


def _upsert_seen_object(
    existing: CatalogObjectState | None,
    *,
    key: CatalogObjectKey,
    observation_id: str,
    source_sequence: int,
    revision: int,
) -> CatalogObjectState:
    if existing is None:
        return CatalogObjectState(
            key=key,
            first_seen_observation_id=observation_id,
            last_seen_observation_id=observation_id,
            last_source_sequence=source_sequence,
            catalog_revision=revision,
        )
    return existing.model_copy(
        update={
            "last_seen_observation_id": observation_id,
            "last_source_sequence": max(source_sequence, existing.last_source_sequence),
            "catalog_revision": revision,
        }
    )


def _bounded_searches(
    searches: tuple[SearchFootprint, ...],
) -> tuple[SearchFootprint, ...]:
    if len(searches) <= MAX_CATALOG_SEARCHES:
        return tuple(sorted(searches, key=_search_sort_key))
    kept = sorted(
        searches,
        key=lambda item: (item.source_sequence, item.observation_id),
    )[-MAX_CATALOG_SEARCHES:]
    return tuple(sorted(kept, key=_search_sort_key))


def _search_sort_key(footprint: SearchFootprint) -> tuple[int, str]:
    return (footprint.source_sequence, footprint.observation_id)


def _bounded_objects(
    objects: tuple[CatalogObjectState, ...],
) -> tuple[CatalogObjectState, ...]:
    if len(objects) <= MAX_CATALOG_OBJECTS:
        return tuple(objects)
    ranked = sorted(
        objects,
        key=lambda item: (
            0 if item.last_inspected_observation_id is not None else 1,
            -item.last_source_sequence,
            item.key.canonical_tuple,
        ),
    )
    return tuple(
        sorted(
            ranked[:MAX_CATALOG_OBJECTS],
            key=lambda item: item.key.canonical_tuple,
        )
    )
