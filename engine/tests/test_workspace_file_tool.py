"""P7 Workspace file_read Tool contract tests."""

from __future__ import annotations

import pytest

from engine.agent.artifact import validate_artifact_payload
from engine.errors import ToolInputError
from engine.models import DataSource, Project
from engine.tools.runtime import ToolRegistry, ToolRuntime
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.tools.builtin.registry import register_workspace_extension
from engine.tools.runtime.resource_context import build_tool_scope_context
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
        db=None,
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


def test_file_read_rejects_path_escape_with_safe_error(runtime) -> None:
    registry, service, scope = runtime
    result = ToolRuntime(registry).invoke(
        tool_name="file_read",
        raw_input={"path": "../outside.txt"},
        request=None,
        db=None,
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

    assert [ref.kind for ref in scope_refs] == ["database", "workspace"]
    assert scope_refs[0].version == 3
    assert scope_refs[1].id == project.id
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
