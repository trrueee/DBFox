"""Independent signed-package persistence/fault verification; product code is never repaired here."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from dbfox_dlc_api import DlcOperationError, ResourceScopeRef, ToolKey
from engine.dlc import BuiltinContributionSet, ContributionCompiler
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_pixel.runtime import PixelRuntime

PROJECT = "pixel-independent-faults"


@pytest.fixture
def runtime(tmp_path):
    with PixelRuntime(tmp_path / "runtime") as value:
        yield value


def store(runtime):
    return next(item.tool.store for item in runtime.snapshot.tools if item.tool.name == "pixel_create")


def create(runtime):
    return runtime.operation(PROJECT, "documents.create", {"title": "Independent faults", "width": 8, "height": 8,
        "expected_version": 0, "mutation_id": "create"})


def edit(runtime, current, identity="edit", **fields):
    return runtime.operation(PROJECT, "documents.apply", {"document_id": current["document_id"],
        "expected_version": current["revision"], "mutation_id": identity,
        "operations": [{"kind": "rect", "frame_id": "frame_1", "layer_id": "layer_1",
                        "rect": {"x": 1, "y": 1, "width": 2, "height": 2}, "palette_index": 1}], **fields})


def invoke(runtime, payload, ref, identity, *, reconcile=False, **options):
    name = runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.pixel", local_name="pixel_rect"))
    resolver = build_attempt_resource_resolver(snapshot=runtime.snapshot)
    method = ToolRuntime(runtime.registry).reconcile if reconcile else ToolRuntime(runtime.registry).invoke
    return method(tool_name=name, raw_input=payload, request=None, invocation_id=identity, idempotency_key=identity,
        scope_refs=(ref,), resources=resolver.resolve((ref,)), **options)


def tool_payload(current, color=1):
    return {"document_id": current["document_id"], "expected_version": current["revision"], "operation": {
        "kind": "rect", "frame_id": "frame_1", "layer_id": "layer_1", "rect": {"x": 1, "y": 1, "width": 2, "height": 2}, "palette_index": color}}


def test_signed_deactivate_reactivate_preserves_fixed_frame_and_cleans_contributions(runtime):
    initial = create(runtime)
    changed = edit(runtime, initial)
    before = runtime.document(PROJECT, initial["document_id"], 1)
    runtime.service.set_desired_enabled("dbfox.pixel", False)
    compiler = ContributionCompiler(runtime.service.storage_root)
    disabled = compiler.compile(built_ins=BuiltinContributionSet())
    assert not disabled.active_dlcs and not disabled.activation_failures
    assert not disabled.tools and not disabled.operations and not disabled.context_contributors
    assert not disabled.resource_providers and not disabled.resource_resolvers and not disabled.artifact_representations
    runtime.service.set_desired_enabled("dbfox.pixel", True)
    runtime.snapshot = compiler.compile(built_ins=BuiltinContributionSet())
    assert not runtime.snapshot.activation_failures
    assert runtime.document(PROJECT, initial["document_id"], 1) == before
    assert runtime.operation(PROJECT, "documents.get", {"document_id": initial["document_id"]})["summary"] == {k: v for k, v in changed.items() if not k.startswith("changed")}


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
def test_no_write_before_runtime_start(runtime, failure):
    initial = create(runtime)
    ref = ResourceScopeRef(kind="dbfox.pixel.document", id=initial["document_id"], version="1")
    options = {"cancellation_probe": lambda: True} if failure == "cancel" else {"deadline": time.monotonic() - 1}
    result = invoke(runtime, tool_payload(initial), ref, failure, **options)
    assert result.error_code == ("TOOL_CANCELLED" if failure == "cancel" else "TOOL_TIMEOUT")
    assert runtime.operation(PROJECT, "documents.head", {"document_id": initial["document_id"]})["revision"] == 1


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
def test_unknown_after_commit_reconciles_original_after_human_changes(runtime, monkeypatch, failure):
    initial = create(runtime)
    owner = store(runtime)
    original = owner.mutate
    committed = False
    calls = 0
    def mutate(*args, **kwargs):
        nonlocal committed, calls
        result = original(*args, **kwargs)
        calls += 1
        committed = True
        if failure == "timeout":
            time.sleep(0.08)
        return result
    monkeypatch.setattr(owner, "mutate", mutate)
    ref = ResourceScopeRef(kind="dbfox.pixel.document", id=initial["document_id"], version="1")
    options = {"cancellation_probe": lambda: committed} if failure == "cancel" else {"deadline": time.monotonic() + 0.05}
    result = invoke(runtime, tool_payload(initial), ref, "unknown", **options)
    assert result.error_code == ("TOOL_CANCELLED" if failure == "cancel" else "TOOL_TIMEOUT")
    assert calls == 1
    head = runtime.operation(PROJECT, "documents.get", {"document_id": initial["document_id"]})["summary"]
    assert head["revision"] == 2
    monkeypatch.setattr(owner, "mutate", original)
    runtime.operation(PROJECT, "documents.delete", {"document_id": initial["document_id"], "expected_version": 2, "mutation_id": "delete-after-unknown"})
    recovered = invoke(runtime, tool_payload(initial), ref, "unknown", reconcile=True)
    assert recovered.status == "success" and recovered.output["revision"] == 2
    assert recovered.artifact_drafts[0].payload["content_hash"] == head["content_hash"]
    assert runtime.operation(PROJECT, "documents.head", {"document_id": initial["document_id"]})["revision"] == 3
    assert calls == 1


def test_cancel_after_revision_insert_rolls_back_birth_head_and_receipt(runtime, monkeypatch):
    initial = create(runtime)
    owner = store(runtime)
    original = owner._save_revision
    inserted = False
    def insert(*args, **kwargs):
        nonlocal inserted
        original(*args, **kwargs)
        inserted = True
    monkeypatch.setattr(owner, "_save_revision", insert)
    ref = ResourceScopeRef(kind="dbfox.pixel.document", id=initial["document_id"], version="1")
    result = invoke(runtime, tool_payload(initial), ref, "cancel-in-transaction", cancellation_probe=lambda: inserted)
    assert result.status != "success"
    with sqlite3.connect(owner.path) as db:
        assert db.execute("SELECT head FROM documents").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM receipts WHERE identity='cancel-in-transaction'").fetchone()[0] == 0


def test_real_receipt_failure_rolls_back_all_prior_changes(runtime):
    initial = create(runtime)
    with sqlite3.connect(store(runtime).path) as db:
        db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(DlcOperationError) as failure:
        edit(runtime, initial)
    assert failure.value.code == "PIXEL_CORRUPT_STATE"
    with sqlite3.connect(store(runtime).path) as db:
        assert db.execute("SELECT head FROM documents").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1
        db.execute("DROP TRIGGER reject_receipt")
    assert edit(runtime, initial)["revision"] == 2


@pytest.mark.parametrize("damage", ["head_rewind", "missing_parent", "schema_bool", "invalid_cel", "receipt_result", "future_schema"])
def test_durable_corruption_fails_closed_at_public_read_or_exact_retry(runtime, damage):
    initial = create(runtime)
    current = edit(runtime, initial)
    owner = store(runtime)
    with sqlite3.connect(owner.path) as db:
        if damage == "head_rewind":
            db.execute("UPDATE documents SET head=1")
        elif damage == "missing_parent":
            db.execute("DELETE FROM revisions WHERE revision=1")
        elif damage in ("schema_bool", "invalid_cel"):
            body = json.loads(db.execute("SELECT body FROM revisions WHERE revision=2").fetchone()[0])
            if damage == "schema_bool":
                body["schema_version"] = True
            else:
                body["frames"][0]["cels"][0]["pixels"][0] = 255
            encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            db.execute("UPDATE revisions SET body=?,content_hash=? WHERE revision=2", (encoded, hashlib.sha256(encoded).hexdigest()))
        elif damage == "receipt_result":
            db.execute("UPDATE receipts SET result_body=? WHERE identity='edit'", (b'{"document_id":true}',))
        else:
            db.execute("PRAGMA user_version=99")
    if damage == "future_schema":
        with pytest.raises(Exception, match="Unsupported Pixel storage schema"):
            type(owner)(owner.path.parent)
    elif damage == "receipt_result":
        with pytest.raises(DlcOperationError) as failure:
            edit(runtime, initial)
        assert failure.value.code == "PIXEL_CORRUPT_STATE"
    else:
        with pytest.raises(DlcOperationError) as failure:
            runtime.operation(PROJECT, "documents.get", {"document_id": current["document_id"]})
        assert failure.value.code == "PIXEL_CORRUPT_STATE"


def test_concurrent_human_and_agent_use_one_head_without_lost_update(runtime):
    initial = create(runtime)
    ref = ResourceScopeRef(kind="dbfox.pixel.document", id=initial["document_id"], version="1")
    barrier = threading.Barrier(2)
    def human():
        barrier.wait()
        try:
            return edit(runtime, initial)
        except Exception as exc:
            return str(exc)
    def agent():
        barrier.wait()
        return invoke(runtime, tool_payload(initial, 2), ref, "agent-race")
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(human), pool.submit(agent)
        human_result, agent_result = a.result(), b.result()
    assert isinstance(human_result, dict) != (agent_result.status == "success")
    final = runtime.document(PROJECT, initial["document_id"], 2)
    pixels = final["frame_reads"][0]["frame"]["cels"][0]["pixels"]
    assert {pixels[i] for i in (9, 10, 17, 18)} in ({1}, {2})
    assert sum(bool(v) for v in pixels) == 4


@pytest.mark.parametrize("read", ["documents.head", "documents.list"])
@pytest.mark.parametrize("damage", ["head_rewind", "missing_parent"])
def test_lightweight_head_and_directory_share_corruption_fence(runtime, read, damage):
    initial = create(runtime)
    edit(runtime, initial)
    with sqlite3.connect(store(runtime).path) as db:
        db.execute("UPDATE documents SET head=1" if damage == "head_rewind" else "DELETE FROM revisions WHERE revision=1")
    with pytest.raises(DlcOperationError) as failure:
        runtime.operation(PROJECT, read, {} if read == "documents.list" else {"document_id": initial["document_id"]})
    assert failure.value.code == "PIXEL_CORRUPT_STATE"


@pytest.mark.parametrize("damage", ["historical_parent_missing", "head_parent_wrong"])
def test_fixed_historical_read_validates_actual_ancestry(runtime, damage):
    initial = create(runtime)
    second = edit(runtime, initial)
    edit(runtime, second, "third", operations=[{"kind": "rename", "title": "Third revision"}])
    with sqlite3.connect(store(runtime).path) as db:
        if damage == "historical_parent_missing":
            db.execute("DELETE FROM revisions WHERE revision=1")
        else:
            db.execute("UPDATE revisions SET parent_revision=1 WHERE revision=3")
    with pytest.raises(DlcOperationError) as failure:
        runtime.operation(PROJECT, "documents.get", {"document_id": initial["document_id"], "revision": 2})
    assert failure.value.code == "PIXEL_CORRUPT_STATE"


def test_subprocess_crash_inside_signed_product_transaction_is_atomic(runtime):
    initial = create(runtime)
    code = '''
import os,sys
from pathlib import Path
from engine.dlc import BuiltinContributionSet,ContributionCompiler
from dbfox_dlc_api import DlcOperationContext
snapshot=ContributionCompiler(Path(sys.argv[1])).compile(built_ins=BuiltinContributionSet())
assert not snapshot.activation_failures
tool=next(x.tool for x in snapshot.tools if x.tool.name=="pixel_create")
tool.store._save_receipt=lambda *args:os._exit(73)
op=snapshot.get_operation("dbfox.pixel","documents.apply").spec
payload=op.input_model.model_validate({"document_id":sys.argv[2],"expected_version":1,"mutation_id":"crash", "operations":[{"kind":"frame_create","frame_id":"crashed-frame","position":1}]})
op.handler(payload,DlcOperationContext(dlc_id="dbfox.pixel",operation_name="documents.apply",project_id=sys.argv[3]))
'''
    result = subprocess.run([sys.executable, "-c", code, str(runtime.service.storage_root), initial["document_id"], PROJECT],
        cwd=str(Path(__file__).resolve().parents[3]), env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3])}, capture_output=True, text=True, check=False)
    assert result.returncode == 73, result.stderr
    reopened = type(store(runtime))(store(runtime).path.parent)
    assert reopened.get_revision(PROJECT, initial["document_id"]).summary.revision == 1
    with sqlite3.connect(reopened.path) as db:
        assert db.execute("SELECT COUNT(*) FROM object_identities WHERE object_id='crashed-frame'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM receipts WHERE identity='crash'").fetchone()[0] == 0
    assert edit(runtime, initial, operations=[{"kind": "frame_create", "frame_id": "crashed-frame", "position": 1}])["revision"] == 2


def test_two_hundred_frames_fit_existing_slot_budget(runtime):
    current = runtime.operation(PROJECT, "documents.create", {"title": "200 frame scale gate", "width": 32, "height": 32,
        "expected_version": 0, "mutation_id": "scale-create"})
    for start in range(1, 200, 32):
        current = edit(runtime, current, f"scale-{start}", operations=[
            {"kind": "frame_create", "frame_id": f"scale_{index}", "position": index}
            for index in range(start, min(200, start + 32))])
    value = runtime.operation(PROJECT, "documents.get", {"document_id": current["document_id"]})
    assert value["summary"]["frame_count"] == 200
    assert len(value["document"]["frames"]) == 200
    assert 32 * 32 * len(value["document"]["frames"]) * len(value["document"]["layers"]) <= 262144
    assert len(json.dumps(value["document"], separators=(",", ":")).encode()) < 2 * 1024 * 1024


@pytest.mark.parametrize("damage", ["false_truncation", "missing_truncation", "false_changed"])
def test_exact_receipt_rejects_derived_change_summary_corruption(runtime, damage):
    current = create(runtime)
    for start in range(1, 200, 64):
        current = edit(runtime, current, f"receipt-frames-{start}", operations=[
            {"kind": "frame_create", "frame_id": f"scale_{index}", "position": index}
            for index in range(start, min(200, start + 64))])
    operations = [{"kind": "layer_create", "layer_id": "receipt-overlay", "name": "Overlay", "position": 1}]
    result = edit(runtime, current, "all-frames", operations=operations)
    assert result["changed_frame_ids_truncated"] is True and len(result["changed_frame_ids"]) == 128
    with sqlite3.connect(store(runtime).path) as db:
        body = json.loads(db.execute("SELECT result_body FROM receipts WHERE identity='all-frames'").fetchone()[0])
        if damage == "missing_truncation":
            body.pop("changed_frame_ids_truncated")
        elif damage == "false_truncation":
            body["changed_frame_ids_truncated"] = False
        else:
            body["changed"] = False
        db.execute("UPDATE receipts SET result_body=? WHERE identity='all-frames'", (json.dumps(body).encode(),))
    with pytest.raises(DlcOperationError) as failure:
        edit(runtime, current, "all-frames", operations=operations)
    assert failure.value.code == "PIXEL_CORRUPT_STATE"
