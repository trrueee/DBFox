"""Production-shaped Capability DLC Conformance Tests for Data and Workspace (P8/P8.1).

Verifies the complete end-to-end DLC chain for both built-in capabilities:
1. ResourceRef -> Tool Materialization -> Execution -> Observation -> Artifact -> Context / Completion.
2. Frozen selected artifact semantics per admitted input.
3. Freshness fences (SHA256 & canonical version on workspace, generation on data).
4. Full ContextAssembler composition and isolation (no user database resource required for workspace).
5. Resource authority isolation (database vs workspace).
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.completion import CompletionGate
from engine.agent.context import ContextAssembler
from engine.agent.context_fragment import ContextContributionInput
from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.turn import ModelToolCall
from engine.errors import ToolInputError
from engine.models import (
    AgentArtifactRecord,
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    Project,
)
from engine.runtime_composition import (
    build_default_completion_policy,
    build_product_tool_registry,
    default_context_contributors,
)
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import ToolExecutor
from engine.tests.workspace_test_support import (
    legacy_workspace_resolver,
    registry_with_legacy_workspace,
)
from engine.tools.runtime.attempt import ResourceScopeRef

# Retired Core-only tests below remain as migration history until this file is
# split; their package-owned replacements live in test_dbfox_workspace_dlc_package.
WorkspaceContextContributor = object


def test_data_dlc_production_conformance(db_session, test_datasource) -> None:
    """Prove the complete Data DLC chain:

    Resource -> Tool materialization -> Tool execution -> Observation -> Artifact ->
    Frozen selected Artifact -> Next Run Context -> Completion constraint.
    """
    # 1. Setup project and database
    project_id = "project-data-dlc"
    db_session.add(Project(id=project_id, name="Data DLC Project"))
    db_session.flush()
    test_datasource.project_id = project_id
    db_session.flush()

    session_id = "session-data-dlc"
    db_session.add(
        AgentSession(
            id=session_id,
            project_id=project_id,
            title="Data DLC Session",
        )
    )
    db_session.commit()

    # 2. Database-only input admission
    registry = build_product_tool_registry()
    db_ref = ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version=1)

    sessions = SessionRepository(db_session)
    first_admission = sessions.admit(
        session_id=session_id,
        resource_refs=(db_ref,),
        content="查询测试数据",
        idempotency_key="data-input-1",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="conformance-worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    # 3. Tool materialization: Only database tools visible, workspace tools absent
    definition = AgentDefinition(
        allowed_tool_groups=("data", "database", "query", "catalog"),
        execution_mode="agent_autonomous_read",
    )
    materialized = materialize_tools(
        registry,
        execution_mode=definition.execution_mode,
        available_resource_kinds=frozenset({"dbfox.data.database"}),
    )
    materialized_names = {t.name for t in materialized.tools}
    assert "sql_validate" in materialized_names
    assert "sql_execute_readonly" in materialized_names
    assert "schema_inspect" in materialized_names
    assert "file_read" not in materialized_names
    assert "file_search" not in materialized_names

    # 4. Tool execution via ToolDispatcher: Step 4a - sql_validate
    turn = sessions.start_turn(
        lease=lease,
        run_id=first_admission.run_id,
        agent_definition_version=definition.version,
        prompt_version="test",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=materialized.model_dump(mode="json"),
        tool_materialization_hash=materialized.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    executor = ToolExecutor(max_workers=1)
    dispatcher = ToolDispatcher(
        session_factory=factory,
        registry=registry,
        definition=definition,
        executor=executor,
        resource_resolver=legacy_workspace_resolver(db_session),
    )
    run = db_session.get(AgentRun, first_admission.run_id)
    assert run is not None
    control = LeaseAwareRunControl(
        run=run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=lambda: False,
    )

    validate_call = ModelToolCall(
        id=f"call_{uuid4().hex[:8]}",
        name="sql_validate",
        arguments={"sql": "SELECT 42 as answer, 'dbfox' as product"},
    )
    outcome_validate = dispatcher.request_and_execute(
        lease=lease,
        run_id=first_admission.run_id,
        turn_id=str(turn.id),
        call=validate_call,
        materialization=materialized,
        control=control,
    )
    assert outcome_validate.outcome is ToolDispatchOutcome.SETTLED

    sql_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(session_id=session_id, type="sql")
        .first()
    )
    assert sql_artifact is not None

    # Step 4b - sql_execute_readonly with validation_artifact_id
    execute_call = ModelToolCall(
        id=f"call_{uuid4().hex[:8]}",
        name="sql_execute_readonly",
        arguments={"validation_artifact_id": sql_artifact.id},
    )
    try:
        outcome_exec = dispatcher.request_and_execute(
            lease=lease,
            run_id=first_admission.run_id,
            turn_id=str(turn.id),
            call=execute_call,
            materialization=materialized,
            control=control,
        )
    finally:
        executor.close(wait=False)

    assert outcome_exec.outcome is ToolDispatchOutcome.SETTLED

    # 5. Verify durable Observation and Artifacts
    obs = (
        db_session.query(AgentObservationRecord)
        .filter_by(run_id=first_admission.run_id)
        .order_by(AgentObservationRecord.created_at.desc())
        .first()
    )
    assert obs is not None
    assert obs.status == "succeeded"

    artifacts = (
        db_session.query(AgentArtifactRecord)
        .filter_by(session_id=session_id)
        .order_by(AgentArtifactRecord.created_at.asc())
        .all()
    )
    types = [a.type for a in artifacts]
    assert "sql" in types
    assert "result_view" in types

    result_artifact = next(a for a in artifacts if a.type == "result_view")
    payload = json.loads(result_artifact.payload_json)
    assert payload["rowCount"] == 1
    assert "answer" in payload["columns"]

    # 6. Next Run: Admit second input with selected_artifact_ids
    second_admission = sessions.admit(
        session_id=session_id,
        resource_refs=(db_ref,),
        content="解释刚才的结果",
        idempotency_key="data-input-2",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
        selected_artifact_ids=[result_artifact.id],
    )
    db_session.commit()

    # 7. Frozen Selection Invariant: Mutating session.selected_artifact_id does NOT affect second Run
    session_row = db_session.get(AgentSession, session_id)
    session_row.selected_artifact_id = "different-mutated-artifact-id"
    db_session.commit()

    assembler = ContextAssembler(db_session, contributors=default_context_contributors())
    snapshot = assembler.build(second_admission.run_id)

    assert len(snapshot.selected_artifacts) == 1
    assert snapshot.selected_artifacts[0].id == result_artifact.id
    assert snapshot.selected_artifacts[0].descriptor["rowCount"] == 1

    # 8. Zero-resource input: Data tools do NOT materialize
    zero_mat = materialize_tools(registry, execution_mode="agent_autonomous_read", available_resource_kinds=frozenset())
    assert "sql_execute_readonly" not in {t.name for t in zero_mat.tools}

    # 9. Data Completion Policy check
    policy = build_default_completion_policy()
    assert CompletionGate(policy) is not None
    assert {item.id for item in policy.supports} == {"dbfox.data.query_result"}
    assert {item.id for item in policy.constraints} == {"dbfox.data.result_citation"}


@pytest.mark.skip(
    reason="superseded by signed dbfox.workspace package conformance"
)
def test_workspace_dlc_production_conformance(db_session, tmp_path) -> None:
    """Prove the complete Workspace DLC chain:

    Project (no user datasource required) -> Workspace ResourceRef -> Tool materialization ->
    file_read real Tool -> Succeeded Observation -> file_snapshot Artifact ->
    ContextAssembler + WorkspaceContextContributor -> Freshness fences (SHA & version) -> Database independence.
    """
    # 1. Setup workspace project without user datasource
    workspace_root = tmp_path / "ws_conformance"
    (workspace_root / "src").mkdir(parents=True)
    file_path = workspace_root / "src" / "service.py"
    initial_content = "def calculate_total(items):\n    return sum(item.price for item in items)\n"
    file_path.write_bytes(initial_content.encode("utf-8"))

    project_id = "project-ws-dlc"
    db_session.add(
        Project(
            id=project_id,
            name="Workspace DLC Project",
        )
    )
    db_session.flush()

    session_id = "session-ws-dlc"
    db_session.add(
        AgentSession(
            id=session_id,
            project_id=project_id,
            title="Workspace Pure Session",
        )
    )
    db_session.commit()

    # 2. Workspace ResourceRef and input admission
    ws_version = hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()[:16]
    ws_ref = ResourceScopeRef(kind="workspace", id=project_id, version=ws_version)

    sessions = SessionRepository(db_session)
    first_admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ws_ref,),
        content="查看 service.py 内容",
        idempotency_key="ws-input-1",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="conformance-worker-ws")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    # 3. Tool materialization: Workspace tools visible, Database tools absent
    definition = AgentDefinition(
        allowed_tool_groups=("workspace",),
        execution_mode="agent_autonomous_read",
    )
    registry = registry_with_legacy_workspace()
    materialized = materialize_tools(
        registry,
        execution_mode=definition.execution_mode,
        available_resource_kinds=frozenset({"workspace"}),
    )
    materialized_names = {t.name for t in materialized.tools}
    assert "file_read" in materialized_names
    assert "file_search" in materialized_names
    assert "sql_execute_readonly" not in materialized_names
    assert "schema_inspect" not in materialized_names

    # 4. Execute file_read tool via ToolDispatcher
    turn = sessions.start_turn(
        lease=lease,
        run_id=first_admission.run_id,
        agent_definition_version=definition.version,
        prompt_version="test",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=materialized.model_dump(mode="json"),
        tool_materialization_hash=materialized.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    executor = ToolExecutor(max_workers=1)
    dispatcher = ToolDispatcher(
        session_factory=factory,
        registry=registry,
        definition=definition,
        executor=executor,
        resource_resolver=legacy_workspace_resolver(db_session),
    )
    run = db_session.get(AgentRun, first_admission.run_id)
    assert run is not None
    control = LeaseAwareRunControl(
        run=run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=lambda: False,
    )
    call = ModelToolCall(
        id=f"call_{uuid4().hex[:8]}",
        name="file_read",
        arguments={"path": "src/service.py"},
    )
    outcome = dispatcher.request_and_execute(
        lease=lease,
        run_id=first_admission.run_id,
        turn_id=str(turn.id),
        call=call,
        materialization=materialized,
        control=control,
    )
    assert outcome.outcome is ToolDispatchOutcome.SETTLED

    # 5. Verify Observation & file_snapshot Artifact
    obs = db_session.query(AgentObservationRecord).filter_by(run_id=first_admission.run_id).first()
    assert obs is not None
    assert "dbfox.workspace.file_snapshot" in json.loads(obs.semantic_capabilities_json)

    artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(session_id=session_id, type="dbfox.workspace.file_snapshot")
        .first()
    )
    assert artifact is not None
    payload = json.loads(artifact.payload_json)
    assert payload["relativePath"] == "src/service.py"
    assert payload["sha256"] == hashlib.sha256(initial_content.encode("utf-8")).hexdigest()

    # 6. Subsequent Run: ContextAssembler + WorkspaceContextContributor rehydrate file snapshot
    second_admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ws_ref,),
        content="继续重构",
        idempotency_key="ws-input-2",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
    )
    db_session.commit()

    # 6a: Verify WorkspaceContextContributor directly
    contributor = WorkspaceContextContributor(db_session)
    contribution_input = ContextContributionInput(
        session_id=session_id,
        run_id=second_admission.run_id,
        current_request="继续重构",
        resource_refs=(ws_ref,),
    )
    fragments = contributor.build(contribution_input)
    assert len(fragments) == 1
    assert fragments[0].source_id == "dbfox.workspace"
    assert "calculate_total" in fragments[0].content

    # 6b: Verify through full ContextAssembler pipeline
    assembler = ContextAssembler(
        db_session,
        contributors=(WorkspaceContextContributor,),
    )
    snapshot = assembler.build(second_admission.run_id)
    ws_fragments = [f for f in snapshot.context_fragments if f.source_id == "dbfox.workspace"]
    assert len(ws_fragments) == 1
    assert "calculate_total" in ws_fragments[0].content

    # 7. SHA Freshness Fence: If file on disk changes, stale fragment is NOT included
    file_path.write_bytes(b"def calculate_total_v2(): pass\n")
    stale_fragments = contributor.build(contribution_input)
    assert len(stale_fragments) == 0  # fail-soft on SHA mismatch

    stale_snapshot = assembler.build(second_admission.run_id)
    assert len([f for f in stale_snapshot.context_fragments if f.source_id == "dbfox.workspace"]) == 0

    # 8. ResourceRef Fence: If workspace ResourceRef is absent, fragment is NOT included
    file_path.write_bytes(initial_content.encode("utf-8"))  # restore content
    unauth_input = ContextContributionInput(
        session_id=session_id,
        run_id=second_admission.run_id,
        current_request="继续重构",
        resource_refs=(),  # No workspace ref authorized
    )
    assert len(contributor.build(unauth_input)) == 0

    # 9. Workspace Version Fence: Same project id, but wrong version
    wrong_version_ref = ResourceScopeRef(kind="workspace", id=project_id, version="wrong-version-1234")

    # 9a: WorkspaceContextContributor & ContextAssembler reject wrong version
    wrong_ver_input = ContextContributionInput(
        session_id=session_id,
        run_id=second_admission.run_id,
        current_request="继续重构",
        resource_refs=(wrong_version_ref,),
    )
    assert len(contributor.build(wrong_ver_input)) == 0

    # 9b: Tool execution with wrong workspace version is rejected
    wrong_ver_session_id = "session-ws-wrong-ver"
    db_session.add(
        AgentSession(
            id=wrong_ver_session_id,
            project_id=project_id,
            title="Workspace Wrong Version Session",
        )
    )
    db_session.commit()

    third_admission = sessions.admit(
        session_id=wrong_ver_session_id,
        resource_refs=(wrong_version_ref,),
        content="尝试用错误版本读取",
        idempotency_key="ws-input-wrong-ver",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
    )
    third_lease = sessions.claim(session_id=wrong_ver_session_id, owner="conformance-worker-wrong-ver")
    assert third_lease is not None
    sessions.promote_next_input(lease=third_lease)
    db_session.commit()

    turn_wrong_ver = sessions.start_turn(
        lease=third_lease,
        run_id=third_admission.run_id,
        agent_definition_version=definition.version,
        prompt_version="test",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=materialized.model_dump(mode="json"),
        tool_materialization_hash=materialized.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()

    run_wrong_ver = db_session.get(AgentRun, third_admission.run_id)
    assert run_wrong_ver is not None
    control_wrong_ver = LeaseAwareRunControl(
        run=run_wrong_ver,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=lambda: False,
    )
    call_wrong_ver = ModelToolCall(
        id=f"call_{uuid4().hex[:8]}",
        name="file_read",
        arguments={"path": "src/service.py"},
    )
    with pytest.raises(ToolInputError, match="当前项目工作目录不可用"):
        dispatcher.request_and_execute(
            lease=third_lease,
            run_id=third_admission.run_id,
            turn_id=str(turn_wrong_ver.id),
            call=call_wrong_ver,
            materialization=materialized,
            control=control_wrong_ver,
        )


@pytest.mark.skip(
    reason="superseded by signed package and generic multi-resource conformance"
)
def test_data_and_workspace_authority_isolation(db_session, test_datasource, tmp_path) -> None:
    """Prove that dual-resource sessions correctly isolate tool execution scopes."""
    workspace_root = tmp_path / "ws_dual"
    workspace_root.mkdir()
    project_id = "project-dual"
    db_session.add(Project(id=project_id, name="Dual Project"))
    db_session.flush()
    test_datasource.project_id = project_id
    db_session.commit()

    registry = registry_with_legacy_workspace()

    # 1. Dual resources materializes both sets of tools
    dual_mat = materialize_tools(
        registry,
        execution_mode="read_only",
        available_resource_kinds=frozenset({"dbfox.data.database", "workspace"}),
    )
    dual_names = {t.name for t in dual_mat.tools}
    assert "sql_execute_readonly" in dual_names
    assert "file_read" in dual_names

    # 2. Database-only materializes only database tools
    db_only_mat = materialize_tools(
        registry,
        execution_mode="read_only",
        available_resource_kinds=frozenset({"dbfox.data.database"}),
    )
    db_names = {t.name for t in db_only_mat.tools}
    assert "sql_execute_readonly" in db_names
    assert "file_read" not in db_names

    # 3. Workspace-only materializes only workspace tools
    ws_only_mat = materialize_tools(
        registry,
        execution_mode="read_only",
        available_resource_kinds=frozenset({"workspace"}),
    )
    ws_names = {t.name for t in ws_only_mat.tools}
    assert "file_read" in ws_names
    assert "sql_execute_readonly" not in ws_names
