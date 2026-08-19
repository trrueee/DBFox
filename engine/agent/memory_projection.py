"""Session Memory v4 projection service.

The service folds canonical terminal Runs into typed Memory v4 inside the
caller-owned canonical transaction. Derived-projection contract failures are
reported as ``MemoryProjectionError`` and must never mutate Memory or block
canonical terminalization. Database infrastructure failures are not caught
here and continue to fail the canonical transaction.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.memory_v4 import (
    CatalogFoldResult,
    CatalogProjectionError,
    CatalogProjectionScope,
    CatalogWorkingState,
    SessionMemoryStateV4,
    build_catalog_projection_envelope,
    catalog_contract_fingerprint,
    empty_session_memory_v4,
    fold_catalog,
)
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.run import TERMINAL_RUN_STATUSES
from engine.json_codec import JsonCodecError, canonical_dumps, loads
from engine.models import (
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    AgentSessionMemory,
    AgentToolInvocation,
)


class MemoryProjectionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    projected_through_session_sequence: int
    latest_terminal_sequence: int | None = None
    projection_lag: int = Field(default=0, ge=0)
    state_hash: str


class MemoryProjectionError(ValueError):
    """A derived Memory v4 contract/validation error.

    Safe to catch in terminal paths because no Memory mutation has happened.
    """


class MemoryProjectionContractMismatch(MemoryProjectionError):
    pass


class RebuildOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    mode: str
    complete: bool
    written: bool = False
    projected_through_session_sequence: int = Field(default=0, ge=0)
    latest_terminal_sequence: int | None = None
    rebuilt_state_hash: str | None = None
    persisted_state_hash: str | None = None
    matches: bool | None = None
    reason: str | None = None


def _run_scope(
    run: AgentRun,
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
) -> tuple[CatalogWorkingState, CatalogProjectionScope]:
    if run.datasource_id is None:
        return state, scope
    run_datasource_id = str(run.datasource_id)
    run_generation = int(run.datasource_generation or 0)
    if scope.datasource_id == "":
        return state, CatalogProjectionScope(
            datasource_id=run_datasource_id,
            datasource_generation=run_generation,
            catalog_revision=0,
        )
    if (
        scope.datasource_id != run_datasource_id
        or scope.datasource_generation != run_generation
    ):
        # A resource-generation transition invalidates every object from the
        # previous generation even when the new Run contains no Catalog
        # observation at all. The next Catalog observation still refreshes the
        # catalog_revision below.
        return CatalogWorkingState(), CatalogProjectionScope(
            datasource_id=run_datasource_id,
            datasource_generation=run_generation,
            catalog_revision=0,
        )
    return state, scope


def _fold_terminal_sequence(
    db: Session,
    run: AgentRun,
    state: CatalogWorkingState,
    scope: CatalogProjectionScope,
) -> CatalogFoldResult:
    state, current_scope = _run_scope(run, state, scope)
    folded = CatalogFoldResult(state=state, scope=current_scope)
    try:
        for invocation, observation in _run_observation_pairs(db, str(run.id)):
            folded = fold_catalog(
                folded.state,
                scope=current_scope,
                source_sequence=int(run.session_sequence),
                invocation=invocation,
                observation=observation,
            )
            current_scope = folded.scope
    except (CatalogProjectionError, ValidationError) as exc:
        raise MemoryProjectionError(
            "Catalog projection could not reduce a terminal Run"
        ) from exc
    return folded


def project_session_memory(
    db: Session,
    session_id: str,
    through_session_sequence: int,
) -> MemoryProjectionOutcome:
    """Fold terminal Runs ``(watermark, through]`` into shadow Memory v4.

    The function reads and computes first, then mutates one
    ``AgentSessionMemory`` row at the very end. A projection error leaves the
    row untouched.
    """

    row = next(
        (
            pending
            for pending in db.new
            if isinstance(pending, AgentSessionMemory)
            and str(pending.session_id) == session_id
        ),
        None,
    )
    if row is None:
        row = db.execute(
            select(AgentSessionMemory).where(
                AgentSessionMemory.session_id == session_id
            )
        ).scalar_one_or_none()
    memory = _load_memory_v4(row)
    state, scope, watermark = _catalog_projection(memory)

    folded = CatalogFoldResult(state=state, scope=scope)
    for run in _terminal_runs(db, session_id, watermark, through_session_sequence):
        if int(run.session_sequence) != watermark + 1:
            # Do not jump a missing or not-yet-terminal sequence.
            break
        if str(run.status) not in TERMINAL_RUN_STATUSES:
            break
        folded = _fold_terminal_sequence(db, run, folded.state, folded.scope)
        watermark = int(run.session_sequence)

    envelope = build_catalog_projection_envelope(
        scope=folded.scope,
        state=folded.state,
        projected_through_session_sequence=watermark,
    )
    updated_memory = memory.model_copy(
        update={
            "projections": tuple(
                projection
                for projection in memory.projections
                if projection.projection_id != envelope.projection_id
            )
            + (envelope,)
        }
    )
    payload = updated_memory.model_dump(mode="json")
    payload_text = canonical_dumps(payload)

    if row is None:
        session = db.get(AgentSession, session_id)
        if session is None:
            raise MemoryProjectionError(
                f"Agent Session does not exist: {session_id}"
            )
        row = AgentSessionMemory(
            id=f"memory_v4_{session_id}",
            session_id=session_id,
            datasource_id=str(session.datasource_id) if session.datasource_id else None,
            memory_json="{}",
            memory_v4_json=payload_text,
        )
        db.add(row)
    else:
        row.memory_v4_json = payload_text
    db.flush()

    latest_sequence = _latest_terminal_sequence(db, session_id)
    return MemoryProjectionOutcome(
        session_id=session_id,
        projected_through_session_sequence=watermark,
        latest_terminal_sequence=latest_sequence,
        projection_lag=max(0, (latest_sequence or watermark) - watermark),
        state_hash=envelope.state_hash,
    )


def rebuild_session_memory(
    db: Session,
    session_id: str,
    *,
    mode: str,
) -> RebuildOutcome:
    """Full rebuild from canonical records using the same fold function.

    ``compare`` never writes. ``strict`` never writes and reports incomplete
    on a sequence gap or unsupported projection input. ``repair`` writes only
    when a strict-complete rebuild is available.
    """

    if mode not in {"compare", "strict", "repair"}:
        raise ValueError("mode must be compare, strict, or repair")

    latest = _latest_terminal_sequence(db, session_id)
    if latest is None:
        return RebuildOutcome(
            session_id=session_id,
            mode=mode,
            complete=True,
            projected_through_session_sequence=0,
            latest_terminal_sequence=None,
            reason="no terminal Runs",
        )

    expected_sequence = 1
    state = CatalogWorkingState()
    scope = CatalogProjectionScope(
        datasource_id="",
        datasource_generation=0,
        catalog_revision=0,
    )
    runs = list(
        db.execute(
            select(AgentRun)
            .where(
                AgentRun.session_id == session_id,
                AgentRun.session_sequence <= int(latest),
            )
            .order_by(AgentRun.session_sequence)
        ).scalars()
    )
    try:
        for run in runs:
            sequence = int(run.session_sequence)
            if sequence != expected_sequence:
                raise MemoryProjectionError(
                    f"Session sequence gap at {expected_sequence}"
                )
            if str(run.status) not in TERMINAL_RUN_STATUSES:
                raise MemoryProjectionError(
                    f"Session sequence {sequence} is not terminal"
                )
            folded = _fold_terminal_sequence(db, run, state, scope)
            state = folded.state
            scope = folded.scope
            expected_sequence += 1
    except MemoryProjectionError as exc:
        return RebuildOutcome(
            session_id=session_id,
            mode=mode,
            complete=False,
            projected_through_session_sequence=expected_sequence - 1,
            latest_terminal_sequence=latest,
            reason=str(exc),
        )

    envelope = build_catalog_projection_envelope(
        scope=scope,
        state=state,
        projected_through_session_sequence=expected_sequence - 1,
    )
    rebuilt_hash = envelope.state_hash

    row = db.execute(
        select(AgentSessionMemory).where(
            AgentSessionMemory.session_id == session_id
        )
    ).scalar_one_or_none()
    persisted_hash: str | None = None
    if row is not None and row.memory_v4_json:
        try:
            persisted_memory = _load_memory_v4(row)
            persisted = next(
                (
                    item
                    for item in persisted_memory.projections
                    if item.projection_id == envelope.projection_id
                ),
                None,
            )
            if persisted is not None:
                persisted_hash = persisted.state_hash
        except MemoryProjectionError:
            persisted_hash = None

    matches = persisted_hash == rebuilt_hash if persisted_hash is not None else False
    written = False
    if mode == "repair":
        updated = empty_session_memory_v4().model_copy(
            update={
                "projections": (envelope,)
            }
        )
        payload_text = canonical_dumps(updated.model_dump(mode="json"))
        if row is None:
            session = db.get(AgentSession, session_id)
            if session is None:
                raise MemoryProjectionError(
                    f"Agent Session does not exist: {session_id}"
                )
            row = AgentSessionMemory(
                id=f"memory_v4_{session_id}",
                session_id=session_id,
                datasource_id=str(session.datasource_id) if session.datasource_id else None,
                memory_json="{}",
                memory_v4_json=payload_text,
            )
            db.add(row)
        else:
            row.memory_v4_json = payload_text
        db.flush()
        written = True

    return RebuildOutcome(
        session_id=session_id,
        mode=mode,
        complete=True,
        written=written,
        projected_through_session_sequence=expected_sequence - 1,
        latest_terminal_sequence=latest,
        rebuilt_state_hash=rebuilt_hash,
        persisted_state_hash=persisted_hash,
        matches=matches,
    )


def _load_memory_v4(row: AgentSessionMemory | None) -> SessionMemoryStateV4:
    if row is None or not str(row.memory_v4_json or ""):
        return empty_session_memory_v4()
    try:
        value = loads(str(row.memory_v4_json))
    except JsonCodecError as exc:
        raise MemoryProjectionError(
            "Stored Memory v4 JSON is not valid canonical JSON"
        ) from exc
    try:
        return SessionMemoryStateV4.model_validate(value)
    except ValidationError as exc:
        raise MemoryProjectionError(
            "Stored Memory v4 JSON does not match the typed contract"
        ) from exc


def _catalog_projection(
    memory: SessionMemoryStateV4,
) -> tuple[CatalogWorkingState, CatalogProjectionScope, int]:
    projection = next(
        (
            item
            for item in memory.projections
            if item.projection_id == "dbfox.catalog.working_state"
        ),
        None,
    )
    if projection is None:
        return (
            CatalogWorkingState(),
            CatalogProjectionScope(
                datasource_id="",
                datasource_generation=0,
                catalog_revision=0,
            ),
            0,
        )
    if projection.contract_fingerprint != catalog_contract_fingerprint():
        raise MemoryProjectionContractMismatch(
            "Catalog projection contract fingerprint changed; rebuild is required"
        )
    try:
        scope = CatalogProjectionScope.model_validate(projection.scope)
        state = CatalogWorkingState.model_validate(projection.state)
    except ValidationError as exc:
        raise MemoryProjectionError(
            "Catalog projection envelope does not match its typed scope/state"
        ) from exc
    return state, scope, int(projection.projected_through_session_sequence)


def _terminal_runs(
    db: Session,
    session_id: str,
    watermark: int,
    through_session_sequence: int,
) -> list[AgentRun]:
    return list(
        db.execute(
            select(AgentRun)
            .where(
                AgentRun.session_id == session_id,
                AgentRun.session_sequence > watermark,
                AgentRun.session_sequence <= through_session_sequence,
            )
            .order_by(AgentRun.session_sequence)
        ).scalars()
    )


def _run_observation_pairs(
    db: Session,
    run_id: str,
) -> list[tuple[Any, Any]]:
    invocation_rows = list(
        db.execute(
            select(AgentToolInvocation).where(
                AgentToolInvocation.run_id == run_id
            )
        ).scalars()
    )
    invocations = {
        str(row.id): row for row in invocation_rows
    }
    pairs: list[tuple[Any, Any]] = []
    observations = list(
        db.execute(
            select(AgentObservationRecord)
            .where(AgentObservationRecord.run_id == run_id)
            .order_by(AgentObservationRecord.sequence)
        ).scalars()
    )
    for record in observations:
        invocation_row = invocations.get(str(record.tool_invocation_id))
        if invocation_row is None:
            raise MemoryProjectionError(
                "Catalog projection cannot resolve an Observation Invocation"
            )
        pairs.append(
            (
                ToolInvocationRepository._domain(invocation_row),
                ToolInvocationRepository._observation(record, invocation_row),
            )
        )
    return pairs


def _latest_terminal_sequence(db: Session, session_id: str) -> int | None:
    return db.execute(
        select(AgentRun.session_sequence)
        .where(
            AgentRun.session_id == session_id,
            AgentRun.status.in_(TERMINAL_RUN_STATUSES),
        )
        .order_by(AgentRun.session_sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
