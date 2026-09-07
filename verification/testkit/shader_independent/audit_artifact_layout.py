"""Check recorded native layout, signed CSS, and historical download independently."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(raw: bytes):
    return hashlib.sha256(raw).hexdigest()


def main(runtime: Path):
    evidence = Path("verification/testkit/shader_independent/evidence")
    proof = read(evidence / "electron-artifact-layout.json")
    provenance = read(evidence / "package-provenance-cd8c94a7.json")
    archive = runtime / "shader.dbfox-dlc"
    assert sha(archive.read_bytes()) == provenance["package_digest"]
    with zipfile.ZipFile(archive) as package:
        css = package.read("frontend/studio.css")
    style = proof["assetStyle"]
    assert style["href"] == f"dlc-asset://localhost/{provenance['package_digest']}/frontend/studio.css"
    assert len(css) == style["bytes"] and sha(css) == style["sha256"]
    layouts = {}
    for name in ("previewNarrow", "previewWide", "reportNarrow", "documentNarrow", "sourceNarrow"):
        layout = proof[name]
        assert layout["scrollWidth"] <= layout["clientWidth"] + 1
        assert all(not item["width"] or -1 <= item["left"] <= item["right"] <= layout["width"] + 1 for item in layout["controls"])
        assert layout["width"] >= 1000 if name == "previewWide" else layout["width"] <= 400
        if name.startswith("preview"):
            button = next(item for item in layout["controls"] if item["text"] == "Download PNG")
            assert button["disabled"] is False
            assert not any("Reading the immutable representation" in (item["text"] or "") for item in layout["controls"])
        layouts[name] = {key: layout[key] for key in ("width", "clientWidth", "scrollWidth")}
    assert proof["writes"] == []
    cold = read(evidence / "electron-final-cold.json")
    snapshot = next(item for item in cold["snapshots"] if item["version"] == 1)
    canonical = base64.b64decode(snapshot["canonical_base64"], validate=True)
    assert sha(canonical) == snapshot["summary"]["document"]["content_hash"]
    document = json.loads(canonical)["document"]
    native = runtime / "downloads" / proof["download"]["filename"]
    assert read(native) == {"document": document, "textures": snapshot["textures"]}
    stage = next(stage for stage in document["stages"] if stage["id"] == "6a40f6ef-4c1d-42a8-81e6-11003a22fee6")
    assert proof["historicalSource"]["editable"] == "false"
    # CodeMirror innerText includes its final empty rendered line; compare source lines.
    assert proof["historicalSource"]["source"].rstrip("\n") == stage["source"].rstrip("\n")
    events = [json.loads(line) for line in (runtime / "download-events.jsonl").read_text(encoding="utf-8").splitlines()]
    event = next(event for event in reversed(events) if event["filename"] == native.name)
    assert event["state"] == "completed" and event["receivedBytes"] == event["totalBytes"] == native.stat().st_size
    modified = datetime.fromtimestamp(native.stat().st_mtime, timezone.utc)
    requested = datetime.fromisoformat(proof["download"]["requestedAt"])
    verified = datetime.fromisoformat(proof["verifiedAt"])
    assert requested.timestamp() <= modified.timestamp() <= verified.timestamp() + 2
    images = Path("docs/quality/evidence/shader-independent")
    screenshots = {}
    for name in ("preview-narrow", "preview-wide", "report-narrow", "document-narrow", "source-narrow"):
        path = images / f"artifact-{name}.png"
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
        screenshots[path.name] = sha(raw)
    result = {"candidate": proof["candidate"], "verified_at": proof["verifiedAt"],
              "package_digest": provenance["package_digest"], "css_sha256": sha(css),
              "layouts": layouts, "preview_complete_at_both_widths": True,
              "historical_source_readonly_and_equal": True, "observed_document_writes_or_compute": proof["writes"],
              "download": {"filename": native.name, "bytes": native.stat().st_size,
                           "sha256": sha(native.read_bytes()), "modified_at": modified.isoformat(),
                           "native_event": event, "full_snapshot_equal": True}, "screenshots": screenshots}
    (evidence / "artifact-layout-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
