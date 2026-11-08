"""Audit public captured pages and completed native downloads, without DB access."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys


def audit(runtime: Path, captures: Path):
    snapshot = json.loads((captures / "native-snapshots.json").read_text(encoding="utf-8-sig"))
    documents = {}
    fingerprints = {}
    for version in (3, 4, 5):
        pages = {item["section"]: json.loads(item["raw"]) for item in snapshot["pages"] if item["version"] == version}
        summary = pages["summary"]["game"]
        metadata = pages["summary"]["metadata"]
        document = {"id": summary["id"], "title": summary["title"], **{key: metadata[key] for key in ("schema_version", "engine", "tick_hz", "initial_scene_id")}}
        document.update({section: pages[section]["items"] for section in ("scenes", "entities", "behaviors", "rules", "variables", "assets")})
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        assert hashlib.sha256(canonical).hexdigest() == summary["content_hash"]
        documents[str(version)], fingerprints[str(version)] = document, summary["content_hash"]
    expected = copy.deepcopy(documents["3"])
    fox = next(item for item in expected["entities"] if "player" in item["tags"])
    next(item for item in fox["components"] if item["spec"]["kind"] == "transform")["spec"]["x"] += 80
    assert expected == documents["4"], "Drag changed fields beyond the one transform coordinate"
    assert documents["5"] == documents["3"], "Undo did not restore exact canonical content"
    bundle_path = runtime / "downloads" / f"game-{snapshot['gameId']}-v3.json"
    bundle_bytes = bundle_path.read_bytes()
    bundle = json.loads(bundle_bytes)
    assert bundle["document"] == documents["3"] and bundle["revision"]["content_hash"] == fingerprints["3"]
    downloads = [json.loads(line) for line in (runtime / "download-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(item["filename"] == bundle_path.name and item["state"] == "completed" and item["receivedBytes"] == len(bundle_bytes) == item["totalBytes"] for item in downloads)
    provenance = json.loads((runtime / "package-provenance.json").read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[3]
    for entry in provenance["frontend"]:
        assert hashlib.sha256((root / "dlcs/dbfox.game" / entry["path"]).read_bytes()).hexdigest() == entry["sha256"], entry["path"]
    result = {"package_digest": provenance["package_digest"], "public_versions": documents, "fingerprints": fingerprints, "only_change_v4": "Fox transform.x +80", "undo_exact": True, "download": {"bytes": len(bundle_bytes), "sha256": hashlib.sha256(bundle_bytes).hexdigest(), "native_completed": True}}
    (captures / "canonical-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "public_versions"}))


if __name__ == "__main__":
    audit(Path(sys.argv[1]), Path(sys.argv[2]))
