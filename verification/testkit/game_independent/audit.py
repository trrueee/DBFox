"""Independently check captured public pages, installed bytes and native downloads."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import sys


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def audit(runtime: Path, captures: Path):
    def read(name):
        return json.loads((captures / name).read_text(encoding="utf-8-sig"))

    history = read("game-independent-history.json")
    games, fingerprints = {}, {}
    for snapshot in history["snapshots"]:
        pages = {p["section"]: json.loads(p["raw"]) for p in snapshot["pages"]}
        summary = pages.pop("summary")
        metadata, game = summary["metadata"], summary["game"]
        document = {key: metadata[key] for key in ("schema_version", "engine", "tick_hz", "initial_scene_id")}
        document.update(id=game["id"], title=game["title"])
        document.update({key: value["items"] for key, value in pages.items()})
        fingerprint = hashlib.sha256(encoded(document)).hexdigest()
        assert fingerprint == game["content_hash"], "Public canonical fingerprint mismatch"
        games[game["version"]], fingerprints[game["version"]] = document, fingerprint
    expected = copy.deepcopy(games[2])
    fox = next(entity for entity in expected["entities"] if "player" in entity["tags"])
    next(c["spec"] for c in fox["components"] if c["spec"]["kind"] == "transform")["x"] += 80
    assert expected == games[3], "Inspector mutation changed other fields"
    assert games[2] == games[4], "Undo changed canonical content"

    formal = read("game-independent-formal.json")
    assert formal["pauseStable"] and formal["singleStep"] == 1 and formal["reset"] == 0
    outcome = formal["result"]["outcome"]
    assert outcome["game"]["version"] == 4 and outcome["game"]["content_hash"] == fingerprints[4]
    assert outcome["report"]["outcome"] == "lost" and outcome["report"]["ticks_completed"] == 698

    artifacts = read("game-independent-artifacts.json")
    assert artifacts["previewPauseReset"] and not artifacts["nonReadRequests"]
    events = [json.loads(line) for line in (runtime / "download-events.jsonl").read_text(encoding="utf-8").splitlines()]
    for artifact in artifacts["reads"]:
        content = base64.b64decode(artifact.pop("bytesBase64"), validate=True)
        report = "playtest" in artifact["representation"]
        suffix = "-playtest" if report else ""
        name = f"game-{history['game']['id']}-v4{suffix}.json"
        assert (runtime / "downloads" / name).read_bytes() == content
        assert any(e["filename"] == name and e["state"] == "completed" and e["receivedBytes"] == e["totalBytes"] == len(content) for e in events)
        value = json.loads(content)
        assert artifact["hash"] == fingerprints[4] and artifact["version"] == "4"
        if report:
            assert value["report"]["ticks_completed"] == 698 and value["report"]["outcome"] == "lost"
        else:
            assert value["document"] == games[4]
        artifact.update(download_bytes=len(content), download_sha256=hashlib.sha256(content).hexdigest(), native_download_matches=True)

    provenance = json.loads((runtime / "package-provenance.json").read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[3]
    for entry in provenance["frontend"]:
        assert hashlib.sha256((root / "dlcs/dbfox.game" / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    result = {"package_digest": provenance["package_digest"], "installed_frontend_files": len(provenance["frontend"]),
              "game_id": history["game"]["id"], "fingerprints": fingerprints, "v3_only_change": "player transform x +80",
              "v4_exactly_restores_v2": True, "formal": formal, "artifacts": artifacts}
    reopened = captures / "game-independent-reopened.json"
    if reopened.exists():
        after = json.loads(reopened.read_text(encoding="utf-8-sig"))
        assert after["game"] == history["game"] and after["snapshots"] == history["snapshots"]
        result["cold_reopen_public_versions_unchanged"] = True
    after_win = read("game-independent-after-win.json")
    assert after_win["snapshots"][:3] == history["snapshots"]
    new_pages = {p["section"]: json.loads(p["raw"]) for p in after_win["snapshots"][3]["pages"]}
    health_expected = copy.deepcopy(games[4])
    fox = next(e for e in health_expected["entities"] if "player" in e["tags"])
    health = next(c["spec"] for c in fox["components"] if c["spec"]["kind"] == "health")
    health.update(initial=100, maximum=100)
    for section in ("scenes", "entities", "behaviors", "rules", "variables", "assets"):
        assert new_pages[section]["items"] == health_expected[section]
    win_hash = hashlib.sha256(encoded(health_expected)).hexdigest()
    assert new_pages["summary"]["game"]["content_hash"] == win_hash
    winning = read("game-independent-win.json")
    assert winning["outcome"]["game"]["content_hash"] == win_hash
    assert winning["outcome"]["report"]["ticks_completed"] == 3600
    assert winning["outcome"]["report"]["outcome"] == "won"
    old_reads = read("game-independent-artifacts.json")["reads"]
    assert read("game-independent-retained.json") == old_reads
    result.update(v5_only_change="player health initial/maximum 3 to 100", v5_content_hash=win_hash,
                  winning=winning, v4_artifacts_unchanged_after_v5=True)
    (captures / "game-independent-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("formal", "artifacts")}))


if __name__ == "__main__":
    audit(Path(sys.argv[1]), Path(sys.argv[2]))
