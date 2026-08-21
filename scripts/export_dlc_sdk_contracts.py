"""Export generated, reviewable DLC SDK schema artifacts from runtime models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from engine.dlc.manifest import DlcManifestV2

MANIFEST_SCHEMA_PATH = REPOSITORY_ROOT / "sdk" / "schema" / "manifest.schema.json"


def render_manifest_schema() -> str:
    schema = DlcManifestV2.model_json_schema(by_alias=True)
    schema["$id"] = "https://dbfox.dev/schemas/dlc/manifest-v2.json"
    schema["title"] = "DBFox DLC Manifest"
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render_manifest_schema()
    if args.check:
        if not MANIFEST_SCHEMA_PATH.is_file():
            raise SystemExit(f"Missing generated schema: {MANIFEST_SCHEMA_PATH}")
        if MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8") != expected:
            raise SystemExit(
                "DLC manifest schema is stale; run python scripts/export_dlc_sdk_contracts.py"
            )
        return 0
    MANIFEST_SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_SCHEMA_PATH.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
