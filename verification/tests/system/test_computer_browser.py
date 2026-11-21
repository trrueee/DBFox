"""Real Edge/Playwright/Job integration on a dedicated local fixture page."""
from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import pytest
from sqlalchemy.orm import sessionmaker

from engine.computer.browser import edge_executable
from engine.computer.contracts import ActInput, ComputerError, ShareInput
from engine.models import AgentSession, Project
from verification.support.metadata import create_migrated_metadata_engine

pytestmark = pytest.mark.platform_contract


class _Page(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        data = b'<!doctype html><title>DBFox computer fixture</title><label>Name <input id="name"></label><button onclick="document.querySelector(\'output\').textContent=document.querySelector(\'input\').value">Save fixture</button><output>not saved</output>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def computer(tmp_path: Path, monkeypatch) -> Iterator[tuple]:
    from engine.local_execution.broker import supported
    if not supported() or edge_executable() is None:
        pytest.skip("Requires Windows 11 and explicitly installed Edge")
    metadata = create_migrated_metadata_engine(tmp_path / "computer.sqlite")
    sessions = sessionmaker(bind=metadata)
    with sessions.begin() as db:
        db.add(Project(id="p", name="Computer browser fixture"))
        db.flush()
        db.add(AgentSession(id="s", project_id="p"))
    from engine.runtime_composition import active_runtime_snapshot, compose_computer, initialize_runtime_snapshot, set_active_runtime_snapshot
    previous = active_runtime_snapshot()
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(tmp_path / "runtime"))
    snapshot, runtime = compose_computer(initialize_runtime_snapshot(tmp_path / "dlcs"), sessions)
    assert runtime is not None
    set_active_runtime_snapshot(snapshot)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield runtime, f"http://127.0.0.1:{server.server_port}/", sessions, snapshot
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()
        metadata.dispose()
        set_active_runtime_snapshot(previous)


def test_real_browser_edit_observe_stale_guard_and_stop(computer) -> None:
    runtime, url, _sessions, _snapshot = computer
    target = next(item for item in runtime.inventory() if item.target.kind == "browser")
    grant = runtime.share("s", ShareInput(inventory_id=target.inventory_id, permission="control", duration_minutes=5))
    ref = runtime.ref(grant)
    runtime.act("s", ref, None, url, "navigate", lambda: False)
    before = runtime.observe("s", ref, "observe", lambda: False)
    assert before.title == "DBFox computer fixture"
    assert runtime.read_capture(before).startswith(b"\x89PNG")
    edit = next(node for node in before.nodes if node.role == "input")
    runtime.act("s", ref, before, ActInput(target_id=grant.id, observation_artifact_id="unit-artifact",
                action="type_text", node_id=edit.id, text="verified real browser"), "type", lambda: False)
    with pytest.raises(ComputerError, match="最新实际观察"):
        runtime.act("s", ref, before, ActInput(target_id=grant.id, observation_artifact_id="unit-artifact",
                    action="click", node_id=edit.id), "stale", lambda: False)
    after = runtime.observe("s", ref, "observe-after", lambda: False)
    assert any(node.value == "verified real browser" for node in after.nodes)
    save = next(node for node in after.nodes if node.name == "Save fixture")
    runtime.act("s", ref, after, ActInput(target_id=grant.id, observation_artifact_id="unit-artifact",
                action="click", node_id=save.id), "click", lambda: False)
    saved = runtime.observe("s", ref, "saved", lambda: False)
    assert "verified real browser" in " ".join(saved.notes)
    runtime.stop("s", target_id=grant.id)
    assert runtime.store.get("s", grant.id).status == "paused"
    with pytest.raises(ComputerError):
        runtime.act("s", ref, saved, ActInput(target_id=grant.id, observation_artifact_id="unit-artifact",
                    action="click", node_id=save.id), "after-stop", lambda: False)


def test_production_run_loop_approvals_artifacts_and_native_image_input(computer) -> None:
    import base64
    import hashlib
    import json
    from engine.agent.repositories.approval import ApprovalRepository
    from engine.agent.repositories.artifact import ArtifactRepository
    from engine.agent.repositories.session import SessionRepository
    from engine.models import AgentApproval, AgentRun, AgentObservationRecord, AgentTurn
    from engine.runtime_composition import authorize_artifact_session_resources, build_product_run_loop, build_product_tool_registry
    from engine.tools.runtime import ToolKey
    from verification.tests.integration.stream_fixtures import final_turn, tool_turn
    runtime, url, sessions, snapshot = computer
    target = next(item for item in runtime.inventory() if item.target.kind == "browser")
    grant = runtime.share("s", ShareInput(inventory_id=target.inventory_id, permission="control", duration_minutes=5))
    registry = build_product_tool_registry(snapshot)
    assert registry.copy().tool_names() == registry.tool_names()
    outputs, image_hashes = {}, []

    def plan():
        yield "navigate", "browser_navigate", {"target_id": grant.id, "url": url}
        assert outputs["navigate"]["status"] == "succeeded", outputs
        observation = outputs["navigate"]["facts"]["observation"]
        edit = next(node for node in observation["nodes"] if node["role"] == "input")
        yield "type", "computer_act", {"target_id": grant.id, "action": "type_text", "text": "production RunLoop verified",
            "node_id": edit["id"], "observation_artifact_id": outputs["navigate"]["facts"]["observation_artifact_id"]}
        observation = outputs["type"]["facts"]["observation"]
        save = next(node for node in observation["nodes"] if node["name"] == "Save fixture")
        yield "save", "computer_act", {"target_id": grant.id, "action": "click", "node_id": save["id"],
            "observation_artifact_id": outputs["type"]["facts"]["observation_artifact_id"]}
        assert "production RunLoop verified" in " ".join(outputs["save"]["facts"]["observation"]["notes"])
    steps = iter(plan())

    class ModelBoundary:
        def stream(self, *, messages, tools, **_kwargs):
            actual_images = 0
            for item in messages:
                if item.get("type") != "function_call_output":
                    continue
                output = item["output"]
                text = output[0]["text"] if isinstance(output, list) else output
                if item["call_id"] not in outputs:
                    outputs[item["call_id"]] = json.loads(text)
                if isinstance(output, list):
                    image = output[1]
                    assert image["type"] == "input_image"
                    data = base64.b64decode(image["image_url"].split(",")[1])
                    assert data.startswith(b"\x89PNG")
                    image_hashes.append(hashlib.sha256(data).hexdigest())
                    actual_images += 1
            assert actual_images <= 1
            step = next(steps, None)
            if step is None:
                yield from final_turn("The fixture saved the requested text; actual browser evidence is attached.")
            else:
                call_id, name, arguments = step
                wire_name = registry.provider_name_for_key(ToolKey("dbfox.computer", name))
                assert any(tool.get("name") == wire_name for tool in tools)
                yield from tool_turn(call_id, wire_name, arguments)

    with sessions() as db:
        repo = SessionRepository(db)
        admission = repo.admit(session_id="s", resource_refs=(runtime.ref(grant),), content="Save text in the dedicated fixture browser.",
            idempotency_key="browser-production", llm_credential_id="verification-only", api_base=None,
            model_name="verification-only", request_payload={})
        lease = repo.claim(session_id="s", owner="computer-verification", ttl_seconds=120)
        repo.promote_next_input(lease=lease)
        db.commit()
    loop = build_product_run_loop(session_factory=sessions, snapshot=snapshot)
    loop.model_factory = lambda _: ModelBoundary()
    approvals = []
    try:
        for _ in range(5):
            loop.execute(lease=lease, run_id=admission.run_id)
            with sessions() as db:
                run = db.get(AgentRun, admission.run_id)
                if run.status == "completed":
                    break
                assert run.status == "waiting_approval", (run.status, run.error_message)
                pending = db.query(AgentApproval).filter_by(run_id=run.id, status="pending").one()
                request = json.loads(pending.requested_action_json)
                assert "target" in request["review"]
                review = request["review"]
                if review["action"] in {"type_text", "click"}:
                    source = outputs["navigate" if review["action"] == "type_text" else "type"]["facts"]
                    assert review["observation_artifact_id"] == source["observation_artifact_id"]
                    assert review["image_width"] == source["observation"]["image_width"]
                    assert review["image_height"] == source["observation"]["image_height"]
                    assert review["observed_at"] == source["observation"]["observed_at"]
                approvals.append(pending.id)
                ApprovalRepository(db).resolve(approval_id=pending.id, expected_version=0, approved=True, actor="user")
                lease = SessionRepository(db).claim(session_id="s", owner="computer-resume", ttl_seconds=120)
                SessionRepository(db).bind_run(lease=lease, run_id=admission.run_id)
                db.commit()
        assert len(set(approvals)) == 3 and len(image_hashes) == 3
        with sessions() as db:
            assert db.get(AgentRun, admission.run_id).status == "completed"
            observations = db.query(AgentObservationRecord).filter_by(run_id=admission.run_id).all()
            assert observations and all("base64" not in row.model_output_json for row in observations)
            turns = db.query(AgentTurn).filter_by(run_id=admission.run_id).all()
            assert all("base64" not in row.context_snapshot_json for row in turns)
            artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
            captures = [artifact for artifact in artifacts if artifact.type == "dbfox.computer.observation"]
            assert [artifact.payload["image_sha256"] for artifact in captures] == image_hashes
            runtime.stop("s", target_id=grant.id)
            authorize_artifact_session_resources(db, captures[-1], "s")
            assert runtime.read_capture(__import__("engine.computer.contracts", fromlist=["Observation"]).Observation.model_validate(captures[-1].payload)).startswith(b"\x89PNG")
    finally:
        loop.close()


def test_browser_tabs_are_observed_and_require_fresh_target_state(computer) -> None:
    runtime, url, _sessions, _snapshot = computer
    target = next(item for item in runtime.inventory() if item.target.kind == "browser")
    grant = runtime.share("s", ShareInput(inventory_id=target.inventory_id, permission="control", duration_minutes=5))
    ref = runtime.ref(grant)
    runtime.act("s", ref, None, url, "navigate", lambda: False)
    first = runtime.observe("s", ref, "first", lambda: False)
    runtime.act("s", ref, first, ActInput(target_id=grant.id, observation_artifact_id="fixture", action="new_tab"), "new", lambda: False)
    second = runtime.observe("s", ref, "second", lambda: False)
    assert len(second.tabs) == 2 and first.current_tab_id != second.current_tab_id
    runtime.act("s", ref, second, ActInput(target_id=grant.id, observation_artifact_id="fixture", action="select_tab", tab_id=first.current_tab_id), "select", lambda: False)
    selected = runtime.observe("s", ref, "selected", lambda: False)
    assert selected.current_tab_id == first.current_tab_id and selected.title == first.title
    runtime.act("s", ref, selected, ActInput(target_id=grant.id, observation_artifact_id="fixture", action="close_tab", tab_id=second.current_tab_id), "close", lambda: False)
    assert len(runtime.browser_state("s", grant.id).tabs) == 1


def test_authenticated_http_sharing_preview_foreign_scope_and_global_stop(computer, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from engine import main
    from engine.db import get_db
    runtime, _url, sessions, _snapshot = computer
    with sessions.begin() as db:
        db.add(AgentSession(id="other", project_id="p"))
    def database():
        with sessions() as db:
            yield db
    monkeypatch.setitem(main.app.dependency_overrides, get_db, database)
    monkeypatch.setattr(main.app.state, "computer", runtime, raising=False)
    failures = []
    original_share = runtime.share
    def trace_share(*args, **kwargs):
        try:
            return original_share(*args, **kwargs)
        except ComputerError as exc:
            failures.append(repr(exc.__cause__))
            raise
    monkeypatch.setattr(runtime, "share", trace_share)
    client = TestClient(main.app, headers={"X-Local-Token": main.LOCAL_SECURE_TOKEN})
    try:
        targets = client.get("/api/v1/computer/targets")
        assert targets.status_code == 200
        target = next(item for item in targets.json() if item["target"]["kind"] == "browser")
        body = {"inventory_id": target["inventory_id"], "permission": "observe", "duration_minutes": 5}
        assert client.post("/api/v1/conversations/s/computer", json=body, headers={"X-Local-Token": "invalid"}).status_code == 401
        response = client.post("/api/v1/conversations/s/computer", json=body)
        assert response.status_code == 201, (response.text, failures)
        identity = response.json()["id"]
        preview_url = f"/api/v1/conversations/s/computer/{identity}/preview"
        preview = client.get(preview_url)
        assert preview.status_code == 200 and preview.content.startswith(b"\x89PNG")
        assert preview.headers["cache-control"] == "no-store"
        assert client.get(preview_url.replace("/s/", "/other/")).status_code == 404
        assert client.post(f"/api/v1/conversations/other/computer/{identity}/stop").status_code == 404
        assert client.post("/api/v1/computer/stop").status_code == 202
        assert client.get(preview_url).status_code == 409
        assert client.get("/api/v1/conversations/s/computer").json()[0]["status"] == "paused"
    finally:
        client.close()


def test_slow_navigation_does_not_hold_the_metadata_writer(computer, monkeypatch) -> None:
    runtime, url, sessions, _snapshot = computer
    option = next(item for item in runtime.inventory() if item.target.kind == "browser")
    grant = runtime.share("s", ShareInput(inventory_id=option.inventory_id, permission="control"))
    ref = runtime.ref(grant)
    runtime.act("s", ref, None, url, "warmup", lambda: False)
    with sessions.begin() as db:
        db.add(AgentSession(id="other-writer", project_id="p"))
    other = runtime.store.create("other-writer", option.target, permission="control", duration_minutes=5)
    entered, release = Event(), Event()
    requests = []
    original = _Page.do_GET

    def delayed(handler):
        if handler.path == "/slow":
            requests.append(handler.path)
            entered.set()
            assert release.wait(6)
        original(handler)

    monkeypatch.setattr(_Page, "do_GET", delayed)
    with ThreadPoolExecutor(2) as pool:
        navigation = pool.submit(runtime.act, "s", ref, None, url + "slow", "slow", lambda: False)
        try:
            assert entered.wait(3)
            stopped = pool.submit(runtime.stop, "other-writer", target_id=other.id)
            stopped.result(timeout=2)
            assert runtime.store.get("other-writer", other.id).status == "paused"
            assert not navigation.done(), "The controlled network wait ended before the independent write."
        finally:
            release.set()
            navigation.result(timeout=6)
    assert requests == ["/slow"]


def test_stop_interrupts_an_already_submitted_navigation_without_replay(computer, monkeypatch) -> None:
    runtime, url, _sessions, _snapshot = computer
    option = next(item for item in runtime.inventory() if item.target.kind == "browser")
    grant = runtime.share("s", ShareInput(inventory_id=option.inventory_id, permission="control"))
    entered, release = Event(), Event()
    requests = []
    original = _Page.do_GET

    def delayed(handler):
        if handler.path == "/blocked":
            requests.append(handler.path)
            entered.set()
            assert release.wait(6)
        try:
            original(handler)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected when the authorized browser process is terminated.

    monkeypatch.setattr(_Page, "do_GET", delayed)
    with ThreadPoolExecutor(2) as pool:
        pending = pool.submit(runtime.act, "s", runtime.ref(grant), None, url + "blocked", "interrupt", lambda: False)
        try:
            assert entered.wait(3)
            stopped = pool.submit(runtime.stop, "s", target_id=grant.id)
            stopped.result(timeout=2)
            with pytest.raises(ComputerError):
                pending.result(timeout=2)
            assert runtime.store.get("s", grant.id).status == "paused"
        finally:
            release.set()
    assert requests == ["/blocked"]


def test_commit_failure_after_dispatch_preserves_unknown_outcome_and_does_not_replay(computer, monkeypatch) -> None:
    from sqlalchemy import event
    runtime, url, sessions, _snapshot = computer
    option = next(item for item in runtime.inventory() if item.target.kind == "browser")
    grant = runtime.share("s", ShareInput(inventory_id=option.inventory_id, permission="control"))
    requests = []
    original = _Page.do_GET

    def record(handler):
        if handler.path == "/commit-failure":
            requests.append(handler.path)
        original(handler)

    monkeypatch.setattr(_Page, "do_GET", record)
    metadata = sessions.kw["bind"]

    def fail_commit(_connection):
        raise RuntimeError("Injected metadata commit failure after browser submission")

    event.listen(metadata, "commit", fail_commit)
    try:
        with pytest.raises(ComputerError) as failure:
            runtime.act("s", runtime.ref(grant), None, url + "commit-failure", "commit-failure", lambda: False)
        assert failure.value.code == "COMPUTER_OUTCOME_UNKNOWN"
    finally:
        event.remove(metadata, "commit", fail_commit)
    assert requests == ["/commit-failure"]
    observed = runtime.observe("s", runtime.ref(grant), "after-unknown", lambda: False)
    assert observed.url == url + "commit-failure"
    assert observed.title == "DBFox computer fixture"
