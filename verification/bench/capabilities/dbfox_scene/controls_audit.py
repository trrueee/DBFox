"""Read only durable producer evidence for the completed browser lifecycle run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def audit(directory: Path) -> None:
    source = ROOT / "dlcs/dbfox.scene"
    package = json.loads((HERE / "evidence/controls-package.json").read_text(encoding="utf-8"))
    result = json.loads((HERE / "evidence/controls-reactivate.json").read_text(encoding="utf-8"))
    target = result["artifact"]
    with sqlite3.connect((directory / "metadata.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        run = dict(db.execute("SELECT id,session_id,status FROM agent_runs WHERE id=?", (target["run_id"],)).fetchone())
        invocations = [dict(row) for row in db.execute(
            "SELECT id,run_id,session_id,tool_name,owner_id,package_digest,status,attempt_count,resource_refs_json "
            "FROM agent_tool_invocations WHERE run_id=?", (run["id"],))]
        artifact = dict(db.execute(
            "SELECT id,run_id,session_id,type,version,status,payload_json,provenance_json,resource_refs_json "
            "FROM agent_artifacts WHERE id=?", (target["artifact_id"],)).fetchone())
    assert run["status"] == "completed" and run["session_id"] == target["session_id"]
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation["owner_id"] == "dbfox.scene" and invocation["status"] == "succeeded"
    assert invocation["package_digest"] == package["package_digest"] and invocation["attempt_count"] == 1
    assert artifact["run_id"] == run["id"] and artifact["session_id"] == run["session_id"]
    for row in [artifact, *invocations]:
        for key in tuple(row):
            if key.endswith("_json"):
                row[key[:-5]] = json.loads(row.pop(key))
    primitive = (source / "backend/primitives.json").read_bytes()
    prior = subprocess.check_output(["git", "show", "5cdc6242^:dlcs/dbfox.scene/backend/primitives.json"], cwd=ROOT)
    assert primitive == prior
    provenance = package["provenance"]
    original = (source / "node_modules/three/examples/jsm/controls/OrbitControls.js").read_bytes()
    assert hashlib.sha256(original).hexdigest() == provenance["patches"][0]["original_sha256"]
    evidence = {"run": run, "invocations": invocations, "artifact": artifact,
                "primitive_unchanged_from_parent": True, "upstream_node_modules_unmodified": True}
    (HERE / "evidence/controls-durable.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_status": run["status"], "invocations": len(invocations), "package_digest": invocation["package_digest"]}))


if __name__ == "__main__":
    audit(Path(sys.argv[1]).resolve())
