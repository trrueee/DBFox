"""Separate red team: signed-owner public reads after durable/projection faults.

SQL writes below are deliberate corruption injection, never a second product path.
The package and operations are the production registered contributions.
"""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

import pytest

from dbfox_dlc_api import DlcOperationError
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


@pytest.fixture
def signed(tmp_path):
    with ShaderRuntime(tmp_path) as runtime:
        yield runtime


def create(runtime, project=None):
    project = project or str(uuid4())
    generation = runtime.operation(project, "documents.list", {})["studio_generation"]
    data = {"title": "Adversarial durable source", "expected_generation": generation,
            "request_id": str(uuid4())}
    return project, data, runtime.operation(project, "documents.create", data)


def owner_store(runtime):
    return next(item.tool.store for item in runtime.snapshot.tools
                if item.owner_id == "dbfox.shader" and item.tool.name == "shader_create")


def apply(runtime, project, created, operations):
    return runtime.operation(project, "documents.apply", {
        "document_id": created["document"]["id"],
        "expected_version": created["document"]["version"],
        "request_id": str(uuid4()), "operations": operations})


@pytest.mark.parametrize("column", ["version", "generation"])
@pytest.mark.parametrize("bad", [0, -1, 0.5])
@pytest.mark.parametrize("entry", ["documents.head", "documents.get", "documents.list"])
def test_zero_historical_index_cannot_compensate_for_a_missing_first_revision(signed, column, entry, bad):
    project, _, first = create(signed)
    second = apply(signed, project, first, [{"kind": "rename_document", "title": "Second"}])
    identity = first["document"]["id"]
    assert second["document"]["version"] == 2
    # count=2 and max=2 still hold, but the valid one-based sequence is now 0,2.
    assert column in {"version", "generation"}
    with sqlite3.connect(owner_store(signed).path) as db:
        db.execute(f"UPDATE revisions SET {column}=? WHERE id=? AND version=1", (bad, identity))
    payload = {} if entry == "documents.list" else {"document_id": identity}
    with pytest.raises(DlcOperationError) as error:
        signed.operation(project, entry, payload)
    assert error.value.code == "SHADER_CORRUPT"


@pytest.mark.parametrize("field,value", [("title", "Forged receipt title"), ("content_hash", "a" * 64)])
def test_receipt_summary_must_match_its_immutable_document(signed, field, value):
    project, request, first = create(signed)
    with sqlite3.connect(owner_store(signed).path) as db:
        old = db.execute("SELECT payload FROM receipts WHERE request_id=?", (request["request_id"],)).fetchone()[0]
        body = json.loads(old)
        body["document"][field] = value
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        # Keep storage framing valid to isolate semantic source binding.
        db.execute("UPDATE receipts SET payload=?,hash=? WHERE request_id=?",
                   (payload, sha256(payload).hexdigest(), request["request_id"]))
        db.execute("UPDATE quota SET payload_bytes=payload_bytes+?", (len(payload) - len(old),))
    head = signed.operation(project, "documents.head", {"document_id": first["document"]["id"]})
    assert head == {key: first["document"][key] for key in ("id", "version", "content_hash", "deleted")}
    with pytest.raises(DlcOperationError) as error:
        signed.operation(project, "documents.create", request)
    assert error.value.code == "SHADER_CORRUPT"


def test_pass_reorder_is_visible_in_mutation_and_diff(signed):
    project, _, first = create(signed)
    ids = first["created_refs"]
    second = apply(signed, project, first, [{"kind": "pass_create", "ref": "other", "title": "Independent pass",
        "vertex_stage_id": {"id": ids["vertex"]}, "fragment_stage_id": {"id": ids["fragment"]},
        "width": 2, "height": 2, "clear_color": [0., 0., 0., 1.]}])
    order = [second["created_refs"]["other"], ids["pass"]]
    third = apply(signed, project, second, [{"kind": "pass_reorder", "pass_ids": [{"id": value} for value in order]}])
    assert third["changed"] and third["document"]["content_hash"] != second["document"]["content_hash"]
    page = signed.operation(project, "documents.get", {"document_id": first["document"]["id"], "version": 3, "section": "passes"})
    assert [value["id"] for value in page["items"]] == order
    difference = signed.operation(project, "documents.diff", {"document_id": first["document"]["id"], "from_version": 2, "to_version": 3})
    assert difference["total"] > 0, difference
    assert set(order).issubset(third["changed_ids"]), third


def test_reorder_noop_and_undo_of_undo_preserve_order_diffs(signed):
    project, _, first = create(signed)
    ids = first["created_refs"]
    second = apply(signed, project, first, [{"kind": "pass_create", "ref": "other", "title": "Other",
        "vertex_stage_id": {"id": ids["vertex"]}, "fragment_stage_id": {"id": ids["fragment"]},
        "width": 1, "height": 1, "clear_color": [0., 0., 0., 1.]}])
    order = [second["created_refs"]["other"], ids["pass"]]
    operation = [{"kind": "pass_reorder", "pass_ids": [{"id": value} for value in order]}]
    third = apply(signed, project, second, operation)
    noop = apply(signed, project, third, operation)
    assert not noop["changed"] and noop["changed_ids"] == [] and noop["document"] == third["document"]
    fourth = signed.operation(project, "documents.undo", {"document_id": first["document"]["id"],
        "expected_version": 3, "target_version": 2, "request_id": str(uuid4())})
    fifth = signed.operation(project, "documents.undo", {"document_id": first["document"]["id"],
        "expected_version": 4, "target_version": 3, "request_id": str(uuid4())})
    assert fourth["document"]["content_hash"] == second["document"]["content_hash"]
    assert fifth["document"]["content_hash"] == third["document"]["content_hash"]
    page = signed.operation(project, "documents.diff", {"document_id": first["document"]["id"], "from_version": 4, "to_version": 5})
    assert page["total"] == 2 and {item["id"] for item in page["items"]} == set(order)


def test_noop_receipt_remains_valid_after_other_document_generation_changes(signed):
    project, _, first = create(signed)
    _, _, second = create(signed, project)
    request = {"document_id": first["document"]["id"], "expected_version": 1, "request_id": str(uuid4()),
        "operations": [{"kind": "rename_document", "title": first["document"]["title"]}]}
    noop = signed.operation(project, "documents.apply", request)
    assert noop["studio_generation"] == 2 and not noop["changed"]
    apply(signed, project, second, [{"kind": "rename_document", "title": "Unrelated generation 3"}])
    assert signed.operation(project, "documents.apply", request) == noop
