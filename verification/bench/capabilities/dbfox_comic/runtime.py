"""Signed full Comic DLC and default product RunLoop; only model output is scripted."""
from contextlib import AbstractContextManager
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.orm import sessionmaker
from dbfox_dlc_api import DlcOperationContext, RequestedResourceRef, ToolKey
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.artifact import ArtifactRepository
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentRun, AgentSession, AgentToolInvocation, AgentTurn, Project
from engine.runtime_composition import (active_runtime_snapshot, authorize_project_resources,
    build_dlc_action_runs_host, build_product_run_loop, initialize_runtime_snapshot, set_active_runtime_snapshot)
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

OWNER = "dbfox.comic"
ROOT = Path(__file__).resolve().parents[4]


class ComicRuntime(AbstractContextManager):
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Comic author test publisher").digest())
        self.package = build_dlc_package_from_source(ROOT / "dlcs/dbfox.comic", private_key=key)
        archive = self.directory / "comic.dbfox-dlc"
        archive.write_bytes(self.package.archive_bytes)
        self.service = DlcPackageService(self.directory / "dlcs")
        self.service.trust_publisher_from_file(archive, expected_package_digest=self.package.package_digest, expected_publisher_key_id=self.package.publisher_fingerprint)
        self.service.install_from_file(archive)
        self.service.set_desired_enabled(OWNER, True)
        self.previous = active_runtime_snapshot()
        self.snapshot = initialize_runtime_snapshot(storage_root=self.service.storage_root)
        if self.snapshot.activation_failures:
            raise AssertionError(self.snapshot.activation_failures)
        self.engine = create_migrated_metadata_engine(self.directory / "metadata.sqlite")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def __exit__(self, *args):
        set_active_runtime_snapshot(self.previous)
        self.engine.dispose()

    def operation(self, project, name, payload):
        spec = self.snapshot.get_operation(OWNER, name).spec
        return spec.output_model.model_validate(spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(
            dlc_id=OWNER, operation_name=name, project_id=project,
            action_runs=build_dlc_action_runs_host(dlc_id=OWNER, project_id=project, snapshot=self.snapshot, session_factory=self.factory),
        ))).model_dump(mode="json")


class ComicScript:
    def __init__(self, case, runtime, registry, project):
        self.case, self.runtime, self.project = case, runtime, project
        self.names = {t.tool.name: registry.provider_name_for_key(ToolKey(owner_id=OWNER, local_name=t.tool.name)) for t in runtime.snapshot.tools if t.owner_id == OWNER}
        self.index, self.comic = 0, None
        self.clarifications, self.pending_answer = [], None
        self.seen, self.observations, self.requests, self.human = set(), [], [], []

    def resolve(self, value):
        if isinstance(value, str) and value == "$comic":
            return self.comic["id"]
        if isinstance(value, str) and value == "$version":
            return self.comic["version"]
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def stream(self, *, messages, tools, **kwargs):
        for item in messages:
            if item.get("type") != "function_call_output" or item["call_id"] in self.seen:
                continue
            self.seen.add(item["call_id"])
            value = json.loads(item["output"])
            self.observations.append({"call_id": item["call_id"], "output": value})
            if isinstance(value.get("facts", {}).get("comic"), dict):
                self.comic = value["facts"]["comic"]
        while self.index < len(self.case["steps"]) and self.case["steps"][self.index].get("human"):
            step = self.case["steps"][self.index]
            self.index += 1
            result = self.runtime.operation(self.project, "comics.apply", {**self.resolve(step["input"]), "request_id": uuid4().hex})
            self.human.append(result)
        if self.index == len(self.case["steps"]):
            yield from ScriptedProvider(answer_events(self.case.get("answer", "The explicitly requested Comic operations are complete."))).stream()
            return
        step = self.case["steps"][self.index]
        self.index += 1
        if "clarify" in step:
            before = self.runtime.operation(self.project, "comics.get", {"comic_id": self.comic["id"], "section": "pages"})["comic"]
            self.clarifications.append({"question": step["clarify"], "comic": before, "request_count": len(self.requests)})
            self.pending_answer = step["answer"]
            yield from ScriptedProvider(answer_events(step["clarify"])).stream()
            return
        name = self.names[step["tool"]]
        if name not in {tool.get("name") for tool in tools}:
            raise AssertionError(f"Tool is not discoverable: {name}")
        args = self.resolve(step["input"])
        self.requests.append({"id": f"step-{self.index}", "tool": step["tool"], "input": args, "success": step.get("success", True)})
        yield from ScriptedProvider(tool_call_events(call_id=f"step-{self.index}", tool_name=name, arguments=args)).stream()


def run_case(runtime, case):
    project, session = "comic-bench-" + uuid4().hex, "session-" + uuid4().hex
    with runtime.factory() as db:
        db.add(Project(id=project, name=case["id"]))
        db.flush()
        db.add(AgentSession(id=session, project_id=project, title=case["id"]))
        db.commit()
        refs = authorize_project_resources(db, project, (RequestedResourceRef(kind="dbfox.comic.library", id=project),), snapshot=runtime.snapshot)
        repo = SessionRepository(db)
        admission = repo.admit(session_id=session, resource_refs=refs, content=case["prompt"], idempotency_key=uuid4().hex,
            llm_credential_id="comic-scripted", api_base=None, model_name="scripted", request_payload={"suite": "comic"})
        lease = repo.claim(session_id=session, owner="comic-author-bench", ttl_seconds=600)
        repo.promote_next_input(lease=lease)
        db.commit()
    loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
    script = ComicScript(case, runtime, loop.registry, project)
    loop.model_factory = lambda settings: script
    run_ids = [admission.run_id]
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
        while script.pending_answer:
            answer, script.pending_answer = script.pending_answer, None
            with runtime.factory() as db:
                before = runtime.operation(project, "comics.get", {"comic_id": script.comic["id"], "section": "pages"})["comic"]
                script.clarifications[-1]["unchanged_until_answer"] = before == script.clarifications[-1]["comic"]
                refs = authorize_project_resources(db, project, (RequestedResourceRef(kind="dbfox.comic.document", id=script.comic["id"]),), snapshot=runtime.snapshot)
                repo = SessionRepository(db)
                admission = repo.admit(session_id=session, resource_refs=refs, content=answer, idempotency_key=uuid4().hex,
                    llm_credential_id="comic-scripted", api_base=None, model_name="scripted", request_payload={"suite": "comic"})
                lease = repo.claim(session_id=session, owner="comic-author-bench", ttl_seconds=600)
                repo.promote_next_input(lease=lease)
                db.commit()
            run_ids.append(admission.run_id)
            loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
    with runtime.factory() as db:
        run = db.get(AgentRun, admission.run_id)
        calls = db.query(AgentToolInvocation).filter(AgentToolInvocation.run_id.in_(run_ids)).all()
        turns = db.query(AgentTurn).filter(AgentTurn.run_id.in_(run_ids)).all()
        artifacts = [artifact for identity in run_ids for artifact in ArtifactRepository(db).list_for_run(identity)]
        actual = {call.provider_call_id: call for call in calls}
        checks = {"run_completed": all(str(db.get(AgentRun, identity).status) == "completed" for identity in run_ids), "all_steps": script.index == len(case["steps"]),
                  "exact_calls": len(calls) == len(script.requests), "owner": all(call.owner_id == OWNER for call in calls)}
        for request in script.requests:
            call = actual.get(request["id"])
            checks[request["id"]] = call is not None and ((call.status == "succeeded") == request["success"])
        checks["clarification_no_write"] = all(entry["unchanged_until_answer"] for entry in script.clarifications)
        budget = [json.loads(turn.context_snapshot_json).get("prompt_budget", {}) for turn in turns]
        checks["default_prompt_budget"] = all(b.get("estimated_prompt_tokens", 0) <= 32768 for b in budget)
        if script.comic:
            current = runtime.operation(project, "comics.get", {"comic_id": script.comic["id"], "section": "pages"})
            checks["page_count"] = current["comic"]["page_count"] == case["expected_pages"]
            checks["panel_count"] = current["comic"]["panel_count"] == case["expected_panels"]
            if "expected_version" in case:
                checks["expected_version"] = current["comic"]["version"] == case["expected_version"]
        else:
            checks["no_document"] = case.get("expect_no_document", False) and not runtime.operation(project, "comics.list", {})["comics"]
        evidence = {"checks": checks, "package_digest": runtime.package.package_digest, "run_id": admission.run_id, "run_ids": run_ids, "clarifications": script.clarifications,
            "run_status": str(run.status), "requests": script.requests, "observations": script.observations, "human": script.human,
            "calls": [{"id": c.provider_call_id, "status": c.status, "error": c.error_message} for c in calls],
            "turns": len(turns), "prompt_peak": max((b.get("estimated_prompt_tokens", 0) for b in budget), default=0),
            "artifacts": [{"id": a.id, "payload": a.payload, "provenance": a.provenance} for a in artifacts]}
    return evidence
