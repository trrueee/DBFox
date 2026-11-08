"""Small, newly signed production Scene package for independent controls QA."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from engine.models import Project
from .runtime import HERE, SOURCE, SceneRuntime


def prepare(directory: Path) -> None:
    if directory.exists():
        raise FileExistsError("Controls QA needs a fresh isolated runtime")
    with SceneRuntime(directory) as runtime:
        project = "scene-controls-project"
        with runtime.factory() as db:
            db.add(Project(id=project, name="Scene Controls QA"))
            db.add(Project(id="scene-controls-other", name="Other Controls Project"))
            db.commit()
        created = runtime.operation(project, "scenes.create", {
            "title": "Controls Regression", "request_id": "controls-create"})
        scene = runtime.operation(project, "scenes.apply", {
            "scene_id": created["scene"]["id"], "expected_version": 1,
            "request_id": "controls-content", "operation": {
                "kind": "object_create", "objects": [
                    {"id": "controls-cube", "name": "Controls Cube", "kind": "mesh"},
                    {"id": "controls-light", "name": "Controls Light", "kind": "light",
                     "light_type": "directional", "intensity": 5, "position": [3, 5, 4]},
                ]}})["scene"]
        provenance = json.loads((SOURCE / "frontend/vendor/provenance.json").read_text())
        files = {}
        with ZipFile(io.BytesIO(runtime.package.archive_bytes)) as archive:
            for local in ("frontend/index.js", "frontend/viewport.js", "frontend/vendor/three.js",
                          "frontend/vendor/provenance.json", "backend/primitives.json"):
                names = [name for name in archive.namelist() if name.endswith(local)]
                assert len(names) == 1, (local, names)
                content = archive.read(names[0])
                assert content == (SOURCE / local).read_bytes()
                files[local] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        assert files["frontend/vendor/three.js"]["sha256"] == provenance["bundle_sha256"]
        assert files["backend/primitives.json"]["sha256"] == provenance["primitive_sha256"]
        result = {"project_id": project, "scene": scene, "package_digest": runtime.package.package_digest,
                  "files": files, "provenance": provenance,
                  "boundary": "fresh signed package, trusted install, active registered typed operations"}
        (directory / "controls-fixture.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (HERE / "evidence/controls-package.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"scene_id": scene["id"], "package_digest": result["package_digest"]}))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
