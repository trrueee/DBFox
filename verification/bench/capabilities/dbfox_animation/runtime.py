"""Real signed payload, migrated metadata and production RunLoop; scripted model only."""
from contextlib import AbstractContextManager
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.orm import sessionmaker
from dbfox_dlc_api import DlcOperationContext, RequestedResourceRef, ToolKey
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.agent.completion import CompletionGate
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.models import AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import (active_runtime_snapshot, authorize_project_resources, build_attempt_resource_resolver,
    build_default_completion_policy, build_product_tool_registry, default_capability_guidance,
    default_context_contributors, initialize_runtime_snapshot, set_active_runtime_snapshot)
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

OWNER = "dbfox.animation"
ROOT = Path(__file__).resolve().parents[4]


class AnimationRuntime(AbstractContextManager):
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Animation author verification publisher").digest())
        self.package = build_dlc_package_from_source(ROOT / "dlcs" / OWNER, private_key=key)
        archive = self.directory / "animation.dbfox-dlc"
        archive.write_bytes(self.package.archive_bytes)
        self.service = DlcPackageService(self.directory / "dlcs")
        self.service.trust_publisher_from_file(archive, expected_package_digest=self.package.package_digest,
            expected_publisher_key_id=self.package.publisher_fingerprint)
        self.service.install_from_file(archive)
        self.service.select_package(OWNER, self.package.package_digest)
        self.service.set_desired_enabled(OWNER, True)
        self.previous = active_runtime_snapshot()
        self.snapshot = initialize_runtime_snapshot(storage_root=self.service.storage_root)
        if self.snapshot.activation_failures:
            raise AssertionError(self.snapshot.activation_failures)
        self.engine = create_migrated_metadata_engine(self.directory / "metadata.sqlite")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.registry = build_product_tool_registry(self.snapshot)

    def __exit__(self, *args):
        set_active_runtime_snapshot(self.previous)
        self.engine.dispose()

    def operation(self, project_id, name, payload):
        contribution = self.snapshot.get_operation(OWNER, name)
        spec = contribution.spec
        result = spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(dlc_id=OWNER, operation_name=name, project_id=project_id))
        return spec.output_model.model_validate(result).model_dump(mode="json")

    def seed(self, project_id, large=False):
        with self.factory() as db:
            db.add(Project(id=project_id, name="Animation QA " + project_id))
            db.commit()
        summary = self.operation(project_id, "animations.create", {"title": "Fox gesture" if not large else "2048 key timing study", "request_id": uuid4().hex})["animation"]
        operations = [
            {"kind":"target_create","target":{"id":"fox","name":"Fox"}},
            {"kind":"track_create","track":{"id":"move","name":"位置 X","target_id":"fox","property":"position.x"}},
        ]
        if large:
            for offset in range(0,2048,256):
                operations.append({"kind":"keyframe_add","keyframes":[{"id":f"k{index}","track_id":"move","tick":index*3,"value":(index%80)/10} for index in range(offset,offset+256)]})
        else:
            operations.extend([
                {"kind":"keyframe_add","keyframes":[{"id":"begin","track_id":"move","tick":0,"value":0},{"id":"contact","track_id":"move","tick":4000,"value":6},{"id":"settle","track_id":"move","tick":8000,"value":0}]},
                {"kind":"easing_set","curve":{"id":"ease","kind":"bezier","x1":.25,"y1":0,"x2":.75,"y2":1},"keyframe_ids":["begin"]},
                {"kind":"clip_create","clip":{"id":"gesture","name":"Gesture","track_ids":["move"],"start":0,"end":8000}},
                {"kind":"marker_set","marker":{"id":"beat","name":"Contact","tick":4000}},
            ])
        for operation in operations:
            summary = self.operation(project_id,"animations.apply",{"animation_id":summary["id"],"expected_version":summary["version"],"operation":operation,"request_id":uuid4().hex})["animation"]
        return summary


class Script:
    def __init__(self, runtime, project_id, steps):
        self.runtime, self.project_id, self.steps = runtime, project_id, steps
        self.index, self.observations, self.summary = 0, {}, None
        self.max_output = 0
        self.max_prompt = 0
        self.names = {item.tool.name: runtime.registry.provider_name_for_key(ToolKey(owner_id=OWNER, local_name=item.tool.name)) for item in runtime.snapshot.tools if item.owner_id == OWNER}

    def resolve(self, value):
        if value == "$id":
            return self.summary["id"]
        if value == "$version":
            return self.summary["version"]
        if isinstance(value, dict):
            return {key:self.resolve(item) for key,item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def stream(self, *, messages, tools, **kwargs):
        self.max_prompt = max(self.max_prompt, len(json.dumps(messages).encode()))
        for item in messages:
            if item.get("type") == "function_call_output" and item["call_id"] not in self.observations:
                self.max_output = max(self.max_output, len(item["output"].encode()))
                observation = json.loads(item["output"])
                self.observations[item["call_id"]] = observation
                if "animation" in observation.get("facts", {}):
                    self.summary = observation["facts"]["animation"]
        if self.index >= len(self.steps):
            yield from ScriptedProvider(answer_events("Animation verification complete.")).stream()
            return
        step = self.steps[self.index]
        self.index += 1
        if "human" in step:
            # Human goes through the same public operation, while the model deliberately
            # retains its last observed version until a successful re-inspection.
            payload = self.resolve(step["human"])
            self.runtime.operation(self.project_id,"animations.apply",{**payload,"request_id":uuid4().hex})
            yield from self.stream(messages=messages,tools=tools)
            return
        if "answer" in step:
            yield from ScriptedProvider(answer_events(step["answer"])).stream()
            return
        name = self.names[step["tool"]]
        assert name in {tool["name"] for tool in tools}, name
        yield from ScriptedProvider(tool_call_events(call_id=f"step-{self.index}",tool_name=name,arguments=self.resolve(step["arguments"]))).stream()


def run_case(runtime, case):
    project_id, session_id = uuid4().hex, uuid4().hex
    with runtime.factory() as db:
        db.add(Project(id=project_id,name=case["id"]))
        db.flush()
        db.add(AgentSession(id=session_id,project_id=project_id,title=case["id"]))
        db.commit()
        refs = authorize_project_resources(db,project_id,(RequestedResourceRef(kind="dbfox.animation.library",id=project_id),),snapshot=runtime.snapshot)
        sessions = SessionRepository(db)
        admission = sessions.admit(session_id=session_id,resource_refs=refs,content=case["prompt"],idempotency_key=uuid4().hex,
            llm_credential_id="animation-scripted",api_base=None,model_name="scripted",request_payload={"suite":"animation"})
        lease = sessions.claim(session_id=session_id,owner="animation-bench",ttl_seconds=600)
        sessions.promote_next_input(lease=lease)
        db.commit()
    script = Script(runtime,project_id,case["steps"])
    snapshot = runtime.snapshot
    loop = RunLoop(session_factory=runtime.factory,model_factory=lambda settings:script,registry=runtime.registry,
        context_contributors=default_context_contributors(snapshot),capability_guidance=default_capability_guidance(snapshot),
        resource_providers=snapshot.resource_providers,resource_resolver=build_attempt_resource_resolver(snapshot=snapshot),
        artifact_payload_contract_resolver=lambda kind,version:snapshot.get_artifact_contract(kind,version).validator,
        runtime_snapshot_id=snapshot.snapshot_id,completion=CompletionGate(build_default_completion_policy(snapshot)),
        definition=AgentDefinition(limits=RunLimits(max_turns=100,max_tool_invocations=120,max_repair_attempts=10,
            finalization_turn_reserve=1,finalization_tool_reserve=1,max_prompt_tokens=128000)),live_stream=LiveStreamHub())
    try:
        loop.execute(lease=lease,run_id=admission.run_id)
    finally:
        loop.close()
    with runtime.factory() as db:
        run = db.get(AgentRun,admission.run_id)
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).order_by(AgentToolInvocation.created_at).all()
        actual = [{"tool":item.tool_name,"call_id":item.provider_call_id,"status":item.status,"error_code":item.error_code,"owner":item.owner_id,"package_digest":item.package_digest,
            "attempts":item.attempt_count,"input":json.loads(item.input_json),"resource_refs":json.loads(item.resource_refs_json)} for item in invocations]
    expected = [step.get("success",True) for step in case["steps"] if "tool" in step]
    passed = str(run.status) == "completed" and len(actual) == len(expected) and all((item["status"] == "succeeded") == success for item,success in zip(actual,expected))
    final = {}
    if script.summary:
        for section in ("targets","tracks","keyframes","curves","clips","markers"):
            final[section] = []
            offset = 0
            while True:
                page = runtime.operation(project_id,"animations.get",{"animation_id":script.summary["id"],"section":section,"offset":offset,"limit":100})
                final[section].extend(page["items"])
                final["animation"] = page["animation"]
                if not page["has_more"]:
                    break
                offset = page["next_offset"]
    return {"case_id":case["id"],"category":case["category"],"passed":passed,"run_status":str(run.status),"invocations":actual,"final_document":final,
        "observations":script.observations,"max_observation_bytes":script.max_output,"max_prompt_bytes":script.max_prompt,
        "package_digest":runtime.package.package_digest,"animation":script.summary}
