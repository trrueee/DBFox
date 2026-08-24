"""Data + Workspace composition runner over one production Agent Run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from engine.tools.runtime import provider_tool_name

from verification.bench.composition.data_workspace.schema import (
    DataWorkspaceCase,
    load_cases,
)
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import (
    answer_events,
    tool_call_events,
)
from verification.testkit.system_dlc_fixture import build_isolated_system_dlc_bundle


HERE = Path(__file__).resolve().parent
FILE_READ_TOOL = provider_tool_name("dbfox.workspace", "file_read")
SCHEMA_LIST_TOOL = provider_tool_name("dbfox.data", "schema_list")


def _function_output(messages: list[dict[str, Any]], call_id: str) -> dict[str, Any]:
    for item in messages:
        if item.get("type") == "function_call_output" and item.get("call_id") == call_id:
            raw = item.get("output")
            if isinstance(raw, dict):
                return raw
            try:
                value = json.loads(str(raw or "{}"))
            except json.JSONDecodeError:
                return {}
            return value if isinstance(value, dict) else {}
    return {}


class _CompositionProvider:
    def __init__(
        self,
        case: DataWorkspaceCase,
        database_id: str,
        call_number: int,
        evidence: dict[str, bool],
    ) -> None:
        self.case = case
        self.database_id = database_id
        self.call_number = call_number
        self.evidence = evidence

    def stream(self, *, messages, tools, **_kwargs):
        tool_names = {str(tool.get("name") or "") for tool in tools}
        self.evidence["both_tools_materialized"] = {
            FILE_READ_TOOL,
            SCHEMA_LIST_TOOL,
        } <= tool_names
        if self.call_number == 1:
            yield from tool_call_events(
                call_id="read-analysis-target",
                tool_name=FILE_READ_TOOL,
                arguments={"path": self.case.workspace_file},
            )
            return
        if self.call_number == 2:
            read_output = _function_output(messages, "read-analysis-target")
            self.evidence["workspace_observation_received"] = (
                self.case.workspace_content in json.dumps(read_output, ensure_ascii=False)
            )
            yield from tool_call_events(
                call_id="list-data-schema",
                tool_name=SCHEMA_LIST_TOOL,
                arguments={"database_id": self.database_id, "limit": 20},
            )
            return
        schema_output = _function_output(messages, "list-data-schema")
        self.evidence["data_observation_received"] = "orders" in json.dumps(
            schema_output,
            ensure_ascii=False,
        )
        if all(
            self.evidence.get(key, False)
            for key in (
                "both_tools_materialized",
                "workspace_observation_received",
                "data_observation_received",
            )
        ):
            yield from answer_events(
                "工作区要求核对订单收入；数据库目录中应分析 orders 表。"
            )
            return
        yield from answer_events("跨能力观察不完整。")


def _invoke(
    snapshot: Any,
    *,
    dlc_id: str,
    project_id: str,
    name: str,
    payload: dict[str, Any],
) -> Any:
    from engine.dlc.api import DlcOperationContext

    contribution = snapshot.get_operation(dlc_id, name)
    if contribution is None:
        raise RuntimeError(f"Production {dlc_id} operation is unavailable: {name}")
    result = contribution.spec.handler(
        contribution.spec.input_model.model_validate(payload),
        DlcOperationContext(
            dlc_id=dlc_id,
            operation_name=name,
            project_id=project_id,
        ),
    )
    return contribution.spec.output_model.model_validate(result)


def _seed_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                total_cents INTEGER NOT NULL
            );
            INSERT INTO customers VALUES (1, 'Ada');
            INSERT INTO orders VALUES (1, 1, 4200);
            """
        )
        connection.commit()
    finally:
        connection.close()


def _run_case(
    session_factory: sessionmaker[Session],
    snapshot: Any,
    *,
    suite_id: str,
    case: DataWorkspaceCase,
    repetition: int,
    fixture_root: Path,
) -> TrialOutcome:
    from engine.agent.completion import CompletionGate
    from engine.agent.events import LiveStreamHub
    from engine.agent.loop import RunLoop
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.resource_refs import RequestedResourceRef
    from engine.models import (
        AgentArtifactRecord,
        AgentMessage,
        AgentRun,
        AgentToolInvocation,
        AgentTurn,
        Project,
    )
    from engine.runtime_composition import (
        authorize_project_resources,
        build_attempt_resource_resolver,
        build_default_completion_policy,
        build_product_tool_registry,
        default_capability_guidance,
        default_context_contributors,
    )

    project_id = f"composition-{case.case_id}-{repetition}-{uuid4().hex[:8]}"
    workspace = fixture_root / f"workspace-{project_id}"
    workspace.mkdir(parents=True)
    target_file = workspace / case.workspace_file
    target_file.write_text(case.workspace_content, encoding="utf-8")
    database_path = fixture_root / f"{project_id}.sqlite"
    _seed_database(database_path)
    source_before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    workspace_before = hashlib.sha256(target_file.read_bytes()).hexdigest()

    with session_factory() as db:
        db.add(Project(id=project_id, name=f"CompositionBench {case.case_id}"))
        db.commit()

    created = _invoke(
        snapshot,
        dlc_id="dbfox.data",
        project_id=project_id,
        name="profiles.create",
        payload={
            "name": "CompositionBench SQLite",
            "provider": "sqlite",
            "is_read_only": True,
            "environment": "test",
            "initial_database_name": str(database_path.resolve()),
            "initial_database_display_name": "CompositionBench",
        },
    )
    database_id = str(created.databases[0].id)
    _invoke(
        snapshot,
        dlc_id="dbfox.data",
        project_id=project_id,
        name="catalog.refresh",
        payload={"database_id": database_id},
    )
    _invoke(
        snapshot,
        dlc_id="dbfox.workspace",
        project_id=project_id,
        name="binding.create",
        payload={"root_path": str(workspace.resolve())},
    )
    with session_factory() as db:
        refs = authorize_project_resources(
            db,
            project_id,
            (
                RequestedResourceRef(kind="dbfox.data.database", id=database_id),
                RequestedResourceRef(kind="dbfox.workspace.root", id=project_id),
            ),
            snapshot=snapshot,
        )
        sessions = SessionRepository(db)
        aggregate = sessions.create(
            project_id=project_id,
            title=f"[CompositionBench] {case.case_id}",
        )
        db.commit()
        admission = sessions.admit(
            session_id=str(aggregate.id),
            resource_refs=refs,
            content=case.prompt,
            idempotency_key=f"{suite_id}:{case.case_id}:{repetition}",
            llm_credential_id="composition-bench-scripted-provider",
            api_base=None,
            model_name="scripted",
            request_payload={"benchmark_suite": suite_id, "case_id": case.case_id},
        )
        lease = sessions.claim(
            session_id=str(aggregate.id),
            owner="composition-bench",
            ttl_seconds=120,
        )
        if lease is None:
            raise RuntimeError("CompositionBench could not claim the production Session lease")
        sessions.promote_next_input(lease=lease)
        db.commit()

    calls = {"count": 0}
    provider_evidence: dict[str, bool] = {}

    def model_factory(_settings):
        calls["count"] += 1
        return _CompositionProvider(
            case,
            database_id,
            calls["count"],
            provider_evidence,
        )

    product_registry = build_product_tool_registry(snapshot)
    loop = RunLoop(
        session_factory=session_factory,
        model_factory=model_factory,
        registry=product_registry,
        context_contributors=default_context_contributors(snapshot),
        capability_guidance=default_capability_guidance(snapshot),
        completion=CompletionGate(build_default_completion_policy(snapshot)),
        live_stream=LiveStreamHub(),
        resource_resolver=build_attempt_resource_resolver(snapshot=snapshot),
    )
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()

    source_after = hashlib.sha256(database_path.read_bytes()).hexdigest()
    workspace_after = hashlib.sha256(target_file.read_bytes()).hexdigest()
    with session_factory() as db:
        run = db.get(AgentRun, admission.run_id)
        answer = db.get(AgentMessage, admission.assistant_message_id)
        turns = db.query(AgentTurn).filter_by(run_id=admission.run_id).count()
        invocations = (
            db.query(AgentToolInvocation)
            .filter_by(run_id=admission.run_id)
            .order_by(AgentToolInvocation.created_at, AgentToolInvocation.id)
            .all()
        )
        artifacts = db.query(AgentArtifactRecord).filter_by(run_id=admission.run_id).all()
        text = str(answer.content or "") if answer is not None else ""
        tool_names = tuple(
            product_registry.key_of(product_registry.require(str(item.tool_name))).local_name
            for item in invocations
        )
        workspace_artifacts = tuple(
            item for item in artifacts if str(item.type) == "dbfox.workspace.file_snapshot"
        )
        handoff_ok = all(term in text for term in case.required_answer_terms) and all(
            provider_evidence.get(key, False)
            for key in (
                "workspace_observation_received",
                "data_observation_received",
            )
        )
        lineage_ok = bool(
            workspace_artifacts
            and all(project_id in str(item.resource_refs_json) for item in workspace_artifacts)
        )
        checks = {
            "completed": run is not None and str(run.status) == "completed",
            "cross_capability_handoff": handoff_ok,
            "required_tools": tool_names == case.required_tools,
            "tools_succeeded": all(
                str(item.status) == "succeeded" for item in invocations
            ),
            "frozen_authority": {ref.kind for ref in refs}
            == {"dbfox.data.database", "dbfox.workspace.root"},
            "artifact_lineage": lineage_ok,
            "source_database_unchanged": source_before == source_after,
            "workspace_unchanged": workspace_before == workspace_after,
            "turn_budget": turns <= case.max_turns,
            "tool_budget": len(invocations) <= case.max_tool_calls,
        }
        failed = tuple(name for name, passed in checks.items() if not passed)
        return TrialOutcome(
            suite_id=suite_id,
            case_id=case.case_id,
            repetition=repetition,
            verdict="pass" if not failed else "fail",
            metrics={
                "task.success_rate": 1.0 if not failed else 0.0,
                "composition.handoff_accuracy": 1.0 if handoff_ok else 0.0,
                "composition.authorized_resource_count": float(len(refs)),
                "composition.artifact_lineage_accuracy": 1.0 if lineage_ok else 0.0,
                "runtime.turns": float(turns),
                "runtime.tool_calls": float(len(invocations)),
            },
            failed_checks=failed,
            evidence={
                "run_status": str(run.status) if run is not None else "missing",
                "resource_refs": tuple((ref.kind, ref.id, ref.version) for ref in refs),
                "tool_names": tool_names,
                "artifact_types": tuple(sorted(str(item.type) for item in artifacts)),
                "provider_checks": provider_evidence,
            },
        )


def run_data_workspace_bench(
    *,
    output_dir: Path,
    repetitions: int = 1,
    case_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    manifest = load_suite_manifest(HERE / "suite.json")
    dataset = load_cases(HERE / manifest.dataset)
    cases = tuple(case for case in dataset.cases if not case_ids or case.case_id in case_ids)
    if not cases:
        raise ValueError("No Data + Workspace cases matched the requested case ids")
    work_dir = output_dir.parent / f".{output_dir.name}-work"
    work_dir.mkdir(parents=True, exist_ok=False)
    engine = create_migrated_metadata_engine(work_dir / "metadata.sqlite")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    previous_snapshot: Any | None = None
    snapshot_state_loaded = False
    try:
        from engine.runtime_composition import (
            active_runtime_snapshot,
            initialize_runtime_snapshot,
            set_active_runtime_snapshot,
        )

        previous_snapshot = active_runtime_snapshot()
        snapshot_state_loaded = True
        system_dlc_dir, system_dlc_manifest = build_isolated_system_dlc_bundle(
            work_dir / "system-bundle"
        )
        snapshot = initialize_runtime_snapshot(
            storage_root=work_dir / "installed-dlcs",
            system_dlc_dir=system_dlc_dir,
            system_dlc_manifest=system_dlc_manifest,
        )
        outcomes = tuple(
            _run_case(
                factory,
                snapshot,
                suite_id=manifest.suite_id,
                case=case,
                repetition=repetition,
                fixture_root=work_dir,
            )
            for case in cases
            for repetition in range(1, repetitions + 1)
        )
        return write_suite_report(output_dir, manifest=manifest, outcomes=outcomes)
    finally:
        if snapshot_state_loaded:
            set_active_runtime_snapshot(previous_snapshot)
        engine.dispose()
        resolved_work = work_dir.resolve()
        resolved_parent = output_dir.parent.resolve()
        if resolved_work.parent == resolved_parent and resolved_work.name.startswith("."):
            shutil.rmtree(resolved_work)
