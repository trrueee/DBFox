"""P5B serializable Tool attempt and resource scope contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import signature

import pytest

from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ToolAttemptRequest,
    ToolInvocationContext,
)
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.runtime import ToolRuntime


def _scope(kind: str = "database", version: str | int | None = 11) -> ResourceScopeRef:
    return ResourceScopeRef(kind=kind, id=f"{kind}-1", version=version)


def test_tool_invocation_context_requires_unique_scope_identity() -> None:
    context = ToolInvocationContext(
        session_id="session-1",
        run_id="run-1",
        turn_id="turn-1",
        invocation_id="invocation-1",
        idempotency_key="idem-1",
        deadline_at=datetime.now(UTC),
        scope_refs=(_scope(), _scope(kind="workspace", version="v1")),
    )
    assert context.scope("database") == _scope()
    assert context.scope("workspace").version == "v1"

    with pytest.raises(ValueError, match="unique"):
        ToolInvocationContext(
            session_id="session-1",
            run_id="run-1",
            turn_id="turn-1",
            invocation_id="invocation-2",
            idempotency_key="idem-2",
            scope_refs=(_scope(), _scope(version=12)),
        )


def test_attempt_request_is_serializable_and_excludes_live_objects() -> None:
    request = ToolAttemptRequest(
        mode="execute",
        tool_name="schema_search",
        frozen_tool_declared_version="1",
        frozen_tool_contract_hash="sha256:1",
        invocation=ToolInvocationContext(
            session_id="session-1",
            run_id="run-1",
            turn_id="turn-1",
            invocation_id="invocation-1",
            idempotency_key="idem-1",
            scope_refs=(
                _scope(),
                _scope(kind="workspace", version="workspace-root-v1"),
            ),
        ),
        authorized_input={"queries": ["orders"]},
        attempt_timeout_ms=15_000,
    )
    payload = request.model_dump(mode="json")
    assert payload["mode"] == "execute"
    assert payload["invocation"]["scope_refs"][0]["kind"] == "database"
    assert payload["invocation"]["scope_refs"][1] == {
        "kind": "workspace",
        "id": "workspace-1",
        "version": "workspace-root-v1",
    }
    assert "location" not in str(payload)

    with pytest.raises(Exception):
        ToolAttemptRequest(
            mode="execute",
            tool_name="bad",
            frozen_tool_declared_version="1",
            frozen_tool_contract_hash="sha256:1",
            invocation=request.invocation,
            authorized_input={"callback": lambda: True},  # type: ignore[dict-item]
            attempt_timeout_ms=100,
        )


def test_composite_resolver_registers_capability_resolvers_and_freezes() -> None:
    resolver = CompositeResourceResolver()
    resolver.register("database", lambda ref: {"id": ref.id, "version": ref.version})
    resolver.register("workspace", lambda ref: object())

    resolved = resolver.resolve((_scope(), _scope(kind="workspace", version=1)))
    assert resolved["database"]["id"] == "database-1"
    assert isinstance(resolved["workspace"], object)

    with pytest.raises(KeyError, match="No resolver"):
        resolver.resolve((_scope(kind="network"),))

    resolver.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        resolver.register("network", lambda ref: None)


def test_tool_run_context_exposes_only_authorized_resources() -> None:
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="idem-1",
        scope_refs=(_scope(kind="workspace", version=1),),
        resources={"workspace": {"root": "C:/demo"}},
    )
    assert context.require_resource("workspace") == {"root": "C:/demo"}
    with pytest.raises(RuntimeError, match="resource"):
        context.require_resource("database")


def test_database_resource_has_one_context_access_path() -> None:
    database = object()
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="idem-database",
        scope_refs=(_scope(),),
        resources={"database": database},
    )

    assert context.require_database() is database
    assert "db_session" not in ToolRunContext.model_fields
    assert "db" not in signature(ToolRuntime.invoke).parameters
    assert "db" not in signature(ToolRuntime.reconcile).parameters


def test_resource_scope_ref_is_identity_only_and_rejects_transport_location() -> None:
    workspace = ResourceScopeRef(kind="workspace", id="project-1", version="root-v1")

    assert workspace.model_dump(mode="json") == {
        "kind": "workspace",
        "id": "project-1",
        "version": "root-v1",
    }
    with pytest.raises(Exception):
        ResourceScopeRef(
            kind="workspace",
            id="project-1",
            version="root-v1",
            location="C:/must-not-cross-wire",
        )
