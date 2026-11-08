"""Independent durable/browser export comparison using public owner contracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from dbfox_dlc_api import DlcOperationContext
from engine.runtime_composition import initialize_runtime_snapshot


def audit(directory: Path, evidence: Path, report_name: str = "electron-durable-audit.json") -> None:
    if Path(report_name).name != report_name or not report_name.endswith(".json"):
        raise ValueError("The evidence report must be a JSON filename")
    fixture = json.loads((directory / "browser-fixture.json").read_text(encoding="utf-8"))
    snapshot = initialize_runtime_snapshot(storage_root=directory / "dlcs")
    def operation(name, payload):
        spec = snapshot.get_operation("dbfox.voxel", name).spec
        output = spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(dlc_id="dbfox.voxel", operation_name=name, project_id=fixture["project_id"]))
        return spec.output_model.model_validate(output).model_dump(mode="json")
    world_id = fixture["small_world_id"]
    downloaded = evidence / f"{world_id}-v8.voxel.json"
    content = downloaded.read_bytes()
    exported = json.loads(content)
    historical = operation("worlds.get", {"world_id": world_id, "version": 8})
    assert exported["manifest"] == historical
    expected = []; cursor = None
    while True:
        page = operation("worlds.chunks", {"world_id": world_id, "version": 8, "limit": 16, "after": cursor})
        expected.extend(page["chunks"])
        cursor = page["next_after"]
        if cursor is None: break
    assert exported["chunks"] == expected
    cells = sum(sum(value != 0 for value in chunk["values"]) for chunk in exported["chunks"])
    assert cells == 1135 == historical["nonzero_count"]
    assert all(chunk["hash"] == "sha256:" + hashlib.sha256(bytes(chunk["values"])).hexdigest() for chunk in exported["chunks"])
    with sqlite3.connect((directory / "metadata.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        runs = [dict(row) for row in db.execute("SELECT r.id,r.session_id,r.status,r.consumed_tokens,r.consumed_cost_usd FROM agent_runs r JOIN agent_sessions s ON s.id=r.session_id WHERE s.project_id=? ORDER BY r.created_at", (fixture["project_id"],))]
        invocations = [dict(row) for row in db.execute("SELECT i.id,i.run_id,i.tool_name,i.owner_id,i.package_digest,i.status,i.attempt_count,i.input_json,i.resource_refs_json FROM agent_tool_invocations i JOIN agent_sessions s ON s.id=i.session_id WHERE s.project_id=? ORDER BY i.created_at", (fixture["project_id"],))]
        artifacts = [dict(row) for row in db.execute("SELECT a.id,a.run_id,a.session_id,a.type,a.payload_json,a.resource_refs_json FROM agent_artifacts a JOIN agent_sessions s ON s.id=a.session_id WHERE s.project_id=? ORDER BY a.created_at", (fixture["project_id"],))]
    current = operation("worlds.get", {"world_id":world_id})
    chunks = operation("worlds.chunks", {"world_id": world_id, "version":current["version"], "limit":16})
    def cell(point):
        coord=[n//16 for n in point]
        chunk=next((chunk for chunk in chunks["chunks"] if chunk["layer_id"]=="base" and chunk["coord"]==coord),None)
        x,y,z=[n%16 for n in point]
        return chunk["values"][x+16*z+256*y] if chunk else 0
    assert cell([0,30,0]) == 4, "The next Agent must retain the human Gold block"
    assert cell([28]*3) == cell([29]*3) == cell([30]*3) == 3
    result = {"fixture":fixture,"runs":runs,"invocations":invocations,"artifacts":artifacts,
        "current":current,"sentinel_cells":{"first_agent_28":cell([28]*3),"second_agent_29":cell([29]*3),"conflict_agent_30":cell([30]*3),"human_gold_0_30_0":cell([0,30,0])},
        "download":{"filename":downloaded.name,"bytes":len(content),"sha256":hashlib.sha256(content).hexdigest(),
            "manifest_matches_public_history":True,"every_chunk_matches_public_history":True,"chunk_hashes_verified":True,"nonzero_count":cells,
            "all_layers_match_pinned_public_pages":True},
        "native_download_events":[json.loads(line) for line in (directory / "voxel-download-events.jsonl").read_text().splitlines()]}
    (evidence / report_name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"current_version":current["version"],"download":result["download"],"runs":len(runs)},ensure_ascii=False))


if __name__ == "__main__":
    audit(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3] if len(sys.argv) > 3 else "electron-durable-audit.json")
