"""Independently decode a native download using the existing Pillow test dependency."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import PIL
from PIL import Image


def audit(runtime: Path, evidence: Path):
    public = json.loads((evidence / "electron-public-reports.json").read_text(encoding="utf-8-sig"))
    selected = next(item for item in public["reports"] if item["artifact"]["type"] == "dbfox.shader.preview" and item["artifact"]["payload"]["version"] == 4)
    report = selected["value"]["payload"]
    name = f"shader-{report['id']}.png"
    path = runtime / "downloads" / name
    raw = path.read_bytes()
    with Image.open(path) as image:
        assert image.format == "PNG" and image.size == (256, 256) and image.mode == "RGBA"
        pixels = image.tobytes()
    # Analytical expected full image, independent of the renderer and PNG writer.
    # ES 3.0 normalized conversion permits either closest uint at the exact
    # 127.5 tie; this driver chooses 127. Preserve both complete-image oracles.
    # https://registry.khronos.org/OpenGL/specs/es/3.0/es_spec_3.0.withchanges.pdf
    expected = [bytes(component for y in range(256) for x in range(256) for component in (x, 255-y, blue, 255))
                for blue in (127, 128)]
    assert pixels in expected, "Downloaded top-left RGBA pixels differ from both full GLSL gradient oracles"
    pixel_hash = hashlib.sha256(pixels).hexdigest()
    assert pixel_hash == report["pixel_hash"]
    events = [json.loads(line) for line in (runtime / "download-events.jsonl").read_text().splitlines()]
    event = next(value for value in events if value["filename"] == name)
    assert event["state"] == "completed" and event["receivedBytes"] == event["totalBytes"] == len(raw)
    result = {"decoder": f"Pillow {PIL.__version__}", "artifact_id": selected["artifact"]["id"],
              "document_id": report["document_id"], "version": 4, "content_hash": report["content_hash"],
              "filename": name, "bytes": len(raw), "file_sha256": hashlib.sha256(raw).hexdigest(),
              "pixel_sha256": pixel_hash, "analytical_all_65536_pixels_match": True,
              "normalized_half_blue": pixels[2], "half_tie_permitted_values": [127, 128],
              "top_left": list(pixels[:4]), "bottom_left": list(pixels[255*256*4:255*256*4+4]),
              "native_download": event}
    (evidence / "native-png-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    audit(Path(sys.argv[1]), Path(sys.argv[2]))
