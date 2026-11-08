"""Fresh cold signed fixture for Pixel red-team UI; no provider or credential data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def prepare(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    os.environ.update(DBFOX_RUNTIME_DIR=str(directory), DBFOX_DATABASE_URL="sqlite:///" + str(directory / "metadata.sqlite").replace("\\", "/"),
        DBFOX_TESTING="1", DBFOX_SYSTEM_DLC_DIR="", DBFOX_SYSTEM_DLC_MANIFEST="")
    from engine.models import Project
    from .runtime import PixelRuntime
    with PixelRuntime(directory) as runtime:
        project = "pixel-redteam-ui"
        with runtime.factory() as db:
            db.add_all([Project(id=project, name="Pixel Red Team"), Project(id="pixel-redteam-other", name="Pixel Other Scope")])
            db.commit()
        created = runtime.operation(project, "documents.create", {"title": "Adversarial Canvas", "width": 16, "height": 16,
            "expected_version": 0, "mutation_id": "red-initial"})
        result = {"project_id": project, "document_id": created["document_id"], "package_digest": runtime.package.package_digest,
            "initial": created, "product": "88e7c7d1", "shared_factory": "fac8a170"}
        (directory / "redteam-fixture.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
