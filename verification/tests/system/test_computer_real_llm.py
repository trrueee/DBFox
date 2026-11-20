"""Opt-in local vision model task on a canvas-only challenge and real browser.

The challenge never enters the user prompt, DOM text or accessible node names.
The fixture server independently checks the submitted value. No paid API is used.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
from threading import Thread

import pytest

from verification.tests.system.test_computer_browser import computer as computer


@pytest.mark.real_llm
def test_real_local_vision_model_completes_the_browser_fixture(computer, tmp_path: Path) -> None:
    profile_path = os.environ.get("DBFOX_COMPUTER_TEST_PROFILE")
    if not profile_path:
        pytest.skip("Set DBFOX_COMPUTER_TEST_PROFILE to an existing verified local-model.json")
    from engine.agent.repositories.approval import ApprovalRepository
    from engine.agent.projection import conversation_snapshot
    from engine.agent.repositories.artifact import ArtifactRepository
    from engine.agent.repositories.session import SessionRepository
    from engine.computer.contracts import ShareInput
    from engine.llm.local_model import ManagedLocalModel
    from engine.models import AgentApproval, AgentRun
    from engine.runtime_composition import build_product_run_loop
    runtime, _url, sessions, snapshot = computer
    output = Path(os.environ.get("DBFOX_COMPUTER_EVIDENCE_DIR", str(tmp_path / "evidence"))).resolve()
    output.mkdir(parents=True, exist_ok=False)
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8-sig"))
    for field, name in (("state_dir", "model-state"), ("scratch_dir", "model-tmp")):
        directory = output / name
        directory.mkdir()
        profile[field] = str(directory)
    model_path = output / "local-model.json"
    model_path.write_text(json.dumps(profile), encoding="utf-8")
    model = ManagedLocalModel(model_path)
    challenge = "FOX-" + str(secrets.randbelow(900) + 100)
    submissions: list[dict] = []

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>DBFox 视觉夹具</title>
            <style>body{font:22px "Segoe UI",sans-serif;padding:50px;background:#f5f5f7;color:#1d1d1f}canvas{display:block;margin:24px 0;background:white;border-radius:16px}input,button{font:inherit;padding:12px;border:1px solid #ccc;border-radius:12px}button{background:#0071e3;color:white}output{display:block;margin-top:24px}</style>
            <h1>视觉验证码验收</h1><p>将蓝色卡片中的验证码填入下方，然后验证并保存。</p><canvas id="card" width="650" height="170" aria-label="验证码卡片"></canvas>
            <label>验证码 <input id="code" autocomplete="off"></label><button id="save">验证并保存</button><output>等待验证</output>
            <script>const c=document.getElementById('card').getContext('2d');c.fillStyle='#0066cc';c.font='bold 86px Segoe UI';c.fillText(CHALLENGE,32,112);
            document.getElementById('save').onclick=async()=>{const r=await fetch('/save',{method:'POST',body:JSON.stringify({value:document.getElementById('code').value})});const x=await r.json();document.querySelector('output').textContent=x.passed?'验证通过，已保存':'验证码不正确，请重新观察';};</script></html>'''.replace("CHALLENGE", json.dumps(challenge))
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            value = json.loads(self.rfile.read(min(4096, int(self.headers.get("Content-Length", "0")))))
            record = {"received": value.get("value"), "passed": value.get("value") == challenge}
            submissions.append(record)
            (output / "independent-submission.json").write_text(json.dumps(record), encoding="utf-8")
            data = json.dumps(record).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    Thread(target=server.serve_forever, daemon=True).start()
    address = f"http://127.0.0.1:{server.server_port}/"
    loop = None
    approvals = []
    try:
        target = next(item for item in runtime.inventory() if item.target.kind == "browser")
        grant = runtime.share("s", ShareInput(inventory_id=target.inventory_id, permission="control", duration_minutes=30))
        prompt = f"在已共享的受控浏览器中打开 {address}。读取页面蓝色卡片中的验证码，填入“验证码”输入框并点击“验证并保存”。检查页面显示验证通过后结束，并提供可检查的画面成果。只操作此夹具。"
        (output / "request.json").write_text(json.dumps({"prompt": prompt, "model": profile["model_name"], "digest": profile["model_digest"]}, ensure_ascii=False), encoding="utf-8")
        with sessions() as db:
            repository = SessionRepository(db)
            admission = repository.admit(session_id="s", resource_refs=(runtime.ref(grant),), content=prompt,
                idempotency_key="real-computer", llm_credential_id=None, api_base=None,
                model_name=profile["model_name"], request_payload={"model_digest": profile["model_digest"]})
            lease = repository.claim(session_id="s", owner="computer-real-model", ttl_seconds=900)
            repository.promote_next_input(lease=lease)
            db.commit()
        loop = build_product_run_loop(session_factory=sessions, snapshot=snapshot, local_model=model)
        for _ in range(12):
            loop.execute(lease=lease, run_id=admission.run_id)
            with sessions() as db:
                run = db.get(AgentRun, admission.run_id)
                print("local computer task:", run.status, flush=True)
                artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
                projection = conversation_snapshot(db, "s")
                final_messages = [item["payload"] for item in projection["items"]
                    if item["type"] == "message" and item["payload"].get("completion_disposition") is not None]
                delivery = projection["runs"][-1]["result"]
                report = {"run_status": run.status, "error": run.error_message, "submissions": submissions,
                    "final_messages": final_messages, "delivery": delivery,
                    "repair_attempt_count": run.repair_attempt_count,
                    "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts], "approvals": approvals}
                (output / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                from engine.computer.contracts import Observation
                for artifact in artifacts:
                    if artifact.type == "dbfox.computer.observation":
                        capture = Observation.model_validate(artifact.payload)
                        destination = output / (capture.id + ".png")
                        if not destination.exists():
                            destination.write_bytes(runtime.read_capture(capture))
                if run.status != "waiting_approval":
                    assert run.status == "completed", report
                    break
                pending = db.query(AgentApproval).filter_by(run_id=run.id, status="pending").one()
                action = json.loads(pending.requested_action_json)
                args = action["arguments"]
                # Explicit fixture-only test consent through real ApprovalRepository.
                approved = args.get("target_id") == grant.id and (args.get("url") == address or (
                    args.get("action") in {"click", "type_text", "focus", "key"} and len(args.get("text") or "") <= 30
                    and args.get("key") in (None, "ENTER", "CTRL+A", "TAB")))
                approvals.append({"approved": approved, "action": action})
                print("fixture approval:", args.get("action") or "navigate", approved, flush=True)
                ApprovalRepository(db).resolve(approval_id=pending.id, expected_version=0, approved=approved, actor="user")
                lease = SessionRepository(db).claim(session_id="s", owner="computer-real-model-resume", ttl_seconds=900)
                SessionRepository(db).bind_run(lease=lease, run_id=admission.run_id)
                db.commit()
        assert any(item["passed"] for item in submissions), report
        assert any(artifact.type == "dbfox.computer.observation" for artifact in artifacts)
        assert final_messages and final_messages[-1]["content"].strip(), report
        captures = {artifact.id for artifact in artifacts if artifact.type == "dbfox.computer.observation"}
        assert delivery["completion_disposition"] == "complete", report
        assert delivery["selection_suggestion"]["artifact_id"] in captures, report
    finally:
        if loop:
            loop.close()
        model.close()
        server.shutdown()
        server.server_close()
