"""Signed Voxel package + production RunLoop; only the model boundary is scripted."""
from __future__ import annotations

from contextlib import AbstractContextManager
import hashlib
import json
from pathlib import Path
import tempfile
import time
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import DlcOperationContext, RequestedResourceRef, ToolKey
from engine.agent.completion import CompletionGate
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentMessage, AgentObservationRecord, AgentRun, AgentSession, AgentToolInvocation, AgentTurn, Project
from engine.runtime_composition import (
    active_runtime_snapshot, authorize_project_resources, build_attempt_resource_resolver,
    build_default_completion_policy, build_product_tool_registry, default_capability_guidance,
    default_context_contributors, initialize_runtime_snapshot, set_active_runtime_snapshot,
)
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

from .schema import VoxelCase, load_cases

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "dlcs" / "dbfox.voxel"
OWNER = "dbfox.voxel"


class VoxelRuntime(AbstractContextManager):
    """Director-authored suite fixture installs the real payload, including frontend/vendor bytes."""

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Voxel deterministic capability publisher").digest())
        self.package = build_dlc_package_from_source(SOURCE, private_key=key)
        archive = directory / "voxel.dbfox-dlc"
        archive.write_bytes(self.package.archive_bytes)
        self.service = DlcPackageService(directory / "dlcs")
        self.service.trust_publisher_from_file(archive, expected_package_digest=self.package.package_digest,
            expected_publisher_key_id=self.package.publisher_fingerprint)
        self.service.install_from_file(archive)
        self.service.set_desired_enabled(OWNER, True)
        self.previous = active_runtime_snapshot()
        self.snapshot = initialize_runtime_snapshot(storage_root=self.service.storage_root)
        if self.snapshot.activation_failures:
            raise AssertionError(self.snapshot.activation_failures)
        self.engine = create_migrated_metadata_engine(directory / "metadata.sqlite")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.registry = build_product_tool_registry(self.snapshot)

    def __exit__(self, *args):
        set_active_runtime_snapshot(self.previous)
        self.engine.dispose()

    def operation(self, project_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        contribution = self.snapshot.get_operation(OWNER, name)
        assert contribution is not None
        spec = contribution.spec
        value = spec.handler(spec.input_model.model_validate(payload),
            DlcOperationContext(dlc_id=OWNER, operation_name=name, project_id=project_id))
        return spec.output_model.model_validate(value).model_dump(mode="json")

    def document(self, project_id: str, world_id: str, version: int) -> dict[str, Any]:
        result = self.operation(project_id, "worlds.get", {"world_id": world_id, "version": version})
        result["chunks"] = {}
        cursor = None
        while True:
            page = self.operation(project_id, "worlds.chunks", {"world_id": world_id, "version": version,
                "limit": 16, "after": cursor})
            for chunk in page["chunks"]:
                result["chunks"][(chunk["layer_id"], *chunk["coord"])] = bytes(chunk["values"] or [0] * 4096)
            cursor = page["next_after"]
            if cursor is None:
                return result


class VoxelScript:
    """Model state contains only actual provider-visible observations, never store reads."""

    def __init__(self, case: VoxelCase, human_edit, tool_names):
        self.case = case
        self.human_edit = human_edit
        self.tool_names = tool_names
        self.index = 0
        self.observations: dict[str, dict[str, Any]] = {}
        self.voxel: dict[str, Any] | None = None
        self.requests: list[dict[str, Any]] = []
        self.human_results: list[dict[str, Any]] = []
        self.max_observation_bytes = 0
        self.max_prompt_bytes = 0

    def resolve(self, value):
        if isinstance(value, str) and value.startswith("$"):
            if value == "$world_id":
                assert self.voxel is not None, "No voxel ID has been observed"
                return self.voxel["world_id"]
            if value == "$version":
                assert self.voxel is not None, "No version has been observed"
                return self.voxel["version"]
            label, *path = value[1:].split(".")
            observed: Any = self.observations[label]["facts"]
            for key in path:
                observed = observed[int(key)] if isinstance(observed, list) else observed[key]
            return observed
        if isinstance(value, dict):
            return {key: self.resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def stream(self, *, messages, tools, **kwargs):
        self.max_prompt_bytes = max(self.max_prompt_bytes, len(json.dumps(messages).encode()))
        for item in messages:
            if item.get("type") != "function_call_output":
                continue
            call_id = item["call_id"]
            if call_id in self.observations:
                continue
            encoded = item["output"]
            value = json.loads(encoded)
            self.max_observation_bytes = max(self.max_observation_bytes, len(encoded.encode()))
            self.observations[call_id] = value
            facts = value.get("facts", {})
            if all(key in facts for key in ("world_id", "version", "content_hash")):
                self.voxel = facts
        if self.index >= len(self.case.steps):
            yield from ScriptedProvider(answer_events("Voxel verification complete; no additional changes requested.")).stream()
            return
        step = self.case.steps[self.index]
        self.index += 1
        while step.kind == "human":
            # External user action. Its result is recorded as evidence, never made a model observation.
            payload = self.resolve(step.arguments)
            result = self.human_edit(step.tool, payload)
            self.human_results.append({"step": step.id, "result": result})
            step = self.case.steps[self.index]
            self.index += 1
        if step.kind == "answer":
            yield from ScriptedProvider(answer_events(step.text)).stream()
            return
        arguments = self.resolve(step.arguments)
        wire_name = self.tool_names[step.tool]
        assert wire_name in {tool["name"] for tool in tools}, f"Voxel tool is not discoverable: {wire_name}"
        self.requests.append({"id": step.id, "tool": step.tool, "arguments": arguments})
        yield from ScriptedProvider(tool_call_events(call_id=step.id, tool_name=wire_name, arguments=arguments)).stream()


def _run_segment(runtime: VoxelRuntime, case: VoxelCase, *, repetition: int,
                 script: VoxelScript | None = None, project_id: str | None = None,
                 session_id: str | None = None):
    project_id = project_id or f"voxel-bench-{uuid4().hex}"
    session_id = session_id or f"voxel-session-{uuid4().hex}"
    with runtime.factory() as db:
        if script is None:
            db.add(Project(id=project_id, name=project_id))
            db.flush()
            db.add(AgentSession(id=session_id, project_id=project_id, title=case.prompt[:120]))
            db.commit()
        requested = (RequestedResourceRef(kind="dbfox.voxel.world", id=script.voxel["world_id"]),) if script and script.voxel else (
            RequestedResourceRef(kind="dbfox.voxel.library", id=project_id),)
        refs = authorize_project_resources(db, project_id, requested, snapshot=runtime.snapshot)
        sessions = SessionRepository(db)
        prompt = case.prompt if script is None else "Clarification: keep the shrine as it is. Proceed only with the specified targeted operations, inspect after human changes, then undo, correct and refine."
        admission = sessions.admit(session_id=session_id, resource_refs=refs, content=prompt,
            idempotency_key=f"{case.case_id}:{repetition}:{uuid4().hex}", llm_credential_id="voxel-scripted",
            api_base=None, model_name="scripted", request_payload={"suite": "capability.dbfox-voxel.scripted"})
        lease = sessions.claim(session_id=session_id, owner="voxel-bench", ttl_seconds=600)
        assert lease is not None
        sessions.promote_next_input(lease=lease)
        db.commit()
    if script is None:
        script = VoxelScript(case, lambda name, payload: runtime.operation(project_id, name, payload),
            {item.tool.name: runtime.registry.provider_name_for_key(ToolKey(owner_id=OWNER, local_name=item.tool.name))
             for item in runtime.snapshot.tools if item.owner_id == OWNER})
    snap = runtime.snapshot
    loop = RunLoop(session_factory=runtime.factory, model_factory=lambda settings: script,
        registry=runtime.registry, context_contributors=default_context_contributors(snap),
        capability_guidance=default_capability_guidance(snap), resource_providers=snap.resource_providers,
        resource_resolver=build_attempt_resource_resolver(snapshot=snap),
        artifact_payload_contract_resolver=lambda kind, version: snap.get_artifact_contract(kind, version).validator,
        runtime_snapshot_id=snap.snapshot_id, completion=CompletionGate(build_default_completion_policy(snap)),
        definition=AgentDefinition(limits=RunLimits(max_turns=100, max_tool_invocations=200,
            max_repair_attempts=20, finalization_turn_reserve=1, finalization_tool_reserve=1,
            max_prompt_tokens=128_000)), live_stream=LiveStreamHub())
    started = time.perf_counter()
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
    with runtime.factory() as db:
        run = db.get(AgentRun, admission.run_id)
        answer = db.get(AgentMessage, admission.assistant_message_id)
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).order_by(AgentToolInvocation.created_at).all()
        observations = db.query(AgentObservationRecord).filter_by(run_id=admission.run_id).order_by(AgentObservationRecord.sequence).all()
        artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
        turns = db.query(AgentTurn).filter_by(run_id=admission.run_id).all()
        voxel_fragments = [[fragment for fragment in json.loads(turn.context_snapshot_json).get("context_fragments", [])
            if fragment.get("source_id") == "dbfox.voxel"] for turn in turns]
        evidence = {
            "project_id": project_id, "session_id": session_id, "run_id": admission.run_id,
            "run_status": str(run.status), "answer": str(answer.content or ""),
            "package_digest": runtime.package.package_digest,
            "invocations": [{"id": item.id, "call_id": item.provider_call_id, "tool": item.tool_name,
                "run_id": item.run_id, "session_id": item.session_id,
                "owner": item.owner_id, "package_digest": item.package_digest, "status": item.status, "attempts": item.attempt_count,
                "error_code": item.error_code, "error_message": item.error_message,
                "resource_refs": json.loads(item.resource_refs_json), "input": json.loads(item.input_json)} for item in invocations],
            "observations": [{"call_id": next(item.provider_call_id for item in invocations if item.id == obs.tool_invocation_id),
                "status": obs.status, "facts": json.loads(obs.facts_json), "model_output": json.loads(obs.model_output_json),
                "artifacts": json.loads(obs.artifact_ids_json)} for obs in observations],
            "artifacts": [{"id": item.id, "run_id": item.run_id, "session_id": item.session_id,
                "type": item.type, "version": item.version, "payload": item.payload,
                "resource_refs": [ref.model_dump(mode="json") for ref in item.resource_refs]} for item in artifacts],
            "human_edits": script.human_results, "provider_observations": dict(script.observations),
            "max_observation_bytes": script.max_observation_bytes, "max_prompt_bytes": script.max_prompt_bytes,
            "turns": len(turns), "voxel_contexts": voxel_fragments,
            "latency_ms": (time.perf_counter() - started) * 1000,
        }
    return evidence, script


def run_case(runtime: VoxelRuntime, case: VoxelCase, *, repetition: int = 1) -> TrialOutcome:
    from .scoring import score_case
    evidence, script = _run_segment(runtime, case, repetition=repetition)
    evidence["runs"] = [{"id": evidence["run_id"], "status": evidence["run_status"], "answer": evidence["answer"]}]
    while script.index < len(case.steps) and evidence["run_status"] == "completed":
        previous_index = script.index
        continuation, script = _run_segment(runtime, case, repetition=repetition, script=script,
            project_id=evidence["project_id"], session_id=evidence["session_id"])
        assert script.index > previous_index, "Continuation made no scripted progress"
        evidence["runs"].append({"id": continuation["run_id"], "status": continuation["run_status"], "answer": continuation["answer"]})
        for field in ("invocations", "observations", "artifacts", "voxel_contexts"):
            evidence[field].extend(continuation[field])
        for field in ("turns", "latency_ms"):
            evidence[field] += continuation[field]
        for field in ("human_edits", "provider_observations", "run_status", "answer", "max_observation_bytes", "max_prompt_bytes"):
            evidence[field] = continuation[field]
    return score_case(runtime, case, evidence, repetition)


def run_voxel_bench(*, output_dir: Path, repetitions: int = 1, case_ids: frozenset[str] = frozenset()) -> dict[str, Any]:
    manifest = load_suite_manifest(HERE / "suite.json")
    if not 1 <= repetitions <= manifest.execution.max_repetitions:
        raise ValueError("Invalid repetition count")
    cases = [case for case in load_cases(HERE / manifest.dataset).cases if not case_ids or case.case_id in case_ids]
    if not cases:
        raise ValueError("No Voxel cases selected")
    # Runtime databases are external disposable verification state, not report artifacts.
    workspace = Path(tempfile.mkdtemp(prefix="dbfox-voxel-bench-"))
    with VoxelRuntime(workspace) as runtime:
        outcomes = tuple(run_case(runtime, case, repetition=rep) for case in cases for rep in range(1, repetitions + 1))
        summary = write_suite_report(output_dir, manifest=manifest, outcomes=outcomes)
        for outcome in outcomes:
            if outcome.case_id == "fox-shrine-stress" and outcome.verdict == "pass":
                from .scoring import export_stress
                export_stress(runtime, outcome, output_dir)
    summary["external_runtime_directory"] = str(workspace)
    return summary
