"""P7 Workspace file_read Tool contract tests."""

from __future__ import annotations

import pytest

from engine.agent.artifact import validate_artifact_payload
from engine.errors import ToolInputError
from engine.models import DataSource, Project
from engine.tools.runtime import ToolRegistry, ToolRuntime
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.tools.builtin.registry import register_workspace_extension
from engine.tools.runtime.resource_context import (
    build_tool_scope_context,
    resolve_workspace_scope_ref,
)
from engine.workspace.read_service import WorkspaceReadService


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 39, 111, 107, 39, 41, 10]))
    registry = ToolRegistry()
    register_workspace_extension(registry)
    registry.freeze()
    service = WorkspaceReadService(root)
    return registry, service, ResourceScopeRef(
        kind="workspace",
        id="project-1",
        version="root-v1",
    )


def test_file_read_returns_bounded_snapshot_and_artifact(runtime) -> None:
    registry, service, scope = runtime
    result = ToolRuntime(registry).invoke(
        tool_name="file_read",
        raw_input={"path": "src/main.py"},
        request=None,
        idempotency_key="file-read-1",
        scope_refs=(scope,),
        resources={"workspace": service},
    )

    assert result.status == "success"
    assert result.output["path"] == "src/main.py"
    assert result.output["sha256"] == service.read_text_file("src/main.py").sha256
    assert len(result.artifact_drafts) == 1
    draft = result.artifact_drafts[0]
    assert draft.type == "dbfox.workspace.file_snapshot"
    assert draft.schema_version == 1
    assert draft.payload["relativePath"] == "src/main.py"


def test_file_search_lists_bounded_workspace_matches(runtime) -> None:
    registry, service, scope = runtime
    result = ToolRuntime(registry).invoke(
        tool_name="file_search",
        raw_input={"query": "main", "path_prefix": "src", "limit": 10},
        request=None,
        idempotency_key="file-search-1",
        scope_refs=(scope,),
        resources={"workspace": service},
    )

    assert result.status == "success"
    assert result.output["returned_count"] == 1
    assert result.output["matches"][0]["relative_path"] == "src/main.py"


def test_file_read_rejects_path_escape_with_safe_error(runtime) -> None:
    registry, service, scope = runtime
    result = ToolRuntime(registry).invoke(
        tool_name="file_read",
        raw_input={"path": "../outside.txt"},
        request=None,
        idempotency_key="file-read-2",
        scope_refs=(scope,),
        resources={"workspace": service},
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_INPUT_ERROR"
    assert result.error == "无法读取该项目文件。"


def test_file_snapshot_artifact_contract_is_registered() -> None:
    payload = validate_artifact_payload(
        "dbfox.workspace.file_snapshot",
        {
            "relativePath": "src/main.py",
            "sizeBytes": 12,
            "sha256": "a" * 64,
            "truncated": False,
        },
        schema_version=1,
    )
    assert payload["relativePath"] == "src/main.py"


def test_scope_context_resolves_authorized_workspace_from_project(
    db_session,
    tmp_path,
) -> None:
    project = Project(
        id="project-workspace",
        name="Workspace Project",
        workspace_root=str(tmp_path),
    )
    datasource = DataSource(
        id="ds-workspace",
        project_id=project.id,
        name="Workspace DS",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        connection_generation=3,
    )
    db_session.add_all([project, datasource])
    db_session.commit()

    registry = ToolRegistry()
    register_workspace_extension(registry)
    tool = registry.require("file_read")
    request = type(
        "Request",
        (),
        {"datasource_id": datasource.id, "datasource_generation": 3},
    )()
    scope_refs, resources = build_tool_scope_context(db_session, request, tool)

    # file_read only has filesystem capability, so it must not receive a
    # database scope or Session through the resource boundary.
    assert [ref.kind for ref in scope_refs] == ["workspace"]
    assert scope_refs[0].id == project.id
    assert resources["workspace"].root == tmp_path.resolve()


def test_scope_context_rejects_project_without_workspace_root(db_session) -> None:
    project = Project(id="project-no-root", name="No Root")
    datasource = DataSource(
        id="ds-no-root",
        project_id=project.id,
        name="No Root DS",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        connection_generation=1,
    )
    db_session.add_all([project, datasource])
    db_session.commit()

    registry = ToolRegistry()
    register_workspace_extension(registry)
    tool = registry.require("file_read")
    request = type(
        "Request",
        (),
        {"datasource_id": datasource.id, "datasource_generation": 1},
    )()
    with pytest.raises(ToolInputError, match="工作目录"):
        build_tool_scope_context(db_session, request, tool)


def test_scope_context_uses_frozen_resource_refs_without_datasource_id(
    db_session,
    tmp_path,
) -> None:
    project = Project(
        id="project-frozen-ws",
        name="Frozen WS Project",
        workspace_root=str(tmp_path),
    )
    db_session.add(project)
    db_session.commit()

    ws_ref = resolve_workspace_scope_ref(db_session, project_id=project.id)
    assert ws_ref is not None
    registry = ToolRegistry()
    register_workspace_extension(registry)
    tool = registry.require("file_read")

    # Request has NO datasource_id or datasource_generation, but has frozen_resource_refs
    request = type(
        "Request",
        (),
        {
            "datasource_id": None,
            "datasource_generation": 0,
            "frozen_resource_refs": (ws_ref,),
        },
    )()
    scope_refs, resources = build_tool_scope_context(db_session, request, tool)

    assert scope_refs == (ws_ref,)
    assert resources["workspace"].root == tmp_path.resolve()


def test_scope_context_matrix_legacy_derivation_when_frozen_refs_none(
    db_session,
    tmp_path,
) -> None:
    """A. frozen_resource_refs=None + datasource -> legacy Database/Workspace derivation still works."""
    from engine.tools.builtin.catalog import SchemaListTool

    project = Project(
        id="proj-legacy",
        name="Legacy Proj",
        workspace_root=str(tmp_path),
    )
    datasource = DataSource(
        id="ds-legacy",
        project_id=project.id,
        name="Legacy DS",
        db_type="sqlite",
        database_name=":memory:",
        connection_generation=1,
    )
    db_session.add_all([project, datasource])
    db_session.commit()

    registry = ToolRegistry()
    register_workspace_extension(registry)
    ws_tool = registry.require("file_read")
    db_tool = SchemaListTool()

    # Request has frozen_resource_refs=None
    request = type(
        "LegacyRequest",
        (),
        {
            "datasource_id": datasource.id,
            "datasource_generation": 1,
            "frozen_resource_refs": None,
        },
    )()

    # Legacy derivation derives database for db_tool
    db_scope_refs, db_res = build_tool_scope_context(db_session, request, db_tool)
    assert len(db_scope_refs) == 1
    assert db_scope_refs[0].kind == "database"
    assert db_scope_refs[0].id == datasource.id
    assert db_res["database"] is db_session

    # Legacy derivation derives workspace for ws_tool
    ws_scope_refs, ws_res = build_tool_scope_context(db_session, request, ws_tool)
    assert len(ws_scope_refs) == 1
    assert ws_scope_refs[0].kind == "workspace"
    assert ws_scope_refs[0].id == project.id
    assert ws_res["workspace"].root == tmp_path.resolve()


def test_scope_context_matrix_explicit_empty_rejects_both_tools(
    db_session,
    tmp_path,
) -> None:
    """B. frozen_resource_refs=() + datasource compatibility field -> Database Tool rejected, Workspace Tool rejected."""
    from engine.tools.builtin.catalog import SchemaListTool

    project = Project(
        id="proj-empty-auth",
        name="Empty Auth Proj",
        workspace_root=str(tmp_path),
    )
    datasource = DataSource(
        id="ds-empty-auth",
        project_id=project.id,
        name="Empty Auth DS",
        db_type="sqlite",
        database_name=":memory:",
        connection_generation=1,
    )
    db_session.add_all([project, datasource])
    db_session.commit()

    registry = ToolRegistry()
    register_workspace_extension(registry)
    ws_tool = registry.require("file_read")
    db_tool = SchemaListTool()

    # Request has explicit empty frozen_resource_refs=()
    request = type(
        "EmptyAuthRequest",
        (),
        {
            "datasource_id": datasource.id,
            "datasource_generation": 1,
            "frozen_resource_refs": (),
        },
    )()

    with pytest.raises(ToolInputError, match="没有授权的数据库"):
        build_tool_scope_context(db_session, request, db_tool)

    with pytest.raises(ToolInputError, match="没有已授权的本地工作目录"):
        build_tool_scope_context(db_session, request, ws_tool)


def test_scope_context_matrix_database_only_rejects_workspace_without_expansion(
    db_session,
    tmp_path,
) -> None:
    """C. frozen_resource_refs=(database_ref,) -> Database Tool works, Workspace Tool rejected without authority expansion."""
    from engine.tools.builtin.catalog import SchemaListTool

    project = Project(
        id="proj-db-only",
        name="DB Only Proj",
        workspace_root=str(tmp_path),
    )
    datasource = DataSource(
        id="ds-db-only",
        project_id=project.id,
        name="DB Only DS",
        db_type="sqlite",
        database_name=":memory:",
        connection_generation=2,
    )
    db_session.add_all([project, datasource])
    db_session.commit()

    db_ref = ResourceScopeRef(kind="database", id=datasource.id, version=2)

    registry = ToolRegistry()
    register_workspace_extension(registry)
    ws_tool = registry.require("file_read")
    db_tool = SchemaListTool()

    request = type(
        "DbOnlyRequest",
        (),
        {
            "datasource_id": datasource.id,
            "datasource_generation": 2,
            "frozen_resource_refs": (db_ref,),
        },
    )()

    # Database tool resolves exact db ref
    scope_refs, res = build_tool_scope_context(db_session, request, db_tool)
    assert scope_refs == (db_ref,)
    assert res["database"] is db_session

    # Workspace tool MUST be rejected even though datasource belongs to project with workspace_root
    with pytest.raises(ToolInputError, match="没有已授权的本地工作目录"):
        build_tool_scope_context(db_session, request, ws_tool)


def test_scope_context_matrix_workspace_only_rejects_database(
    db_session,
    tmp_path,
) -> None:
    """D. frozen_resource_refs=(workspace_ref,) -> Workspace Tool works, Database Tool rejected."""
    from engine.tools.builtin.catalog import SchemaListTool

    project = Project(
        id="proj-ws-only-matrix",
        name="WS Only Matrix",
        workspace_root=str(tmp_path),
    )
    db_session.add(project)
    db_session.commit()

    ws_ref = resolve_workspace_scope_ref(db_session, project_id=project.id)
    assert ws_ref is not None

    registry = ToolRegistry()
    register_workspace_extension(registry)
    ws_tool = registry.require("file_read")
    db_tool = SchemaListTool()

    request = type(
        "WsOnlyRequest",
        (),
        {
            "datasource_id": "compat-ds",
            "datasource_generation": 1,
            "frozen_resource_refs": (ws_ref,),
        },
    )()

    # Workspace tool works
    scope_refs, res = build_tool_scope_context(db_session, request, ws_tool)
    assert scope_refs == (ws_ref,)
    assert res["workspace"].root == tmp_path.resolve()

    # Database tool rejected
    with pytest.raises(ToolInputError, match="没有授权的数据库"):
        build_tool_scope_context(db_session, request, db_tool)


def test_scope_context_matrix_both_resources_resolve_exact_subsets(
    db_session,
    tmp_path,
) -> None:
    """E. frozen_resource_refs=(database_ref, workspace_ref) -> both tools resolve exact subsets."""
    from engine.tools.builtin.catalog import SchemaListTool

    project = Project(
        id="proj-both",
        name="Both Proj",
        workspace_root=str(tmp_path),
    )
    datasource = DataSource(
        id="ds-both",
        project_id=project.id,
        name="Both DS",
        db_type="sqlite",
        database_name=":memory:",
        connection_generation=3,
    )
    db_session.add_all([project, datasource])
    db_session.commit()

    ws_ref = resolve_workspace_scope_ref(db_session, project_id=project.id)
    assert ws_ref is not None
    db_ref = ResourceScopeRef(kind="database", id=datasource.id, version=3)

    registry = ToolRegistry()
    register_workspace_extension(registry)
    ws_tool = registry.require("file_read")
    db_tool = SchemaListTool()

    request = type(
        "BothRequest",
        (),
        {
            "datasource_id": datasource.id,
            "datasource_generation": 3,
            "frozen_resource_refs": (db_ref, ws_ref),
        },
    )()

    # Database tool gets only database ref
    db_scope, db_res = build_tool_scope_context(db_session, request, db_tool)
    assert db_scope == (db_ref,)
    assert "database" in db_res
    assert "workspace" not in db_res

    # Workspace tool gets only workspace ref
    ws_scope, ws_res = build_tool_scope_context(db_session, request, ws_tool)
    assert ws_scope == (ws_ref,)
    assert "workspace" in ws_res
    assert "database" not in ws_res


