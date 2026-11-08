"""Read-only package, durable edit and native download evidence audit."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from engine.dlc import DlcPackageService


def audit(directory):
    registry = json.loads((directory/"dlcs/registry.json").read_text())
    record = registry["installed_dlcs"]["dbfox.animation"]
    selected = record["selected_digest"]
    service = DlcPackageService(directory/"dlcs")
    package = service.store.get_package_dir(selected)
    source = Path(__file__).resolve().parents[4]/"dlcs/dbfox.animation"
    files = {}
    for name in ("frontend/index.js","frontend/index.css","frontend/playback.js","frontend/vendor/three.js","backend/contracts.py","backend/store.py"):
        raw = (package/name).read_bytes()
        files[name] = {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"matches_source":raw == (source/name).read_bytes()}
        assert files[name]["matches_source"]
    databases = list((directory/"dlcs").rglob("animation.sqlite3"))
    assert len(databases) == 1
    connection = sqlite3.connect(databases[0].as_uri()+"?mode=ro",uri=True)
    connection.row_factory = sqlite3.Row
    documents = []
    for head in connection.execute("SELECT * FROM documents ORDER BY project_id"):
        revisions = []
        for row in connection.execute("SELECT version,content_hash,document,operation,status FROM revisions WHERE id=? ORDER BY version",(head["id"],)):
            assert hashlib.sha256(row["document"].encode()).hexdigest() == row["content_hash"]
            doc = json.loads(row["document"])
            revisions.append({"version":row["version"],"status":row["status"],"content_hash":row["content_hash"],"operation":json.loads(row["operation"]),
                "key_count":len(doc["keyframes"]),"first_keys":doc["keyframes"][:3],"contact":next((key for key in doc["keyframes"] if key["id"]=="contact"),None),
                "curve":next((curve for curve in doc["curves"] if curve["id"]=="ease"),None),"clips":doc["clips"],"markers":doc["markers"]})
        documents.append({"id":head["id"],"project_id":head["project_id"],"head":head["head"],"revisions":revisions})
    downloads = []
    log = directory/"download-evidence.jsonl"
    for line in log.read_text().splitlines() if log.exists() else ():
        item = json.loads(line)
        name = item["filename"]
        identity, version = name.removeprefix("animation-").removesuffix(".json").rsplit("-v",1)
        row = connection.execute("SELECT document,content_hash FROM revisions WHERE id=? AND version=?",(identity,int(version))).fetchone()
        raw = Path(item["path"]).read_bytes()
        match = raw == row["document"].encode()
        assert item["state"] == "completed" and match and hashlib.sha256(raw).hexdigest() == row["content_hash"]
        downloads.append({"file":name,"version":int(version),"bytes":len(raw),"sha256":row["content_hash"],"state":item["state"],"boundary":item["boundary"],"matches_canonical":match})
    connection.close()
    metadata = sqlite3.connect((directory/"metadata.sqlite").as_uri()+"?mode=ro",uri=True)
    metadata.row_factory = sqlite3.Row
    invocations = [dict(row) for row in metadata.execute("SELECT owner_id,package_digest,tool_name,status FROM agent_tool_invocations WHERE owner_id='dbfox.animation'")]
    metadata.close()
    return {"package_digest":selected,"files":files,"documents":documents,"downloads":downloads,
        "native_action_invocations":invocations,
        "scope":"Author read-only audit. Native save destination was controlled; Electron received/wrote the bytes. No model endpoint or independent reviewer claim."}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("runtime",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.runtime.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"package_digest":result["package_digest"],"documents":len(result["documents"]),"downloads":len(result["downloads"])}))
