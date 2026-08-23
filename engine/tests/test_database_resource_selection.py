from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.errors import ToolInputError
from engine.resource import ResourceScopeRef
from engine.tools.db.resource_selection import select_database
from engine.tools.runtime import ToolRunContext


def _context(db_session) -> ToolRunContext:
    refs = (
        ResourceScopeRef(kind="dbfox.data.database", id="billing", version=4),
        ResourceScopeRef(kind="dbfox.data.database", id="analytics", version="2:7"),
    )
    return ToolRunContext.for_invocation(
        request=SimpleNamespace(session_id="session-multi-database"),
        idempotency_key="select-database",
        scope_refs=refs,
        resources={ref.canonical(): object() for ref in refs},
        metadata_session=db_session,
    )


def test_database_id_is_required_for_ambiguous_authority(db_session) -> None:
    with pytest.raises(ToolInputError, match="database_id is required"):
        select_database(_context(db_session), None)


def test_explicit_database_selection_preserves_exact_string_version(db_session) -> None:
    selected = select_database(_context(db_session), "analytics")

    assert selected.ref == ResourceScopeRef(
        kind="dbfox.data.database",
        id="analytics",
        version="2:7",
    )
    assert selected.metadata is db_session
    with pytest.raises(ToolInputError, match="dbfox.data execution tools"):
        selected.require_legacy_generation()


def test_database_selection_rejects_resource_outside_run_authority(db_session) -> None:
    with pytest.raises(ToolInputError, match="not authorized"):
        select_database(_context(db_session), "archive")
