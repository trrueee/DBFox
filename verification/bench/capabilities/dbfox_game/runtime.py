"""Full signed Game package, production factory and deterministic domain scoring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import DlcOperationContext, RequestedResourceRef, ToolKey
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import active_runtime_snapshot, authorize_project_resources, build_product_run_loop, build_product_tool_registry, set_active_runtime_snapshot
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OWNER = "dbfox.game"


class GameBench:
    def __init__(self, directory: Path):
        key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Game capability verification publisher").digest())
        package = build_dlc_package_from_source(ROOT / "dlcs" / OWNER, private_key=key)
        archive = directory / "game.dbfox-dlc"
        archive.write_bytes(package.archive_bytes)
        self.package_digest = package.package_digest
        self.service = DlcPackageService(directory / "dlcs")
        self.service.trust_publisher_from_file(archive, expected_package_digest=package.package_digest, expected_publisher_key_id=package.publisher_fingerprint)
        self.service.install_from_file(archive)
        self.service.set_desired_enabled(OWNER, True)
        self.snapshot = ContributionCompiler(self.service.storage_root).compile(built_ins=BuiltinContributionSet())
        assert not self.snapshot.activation_failures, self.snapshot.activation_failures
        self.engine = create_migrated_metadata_engine(directory / "metadata.sqlite")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.registry = build_product_tool_registry(self.snapshot)
        self.previous = active_runtime_snapshot()
        set_active_runtime_snapshot(self.snapshot)

    def close(self):
        set_active_runtime_snapshot(self.previous)
        self.engine.dispose()

    def operation(self, project, name, payload):
        spec = self.snapshot.get_operation(OWNER, name).spec
        result = spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(dlc_id=OWNER, operation_name=name, project_id=project))
        return result.model_dump(mode="json", exclude_none=True)

    def run(self, project, game_id, steps, prompt):
        session = str(uuid4())
        calls, observed = [], {}
        outer = self

        class Provider:
            def stream(self, *, messages, tools, **kwargs):
                for message in messages:
                    if message.get("type") == "function_call_output":
                        observed[message["call_id"]] = json.loads(message["output"])
                if len(calls) >= len(steps):
                    yield from ScriptedProvider(answer_events("Verification task completed. Ambiguous requests require clarification before modification.")).stream()
                    return
                name, arguments, succeeds = steps[len(calls)](observed) if callable(steps[len(calls)]) else steps[len(calls)]
                wire = outer.registry.provider_name_for_key(ToolKey(OWNER, name))
                assert wire in {tool["name"] for tool in tools}, name
                identity = f"call-{len(calls)}"
                calls.append((identity, succeeds))
                yield from ScriptedProvider(tool_call_events(call_id=identity, tool_name=wire, arguments=arguments)).stream()

        with self.factory() as db:
            db.add(AgentSession(id=session, project_id=project))
            db.commit()
            requested = RequestedResourceRef(kind="dbfox.game.project" if game_id else "dbfox.game.library", id=game_id or project)
            refs = authorize_project_resources(db, project, (requested,), snapshot=self.snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id=session, resource_refs=refs, content=prompt, idempotency_key=session, llm_credential_id="scripted", api_base=None, model_name="scripted", request_payload={})
            lease = sessions.claim(session_id=session, owner="game-bench", ttl_seconds=600)
            sessions.promote_next_input(lease=lease)
            db.commit()
        loop = build_product_run_loop(session_factory=self.factory, snapshot=self.snapshot)
        loop.model_factory = lambda settings: Provider()
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
        assert len(calls) == len(steps), (len(calls), len(steps))
        for identity, succeeds in calls:
            assert (observed[identity]["status"] == "succeeded") is succeeds, observed[identity]
        with self.factory() as db:
            run = db.get(AgentRun, admission.run_id)
            assert run.status == "completed", run.status
            invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
            assert len(invocations) == len(calls)
            for artifact in ArtifactRepository(db).list_for_run(admission.run_id):
                producer = next(item for item in invocations if item.id == artifact.provenance["tool_invocation_id"])
                assert artifact.resource_refs[0].model_dump() in json.loads(producer.resource_refs_json)
        return observed, admission.run_id, len(calls)

    def case(self, case):
        category = case["id"]
        project = str(uuid4())
        with self.factory() as db:
            db.add(Project(id=project, name=category))
            db.commit()
        run_ids, count = [], 0
        if category == "simple_creation":
            steps = [("game_create", {"title": "Fox survival", "expected_library_version": 1}, True), lambda seen: ("game_inspect", {"game_id": seen["call-0"]["facts"]["game"]["id"]}, True)]
            seen, identity, count = self.run(project, None, steps, case["requirement"])
            game_id = seen["call-0"]["facts"]["game"]["id"]
            run_ids.append(identity)
        else:
            created = self.operation(project, "games.create", {"title": "Fox survival", "expected_library_version": 1, "request_id": str(uuid4())})
            game_id = created["game"]["id"]
            head = lambda: self.operation(project, "games.head", {"game_id": game_id})["game"]
            get = lambda section, **extra: self.operation(project, "games.get", {"game_id": game_id, "version": head()["version"], "section": section, **extra})
            scene = get("summary")["metadata"]["initial_scene_id"]
            def human(operations):
                return self.operation(project, "games.apply", {"game_id": game_id, "expected_version": head()["version"], "request_id": str(uuid4()), "operations": operations})
            # Reuse the product's actual fox/slime example operations. The suite
            # does not maintain a second game model or an easier mock scene.
            script = "import {survivalOperations} from './dlcs/dbfox.game/frontend/presets.js'; console.log(JSON.stringify(survivalOperations(process.argv[1])));"
            example = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script, scene], cwd=ROOT, text=True, encoding="utf-8"))
            human(example)
            n = 125 if category in {"large_document", "bounded_context"} else 24 if category == "creative_stress" else 0
            if n:
                scenery = [{"scene_id": {"id": scene}, "name": f"Scenery {i}", "tags": ["scenery"], "components": [{"kind": "transform", "x": 80 + i % 20 * 30, "y": 80 + i // 20 * 35}, {"kind": "visual", "color": "#315e49"}]} for i in range(n)]
                human([{"kind": "entity_create", "entities": scenery}])
            before = head()
            fox = next(item for item in get("entities", limit=50)["items"] if "player" in item["tags"])
            fox_id = fox["id"]
            transform = lambda dx: {"kind": "entities_transform", "entity_ids": [{"id": fox_id}], "dx": dx, "dy": 0}
            modify = lambda ops, version=None, succeeds=True: ("game_modify", {"game_id": game_id, "expected_version": head()["version"] if version is None else version, "operations": ops}, succeeds)
            inspect = ("game_inspect", {"game_id": game_id, "section": "entities", "limit": 1}, True)
            rename = {"kind": "game_rename", "title": "Forest survival"}
            invalid = {"kind": "entity_delete", "entity_ids": [{"id": str(uuid4())}], "cascade": True}
            steps = []
            unchanged = False
            if category == "incremental_modification": steps = [modify([rename])]
            elif category == "multi_stage_creation":
                steps = [inspect, modify([{"kind": "rule_create", "rule": {"scene_id": {"id": scene}, "name": "Survive sixty seconds", "trigger": {"kind": "elapsed_tick", "at_tick": 3600}, "actions": [{"kind": "finish", "result": "won"}]}}])]
            elif category == "invalid_recovery": steps = [modify([invalid], succeeds=False), modify([rename])]
            elif category == "inspect_before_edit": steps = [inspect, modify([transform(12)])]
            elif category == "stale_version":
                def stale(_):
                    human([transform(7)])
                    return modify([rename], version=before["version"], succeeds=False)
                steps = [inspect, stale, inspect, lambda _: modify([rename])]
            elif category == "no_op": steps, unchanged = [modify([{"kind": "game_rename", "title": before["title"]}])], True
            elif category == "ambiguous_request": unchanged = True
            elif category in {"large_document", "bounded_context"}: steps, unchanged = [inspect], True
            elif category == "human_then_agent":
                human([transform(7)])
                steps = [inspect, modify([transform(12)])]
            elif category == "negative_no_modification": steps, unchanged = [modify([invalid], succeeds=False)], True
            elif category == "creative_stress":
                # Each user request receives its own production Run. An ambiguous
                # request ends with clarification, then a later request continues.
                for index in range(10):
                    version = head()["version"]
                    if index == 0: planned = [modify([{"kind": "entity_create", "entities": [{"name": "Lantern", "scene_id": {"id": scene}, "tags": ["decoration"]}]}])]
                    elif index == 1:
                        lantern = next(item for item in get("entities", limit=50)["items"] if item["name"] == "Lantern")
                        planned = [modify([{"kind": "entity_delete", "entity_ids": [{"id": lantern["id"]}], "cascade": True}])]
                    elif index == 2: planned = [modify([transform(12)])]
                    elif index == 3: planned = [modify([rename, {"kind": "entities_transform", "entity_ids": [{"id": item["id"]} for item in get("entities", limit=50)["items"]], "dx": 20, "dy": 20}])]
                    elif index == 4:
                        behavior = get("behaviors")["items"][0]
                        planned = [modify([{"kind": "behavior_modify", "behavior_id": {"id": behavior["id"]}, "behavior": {"kind": "player_control", "entity_id": {"id": fox_id}, "speed": 260}}])]
                    elif index == 5: planned = []
                    elif index == 6: planned = [modify([transform(100)], version=1, succeeds=False)]
                    elif index == 7:
                        human([transform(7)])
                        planned = [inspect, modify([transform(12)])]
                    elif index == 8: planned = [("game_undo", {"game_id": game_id, "expected_version": version, "target_version": version - 1}, True)]
                    else: planned = [modify([{"kind": "game_rename", "title": "Forest survival — refined"}])]
                    _, identity, used = self.run(project, game_id, planned, f"Creative change {index + 1}: {case['requirement']}")
                    run_ids.append(identity); count += used
                    if index in {5, 6}: assert head()["version"] == version
                assert len(run_ids) == 10
                assert head()["title"] == "Forest survival — refined"
            if category != "creative_stress":
                seen, identity, count = self.run(project, game_id, steps, case["requirement"])
                run_ids.append(identity)
                if category in {"large_document", "bounded_context"}:
                    facts = seen["call-0"]["facts"]
                    assert len(facts["items"]) == 1 and facts["total"] == 128
                    assert len(json.dumps(facts)) < 10000
                if unchanged: assert head() == before
                if category in {"stale_version", "human_then_agent"}:
                    current = next(item for item in get("entities", limit=50)["items"] if item["id"] == fox_id)
                    assert current["components"][0]["spec"]["x"] == fox["components"][0]["spec"]["x"] + (7 if category == "stale_version" else 19)
            assert any(item["id"] == fox_id for item in get("entities", limit=50)["items"])
        final = self.operation(project, "games.head", {"game_id": game_id})["game"]
        return TrialOutcome(suite_id="capability.dbfox-game.scripted", case_id=category, repetition=1, verdict="pass", metrics={"task.success_rate": 1, "runtime.tool_calls": count, "game.final_version": final["version"]}, evidence={"run_ids": run_ids, "package_digest": self.package_digest, "final": final, "factory": "build_product_run_loop", "budget_override": False})


def run_bench(output: Path):
    manifest = load_suite_manifest(HERE / "suite.json")
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    results = []
    with tempfile.TemporaryDirectory(prefix="dbfox-game-bench-") as directory:
        bench = GameBench(Path(directory))
        try:
            for case in cases:
                try:
                    outcome = bench.case(case)
                except Exception as error:
                    outcome = TrialOutcome(suite_id=manifest.suite_id, case_id=case["id"], repetition=1, verdict="fail", metrics={"task.success_rate": 0}, failed_checks=(str(error)[:1000] or type(error).__name__,))
                results.append(outcome)
        finally:
            bench.close()
    return write_suite_report(output_dir=output, manifest=manifest, outcomes=tuple(results))
