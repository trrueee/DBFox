"""Prepare isolated real signed Scene state for Electron QA; no provider credentials."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from engine.models import Project
from .runtime import SceneRuntime


def prepare(directory: Path) -> None:
    with SceneRuntime(directory) as runtime:
        project = "scene-browser-project"
        with runtime.factory() as db:
            db.add(Project(id=project, name="Scene Browser QA"))
            db.commit()
        small = runtime.operation(project, "scenes.create", {"title": "Interactive Scene", "request_id": "small"})["scene"]
        runtime.operation(project, "scenes.apply", {"scene_id": small["id"], "expected_version": 1,
            "request_id": "small-content", "operation": {"kind": "object_create", "objects": [
                {"id": "qa-cube", "name": "QA Cube", "kind": "mesh"},
                {"id": "qa-light", "name": "QA Light", "kind": "light", "light_type": "directional", "intensity": 5, "position": [3, 5, 4]},
            ]}})
        large = runtime.operation(project, "scenes.create", {"title": "10000 Object Hierarchy", "request_id": "large"})["scene"]
        for batch in range(20):
            nodes = [{"id": f"node-{i}", "name": f"Node {i}", "kind": "mesh", "parent_id": "large-root",
                "position": [(i % 100) * 1.5, 0, (i // 100) * 1.5]} for i in range(batch * 500, min(9999, (batch + 1) * 500))]
            if batch == 0:
                nodes[0] = {"id": "large-root", "name": "Large Root", "kind": "group"}
            large = runtime.operation(project, "scenes.apply", {"scene_id": large["id"], "expected_version": large["version"],
                "request_id": f"large-{batch}", "operation": {"kind": "object_create", "objects": nodes}})["scene"]
        # Fill the last slot: one root + 9999 meshes = 10,000 canonical nodes.
        large = runtime.operation(project, "scenes.apply", {"scene_id": large["id"], "expected_version": large["version"],
            "request_id": "large-last", "operation": {"kind": "object_create", "objects": [{"id": "node-9999", "name": "Node 9999", "kind": "mesh", "parent_id": "large-root", "position": [150, 0, 150]}]}})["scene"]
        (directory / "browser-fixture.json").write_text(json.dumps({"project_id": project, "small_scene_id": small["id"],
            "large_scene_id": large["id"], "large_count": large["object_count"], "package_digest": runtime.package.package_digest}, indent=2), encoding="utf-8")
        print(json.dumps({"fixture": str(directory), "large_count": large["object_count"]}))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
