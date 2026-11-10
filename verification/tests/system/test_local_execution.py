"""Windows processes and real Tool Runtime; only the model boundary is scripted."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.artifact import artifact_payload_contracts
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.dlc.api import DlcOperationContext
from engine.local_execution.broker import LocalExecutionBroker, supported
from engine.local_execution.command import ExecutionError
from engine.local_execution.contracts import ACTIVE_STATES, ExecutionScope, StartInput
from engine.local_execution.records import LocalExecutionJob
from engine.local_execution.representation import LOG_REPRESENTATION, RESULT_ARTIFACT
from engine.models import AgentApproval, AgentRun, AgentSession, Project
from engine.representation import ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest
from engine.runtime_composition import (
    active_runtime_snapshot, authorize_artifact_session_resources, build_product_run_loop, build_product_tool_registry, compose_local_execution,
    initialize_runtime_snapshot, set_active_runtime_snapshot,
)
from engine.tools.runtime import ToolKey
from verification.support.metadata import create_migrated_metadata_engine
from verification.tests.integration.stream_fixtures import final_turn, tool_turn
from verification.tests.system.test_system_dlc_bootstrap import _workspace_bundle

pytestmark = pytest.mark.skipif(not supported(), reason="Managed execution targets Windows 11 x64")


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    previous = active_runtime_snapshot()
    registry = artifact_payload_contracts
    saved_contracts, saved_frozen = registry._contracts, registry._frozen
    registry._contracts = {key: value for key, value in saved_contracts.items() if not key[0].startswith("dbfox.workspace.")}
    registry._frozen = False
    runtime = tmp_path / "runtime"
    package_dir, manifest_path = _workspace_bundle(tmp_path)
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("DBFOX_SYSTEM_DLC_DIR", str(package_dir))
    monkeypatch.setenv("DBFOX_SYSTEM_DLC_MANIFEST", str(manifest_path))
    engine = create_migrated_metadata_engine(tmp_path / "metadata.sqlite")
    sessions = sessionmaker(bind=engine)
    broker = None
    try:
        base = initialize_runtime_snapshot(runtime / "dlcs")
        assert base.active_dlcs[0].system_pinned
        snapshot, broker = compose_local_execution(base, sessions)
        assert broker is not None
        set_active_runtime_snapshot(snapshot)
        project = tmp_path / "Unfamiliar Project"
        project.mkdir()

        def binding(operation, **args):
            spec = snapshot.get_operation("dbfox.workspace", f"binding.{operation}").spec
            return spec.handler(spec.input_model(**args), DlcOperationContext(
                dlc_id="dbfox.workspace", operation_name=f"binding.{operation}", project_id="p",
            ))

        binding("create", root_path=str(project))
        with sessions.begin() as db:
            db.add(Project(id="p", name=project.name))
            db.flush()
            db.add(AgentSession(id="s", project_id="p"))
            ref = snapshot.resource_providers[0](db, "p")[0].to_scope_ref()
        yield sessions, snapshot, broker, project, ExecutionScope("s", ref), binding
    finally:
        if broker is not None:
            broker.close()
        engine.dispose()
        registry._contracts, registry._frozen = saved_contracts, saved_frozen
        set_active_runtime_snapshot(previous)


def _until(check, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if result := check():
            return result
        time.sleep(0.04)
    pytest.fail("Timed out waiting for the observed execution fact")


def _terminal(broker, scope, job_id, seconds=12):
    def observe():
        job = broker.get(scope, job_id)
        return job if job.state not in ACTIVE_STATES else None
    return _until(observe, seconds)


def _start(broker, scope, script, *, invocation=None, resource=None, **input):
    return broker.start(
        scope=scope, run_id="r", invocation_id=invocation or uuid4().hex, approval_id="test-approval",
        input=StartInput(argv=[sys.executable, "-u", "-c", script], **input),
        resource=resource or broker.resolve_workspace(scope.workspace),
        is_approved=lambda _: True, is_cancelled=lambda: False,
    )


def test_real_process_tree_pipes_cursors_duplicate_and_termination(workbench):
    sessions, _, broker, _, scope, _ = workbench
    with sessions.begin() as db:
        db.add(AgentRun(id="r", session_id="s", question="Run two commands", status="running"))
    script = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "print('echo=' + sys.stdin.readline().strip()); print('stderr-evidence', file=sys.stderr); sys.exit(7)"
    )
    job = _start(broker, scope, script, invocation="same-invocation", interactive=True)
    assert _start(broker, scope, script, invocation="same-invocation", interactive=True).id == job.id
    other = _start(broker, scope, "print('parallel')")
    assert other.id != job.id
    assert _terminal(broker, scope, other.id).root_exit_code == 0
    assert broker.write(scope, job.id, "hello\n", close=True) == 6
    _until(lambda: broker.get(scope, job.id).root_exit_code == 7)
    waiting = broker.get(scope, job.id)
    assert waiting.state == "running" and waiting.active_processes > 0 and not waiting.output_finalized
    first = broker.page(scope, job.id, 0, 1)
    second = broker.page(scope, job.id, first.next_cursor, 4)
    assert {(chunk.stream, chunk.text.strip()) for chunk in first.chunks + second.chunks} == {
        ("stdout", "echo=hello"), ("stderr", "stderr-evidence"),
    }
    with pytest.raises(ExecutionError, match="unavailable"):
        broker.get(ExecutionScope("another-conversation", scope.workspace), job.id)
    broker.stop(scope, job.id)
    ended = _terminal(broker, scope, job.id)
    assert (ended.state, ended.root_exit_code, ended.active_processes, ended.output_finalized) == ("cancelled", 7, 0, True)
    # Startup recovery preserves recorded output and never starts an old command again.
    with sessions.begin() as db:
        db.get(LocalExecutionJob, job.id).state = "running"
    broker.close()
    restarted = LocalExecutionBroker(sessions, broker.resolve_workspace)
    try:
        recovered = restarted.page(scope, job.id, 0, 4)
        assert recovered.job.state == "interrupted" and recovered.job.active_processes is None
        assert len(recovered.chunks) == 2
    finally:
        restarted.close()


def test_background_run_completion_and_same_path_revocation(workbench):
    sessions, _, broker, project, scope, binding = workbench
    with sessions.begin() as db:
        db.add(AgentRun(id="r", session_id="s", question="Keep one server", status="running"))
    foreground = _start(broker, scope, "import time; time.sleep(60)")
    background = _start(broker, scope, "import time; time.sleep(60)", lifetime="background")
    resource = broker.resolve_workspace(scope.workspace)
    with sessions.begin() as db:
        db.get(AgentRun, "r").status = "completed"
    assert _terminal(broker, scope, foreground.id).reason == "run_completed"
    assert broker.get(scope, background.id).state == "running"
    binding("delete")
    replacement = binding("create", root_path=str(project))
    assert replacement.binding_generation != scope.workspace.version
    with pytest.raises(ValueError, match="revoked"):
        with resource.execution_directory(""):
            pytest.fail("A revoked resource acquired a launch lease")

    def observe():
        with sessions() as db:
            job = db.get(LocalExecutionJob, background.id)
            return job if job.state not in ACTIVE_STATES else None
    ended = _until(observe)
    assert ended.reason == "workspace_revoked" and ended.active_processes == 0
    with pytest.raises(ExecutionError, match="unavailable"):
        broker.get(ExecutionScope("s", scope.workspace.model_copy(update={"version": replacement.binding_generation})), background.id)


def test_rolling_retention_keeps_terminal_output(workbench):
    sessions, _, broker, _, scope, _ = workbench
    with sessions.begin() as db:
        db.add(AgentRun(id="r", session_id="s", question="Produce large logs", status="running"))
    job = _start(broker, scope, "import sys; sys.stdout.buffer.write(b'x' * (9 * 1024 * 1024)); print('DONE')", timeout_seconds=45)
    final = _terminal(broker, scope, job.id, seconds=45)
    assert (final.state, final.root_exit_code, final.output_finalized) == ("exited", 0, True)
    assert final.first_cursor > 1 and final.retained_bytes <= 8 * 1024 * 1024
    assert broker.page(scope, job.id, 0, 1).cursor_expired
    assert "DONE" in "".join(chunk.text for chunk in broker.page(scope, job.id, 0, 2, tail=True).chunks)


def test_timeout_and_launch_failure_have_distinct_states(workbench):
    sessions, _, broker, project, scope, _ = workbench
    with sessions.begin() as db:
        db.add(AgentRun(id="r", session_id="s", question="Check two failure modes", status="running"))
    running = _start(broker, scope, "import time; time.sleep(60)", timeout_seconds=1)
    ended = _terminal(broker, scope, running.id)
    assert (ended.state, ended.reason, ended.active_processes, ended.output_finalized) == (
        "timed_out", "execution_timeout", 0, True,
    )

    invalid = project / "broken.exe"
    invalid.write_bytes(b"not a Windows program")
    with pytest.raises(ExecutionError, match="win32_start_"):
        broker.start(
            scope=scope, run_id="r", invocation_id="invalid-exe", approval_id="invalid-exe-test",
            input=StartInput(argv=[str(invalid)]), resource=broker.resolve_workspace(scope.workspace),
            is_approved=lambda _: True, is_cancelled=lambda: False,
        )
    failed = next(job for job in broker.list_jobs(scope) if job.executable == str(invalid.resolve()))
    assert failed.state == "start_failed" and failed.root_exit_code is None


def test_explicit_cmd_quotes_and_filtered_host_environment(workbench, monkeypatch):
    sessions, _, broker, project, scope, _ = workbench
    with sessions.begin() as db:
        db.add(AgentRun(id="r", session_id="s", question="Run an approved batch script", status="running"))
    batch = project / "spaces & quotes.cmd"
    batch.write_text("@echo off\r\necho %1\r\nexit /b 13\r\n", encoding="ascii", newline="")
    with pytest.raises(ExecutionError, match="explicit shell_script"):
        broker.start(
            scope=scope, run_id="r", invocation_id="direct-batch", approval_id="direct-test",
            input=StartInput(argv=[str(batch), "quoted"]),
            resource=broker.resolve_workspace(scope.workspace), is_approved=lambda _: True, is_cancelled=lambda: False,
        )
    job = broker.start(
        scope=scope, run_id="r", invocation_id="explicit-shell", approval_id="shell-test",
        input=StartInput(shell_script=f'"{batch}" "a & b"'),
        resource=broker.resolve_workspace(scope.workspace), is_approved=lambda _: True, is_cancelled=lambda: False,
    )
    assert _terminal(broker, scope, job.id).root_exit_code == 13
    assert '"a & b"' in "".join(chunk.text for chunk in broker.page(scope, job.id, 0, 8).chunks)

    monkeypatch.setenv("DBFOX_ENGINE_TOKEN", "fixture-not-a-credential")
    probe = _start(broker, scope, "import os; assert 'DBFOX_ENGINE_TOKEN' not in os.environ; print(os.environ['FEATURE_MODE'])",
                   env={"FEATURE_MODE": "qa"})
    assert _terminal(broker, scope, probe.id).root_exit_code == 0
    assert "".join(chunk.text for chunk in broker.page(scope, probe.id, 0, 8).chunks).strip() == "qa"


def test_conversation_http_reconnect_scope_and_stop(workbench, monkeypatch):
    from fastapi.testclient import TestClient

    from engine import main
    from engine.db import get_db

    sessions, _, broker, _, scope, _ = workbench
    with sessions.begin() as db:
        db.add(AgentSession(id="other", project_id="p"))
        db.add(AgentRun(id="r", session_id="s", question="Keep a task running", status="running"))
    job = _start(broker, scope, "import time; print('connected'); time.sleep(60)")
    def database():
        with sessions() as db:
            yield db
    monkeypatch.setitem(main.app.dependency_overrides, get_db, database)
    monkeypatch.setattr(main.app.state, "local_execution", broker, raising=False)
    root = "/api/v1/conversations"
    route = f"{root}/s/execution-jobs/{job.id}"
    headers = {"X-Local-Token": main.LOCAL_SECURE_TOKEN}
    client = TestClient(main.app, headers=headers)
    try:
        first = _until(lambda: (
            page if (page := client.get(route).json()).get("chunks") else None
        ))
        assert first["chunks"][0]["text"].strip() == "connected"
        assert client.get(route, headers={"X-Local-Token": "wrong"}).status_code == 401
        assert client.post(f"{root}/other/execution-jobs/{job.id}/stop").status_code == 404
        assert client.get(f"{root}/s/execution-jobs").json()[0]["id"] == job.id
        assert client.post(route + "/stop").status_code == 202
        assert _terminal(broker, scope, job.id).state == "cancelled"
        assert client.get(route, params={"after": first["next_cursor"]}).json()["job"]["active_processes"] == 0
    finally:
        client.close()


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_unfamiliar_project_failure_drives_repair_through_real_run_loop(workbench, language):
    sessions, snapshot, _, project, scope, _ = workbench
    git = shutil.which("git.exe")
    if not git:
        pytest.skip("git.exe is required for independent diff verification")
    if language == "python":
        filename, before, after = "normalize.py", "return value + 100", "return value - 100"
        (project / filename).write_text(f"def normalize(value):\n    {before}\n", encoding="utf-8")
        (project / "test_normalize.py").write_text(
            "from normalize import normalize\n\ndef test_baseline():\n    assert normalize(125) == 25\n", encoding="utf-8",
        )
        argv = [sys.executable, "-m", "pytest", "-q"]
        diagnostic = "1 failed"
    else:
        node = shutil.which("node.exe")
        tsc = Path(__file__).resolve().parents[3] / "desktop" / "node_modules" / "typescript" / "lib" / "tsc.js"
        if not node or not tsc.is_file():
            pytest.skip("Node and the locked desktop TypeScript compiler are required")
        filename, before, after = "normalize.ts", 'return "25";', "return 25;"
        (project / filename).write_text(f"export function normalize(): number {{ {before} }}\n", encoding="utf-8")
        (project / "package.json").write_text('{"name":"unfamiliar-normalizer","scripts":{"check":"tsc --noEmit"}}', encoding="utf-8")
        (project / "tsconfig.json").write_text('{"compilerOptions":{"strict":true,"noEmit":true}}', encoding="utf-8")
        argv = [node, str(tsc), "--noEmit"]
        diagnostic = "TS2322"
    subprocess.run([git, "init", "--quiet"], cwd=project, check=True)
    subprocess.run([git, "add", "--", filename], cwd=project, check=True)
    registry = build_product_tool_registry(snapshot)
    outputs = {}

    def plan():
        yield "env", "command_environment", {}
        assert "cwd" not in outputs["env"]["facts"]
        yield "search-absolute", "file_search", {"query": filename, "path_prefix": str(project)}
        yield "search", "file_search", {"query": filename}
        assert outputs["search"]["facts"]["path_prefix"] == "."
        path = outputs["search"]["facts"]["matches"][0]["path"]
        yield "unknown-tool", "unavailable_function", {}
        yield "read", "file_read", {"path": path}
        yield "command-absolute", "command_start", {"argv": argv, "cwd": str(project)}
        yield "first", "command_start", {"argv": argv}
        for suffix, expected in (("first", 1 if language == "python" else 2), ("second", 0)):
            if suffix == "second":
                yield "second", "command_start", {"argv": argv}
            job_id = outputs[suffix]["facts"]["execution_job_id"]
            cursor = 0
            log = ""
            for i in range(8):
                call_id = f"{suffix}-inspect-{i}"
                yield call_id, "command_inspect", {"job_id": job_id, "after": cursor, "wait_seconds": 5}
                observation = outputs[call_id]["facts"]
                cursor = observation["next_cursor"]
                log += "".join(chunk["text"] for chunk in observation["chunks"])
                if observation["state"] == "exited" and not observation["has_more"]:
                    break
            assert observation["root_exit_code"] == expected and observation["output_finalized"], observation
            if suffix == "first":
                assert diagnostic in log, log
                yield "edit", "file_edit", {
                    "path": filename, "old_string": before, "new_string": after,
                    "expected_sha256": outputs["read"]["facts"]["sha256"],
                }
            else:
                yield "publish", "command_result", {"job_id": job_id, "related_artifact_ids": outputs["edit"]["artifact_ids"]}

    steps = iter(plan())

    class ModelBoundary:
        def stream(self, *, messages, tools, **kwargs):
            for item in messages:
                if item.get("type") == "function_call_output" and item["call_id"] not in outputs:
                    value = json.loads(item["output"])
                    if item["call_id"] in {"search-absolute", "command-absolute"}:
                        assert value["status"] in {"failed", "rejected"}, value
                        assert "relative to the bound project" in item["output"], value
                        assert str(project) not in str(value), value
                    elif item["call_id"] == "unknown-tool":
                        assert value["status"] == "rejected" and value["error_code"] == "UNKNOWN_TOOL", value
                    else:
                        assert value["status"] == "succeeded", (item["call_id"], value)
                    outputs[item["call_id"]] = value
            step = next(steps, None)
            if step is None:
                yield from final_turn("Verified repaired project with exit code 0 and attached execution evidence.")
            else:
                call_id, local_name, arguments = step
                if call_id == "unknown-tool":
                    name = local_name
                else:
                    name = registry.provider_name_for_key(ToolKey(owner_id="dbfox.workspace", local_name=local_name))
                    assert any(tool.get("name") == name for tool in tools)
                yield from tool_turn(call_id, name, arguments)

    with sessions() as db:
        repo = SessionRepository(db)
        admission = repo.admit(
            session_id="s", resource_refs=(scope.workspace,), content="Find and fix the failing project check.",
            idempotency_key="repair", llm_credential_id="verification-only", api_base=None,
            model_name="verification-only", request_payload={},
        )
        lease = repo.claim(session_id="s", owner="verification", ttl_seconds=120)
        repo.promote_next_input(lease=lease)
        db.commit()
    loop = build_product_run_loop(session_factory=sessions, snapshot=snapshot)
    loop.model_factory = lambda _: ModelBoundary()
    approvals = []
    try:
        for _ in range(6):
            loop.execute(lease=lease, run_id=admission.run_id)
            with sessions() as db:
                run = db.get(AgentRun, admission.run_id)
                if run.status == "completed":
                    break
                assert run.status == "waiting_approval", (run.status, run.error_message)
                pending = db.query(AgentApproval).filter_by(run_id=run.id, status="pending").one()
                request = json.loads(pending.requested_action_json)
                if "argv" in request["arguments"]:
                    assert Path(request["review"]["executable"]).is_absolute()
                    assert request["review"]["cwd"] == str(project.resolve())
                    approvals.append(pending.id)
                ApprovalRepository(db).resolve(approval_id=pending.id, expected_version=0, approved=True, actor="user")
                lease = SessionRepository(db).claim(session_id="s", owner="verification-resume", ttl_seconds=120)
                SessionRepository(db).bind_run(lease=lease, run_id=admission.run_id)
                db.commit()
        assert len(set(approvals)) == 2 and "publish" in outputs
        diff = subprocess.check_output([git, "diff", "--", filename], cwd=project, text=True)
        assert before in diff and after in diff
        with sessions() as db:
            assert db.get(AgentRun, admission.run_id).status == "completed"
            artifact = ArtifactRepository(db).get(outputs["publish"]["artifact_ids"][0])
            for foreign_scope in (None, "another-session"):
                with pytest.raises(ArtifactRepresentationError):
                    authorize_artifact_session_resources(db, artifact, foreign_scope)
            authorize_artifact_session_resources(db, artifact, scope.session_id)
        assert artifact.type == RESULT_ARTIFACT
        provider = snapshot.get_artifact_representation(RESULT_ARTIFACT, LOG_REPRESENTATION).provider
        evidence = provider.execute(artifact, ArtifactRepresentationRequest(operation="read"), ArtifactRepresentationContext(lambda _: None))
        assert evidence.payload["job"]["root_exit_code"] == 0
    finally:
        loop.close()
