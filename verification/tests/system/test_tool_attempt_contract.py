"""P5B serializable Tool attempt and resource scope contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import signature

import pytest

from engine.agent.artifact import Artifact
from engine.representation import (
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
)
from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ToolAttemptRequest,
    ToolInvocationContext,
)
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.runtime import ToolRuntime


def _scope(kind: str = "dbfox.data.database", version: str | int | None = 11) -> ResourceScopeRef:
    return ResourceScopeRef(kind=kind, id=f"{kind}-1", version=version)


def test_tool_context_artifact_access_is_explicit_and_fail_closed() -> None:
    artifact = Artifact(
        id="artifact-1",
        session_id="session-1",
        run_id="run-1",
        type="markdown",
        title="Result",
        payload={"content": "bounded"},
    )
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="artifact-access",
        artifact_loader=lambda artifact_id: artifact if artifact_id == artifact.id else None,
    )

    assert context.artifact("artifact-1") is artifact
    with pytest.raises(RuntimeError, match="unavailable in this Run"):
        context.artifact("artifact-2")
    with pytest.raises(RuntimeError, match="cannot access"):
        ToolRunContext.for_invocation(
            request=None,
            idempotency_key="no-artifact-access",
        ).artifact("artifact-1")


def test_tool_context_representation_access_is_explicit_and_frozen() -> None:
    expected = ArtifactRepresentationResult(
        representation_type="acme.table.v1",
        representation_version=1,
        operation="page",
        payload={"fields": []},
        consistency="durable_snapshot",
        read_at="2026-08-28T00:00:00Z",
        read_id="read-1",
        source_version="1",
        source_fingerprint="sha256:test",
    )
    calls: list[tuple[str, str, str]] = []
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="representation-access",
        artifact_representation_reader=lambda artifact_id, representation_type, request: (
            calls.append((artifact_id, representation_type, request.operation))
            or expected
        ),
    )

    result = context.read_artifact_representation(
        "artifact-1",
        "acme.table.v1",
        ArtifactRepresentationRequest(operation="page"),
    )
    assert result is expected
    assert calls == [("artifact-1", "acme.table.v1", "page")]

    with pytest.raises(RuntimeError, match="cannot read"):
        ToolRunContext.for_invocation(
            request=None,
            idempotency_key="no-representation-access",
        ).read_artifact_representation(
            "artifact-1",
            "acme.table.v1",
            ArtifactRepresentationRequest(operation="page"),
        )


def test_tool_invocation_context_requires_unique_scope_identity() -> None:
    context = ToolInvocationContext(
        session_id="session-1",
        run_id="run-1",
        turn_id="turn-1",
        invocation_id="invocation-1",
        idempotency_key="idem-1",
        deadline_at=datetime.now(UTC),
        scope_refs=(_scope(), _scope(kind="synthetic.workspace", version="v1")),
    )
    assert context.scope("dbfox.data.database") == _scope()
    assert context.scope("synthetic.workspace").version == "v1"

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
                _scope(kind="synthetic.workspace", version="workspace-root-v1"),
            ),
        ),
        authorized_input={"queries": ["orders"]},
        attempt_timeout_ms=15_000,
    )
    payload = request.model_dump(mode="json")
    assert payload["mode"] == "execute"
    assert payload["invocation"]["scope_refs"][0]["kind"] == "dbfox.data.database"
    assert payload["invocation"]["scope_refs"][1] == {
        "kind": "synthetic.workspace",
        "id": "synthetic.workspace-1",
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
    resolver.register("dbfox.data.database", lambda ref: {"id": ref.id, "version": ref.version})
    resolver.register("synthetic.workspace", lambda ref: object())

    resolved = resolver.resolve((_scope(), _scope(kind="synthetic.workspace", version=1)))
    assert resolved[_scope().canonical()]["id"] == "dbfox.data.database-1"
    assert isinstance(resolved[_scope(kind="synthetic.workspace", version=1).canonical()], object)

    with pytest.raises(KeyError, match="No resolver"):
        resolver.resolve((_scope(kind="synthetic.network"),))

    resolver.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        resolver.register("synthetic.network", lambda ref: None)


def test_tool_run_context_exposes_only_authorized_resources() -> None:
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="idem-1",
        scope_refs=(_scope(kind="synthetic.workspace", version=1),),
        resources={_scope(kind="synthetic.workspace", version=1).canonical(): {"root": "C:/demo"}},
    )
    assert context.require_one("synthetic.workspace") == {"root": "C:/demo"}
    with pytest.raises(RuntimeError, match="resource"):
        context.require_one("dbfox.data.database")


def test_database_resource_has_one_context_access_path() -> None:
    database = object()
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="idem-database",
        scope_refs=(_scope(),),
        resources={_scope().canonical(): database},
    )

    assert context.require_one("dbfox.data.database") is database
    assert "db_session" not in ToolRunContext.model_fields
    assert "db" not in signature(ToolRuntime.invoke).parameters
    assert "db" not in signature(ToolRuntime.reconcile).parameters


def test_tool_run_context_keeps_multiple_same_kind_resources_distinct() -> None:
    first = ResourceScopeRef(kind="dbfox.data.database", id="billing", version=4)
    second = ResourceScopeRef(kind="dbfox.data.database", id="analytics", version=9)
    context = ToolRunContext.for_invocation(
        request=None,
        idempotency_key="idem-multi-database",
        scope_refs=(first, second),
        resources={first.canonical(): "billing-handle", second.canonical(): "analytics-handle"},
    )

    assert context.scopes("dbfox.data.database") == (first, second)
    assert context.resources("dbfox.data.database") == ("billing-handle", "analytics-handle")
    assert context.resource(second) == "analytics-handle"
    with pytest.raises(RuntimeError, match="exactly one"):
        context.require_one("dbfox.data.database")
    with pytest.raises(RuntimeError, match="ambiguous"):
        context.scope("dbfox.data.database")


def test_resource_scope_ref_is_identity_only_and_rejects_transport_location() -> None:
    workspace = ResourceScopeRef(kind="synthetic.workspace", id="project-1", version="root-v1")

    assert workspace.model_dump(mode="json") == {
        "kind": "synthetic.workspace",
        "id": "project-1",
        "version": "root-v1",
    }
    with pytest.raises(Exception):
        ResourceScopeRef(
            kind="synthetic.workspace",
            id="project-1",
            version="root-v1",
            location="C:/must-not-cross-wire",
        )
