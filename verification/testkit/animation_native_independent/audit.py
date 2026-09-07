"""Read only the explicitly named independent runtime and real downloads."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import urlopen

runtime = Path(sys.argv[1]).resolve()
fixture = json.loads((runtime / "browser-fixture.json").read_text(encoding="utf8"))
small, large = fixture["animation"]["id"], fixture["large_animation"]["id"]
connection = sqlite3.connect((runtime / "dlcs/data/dbfox.animation/animation.sqlite3").as_uri() + "?mode=ro", uri=True)
def document(identity, version):
    row = connection.execute("SELECT document FROM revisions WHERE id=? AND version=?", (identity, version)).fetchone()
    assert row is not None
    return json.loads(row[0])

original = document(small, 7)
edited = json.loads(json.dumps(original)); edited["keyframes"][1].update(tick=4200, value=8)
assert document(small, 8) == edited
assert document(small, 9) == original
curve = json.loads(json.dumps(original)); curve["curves"][0]["x1"] = .4
assert document(small, 10) == curve and document(small, 11) == original
big = document(large, 11)
expected = json.loads(json.dumps(big)); expected["keyframes"][0]["value"] = 12.5
assert document(large, 12) == expected and len(expected["keyframes"]) == 2048

downloads = []
for path in sorted((runtime / "downloads").glob("*.json")):
    match = re.fullmatch(r"animation-([a-f0-9]{32})-v([0-9]+)\.json", path.name)
    assert match
    identity, version = match[1], int(match[2])
    canonical, digest = connection.execute("SELECT document, content_hash FROM revisions WHERE id=? AND version=?", (identity, version)).fetchone()
    data = path.read_bytes()
    assert data == canonical.encode("utf8")
    assert hashlib.sha256(data).hexdigest() == digest
    downloads.append({"filename": path.name, "bytes": len(data), "sha256": digest})
assert len(downloads) == 5
before = json.loads((runtime / "playback-before.json").read_text())
events = [json.loads(line) for line in (runtime / "download-evidence.jsonl").read_text().splitlines()]
assert len(events) == 6 and all(item["state"] == "completed" for item in events)
assert connection.execute("SELECT head FROM documents WHERE id=?", (small,)).fetchone()[0] == 11
assert connection.execute("SELECT head FROM documents WHERE id=?", (large,)).fetchone()[0] == 12
policy = urlopen("http://127.0.0.1:5188/", timeout=5).headers.get("Content-Security-Policy")
assert "script-src 'self' dlc-asset:" in policy and "unsafe-eval" not in policy
print(json.dumps({"fixture": fixture, "downloads": downloads, "download_completed_events":len(events),
    "playback_before_counts": before, "owner_revisions_verified": [7,8,9,10,11], "large_head":12,
    "csp_header": policy}, ensure_ascii=False, indent=2))
connection.close()
