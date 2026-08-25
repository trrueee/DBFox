"""Tests for P9.0 Greenfield Resource Seam Closure.

Verifies:
1. RequestedResourceRef wire model (intent without version).
2. Core resource discovery does not absorb Workspace domain state.
3. Server-side authorization attaching canonical versions to frozen ResourceScopeRefs.
4. Foreign resource request rejection.
5. Legacy admission fallback when requested_resources is omitted.
6. In-process and worker execution unified through CompositeResourceResolver.
7. Third-resource extensibility proof without Kernel domain branches.
"""

from __future__ import annotations
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from engine.agent.resource_refs import RequestedResourceRef
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.dlc import BuiltinContributionSet, ContributionCompiler
from engine.models import Project
from engine.runtime_composition import (
    authorize_project_resources,
    discover_project_resources,
)
from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
)
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolResourceRequirement,
)
from engine.tools.runtime.resource_context import build_tool_scope_context


class DummyInput(ToolInputModel):
    pass


class DummyOutput(ToolOutputModel):
    pass


def _snapshot_with_resources(tmp_path, resources_by_project):
    def provider(_db, project_id):
        return tuple(resources_by_project.get(project_id, ()))

    return ContributionCompiler(tmp_path / "dlcs").compile(
        built_ins=BuiltinContributionSet(resource_providers=(provider,)),
    )


def test_requested_resource_ref_validation() -> None:
    """Prove that RequestedResourceRef enforces kind + id and forbids version/extras."""
    ref = RequestedResourceRef(kind="dbfox.data.database", id="ds-100")
    assert ref.kind == "dbfox.data.database"
    assert ref.id == "ds-100"

    # Forbids version
    with pytest.raises(ValidationError):
        RequestedResourceRef(kind="dbfox.data.database", id="ds-100", version=1)  # type: ignore[call-arg]

    # Forbids extra fields
    with pytest.raises(ValidationError):
        RequestedResourceRef(kind="dbfox.data.database", id="ds-100", custom_flag=True)  # type: ignore[call-arg]


def test_project_resource_discovery(db_session, tmp_path) -> None:
    """Prove that discover_project_resources aggregates descriptors from all providers."""
    project_id = "proj-discovery-test"
    db_session.add(
        Project(
            id=project_id,
            name="Discovery Project",
        )
    )
    db_session.commit()
    snapshot = _snapshot_with_resources(tmp_path, {
        project_id: (
            ProjectResourceDescriptor(
                kind="dbfox.data.database",
                id="db-active-1",
                name="Main Postgres",
                version="5:2",
            ),
        ),
    })

    descriptors = discover_project_resources(db_session, project_id, snapshot=snapshot)
    kinds = {(d.kind, d.id): d for d in descriptors}

    # Active datasource discovered
    assert ("dbfox.data.database", "db-active-1") in kinds
    assert kinds[("dbfox.data.database", "db-active-1")].version == "5:2"
    assert kinds[("dbfox.data.database", "db-active-1")].name == "Main Postgres"

    # A legacy Project column must not silently become Core-owned authority.
    assert ("workspace", project_id) not in kinds


def test_authorize_project_resources_attaches_canonical_versions(db_session, tmp_path) -> None:
    """Prove that server validates requested resources and resolves current canonical versions."""
    project_id = "proj-auth-test"
    db_session.add(
        Project(
            id=project_id,
            name="Auth Project",
        )
    )
    db_session.commit()
    snapshot = _snapshot_with_resources(tmp_path, {
        project_id: (
            ProjectResourceDescriptor(
                kind="dbfox.data.database",
                id="db-auth-1",
                name="Analytics DB",
                version="3:7",
            ),
        ),
    })

    requested = [RequestedResourceRef(kind="dbfox.data.database", id="db-auth-1")]

    authorized = authorize_project_resources(
        db_session, project_id, requested, snapshot=snapshot,
    )
    assert len(authorized) == 1

    db_ref = next(r for r in authorized if r.kind == "dbfox.data.database")
    assert db_ref.id == "db-auth-1"
    assert db_ref.version == "3:7"

    with pytest.raises(ValueError, match="is not available in project"):
        authorize_project_resources(
            db_session,
            project_id,
            [RequestedResourceRef(kind="dbfox.workspace.root", id=project_id)],
            snapshot=snapshot,
        )


def test_authorize_project_resources_rejects_foreign_resource(db_session, tmp_path) -> None:
    """Prove that requesting a resource not belonging to the project fails closed."""
    project_id = "proj-auth-1"
    other_project_id = "proj-auth-2"
    db_session.add(Project(id=project_id, name="Project 1"))
    db_session.add(Project(id=other_project_id, name="Project 2"))
    db_session.commit()
    snapshot = _snapshot_with_resources(tmp_path, {
        other_project_id: (
            ProjectResourceDescriptor(
                kind="dbfox.data.database",
                id="db-foreign",
                name="Foreign DB",
                version="1:1",
            ),
        ),
    })

    requested = [RequestedResourceRef(kind="dbfox.data.database", id="db-foreign")]

    with pytest.raises(ValueError, match="is not available in project"):
        authorize_project_resources(
            db_session, project_id, requested, snapshot=snapshot,
        )


def test_authorize_project_resources_without_request_grants_nothing(db_session, tmp_path) -> None:
    """Project membership must never become implicit Run authority."""
    project_id = "proj-legacy"
    db_session.add(Project(id=project_id, name="Legacy Project"))
    db_session.commit()
    snapshot = _snapshot_with_resources(tmp_path, {
        project_id: (
            ProjectResourceDescriptor(
                kind="dbfox.data.database",
                id="db-member",
                name="Member DB",
                version="7:1",
            ),
        ),
    })

    refs = authorize_project_resources(
        db_session,
        project_id=project_id,
        requested=None,
        snapshot=snapshot,
    )
    assert refs == ()


def test_in_process_execution_uses_composite_resolver(db_session, tmp_path) -> None:
    """Prove that build_tool_scope_context resolves attempt resources via CompositeResourceResolver."""
    workspace_root = tmp_path / "ws_in_proc"
    workspace_root.mkdir()
    (workspace_root / "test.txt").write_text("hello dbfox")
    project_id = "proj-in-proc"
    db_session.add(
        Project(
            id=project_id,
            name="In Proc Project",
        )
    )
    db_session.commit()

    ws_ref = ResourceScopeRef(kind="synthetic.workspace", id=project_id, version="root-v1")

    class DummyWorkspaceTool(BaseTool[DummyInput, DummyOutput]):
        name = "dummy_ws"
        group = "test"
        description = "Dummy workspace tool"
        input_model = DummyInput
        output_model = DummyOutput
        presentation = "code"
        execution = ToolExecutionSpec(
            required_resources=(ToolResourceRequirement(kind="synthetic.workspace"),),
            backend="in_process",
        )

        def run(self, context, **kwargs):
            return DummyOutput()

    request = MagicMock()
    request.frozen_resource_refs = (ws_ref,)

    resolver = (
        CompositeResourceResolver()
        .register("synthetic.workspace", lambda _ref: workspace_root.resolve())
        .freeze()
    )
    scope_refs, resources = build_tool_scope_context(
        db_session,
        request,
        DummyWorkspaceTool(),
        resolver,
    )
    assert len(scope_refs) == 1
    assert scope_refs[0] == ws_ref
    assert ws_ref.canonical() in resources
    assert resources[ws_ref.canonical()] == workspace_root.resolve()


def test_composite_resolver_supports_third_resource_extension(db_session) -> None:
    """Prove that a third resource kind supports multiple same-kind identities."""
    custom_ref = ResourceScopeRef(kind="custom.source", id="source-42", version="v1.0")
    second_ref = ResourceScopeRef(kind="custom.source", id="source-84", version="v2.0")

    class CustomHandle:
        def __init__(self, ref: ResourceScopeRef):
            self.ref = ref

    custom_resolver = CompositeResourceResolver()
    custom_resolver.register("custom.source", lambda ref: CustomHandle(ref))
    frozen_resolver = custom_resolver.freeze()

    class DummyCustomTool(BaseTool[DummyInput, DummyOutput]):
        name = "dummy_custom"
        group = "test"
        description = "Dummy custom tool"
        input_model = DummyInput
        output_model = DummyOutput
        presentation = "code"
        execution = ToolExecutionSpec(
            required_resources=(ToolResourceRequirement(kind="custom.source"),),
            backend="in_process",
        )

        def run(self, context, **kwargs):
            return DummyOutput()

    request = MagicMock()
    request.frozen_resource_refs = (custom_ref, second_ref)

    scope_refs, resources = build_tool_scope_context(
        db_session,
        request,
        DummyCustomTool(),
        resolver=frozen_resolver,
    )
    assert scope_refs == (custom_ref, second_ref)
    assert custom_ref.canonical() in resources
    assert second_ref.canonical() in resources
    assert isinstance(resources[custom_ref.canonical()], CustomHandle)
    assert resources[custom_ref.canonical()].ref.id == "source-42"
    assert resources[second_ref.canonical()].ref.id == "source-84"
