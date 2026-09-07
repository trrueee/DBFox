"""Isolated signed Comic package and public operations for native UI verification."""
import json
from pathlib import Path
import sys
from engine.models import Project
from .runtime import ComicRuntime

directory = Path(sys.argv[1]).resolve()
with ComicRuntime(directory) as runtime:
    project = "comic-browser-project"
    with runtime.factory() as db:
        db.add(Project(id=project, name="Comic Studio 验证"))
        db.commit()
    first = runtime.operation(project, "comics.create", {"title": "灯塔归途", "request_id": "native-create"})["comic"]
    example = json.loads((Path(__file__).resolve().parents[4] / "dlcs/dbfox.comic/examples/lighthouse.json").read_text(encoding="utf-8"))
    current = first
    for index, page in enumerate(example["pages"]):
        final = runtime.operation(project, "comics.apply", {"comic_id": first["id"], "expected_version": current["version"], "request_id": f"native-page-{index}", "operation": {"kind": "page_create", "page": page}})
        current = final["comic"]
    (directory / "comic-browser-fixture.json").write_text(json.dumps({"project_id": project, "comic_id": first["id"], "package_digest": runtime.package.package_digest, "summary": final["comic"]}, ensure_ascii=False, indent=2), encoding="utf-8")
