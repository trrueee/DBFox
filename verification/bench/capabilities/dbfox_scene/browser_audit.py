"""Read-only durable audit of the real Electron browser fixture (no credentials)."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys


def audit(directory: Path, output: Path) -> None:
    fixture = json.loads((directory / "browser-fixture.json").read_text(encoding="utf-8"))
    with sqlite3.connect((directory / "metadata.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        runs = [dict(row) for row in db.execute(
            "SELECT r.id,r.session_id,r.status,r.error_code,r.consumed_tokens,r.consumed_cost_usd "
            "FROM agent_runs r JOIN agent_sessions s ON s.id=r.session_id WHERE s.project_id=? ORDER BY r.created_at",
            (fixture["project_id"],))]
        invocations = []
        artifacts = []
        for run in runs:
            invocations.extend(dict(row) for row in db.execute(
                "SELECT id,run_id,tool_name,owner_id,package_digest,status,attempt_count,input_json,resource_refs_json "
                "FROM agent_tool_invocations WHERE run_id=?", (run["id"],)))
            artifacts.extend(dict(row) for row in db.execute(
                "SELECT id,run_id,session_id,type,status,payload_json,resource_refs_json "
                "FROM agent_artifacts WHERE run_id=?", (run["id"],)))
    with sqlite3.connect((directory / "dlcs/data/dbfox.scene/state.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        revisions = []
        for row in db.execute("SELECT version,content_hash,document_json FROM scene_revisions WHERE scene_id=? ORDER BY version", (fixture["small_scene_id"],)):
            document = json.loads(row["document_json"])
            revisions.append({"version":row["version"],"content_hash":row["content_hash"],"objects":document["objects"]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"fixture":fixture,"runs":runs,"invocations":invocations,"artifacts":artifacts,"small_scene_revisions":revisions},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"runs":len(runs),"invocations":len(invocations),"artifacts":len(artifacts),"scene_revisions":len(revisions),"output":str(output)}))


if __name__ == "__main__":
    audit(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
