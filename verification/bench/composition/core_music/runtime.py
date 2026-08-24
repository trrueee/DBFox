"""Core + Music scripted benchmark over one real production RunLoop."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from engine.tools.runtime import provider_tool_name

from verification.bench.composition.core_music.schema import CoreMusicCase, load_cases
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.scripted_provider import answer_events, tool_call_events
from verification.testkit.system_dlc_fixture import build_isolated_system_dlc_bundle


HERE = Path(__file__).resolve().parent
COMPOSE_PIANO_TOOL = provider_tool_name("dbfox.music", "music_compose_piano")


def _output(messages: list[dict[str, Any]], call_id: str) -> dict[str, Any]:
    for item in messages:
        if item.get("type") == "function_call_output" and item.get("call_id") == call_id:
            value = item.get("output")
            if isinstance(value, dict):
                return value
            try:
                decoded = json.loads(str(value or "{}"))
            except json.JSONDecodeError:
                return {}
            return decoded if isinstance(decoded, dict) else {}
    return {}


def _draft(case: CoreMusicCase) -> dict[str, Any]:
    notes = []
    for measure in range(1, case.measure_count + 1):
        degree = (measure - 1) % 4
        notes.extend([
            {"id": f"right-{measure}", "measure": measure, "beat": 0, "duration": 1, "pitch": 64 + degree, "velocity": .68, "hand": "right"},
            {"id": f"left-{measure}", "measure": measure, "beat": 0, "duration": 2, "pitch": 48 + degree, "velocity": .55, "hand": "left"},
        ])
    return {
        "title": case.title, "tempo": 72,
        "meter": {"beats": 4, "beat_unit": 4},
        "key": {"tonic": "C", "mode": "major"},
        "measure_count": case.measure_count,
        "sections": [{"id": "section-a", "label": "A", "start_measure": 1, "end_measure": case.measure_count}],
        "notes": notes,
    }


class _MusicProvider:
    def __init__(self, case: CoreMusicCase, call_number: int, evidence: dict[str, bool]) -> None:
        self.case = case
        self.call_number = call_number
        self.evidence = evidence

    def stream(self, *, messages, tools, **_kwargs):
        names = {str(tool.get("name") or "") for tool in tools}
        self.evidence["music_tool_materialized"] = COMPOSE_PIANO_TOOL in names
        if self.call_number == 1:
            draft = _draft(self.case)
            yield from tool_call_events(call_id="compose-score", tool_name=COMPOSE_PIANO_TOOL, arguments={
                "title": self.case.title,
                "intent": "quiet piano music after rain",
                "tempo": 72,
                "meter": draft["meter"],
                "key": draft["key"],
                "measure_count": self.case.measure_count,
                "score_draft": draft,
            })
            return
        output = _output(messages, "compose-score")
        self.evidence["tool_observation_received"] = output.get("status") == "success" or "score_id" in json.dumps(output)
        yield from answer_events(f"已完成 {self.case.measure_count} 小节的 {self.case.title}，可以在 Piano Studio 打开。")


def _run_case(factory: sessionmaker[Session], snapshot: Any, suite_id: str, case: CoreMusicCase, repetition: int) -> TrialOutcome:
    from engine.agent.completion import CompletionGate
    from engine.agent.events import LiveStreamHub
    from engine.agent.loop import RunLoop
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.resource_refs import RequestedResourceRef
    from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentToolInvocation, AgentTurn, Project
    from engine.runtime_composition import authorize_project_resources, build_attempt_resource_resolver, build_default_completion_policy, build_product_tool_registry, default_context_contributors

    project_id = f"core-music-{case.case_id}-{repetition}-{uuid4().hex[:8]}"
    with factory() as db:
        db.add(Project(id=project_id, name=f"CoreMusic {case.case_id}"))
        db.commit()
        refs = authorize_project_resources(db, project_id, (RequestedResourceRef(kind="dbfox.music.library", id=project_id),), snapshot=snapshot)
        sessions = SessionRepository(db)
        aggregate = sessions.create(project_id=project_id, title=f"[CoreMusic] {case.case_id}")
        db.commit()
        admission = sessions.admit(
            session_id=str(aggregate.id), resource_refs=refs, content=case.prompt,
            idempotency_key=f"{suite_id}:{case.case_id}:{repetition}",
            llm_credential_id="core-music-scripted", api_base=None, model_name="scripted",
            request_payload={"benchmark_suite": suite_id, "case_id": case.case_id},
        )
        lease = sessions.claim(session_id=str(aggregate.id), owner="core-music-bench", ttl_seconds=120)
        if lease is None:
            raise RuntimeError("CoreMusic Bench could not claim Session")
        sessions.promote_next_input(lease=lease)
        db.commit()
    calls = {"count": 0}
    provider_evidence: dict[str, bool] = {}
    def model_factory(_settings):
        calls["count"] += 1
        return _MusicProvider(case, calls["count"], provider_evidence)
    product_registry = build_product_tool_registry(snapshot)
    loop = RunLoop(
        session_factory=factory, model_factory=model_factory,
        registry=product_registry,
        context_contributors=default_context_contributors(snapshot),
        completion=CompletionGate(build_default_completion_policy(snapshot)),
        live_stream=LiveStreamHub(),
        resource_resolver=build_attempt_resource_resolver(snapshot=snapshot),
    )
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
    with factory() as db:
        run = db.get(AgentRun, admission.run_id)
        answer = db.get(AgentMessage, admission.assistant_message_id)
        turns = db.query(AgentTurn).filter_by(run_id=admission.run_id).count()
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        artifacts = db.query(AgentArtifactRecord).filter_by(run_id=admission.run_id).all()
        score_artifacts = [item for item in artifacts if str(item.type) == "dbfox.music.score_revision"]
        payload = json.loads(score_artifacts[0].payload_json) if score_artifacts else {}
        artifact_ok = bool(score_artifacts and payload.get("measureCount") == case.measure_count and payload.get("scoreId"))
        authority_ok = len(refs) == 1 and refs[0].kind == "dbfox.music.library" and all(project_id in str(item.resource_refs_json) for item in score_artifacts)
        checks = {
            "completed": run is not None and str(run.status) == "completed",
            "answer": answer is not None and case.title in str(answer.content),
            "tool_materialized": provider_evidence.get("music_tool_materialized", False),
            "observation": provider_evidence.get("tool_observation_received", False),
            "one_tool": [
                product_registry.key_of(
                    product_registry.require(str(item.tool_name))
                ).local_name
                for item in invocations
            ] == ["music_compose_piano"],
            "artifact": artifact_ok,
            "authority": authority_ok,
            "turn_budget": turns <= case.max_turns,
            "tool_budget": len(invocations) <= case.max_tool_calls,
        }
        failed = tuple(name for name, passed in checks.items() if not passed)
        return TrialOutcome(
            suite_id=suite_id, case_id=case.case_id, repetition=repetition,
            verdict="pass" if not failed else "fail",
            metrics={
                "task.success_rate": 1.0 if not failed else 0.0,
                "composition.artifact_accuracy": float(artifact_ok),
                "composition.authority_accuracy": float(authority_ok),
                "runtime.turns": float(turns), "runtime.tool_calls": float(len(invocations)),
            },
            failed_checks=failed,
            evidence={"run_status": str(run.status) if run else "missing", "resource_refs": tuple((ref.kind, ref.id, ref.version) for ref in refs), "artifact_types": tuple(item.type for item in artifacts)},
        )


def run_core_music_bench(*, output_dir: Path, repetitions: int = 1, case_ids: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    manifest = load_suite_manifest(HERE / "suite.json")
    cases = tuple(case for case in load_cases(HERE / manifest.dataset).cases if not case_ids or case.case_id in case_ids)
    if not cases:
        raise ValueError("No Core + Music cases matched")
    work_dir = output_dir.parent / f".{output_dir.name}-work"
    work_dir.mkdir(parents=True, exist_ok=False)
    engine = create_migrated_metadata_engine(work_dir / "metadata.sqlite")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    previous = None
    loaded = False
    try:
        from engine.runtime_composition import active_runtime_snapshot, initialize_runtime_snapshot, set_active_runtime_snapshot
        previous = active_runtime_snapshot()
        loaded = True
        bundle_dir, bundle_manifest = build_isolated_system_dlc_bundle(work_dir / "system-bundle")
        snapshot = initialize_runtime_snapshot(work_dir / "installed-dlcs", system_dlc_dir=bundle_dir, system_dlc_manifest=bundle_manifest)
        outcomes = tuple(_run_case(factory, snapshot, manifest.suite_id, case, repetition) for case in cases for repetition in range(1, repetitions + 1))
        return write_suite_report(output_dir, manifest=manifest, outcomes=outcomes)
    finally:
        if loaded:
            set_active_runtime_snapshot(previous)
        engine.dispose()
        resolved = work_dir.resolve()
        if resolved.parent == output_dir.parent.resolve() and resolved.name.startswith("."):
            shutil.rmtree(resolved)
