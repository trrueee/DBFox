"""Capture public fixed-revision pages from the full signed production package.

Run from repository root after importing conftest isolation (the module does so).
Only bounded public document data is written; no keys, tokens, databases or logs.
"""
from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
import tempfile
from uuid import uuid4

from verification import conftest  # noqa: F401  -- isolation before DBFox imports
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime

assert conftest.PYTEST_RUNTIME_ROOT.is_dir()


def main():
    directory = Path(tempfile.mkdtemp(prefix="dbfox-shader-adversarial-pages-"))
    with ShaderRuntime(directory) as runtime:
        project = str(uuid4())
        created = runtime.operation(project, "documents.create", {"title": "Paged shader 日本語 🦊",
            "expected_generation": 0, "request_id": str(uuid4())})
        ids = created["created_refs"]
        identity = created["document"]["id"]
        original_source = runtime.operation(project, "documents.get", {"document_id": identity, "version": 1,
            "section": "source", "stage_id": ids["fragment"], "limit": 50})["source"]
        changed = runtime.operation(project, "documents.apply", {"document_id": identity,
            "expected_version": 1, "request_id": str(uuid4()), "operations": [
                {"kind": "stage_replace", "stage_id": {"id": ids["fragment"]},
                    "source": original_source + "".join(f"// fox 🦊 unicode 界 paged comment {number:04d}\n" for number in range(1000))},
                {"kind": "uniform_create", "pass_id": {"id": ids["pass"]}, "name": "strength", "type": "float", "value": 0.25},
                {"kind": "texture_create", "title": "RGBA corners", "width": 2, "height": 2,
                    "rgba_base64": base64.b64encode(bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255])).decode()},
            ]})
        pages = []

        def capture(section, **kwargs):
            parameters = {"section": section, **kwargs}
            value = runtime.operation(project, "documents.get", {"document_id": identity, "version": 2, **parameters})
            pages.append({"parameters": parameters, "page": value})
            return value

        capture("summary")
        offset = 0
        while True:
            value = capture("document_bytes", offset=offset, limit=16384)
            if not value["has_more"]:
                break
            offset = value["next_offset"]
        stages = capture("stages", offset=0, limit=50)["items"]
        for stage in stages:
            offset = 0
            while True:
                value = capture("source", stage_id=stage["id"], offset=offset, limit=50)
                if not value["has_more"]:
                    break
                offset = value["next_offset"]
        capture("passes", offset=0, limit=50)
        capture("uniforms", offset=0, limit=50)
        textures = capture("textures", offset=0, limit=50)["items"]
        for texture in textures:
            capture("texture_bytes", texture_id=texture["id"], offset=0, limit=16384)
        output = {"package_digest": runtime.package.package_digest, "summary": changed["document"], "pages": pages}
        target = Path(__file__).with_name("evidence") / "public-pages.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        original = target.with_name("public-pages-before-fix.json")
        if target.exists() and not original.exists():
            shutil.copyfile(target, original)
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"path": str(target), "pages": len(pages), "package_digest": runtime.package.package_digest}))


if __name__ == "__main__":
    main()
