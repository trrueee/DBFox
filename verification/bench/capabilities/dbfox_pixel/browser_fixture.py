"""Isolated signed Pixel + real scripted Agent artwork for Electron; no provider credentials."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from engine.models import Project
from engine.dlc import DlcPackageService
from .runtime import HERE, PixelRuntime, run_case, run_segment
from .schema import load_cases


def prepare(directory, *, refresh=False):
    if refresh:
        # Explicit cold fixture reinstall uses the official data-retaining lifecycle.
        # Never run this mode while this task's Electron/Sidecar is active.
        service = DlcPackageService(directory / "dlcs")
        service.set_desired_enabled("dbfox.pixel", False)
        result = service.uninstall("dbfox.pixel", active_package_digests=frozenset())
        assert result.data_retained
    with PixelRuntime(directory) as runtime:
        if refresh:
            fixture_path = directory / "browser-fixture.json"
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            current = runtime.operation(fixture["project_id"], "documents.head", {"document_id": fixture["interactive_id"]})
            fixture["package_digest"] = runtime.package.package_digest
            fixture["restart_head"] = current
            scale = next(case for case in load_cases(HERE / "cases.json").cases if case.case_id == "hundreds-of-frames")
            outcome, script = run_segment(runtime, scale, project_id=fixture["project_id"])
            assert outcome["run_status"] == "completed" and all(item["status"] == "succeeded" for item in outcome["invocations"])
            fixture["scale_id"] = script.summary["document_id"]
            fixture["scale_revision"] = script.summary["revision"]
            (HERE / "evidence/browser-scale-runloop.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
            fixture_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
            print(json.dumps({"refreshed": True, "head": current}))
            return
        case = next(case for case in load_cases(HERE / "cases.json").cases if case.stress)
        outcome = run_case(runtime, case)
        assert outcome.verdict == "pass", outcome.failed_checks
        project = outcome.evidence["project_id"]
        with runtime.factory() as db:
            db.get(Project, project).name = "Pixel Browser QA"
            db.add(Project(id="pixel-browser-other", name="Pixel Other Scope"))
            db.commit()
        small = runtime.operation(project, "documents.create", {"title": "Interactive Pixel", "width": 16, "height": 16,
            "expected_version": 0, "mutation_id": "browser-blank"})
        (directory / "browser-fixture.json").write_text(json.dumps({"project_id": project, "interactive_id": small["document_id"],
            "knight_id": outcome.evidence["final_summary"]["document_id"], "knight_revision": outcome.evidence["final_summary"]["revision"],
            "session_id": outcome.evidence["session_id"], "package_digest": runtime.package.package_digest}, indent=2), encoding="utf-8")
        print(json.dumps({"runtime": str(directory), "project_id": project, "knight_frames": 10}))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve(), refresh="--refresh" in sys.argv)
