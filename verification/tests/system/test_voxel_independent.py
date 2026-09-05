"""Independent fault checks. Reuse setup only, never author test assertions."""
from __future__ import annotations

from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import threading
import time

import pytest
from engine.tools.runtime.executor import ToolExecutor
from engine.tools.runtime.registry import provider_tool_name
from engine.tools.runtime.resource_authority import bind_tool_invocation_resources

from verification.tests.system import test_voxel_dlc as owner_setup

modules = owner_setup.modules
harness = owner_setup.harness
fill = owner_setup.fill


def durable_rows(harness):
    with closing(sqlite3.connect(harness.store.database_path)) as db:
        return {name: db.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
                for name in ("worlds", "world_revisions", "chunk_versions", "operation_receipts")}


def test_foreign_project_cannot_read_edit_or_reuse_world_receipt(harness):
    world = harness.create()
    changed = harness.apply(world, fill([0, 0, 0], [2, 2, 2], 2), "shared-request")
    before = durable_rows(harness)
    for name, payload in (
        ("worlds.get", {"world_id":world.world_id,"version":2}),
        ("worlds.chunks", {"world_id":world.world_id,"version":2}),
        ("worlds.apply", {"world_id":world.world_id,"expected_version":1,"mutation_id":"shared-request","operation":fill([0,0,0],[2,2,2],2)})):
        with pytest.raises(owner_setup.DlcOperationError) as failure:
            harness.operation(name,payload,project="foreign-project")
        assert failure.value.code == "WORLD_NOT_FOUND"
    assert durable_rows(harness) == before
    assert harness.apply(world, fill([0,0,0],[2,2,2],2), "shared-request") == changed


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_process_crash_preserves_atomic_receipt_and_history(harness, tmp_path, phase):
    world = harness.create()
    payload = {"world_id": world.world_id, "expected_version": 1, "operation": fill([1, 2, 3], [3, 4, 5], 2)}
    request = tmp_path / "request.json"
    request.write_text(json.dumps(payload), encoding="utf-8")
    child = subprocess.run([sys.executable, "-m", "verification.bench.capabilities.dbfox_voxel.fault_worker",
        str(harness.store.database_path.parent), str(request), phase], capture_output=True, text=True, timeout=30)
    assert child.returncode == 73, child.stderr
    reopened = harness.store_module.VoxelStore(harness.store.database_path.parent)
    snapshot = reopened.snapshot("project-voxel", world.world_id)
    receipt = reopened.receipt("project-voxel", "human", "crash-write", "fill", harness.models.ApplyInput(**payload))
    rows = durable_rows(harness)
    if phase == "before_commit":
        assert snapshot.version == 1 and receipt is None
        assert len(rows["world_revisions"]) == 1 and len(rows["chunk_versions"]) == 0
    else:
        assert snapshot.version == 2 and receipt.version == 2
        assert reopened.summary(snapshot).nonzero_count == 8
        assert len(rows["world_revisions"]) == 2 and len(rows["chunk_versions"]) == 1
        before = durable_rows(harness)
        assert reopened.mutate("project-voxel", harness.models.ApplyInput(**payload), kind="fill",
            origin="human", request_id="crash-write") == receipt
        assert durable_rows(harness) == before


@pytest.mark.parametrize("corruption", ["malformed", "other_world", "other_project", "other_version", "hash", "count",
    "title", "size", "status", "parent", "changed", "changed_type", "changed_chunks", "changed_voxels", "operation"])
def test_corrupt_receipt_cannot_claim_success_or_change_durable_rows(harness, corruption):
    world = harness.create()
    changed = harness.apply(world, fill([0, 0, 0], [2, 2, 2], 2), "receipt-fault")
    raw = changed.model_dump(mode="json")
    alterations = {"other_world": ("world_id", "different-world"), "other_project": ("project_id", "different-project"),
        "other_version": ("version", 1), "hash": ("content_hash", "sha256:" + "0" * 64), "count": ("nonzero_count", 4096),
        "title": ("title", "Forged"), "size": ("size", [64, 64, 64]), "status": ("status", "deleted"),
        "parent": ("parent_version", None), "changed": ("changed", False), "changed_type": ("changed", 1),
        "changed_chunks": ("changed_chunk_count", 2), "changed_voxels": ("changed_voxel_count", 99), "operation": ("operation_kind", "undo")}
    if corruption == "malformed":
        encoded = "{broken"
    else:
        field, value = alterations[corruption]
        raw[field] = value
        encoded = json.dumps(raw)
    with closing(sqlite3.connect(harness.store.database_path)) as db:
        db.execute("UPDATE operation_receipts SET outcome_json=? WHERE request_id='receipt-fault'", (encoded,))
        db.commit()
    before = durable_rows(harness)
    with pytest.raises(Exception, match="receipt|CORRUPT_STATE|corrupt"):
        harness.apply(world, fill([0, 0, 0], [2, 2, 2], 2), "receipt-fault")
    assert durable_rows(harness) == before


@pytest.mark.parametrize("field,value", [("base_version", 2), ("result_version", 1), ("operation_kind", "undo"), ("world_id", "missing")])
def test_corrupt_receipt_columns_cannot_override_request_identity(harness, field, value):
    world = harness.create()
    harness.apply(world, fill([0, 0, 0], [2, 2, 2]), "column-fault")
    with closing(sqlite3.connect(harness.store.database_path)) as db:
        db.execute(f"UPDATE operation_receipts SET {field}=? WHERE request_id='column-fault'", (value,))
        db.commit()
    before = durable_rows(harness)
    with pytest.raises(Exception, match="receipt|CORRUPT_STATE|different voxel input"):
        harness.apply(world, fill([0, 0, 0], [2, 2, 2]), "column-fault")
    assert durable_rows(harness) == before


@pytest.mark.parametrize("field,value", [("expected_version", True), ("expected_version", 1.0),
    ("expected_version", "1"), ("coordinate", True), ("coordinate", 1.5), ("palette_index", False),
    ("palette_index", 1.0), ("unexpected", 1)])
def test_malformed_write_has_no_durable_effect(harness, field, value):
    world = harness.create()
    payload = {"world_id": world.world_id, "expected_version": 1, "mutation_id": "malformed",
        "operation": fill([0, 0, 0], [1, 1, 1])}
    if field == "coordinate":
        payload["operation"]["bounds"]["min"][0] = value
    elif field == "palette_index":
        payload["operation"][field] = value
    else:
        payload[field] = value
    before = durable_rows(harness)
    with pytest.raises(ValueError):
        harness.operation("worlds.apply", payload)
    assert durable_rows(harness) == before


def test_cancel_at_final_commit_checkpoint_rolls_back_every_table(harness, monkeypatch):
    world = harness.create()
    before = durable_rows(harness)
    written = False
    original = harness.store._write_receipt
    def checkpoint(*args):
        nonlocal written
        original(*args)
        written = True
    monkeypatch.setattr(harness.store, "_write_receipt", checkpoint)
    request = harness.models.ApplyInput(world_id=world.world_id, expected_version=1, operation=fill([0, 0, 0], [2, 2, 2]))
    with pytest.raises(harness.geometry.VoxelError, match="cancel"):
        harness.store.mutate("project-voxel", request, kind="fill", origin="human", request_id="cancel-final", cancelled=lambda: written)
    assert written and durable_rows(harness) == before


def test_expired_caller_reconciles_original_receipt_without_geometry_replay(harness, monkeypatch):
    world = harness.create()
    request = harness.models.ApplyInput(world_id=world.world_id, expected_version=1, operation=fill([0, 0, 0], [2, 2, 2]))
    original = harness.store.mutate("project-voxel", request, kind="fill", origin="tool", request_id="timeout-after-commit", frozen_version=1)
    harness.apply(original, fill([4, 4, 4], [5, 5, 5], 3), "later-human")
    before = durable_rows(harness)
    def forbidden(*args, **kwargs):
        pytest.fail("Reconciliation must not execute geometry")
    monkeypatch.setattr(harness.store_module, "apply_geometry", forbidden)
    assert harness.store.receipt("project-voxel", "tool", "timeout-after-commit", "fill", request) == original
    assert durable_rows(harness) == before


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
@pytest.mark.parametrize("termination", ["timeout", "cancel"])
def test_actual_executor_termination_reconciles_without_replaying_write(harness, monkeypatch, phase, termination):
    world = harness.create()
    tool = next(tool for tool in harness.staged.tools if tool.name == "voxel_fill")
    payload = {"world_id": world.world_id, "expected_version": 1, "operation": fill([0, 0, 0], [2, 2, 2], 2)}
    refs = bind_tool_invocation_resources(tool, payload, discovered=harness.staged.resource_providers[0]("project-voxel"))
    resolvers = dict(harness.staged.resource_resolvers)
    resources = {ref.canonical(): resolvers[ref.kind](ref) for ref in refs}
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = 0
    original = harness.store._write_receipt if phase == "before_commit" else harness.store.mutate
    def delayed(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(5), "Verifier did not release the transaction boundary"
        return result
    monkeypatch.setattr(harness.store, "_write_receipt" if phase == "before_commit" else "mutate", delayed)
    identity = f"{termination}-{phase}"
    common = dict(tool_name=provider_tool_name("dbfox.voxel", "voxel_fill"), raw_input=payload, request=None,
        idempotency_key=identity, invocation_id=identity, scope_refs=refs, resources=resources)
    def operation(control):
        try:
            return harness.runtime.invoke(**common, cancellation_probe=control.is_cancelled, deadline=control.deadline)
        finally:
            finished.set()
    executor = ToolExecutor(max_workers=1, poll_interval_seconds=0.01)
    try:
        result = executor.execute(tool=tool, scope_key=world.world_id, operation=operation,
            should_cancel=entered.is_set if termination == "cancel" else None,
            deadline=time.monotonic() + (0.35 if termination == "timeout" else 3))
        assert entered.is_set() and result.status != "success" and result.attempts == 1
        assert result.error_code == ("TOOL_TIMEOUT" if termination == "timeout" else "TOOL_CANCELLED")
        release.set()
        assert finished.wait(5)
        before = durable_rows(harness)
        recovered = harness.runtime.reconcile(**common)
        if phase == "before_commit":
            assert recovered.status == "failed" and recovered.error_code == "TOOL_RECONCILIATION_NOT_APPLIED"
            assert harness.store.snapshot("project-voxel", world.world_id).version == 1
        else:
            assert recovered.status == "success" and recovered.output["version"] == 2
            assert recovered.output["nonzero_count"] == 8
        assert calls == 1 and durable_rows(harness) == before
    finally:
        release.set()
        executor.close()
