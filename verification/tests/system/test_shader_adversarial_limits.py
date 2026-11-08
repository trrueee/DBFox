"""Independent byte, canonical, quota and cross-project boundary attacks."""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dbfox_dlc_api import DlcOperationError
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


@pytest.fixture
def source(tmp_path):
    with ShaderRuntime(tmp_path) as runtime:
        project = str(uuid4())
        first = runtime.operation(project, "documents.create", {"title": "Canonical boundary",
            "expected_generation": 0, "request_id": str(uuid4())})
        store = next(item.tool.store for item in runtime.snapshot.tools
            if item.owner_id == "dbfox.shader" and item.tool.name == "shader_create")
        yield runtime, project, first, store


@pytest.mark.parametrize("fault", ["schema-bool", "schema-float", "unknown-null", "preview-bool", "required-null"])
def test_canonical_storage_revalidates_types_even_with_consistent_framing(source, fault):
    runtime, project, first, store = source
    identity = first["document"]["id"]
    with sqlite3.connect(store.path) as db:
        old = db.execute("SELECT payload FROM revisions WHERE id=?", (identity,)).fetchone()[0]
        document = json.loads(old)
        if fault == "schema-bool":
            document["schema_version"] = True
        elif fault == "schema-float":
            document["schema_version"] = 1.0
        elif fault == "unknown-null":
            document["preview"]["hidden_override"] = None
        elif fault == "preview-bool":
            document["preview"]["width"] = True
        else:
            document["stages"][0]["source"] = None
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        payload = encode(document)
        fingerprint = sha256(encode({"document": document, "deleted": False})).hexdigest()
        db.execute("UPDATE revisions SET payload=?,hash=? WHERE id=?", (payload, fingerprint, identity))
        db.execute("UPDATE quota SET payload_bytes=payload_bytes+?", (len(payload)-len(old),))
    for section in ("summary", "document_bytes"):
        with pytest.raises(DlcOperationError) as error:
            runtime.operation(project, "documents.get", {"document_id": identity, "version": 1, "section": section})
        assert error.value.code == "SHADER_CORRUPT"


def test_canonical_byte_pages_are_pinned_complete_bounded_and_project_owned(source):
    runtime, project, first, _ = source
    identity = first["document"]["id"]
    text = "#version 300 es\n" + "".join(f"// boundary 🦊 unicode 界 {n:04d}\n" for n in range(1300))
    second = runtime.operation(project, "documents.apply", {"document_id": identity, "expected_version": 1,
        "request_id": str(uuid4()), "operations": [{"kind": "stage_replace", "stage_id": {"id": first["created_refs"]["fragment"]}, "source": text}]})
    raw, offset, total, reads = bytearray(), 0, None, 0
    while True:
        page = runtime.operation(project, "documents.get", {"document_id": identity, "version": 2,
            "section": "document_bytes", "offset": offset, "limit": 16384})
        assert len(json.dumps(page, ensure_ascii=False).encode()) <= 32768
        assert page["document"] == second["document"] and page["offset"] == offset
        if total is None:
            total = page["total"]
            runtime.operation(project, "documents.apply", {"document_id": identity, "expected_version": 2,
                "request_id": str(uuid4()), "operations": [{"kind": "rename_document", "title": "Current head changed after first byte page"}]})
        assert page["total"] == total <= 1048608
        selected = base64.b64decode(page["document_bytes"], validate=True)
        assert 0 < len(selected) <= 16384 and page["next_offset"] == offset + len(selected)
        raw.extend(selected)
        offset = page["next_offset"]
        reads += 1
        assert page["has_more"] == (offset < total)
        if not page["has_more"]:
            break
    assert reads >= 3 and len(raw) == total
    assert sha256(raw).hexdigest() == second["document"]["content_hash"]
    assert json.loads(raw)["document"]["stages"][1]["source"] == text
    terminal = runtime.operation(project, "documents.get", {"document_id": identity, "version": 2,
        "section": "document_bytes", "offset": total, "limit": 1})
    assert terminal["document_bytes"] == "" and not terminal["has_more"] and terminal["next_offset"] == total
    bad = [({"document_id": identity, "section": "document_bytes"}, project),
        ({"document_id": identity, "version": 2, "section": "document_bytes", "offset": total + 1}, project),
        ({"document_id": identity, "version": 2, "section": "document_bytes", "limit": 16385}, project),
        ({"document_id": identity, "version": 2, "section": "document_bytes", "stage_id": first["created_refs"]["fragment"]}, project),
        ({"document_id": identity, "version": 2, "section": "document_bytes"}, str(uuid4()))]
    for payload, scope in bad:
        with pytest.raises((ValidationError, DlcOperationError)):
            runtime.operation(scope, "documents.get", payload)


def test_quota_exhausted_only_at_receipt_rolls_back_the_actual_new_revision(source, monkeypatch):
    runtime, project, first, store = source
    identity = first["document"]["id"]
    with sqlite3.connect(store.path) as db:
        quota = db.execute("SELECT payload_bytes FROM quota").fetchone()[0]
        original = json.loads(db.execute("SELECT payload FROM revisions WHERE id=?", (identity,)).fetchone()[0])
    title = "Receipt alone exhausts quota"
    original["title"] = title
    revision_size = len(json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    monkeypatch.setattr(store, "history_limit", quota + revision_size)
    request_id = str(uuid4())
    with pytest.raises(DlcOperationError) as error:
        runtime.operation(project, "documents.apply", {"document_id": identity, "expected_version": 1,
            "request_id": request_id, "operations": [{"kind": "rename_document", "title": title}]})
    assert error.value.code == "SHADER_HISTORY_FULL"
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT payload_bytes FROM quota").fetchone()[0] == quota
        assert db.execute("SELECT count(*) FROM revisions WHERE id=?", (identity,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM receipts WHERE request_id=?", (request_id,)).fetchone()[0] == 0
    page = runtime.operation(project, "documents.get", {"document_id": identity})
    assert page["document"] == first["document"] and page["studio_generation"] == 1


def test_final_graph_and_encoded_source_rejections_do_not_leave_partial_edits(source):
    runtime, project, first, store = source
    ids = first["created_refs"]
    invalid_operations = [
        [{"kind": "stage_remove", "stage_id": {"id": ids["fragment"]}}],
        [{"kind": "binding_set", "pass_id": {"id": ids["pass"]}, "name": "feedback",
            "source": {"kind": "pass", "pass_id": {"id": ids["pass"]}}}],
        [{"kind": "texture_create", "title": "External", "width": 1, "height": 1, "rgba_base64": "https://example.invalid/image.png"}],
        [{"kind": "stage_replace", "stage_id": {"id": ids["fragment"]}, "source": "界" * 683}],
        [{"kind": "stage_create", "ref": "future", "stage_kind": "fragment", "title": "Uncommitted", "source": ""},
         {"kind": "stage_replace", "stage_id": {"ref": "missing"}, "source": ""}],
    ]
    with sqlite3.connect(store.path) as db:
        before = tuple(db.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in ("revisions", "receipts", "textures", "identities"))
    for operations in invalid_operations:
        with pytest.raises((ValidationError, DlcOperationError)):
            runtime.operation(project, "documents.apply", {"document_id": first["document"]["id"],
                "expected_version": 1, "request_id": str(uuid4()), "operations": operations})
    with sqlite3.connect(store.path) as db:
        assert tuple(db.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in ("revisions", "receipts", "textures", "identities")) == before
