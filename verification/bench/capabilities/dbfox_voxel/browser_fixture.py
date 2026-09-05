"""Independent real Electron fixture: signed owner, public operations and RunLoop."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import sys

from engine.models import Project
from engine.dlc import DlcPackageService
from .runtime import HERE, VoxelRuntime, run_case
from .schema import load_cases


def prepare(directory: Path) -> None:
    with VoxelRuntime(directory) as runtime:
        case = next(case for case in load_cases(HERE / "cases.json").cases if case.stress)
        outcome = run_case(runtime, case)
        assert outcome.verdict == "pass", outcome.failed_checks
        project = outcome.evidence["project_id"]
        with runtime.factory() as db:
            db.get(Project, project).name = "Voxel Independent QA"
            db.add(Project(id="voxel-empty-project", name="Voxel Empty QA"))
            db.commit()
        small = runtime.operation(project, "worlds.create", {"title": "Interactive Voxel", "size": [32, 32, 32], "mutation_id": "browser-small"})
        small = runtime.operation(project, "worlds.apply", {"world_id": small["world_id"], "expected_version": 1,
            "mutation_id": "browser-seed", "operation": {"kind": "box", "layer_id": "base", "bounds": {"min": [8, 0, 8], "max": [24, 12, 24]}, "palette_index": 1, "hollow": True}})
        large = runtime.operation(project, "worlds.create", {"title": "128 Cubed Boundary World", "size": [128, 128, 128], "mutation_id": "browser-large"})
        large = runtime.operation(project, "worlds.apply", {"world_id": large["world_id"], "expected_version": 1,
            "mutation_id": "browser-large-shell", "operation": {"kind": "box", "layer_id": "base", "bounds": {"min": [0, 0, 0], "max": [128, 128, 128]}, "palette_index": 1, "hollow": True}})
        fixture = {"project_id": project, "small_world_id": small["world_id"], "small": small,
            "large_world_id": large["world_id"], "large": large, "stress": outcome.evidence["final_world"],
            "package_digest": runtime.package.package_digest, "boundary": "real signed frontend and backend; production RunLoop with scripted Responses only"}
        (directory / "browser-fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"fixture": str(directory), "large_cells": large["nonzero_count"], "stress_checks": len(outcome.evidence["checks"])}))


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve()
    if "--upgrade" in sys.argv:
        import socket
        # Only a stopped, suite-owned runtime may replace a development package
        # with the same version. Use the supported uninstall that retains data.
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", 19227)) != 0, "Stop the Voxel QA Electron before replacing its package"
        service = DlcPackageService(directory / "dlcs")
        service.set_desired_enabled("dbfox.voxel", False)
        removed = service.uninstall("dbfox.voxel", active_package_digests=frozenset())
        with VoxelRuntime(directory) as runtime:
            fixture = json.loads((directory / "browser-fixture.json").read_text(encoding="utf-8"))
            fixture["previous_package_digest"] = fixture["package_digest"]
            fixture["package_digest"] = runtime.package.package_digest
            fixture["reopened_small"] = runtime.operation(fixture["project_id"], "worlds.get", {"world_id": fixture["small_world_id"]})
            fixture["package_replacement"] = asdict(removed)
            (directory / "browser-fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"package_digest": fixture["package_digest"], "reopened_version": fixture["reopened_small"]["version"]}))
    elif "--record-installed" in sys.argv:
        from engine.runtime_composition import initialize_runtime_snapshot
        from dbfox_dlc_api import DlcOperationContext
        service = DlcPackageService(directory / "dlcs")
        fixture = json.loads((directory / "browser-fixture.json").read_text(encoding="utf-8"))
        fixture["previous_package_digest"] = fixture["package_digest"]
        fixture["package_digest"] = service.registry.get_installed_dlc("dbfox.voxel").selected_digest
        snapshot = initialize_runtime_snapshot(storage_root=directory / "dlcs")
        spec = snapshot.get_operation("dbfox.voxel", "worlds.get").spec
        value = spec.handler(spec.input_model.model_validate({"world_id": fixture["small_world_id"]}),
            DlcOperationContext(dlc_id="dbfox.voxel", operation_name="worlds.get", project_id=fixture["project_id"]))
        fixture["reopened_small"] = spec.output_model.model_validate(value).model_dump(mode="json")
        (directory / "browser-fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"package_digest": fixture["package_digest"], "version": fixture["reopened_small"]["version"]}))
    else:
        prepare(directory)
