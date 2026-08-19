"""Comprehensive tests for P5: Tool Resource Prerequisite contract and materialization."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.definition import AgentDefinition
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.tool_dispatcher import ToolRequest
from engine.errors import ToolInputError
from engine.models import AgentSession, DataSource, Project
from engine.runtime_composition import build_product_tool_registry
from engine.tools.materialization import (
    current_tool_contract_hash,
    materialize_tools,
)
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRegistry,
    ToolRunContext,
)
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.tools.runtime.resource_context import (
    build_tool_scope_context,
    legacy_available_resource_kinds,
)


class _DummyInput(ToolInputModel):
    text: str = ""


class _DummyOutput(ToolOutputModel):
    result: str = ""


class _ProbeTool(BaseTool[_DummyInput, _DummyOutput]):
    name = "probe_tool"
    group = "test"
    description = "Probe tool for orthogonality testing"
    input_model = _DummyInput
    output_model = _DummyOutput
    presentation = ToolPresentation(title="Probe", category="explore")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec()

    def run(self, tool_input: _DummyInput, context: ToolRunContext) -> _DummyOutput:
        return _DummyOutput(result="ok")


# ==============================================================================
# A. Materialization Matrix
# ==============================================================================


def test_materialization_empty_available_resources() -> None:
    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset(),
    )
    names = {tool.name for tool in materialized.tools}

    # DB tools must be absent
    assert "catalog_overview" not in names
    assert "catalog_refresh" not in names
    assert "schema_list" not in names
    assert "schema_search" not in names
    assert "schema_inspect" not in names
    assert "data_preview" not in names
    assert "sql_validate" not in names
    assert "sql_execute_readonly" not in names
    assert "result_inspect" not in names
    assert "result_profile" not in names
    assert "chart_create" not in names

    # Workspace tools must be absent
    assert "file_read" not in names
    assert "file_search" not in names
    assert "file_write_patch" not in names

    # Resource-free tools (metadata kernel tools and generic tools) must remain
    assert "request_clarification" in names
    assert "update_plan" in names
    assert "remote_job_submit" in names
    assert "conversation_search" in names
    assert "conversation_read" in names
    assert "remote_job_status" in names
    assert "remote_job_cancel" in names


def test_materialization_database_only() -> None:
    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"database"}),
    )
    names = {tool.name for tool in materialized.tools}

    # DB tools must be present
    assert "catalog_overview" in names
    assert "catalog_refresh" in names
    assert "schema_list" in names
    assert "schema_search" in names
    assert "schema_inspect" in names
    assert "data_preview" in names
    assert "sql_validate" in names
    assert "sql_execute_readonly" in names
    assert "result_inspect" in names
    assert "result_profile" in names
    assert "chart_create" in names

    # Workspace tools must be absent
    assert "file_read" not in names
    assert "file_search" not in names
    assert "file_write_patch" not in names

    # Resource-free tools must be present
    assert "request_clarification" in names
    assert "update_plan" in names
    assert "remote_job_submit" in names
    assert "conversation_search" in names
    assert "conversation_read" in names
    assert "remote_job_status" in names
    assert "remote_job_cancel" in names


def test_materialization_workspace_only() -> None:
    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"workspace"}),
    )
    names = {tool.name for tool in materialized.tools}

    # DB tools must be absent
    assert "catalog_overview" not in names
    assert "sql_execute_readonly" not in names
    assert "data_preview" not in names
    assert "result_inspect" not in names
    assert "chart_create" not in names

    # Workspace tools must be present
    assert "file_read" in names
    assert "file_search" in names
    assert "file_write_patch" in names

    # Resource-free tools must be present
    assert "request_clarification" in names
    assert "update_plan" in names
    assert "remote_job_submit" in names
    assert "conversation_search" in names
    assert "conversation_read" in names
    assert "remote_job_status" in names
    assert "remote_job_cancel" in names


def test_materialization_both_database_and_workspace() -> None:
    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"database", "workspace"}),
    )
    names = {tool.name for tool in materialized.tools}

    # Both families must be present
    assert "catalog_overview" in names
    assert "sql_execute_readonly" in names
    assert "file_read" in names
    assert "file_search" in names
    assert "file_write_patch" in names
    assert "request_clarification" in names
    assert "update_plan" in names


def test_materialization_none_available_resources_unconstrained() -> None:
    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=None,
    )
    names = {tool.name for tool in materialized.tools}
    # When None, no resource-kind filtering occurs (legacy/unconstrained)
    assert "catalog_overview" in names
    assert "file_read" in names
    assert "request_clarification" in names


# ==============================================================================
# B. Orthogonality: Security Capability != Resource Requirement
# ==============================================================================


def test_orthogonality_capability_without_resource_requirement() -> None:
    """A tool with filesystem_read capability but required_resource_kinds=() does not require workspace."""
    class CustomProbeTool(_ProbeTool):
        name = "custom_filesystem_read_no_res"
        execution = ToolExecutionSpec(
            capabilities=("filesystem_read",),
            required_resource_kinds=(),
        )

    reg = ToolRegistry()
    reg.register(CustomProbeTool(), owner="test")

    # When available resources has only 'database', this tool is still materialized because it requires ()
    materialized = materialize_tools(
        reg,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"database"}),
    )
    assert len(materialized.tools) == 1
    assert materialized.tools[0].name == "custom_filesystem_read_no_res"


def test_orthogonality_resource_requirement_without_capability() -> None:
    """A tool with capabilities=() but required_resource_kinds=('workspace',) requires workspace."""
    class CustomProbeTool(_ProbeTool):
        name = "custom_workspace_req_no_cap"
        execution = ToolExecutionSpec(
            capabilities=(),
            required_resource_kinds=("workspace",),
        )

    reg = ToolRegistry()
    reg.register(CustomProbeTool(), owner="test")

    # Absent when available is database only
    db_only = materialize_tools(
        reg,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"database"}),
    )
    assert len(db_only.tools) == 0

    # Present when available is workspace
    ws_avail = materialize_tools(
        reg,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"workspace"}),
    )
    assert len(ws_avail.tools) == 1
    assert ws_avail.tools[0].name == "custom_workspace_req_no_cap"


# ==============================================================================
# C. P4 Frozen Authority and Scope Context Resolution
# ==============================================================================


def test_scope_context_exact_subset_resolution(db_session) -> None:
    registry = build_product_tool_registry()
    db_tool = registry.require("catalog_overview")
    ws_tool = registry.require("file_read")
    free_tool = registry.require("remote_job_submit")

    db_ref = ResourceScopeRef(kind="database", id="ds-1", version=1)
    ws_ref = ResourceScopeRef(kind="workspace", id="p-1", version="hash123")

    db = db_session
    if True:
        # 1. DB-only request
        req_db = ToolRequest(
            datasource_id="ds-1",
            datasource_generation=1,
            question="test",
            session_id="s-1",
            run_id="r-1",
            execution_id="e-1",
            execution_mode="agent_autonomous_read",
            frozen_resource_refs=(db_ref,),
        )
        scopes, resources = build_tool_scope_context(db, req_db, db_tool)
        assert scopes == (db_ref,)
        assert "database" in resources
        assert "workspace" not in resources

        # Trying to execute workspace tool on DB-only request fails
        with pytest.raises(ToolInputError, match="没有已授权的本地工作目录"):
            build_tool_scope_context(db, req_db, ws_tool)

        # Executing resource-free tool on DB-only request succeeds with empty subset
        scopes_free, resources_free = build_tool_scope_context(db, req_db, free_tool)
        assert scopes_free == ()
        assert resources_free == {}

        # 2. Workspace-only request
        req_ws = ToolRequest(
            datasource_id=None,
            datasource_generation=0,
            question="test",
            session_id="s-1",
            run_id="r-1",
            execution_id="e-1",
            execution_mode="agent_autonomous_read",
            frozen_resource_refs=(ws_ref,),
        )
        # Trying to execute database tool on WS-only request fails
        with pytest.raises(ToolInputError, match="没有授权的数据库"):
            build_tool_scope_context(db, req_ws, db_tool)

        # 3. Explicit zero-resource request
        req_zero = ToolRequest(
            datasource_id=None,
            datasource_generation=0,
            question="test",
            session_id="s-1",
            run_id="r-1",
            execution_id="e-1",
            execution_mode="agent_autonomous_read",
            frozen_resource_refs=(),
        )
        with pytest.raises(ToolInputError, match="没有授权的数据库"):
            build_tool_scope_context(db, req_zero, db_tool)
        with pytest.raises(ToolInputError, match="没有已授权的本地工作目录"):
            build_tool_scope_context(db, req_zero, ws_tool)

        scopes_zero_free, res_zero_free = build_tool_scope_context(db, req_zero, free_tool)
        assert scopes_zero_free == ()
        assert res_zero_free == {}


# ==============================================================================
# D. Contract Hash Independence & Validation
# ==============================================================================


def test_contract_hash_differs_when_required_resource_kinds_change() -> None:
    class ToolA(_ProbeTool):
        name = "probe"
        execution = ToolExecutionSpec(
            capabilities=("database_read",),
            required_resource_kinds=(),
        )

    class ToolB(_ProbeTool):
        name = "probe"
        execution = ToolExecutionSpec(
            capabilities=("database_read",),
            required_resource_kinds=("database",),
        )

    hash_a = current_tool_contract_hash(ToolA())
    hash_b = current_tool_contract_hash(ToolB())
    assert hash_a != hash_b
    assert hash_a.startswith("sha256:")
    assert hash_b.startswith("sha256:")


def test_required_resource_kinds_validation() -> None:
    # Non-empty strings
    with pytest.raises(ValueError, match="non-empty string"):
        ToolExecutionSpec(required_resource_kinds=("",))

    with pytest.raises(ValueError, match="non-empty string"):
        ToolExecutionSpec(required_resource_kinds=("   ",))

    # Length <= 64
    with pytest.raises(ValueError, match="cannot exceed 64 characters"):
        ToolExecutionSpec(required_resource_kinds=("a" * 65,))

    # No duplicates
    with pytest.raises(ValueError, match="duplicates"):
        ToolExecutionSpec(required_resource_kinds=("database", "database"))

    # Max 8 items
    with pytest.raises(ValueError, match="cannot exceed 8 items"):
        ToolExecutionSpec(required_resource_kinds=tuple(f"kind_{i}" for i in range(9)))

    # Valid
    spec = ToolExecutionSpec(required_resource_kinds=("database", "workspace", "custom"))
    assert spec.required_resource_kinds == ("database", "workspace", "custom")


# ==============================================================================
# E. Production-shaped RunLoop Turn Preparation
# ==============================================================================


def test_run_loop_turn_preparation_filters_tools_by_input_frozen_refs(
    tmp_path,
    db_session,
) -> None:
    db = db_session
    # Create Project
    project = Project(
        name="P5 Test Project",
        workspace_root=str(tmp_path),
    )
    db.add(project)
    db.flush()

    # Create Session
    session = AgentSession(
        project_id=project.id,
        datasource_id=None,
        title="P5 Turn Materialization Session",
    )
    db.add(session)
    db.flush()

    sessions = SessionRepository(db)
    ws_ref = ResourceScopeRef(kind="workspace", id=str(project.id), version="v1")
    admission = sessions.admit(
        session_id=str(session.id),
        resource_refs=(ws_ref,),
        content="Read workspace file",
        idempotency_key="req_ws_1",
        llm_credential_id="cred_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "Read workspace file"},
    )
    db.commit()

    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    all_groups_def = AgentDefinition(
        allowed_tool_groups=(
            "control",
            "conversation",
            "catalog",
            "query",
            "result",
            "workspace",
            "remote_job",
        )
    )
    run_loop = RunLoop(
        session_factory=factory,
        registry=build_product_tool_registry(),
        definition=all_groups_def,
    )

    lease = sessions.claim(session_id=str(session.id), owner="worker", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db.commit()
    prepared_turn = run_loop._prepare_turn(lease, str(admission.run_id))

    tool_names = {t.name for t in prepared_turn.tools.tools}
    # Workspace tools must be present
    assert "file_read" in tool_names
    assert "file_search" in tool_names
    assert "file_write_patch" in tool_names
    # Database tools must be absent
    assert "catalog_overview" not in tool_names
    assert "sql_validate" not in tool_names
    assert "sql_execute_readonly" not in tool_names
    assert "data_preview" not in tool_names


def test_run_loop_turn_preparation_zero_resources_filters_all_resource_tools(
    tmp_path,
    db_session,
) -> None:
    db = db_session
    project = Project(
        name="P5 Zero Resource Project",
        workspace_root=str(tmp_path),
    )
    db.add(project)
    db.flush()

    session = AgentSession(
        project_id=project.id,
        datasource_id=None,
        title="P5 Zero Resource Session",
    )
    db.add(session)
    db.flush()

    sessions = SessionRepository(db)
    admission = sessions.admit(
        session_id=str(session.id),
        resource_refs=(),
        content="Chat only without any resource",
        idempotency_key="req_zero_1",
        llm_credential_id="cred_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "Chat only without any resource"},
    )
    db.commit()

    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    all_groups_def = AgentDefinition(
        allowed_tool_groups=(
            "control",
            "conversation",
            "catalog",
            "query",
            "result",
            "workspace",
            "remote_job",
        )
    )
    run_loop = RunLoop(
        session_factory=factory,
        registry=build_product_tool_registry(),
        definition=all_groups_def,
    )

    lease = sessions.claim(session_id=str(session.id), owner="worker", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db.commit()
    prepared_turn = run_loop._prepare_turn(lease, str(admission.run_id))

    tool_names = {t.name for t in prepared_turn.tools.tools}
    # Neither database nor workspace tools appear
    assert "catalog_overview" not in tool_names
    assert "sql_validate" not in tool_names
    assert "file_read" not in tool_names
    assert "file_search" not in tool_names
    # Only resource-free tools appear
    assert "request_clarification" in tool_names
    assert "update_plan" in tool_names
    assert "remote_job_submit" in tool_names
    assert "conversation_search" in tool_names
    assert "conversation_read" in tool_names
    assert "remote_job_status" in tool_names
    assert "remote_job_cancel" in tool_names


# ==============================================================================
# F. P5.1: Core Metadata Store Separation & Legacy Consistency
# ==============================================================================


def test_conversation_tools_available_and_executable_in_workspace_only_session(
    tmp_path,
    db_session,
) -> None:
    db = db_session
    project = Project(
        name="Workspace Only Project",
        workspace_root=str(tmp_path),
    )
    db.add(project)
    db.flush()

    session = AgentSession(
        project_id=project.id,
        datasource_id=None,
        title="Workspace Only Session",
    )
    db.add(session)
    db.flush()

    sessions = SessionRepository(db)
    # Add a user message to recall
    sessions.admit(
        session_id=str(session.id),
        resource_refs=(ResourceScopeRef(kind="workspace", id=str(project.id), version="v1"),),
        content="hello database-free conversation recall",
        idempotency_key="admit_ws_conv",
        llm_credential_id="cred_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "hello database-free conversation recall"},
    )
    db.commit()

    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset({"workspace"}),
    )
    names = {t.name for t in materialized.tools}
    # Conversation search and read MUST be visible
    assert "conversation_search" in names
    assert "conversation_read" in names

    # Execute conversation_search using metadata_session (WITHOUT database resource)
    search_tool = registry.require("conversation_search")
    from engine.tools.builtin.contracts import ConversationSearchInput
    from types import SimpleNamespace

    req = SimpleNamespace(
        datasource_id="",
        datasource_generation=0,
        question="search",
        session_id=str(session.id),
        run_id="run_1",
        turn_id="turn_1",
        execution_id="exec_1",
    )
    ctx = ToolRunContext.for_invocation(
        request=req,
        idempotency_key="search_key",
        metadata_session=db,
        resources={},  # No database resource!
    )
    res = search_tool.run(
        ConversationSearchInput(query="hello"),
        ctx,
    )
    assert res.returned_count >= 1
    assert any("hello" in m.snippet for m in res.matches)


def test_remote_job_lifecycle_in_zero_resource_session(
    tmp_path,
    db_session,
) -> None:
    db = db_session
    project = Project(
        name="Zero Resource Project",
        workspace_root=str(tmp_path),
    )
    db.add(project)
    db.flush()

    session = AgentSession(
        project_id=project.id,
        datasource_id=None,
        title="Zero Resource Session",
    )
    db.add(session)
    db.flush()

    sessions = SessionRepository(db)
    admission = sessions.admit(
        session_id=str(session.id),
        resource_refs=(),
        content="submit remote job",
        idempotency_key="admit_rj_0",
        llm_credential_id="cred_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "submit remote job"},
    )
    db.commit()

    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=frozenset(),
    )
    names = {t.name for t in materialized.tools}
    assert "remote_job_submit" in names
    assert "remote_job_status" in names
    assert "remote_job_cancel" in names

    from types import SimpleNamespace
    from engine.tools.builtin.remote_job import (
        RemoteJobSubmitInput,
        RemoteJobStatusInput,
        RemoteJobCancelInput,
    )

    req = SimpleNamespace(
        datasource_id="",
        datasource_generation=0,
        question="run remote job",
        session_id=str(session.id),
        run_id=str(admission.run_id),
        turn_id=None,
        execution_id="exec_rj_1",
    )
    submit_tool = registry.require("remote_job_submit")
    status_tool = registry.require("remote_job_status")
    cancel_tool = registry.require("remote_job_cancel")

    ctx = ToolRunContext.for_invocation(
        request=req,
        idempotency_key="rj_key_1",
        metadata_session=db,
        resources={},  # No database resource!
    )
    # 1. Submit
    outcome = submit_tool.run(
        RemoteJobSubmitInput(command="python test.py"),
        ctx,
    )
    job_id = outcome.output.job_id
    assert job_id

    # Persist the drafted artifact record to the session DB for status/cancel lookup
    from engine.models import AgentArtifactRecord
    import json
    for draft in outcome.artifacts:
        rec = AgentArtifactRecord(
            session_id=str(session.id),
            run_id=str(admission.run_id),
            turn_id=None,
            type=draft.type,
            schema_version=draft.schema_version,
            title=draft.title,
            payload_json=json.dumps(draft.payload),
            presentation_json="{}",
            semantic_id=draft.semantic_key,
            summary=draft.summary,
            version=1,
        )
        db.add(rec)
    db.commit()

    # 2. Status check
    status_out = status_tool.run(
        RemoteJobStatusInput(job_id=job_id),
        ctx,
    )
    assert status_out.job_id == job_id
    assert status_out.status in {"queued", "submitted", "running", "succeeded"}

    # 3. Cancel
    cancel_outcome = cancel_tool.run(
        RemoteJobCancelInput(job_id=job_id),
        ctx,
    )
    assert cancel_outcome.output.status == "cancelled"


def test_legacy_materialization_and_execution_consistency_with_workspace(
    tmp_path,
    db_session,
) -> None:
    db = db_session
    # Project with valid workspace
    project = Project(
        name="Legacy WS Project",
        workspace_root=str(tmp_path),
    )
    db.add(project)
    db.flush()

    ds = DataSource(
        name="Legacy DS",
        db_type="sqlite",
        database_name="test.db",
        project_id=project.id,
    )
    db.add(ds)
    db.flush()

    # Derived kinds must be {"database", "workspace"}
    derived = legacy_available_resource_kinds(db, str(ds.id))
    assert derived == frozenset({"database", "workspace"})

    # Legacy execution scope context resolution:
    # 1. Database tool resolves database
    registry = build_product_tool_registry()
    db_tool = registry.require("catalog_overview")
    ws_tool = registry.require("file_read")

    from types import SimpleNamespace
    legacy_req = SimpleNamespace(
        datasource_id=str(ds.id),
        datasource_generation=1,
        question="legacy test",
        session_id="leg_sess_1",
        run_id="leg_run_1",
        execution_id="leg_exec_1",
        frozen_resource_refs=None,  # Legacy pre-P4
    )

    db_scopes, db_res = build_tool_scope_context(db, legacy_req, db_tool)
    assert len(db_scopes) == 1
    assert db_scopes[0].kind == "database"
    assert "database" in db_res

    # 2. Workspace tool resolves workspace from project
    ws_scopes, ws_res = build_tool_scope_context(db, legacy_req, ws_tool)
    assert len(ws_scopes) == 1
    assert ws_scopes[0].kind == "workspace"
    assert "workspace" in ws_res


def test_legacy_materialization_without_project_workspace(
    db_session,
) -> None:
    db = db_session
    # Project without workspace root
    project = Project(
        name="Legacy No-WS Project",
        workspace_root=None,
    )
    db.add(project)
    db.flush()

    ds = DataSource(
        name="Legacy No-WS DS",
        db_type="sqlite",
        database_name="test.db",
        project_id=project.id,
    )
    db.add(ds)
    db.flush()

    # Derived kinds must be only {"database"}
    derived = legacy_available_resource_kinds(db, str(ds.id))
    assert derived == frozenset({"database"})

    registry = build_product_tool_registry()
    materialized = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds=derived,
    )
    names = {t.name for t in materialized.tools}
    assert "catalog_overview" in names
    assert "file_read" not in names
    assert "file_search" not in names
