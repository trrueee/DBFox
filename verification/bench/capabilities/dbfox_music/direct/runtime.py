"""Direct Music capability runner over the production System DLC host."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from engine.dlc.api import DlcOperationContext, ResourceScopeRef
from engine.tools.runtime import ToolRunContext
from verification.bench.capabilities.dbfox_music.direct.schema import MusicDirectCase, load_cases
from verification.bench.framework.reporting import write_suite_report
from verification.bench.framework.schema import load_suite_manifest
from verification.bench.framework.trial import TrialOutcome
from verification.testkit.system_dlc_fixture import build_isolated_system_dlc_bundle


HERE = Path(__file__).resolve().parent


def _invoke(snapshot: Any, project_id: str, name: str, payload: dict[str, Any]) -> Any:
    contribution = snapshot.get_operation("dbfox.music", name)
    if contribution is None:
        raise RuntimeError(f"Production dbfox.music operation is unavailable: {name}")
    result = contribution.spec.handler(
        contribution.spec.input_model.model_validate(payload),
        DlcOperationContext(dlc_id="dbfox.music", operation_name=name, project_id=project_id),
    )
    return contribution.spec.output_model.model_validate(result)


def _tool(snapshot: Any, name: str) -> Any:
    return next(item.tool for item in snapshot.tools if item.tool.name == name)


def _resolver(snapshot: Any, kind: str) -> Any:
    return next(item.resolver for item in snapshot.resource_resolvers if item.kind == kind)


def _draft() -> dict[str, Any]:
    notes = []
    for measure in range(1, 5):
        notes.extend([
            {"id": f"r-{measure}", "measure": measure, "beat": 0, "duration": 1, "pitch": 60 + measure, "velocity": .72, "hand": "right"},
            {"id": f"l-{measure}", "measure": measure, "beat": 0, "duration": 2, "pitch": 47 + measure, "velocity": .62, "hand": "left"},
        ])
    return {
        "title": "Quiet Rain", "tempo": 76,
        "meter": {"beats": 4, "beat_unit": 4},
        "key": {"tonic": "C", "mode": "major"},
        "measure_count": 4, "notes": notes,
    }


def _run_tool(snapshot: Any, tool_name: str, payload: dict[str, Any], ref: ResourceScopeRef, resource: Any) -> Any:
    tool = _tool(snapshot, tool_name)
    return tool.run(tool.input_model.model_validate(payload), ToolRunContext.for_invocation(
        request=None,
        idempotency_key=f"bench-{uuid4().hex}",
        scope_refs=(ref,),
        resources={ref.canonical(): resource},
    ))


def _execute_case(snapshot: Any, suite_id: str, case: MusicDirectCase, repetition: int) -> TrialOutcome:
    project_id = f"music-direct-{case.case_id}-{repetition}-{uuid4().hex[:8]}"
    library_ref = ResourceScopeRef(kind="dbfox.music.library", id=project_id, version="1")
    composed = _run_tool(snapshot, "music_compose_piano", {
        "title": "Quiet Rain", "intent": "calm four-measure piano fixture", "tempo": 76,
        "meter": {"beats": 4, "beat_unit": 4}, "key": {"tonic": "C", "mode": "major"},
        "measure_count": 4, "score_draft": _draft(),
    }, library_ref, _resolver(snapshot, "dbfox.music.library")(library_ref))
    score_id = composed.output.score_id
    first = _invoke(snapshot, project_id, "scores.get", {"score_id": score_id, "revision": 1})
    first_json = first.revision.document.model_dump_json()
    score_ref = ResourceScopeRef(kind="dbfox.music.score", id=score_id, version=1)
    frozen = _resolver(snapshot, "dbfox.music.score")(score_ref)
    if case.scenario == "edit_locality":
        replacement = [{"id": "r-2-new", "measure": 2, "beat": 0, "duration": 1, "pitch": 72, "velocity": .72, "hand": "right"}]
        outcome = _run_tool(snapshot, "music_revise_phrase", {
            "score_id": score_id, "measure_start": 2, "measure_end": 2,
            "replacement": replacement, "reason": "bench locality",
        }, score_ref, frozen)
    else:
        outcome = _run_tool(snapshot, "music_transpose", {"score_id": score_id, "semitones": 2}, score_ref, frozen)
    second = _invoke(snapshot, project_id, "scores.get", {"score_id": score_id, "revision": outcome.output.revision})
    first_again = _invoke(snapshot, project_id, "scores.get", {"score_id": score_id, "revision": 1})
    immutable = first_again.revision.document.model_dump_json() == first_json
    valid = second.revision.document.measure_count == 4 and all(
        21 <= note.pitch <= 108 and note.beat + note.duration <= 4
        for note in second.revision.document.notes
    )
    if case.scenario == "edit_locality":
        before = [note.model_dump() for note in first.revision.document.notes if note.measure != 2]
        after = [note.model_dump() for note in second.revision.document.notes if note.measure != 2]
        locality = before == after
        scenario_ok = locality
    elif case.scenario == "transpose":
        locality = True
        scenario_ok = [note.pitch for note in second.revision.document.notes] == [note.pitch + 2 for note in first.revision.document.notes]
    else:
        locality = True
        scenario_ok = immutable if case.scenario == "revision_immutability" else valid
    checks = {"scenario_result": scenario_ok, "score_validity": valid, "revision_immutability": immutable, "edit_locality": locality}
    failed = tuple(name for name, passed in checks.items() if not passed)
    return TrialOutcome(
        suite_id=suite_id, case_id=case.case_id, repetition=repetition,
        verdict="pass" if not failed else "fail",
        metrics={
            "task.success_rate": 1.0 if not failed else 0.0,
            "capability.score_validity": float(valid),
            "capability.revision_immutability": float(immutable),
            "capability.edit_locality": float(locality),
        },
        failed_checks=failed,
        evidence={"score_id": score_id, "head_revision": outcome.output.revision, "content_hash": second.revision.content_hash},
    )


def run_music_direct_bench(*, output_dir: Path, repetitions: int = 1, case_ids: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be between 1 and 20")
    manifest = load_suite_manifest(HERE / "suite.json")
    cases = tuple(case for case in load_cases(HERE / manifest.dataset).cases if not case_ids or case.case_id in case_ids)
    if not cases:
        raise ValueError("No Music DirectBench cases matched")
    work_dir = output_dir.parent / f".{output_dir.name}-work"
    work_dir.mkdir(parents=True, exist_ok=False)
    previous = None
    loaded = False
    try:
        from engine.runtime_composition import active_runtime_snapshot, initialize_runtime_snapshot, set_active_runtime_snapshot
        previous = active_runtime_snapshot()
        loaded = True
        bundle_dir, bundle_manifest = build_isolated_system_dlc_bundle(work_dir / "system-bundle")
        snapshot = initialize_runtime_snapshot(work_dir / "installed-dlcs", system_dlc_dir=bundle_dir, system_dlc_manifest=bundle_manifest)
        outcomes = tuple(_execute_case(snapshot, manifest.suite_id, case, repetition) for case in cases for repetition in range(1, repetitions + 1))
        return write_suite_report(output_dir, manifest=manifest, outcomes=outcomes)
    finally:
        if loaded:
            set_active_runtime_snapshot(previous)
        resolved = work_dir.resolve()
        if resolved.parent == output_dir.parent.resolve() and resolved.name.startswith("."):
            shutil.rmtree(resolved)
