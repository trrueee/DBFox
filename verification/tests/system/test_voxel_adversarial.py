"""Separate final red-team attacks against real signed Voxel packages."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import zlib

import pytest

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest, DlcOperationContext, DlcOperationError, RequestedResourceRef
from engine.agent.repositories.artifact import ArtifactRepository
from engine.models import AgentArtifactRecord, AgentToolInvocation, Project
from verification.bench.capabilities.dbfox_voxel.runtime import VoxelRuntime, _run_segment
from verification.bench.capabilities.dbfox_voxel.schema import Step, VoxelCase


@pytest.fixture
def target(tmp_path):
    with VoxelRuntime(tmp_path / "signed-target") as runtime:
        runtime.project = "voxel-adversarial-project"
        with runtime.factory() as db:
            db.add(Project(id=runtime.project, name="Independent adversarial fixture"))
            db.commit()
        runtime.store = next(item.tool.store for item in runtime.snapshot.tools if item.tool.name == "voxel_fill")
        prefix = type(runtime.store).__module__.rsplit(".", 1)[0]
        runtime.models = importlib.import_module(prefix + ".contracts")
        runtime.geometry = importlib.import_module(prefix + ".geometry")
        yield runtime


def rows(target):
    with closing(sqlite3.connect(target.store.database_path)) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in ("worlds", "world_revisions", "chunk_versions", "operation_receipts")}


def create(target, size=(32, 32, 32), identity="create"):
    return target.operation(target.project, "worlds.create", {"title": "Adversarial world", "size": list(size), "mutation_id": identity})


def fill(target, world, identity, lo=(0, 0, 0), hi=(2, 2, 2), color=2):
    return target.operation(target.project, "worlds.apply", {"world_id": world["world_id"], "expected_version": world["version"],
        "mutation_id": identity, "operation": {"kind": "fill", "layer_id": "base", "bounds": {"min": list(lo), "max": list(hi)}, "palette_index": color}})


@pytest.mark.parametrize("operation", ["worlds.get", "worlds.list"])
def test_corrupt_derived_count_cannot_be_published_as_valid_summary(target, operation):
    world = fill(target, create(target), "eight-cells")
    assert world["nonzero_count"] == 8
    with closing(sqlite3.connect(target.store.database_path)) as db:
        # The blob and its raw/content hashes are untouched. Only a derived cache
        # field changes, which must not become an authoritative count in context.
        db.execute("UPDATE chunk_versions SET nonzero_count=9 WHERE world_id=? AND version=2", (world["world_id"],))
        db.commit()
    before = rows(target)
    with pytest.raises(DlcOperationError) as failure:
        target.operation(target.project, operation, {"world_id": world["world_id"]} if operation == "worlds.get" else {})
    assert failure.value.code == "CORRUPT_STATE"
    assert rows(target) == before


def test_undo_noop_and_create_receipts_remain_exact_after_delete_and_newer_heads(target, monkeypatch):
    first = create(target)
    changed = fill(target, first, "changed")
    noop = fill(target, changed, "noop")
    undo_request = {"world_id": first["world_id"], "expected_version": changed["version"], "target_version": first["version"], "mutation_id": "undo"}
    restored = target.operation(target.project, "worlds.undo", undo_request)
    deleted = target.operation(target.project, "worlds.delete", {"world_id": first["world_id"], "expected_version": restored["version"], "mutation_id": "delete"})
    assert deleted["status"] == "deleted" and noop["changed"] is False
    before = rows(target)
    module = importlib.import_module(type(target.store).__module__)
    monkeypatch.setattr(module, "apply_geometry", lambda *args: pytest.fail("An exact receipt replay must not run geometry"))
    assert create(target) == first
    assert fill(target, changed, "noop") == noop
    assert target.operation(target.project, "worlds.undo", undo_request) == restored
    assert rows(target) == before
    assert target.operation(target.project, "worlds.get", {"world_id": first["world_id"]})["version"] == deleted["version"]


def test_four_concurrent_writers_then_explicit_reinspection_preserve_each_region(target, monkeypatch):
    first = create(target)
    module = importlib.import_module(type(target.store).__module__)
    geometry = module.apply_geometry
    barrier = threading.Barrier(4)
    def simultaneous(*args):
        value = geometry(*args)
        barrier.wait(timeout=10)
        return value
    monkeypatch.setattr(module, "apply_geometry", simultaneous)
    def contender(index):
        try:
            return fill(target, first, f"parallel-{index}", (index * 4, 0, 0), (index * 4 + 2, 2, 2), index + 1)
        except DlcOperationError as error:
            return error
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(contender, range(4)))
    monkeypatch.setattr(module, "apply_geometry", geometry)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert [result.code for result in results if isinstance(result, DlcOperationError)] == ["STALE_VERSION"] * 3
    for index, result in enumerate(results):
        if isinstance(result, DlcOperationError):
            current = target.operation(target.project, "worlds.get", {"world_id": first["world_id"]})
            fill(target, current, f"reinspected-{index}", (index * 4, 0, 0), (index * 4 + 2, 2, 2), index + 1)
    final = target.document(target.project, first["world_id"], 5)
    values = final["chunks"][("base", 0, 0, 0)]
    assert final["nonzero_count"] == 32
    assert [values[index * 4] for index in range(4)] == [1, 2, 3, 4]
    assert len(rows(target)["operation_receipts"]) == 5


def test_noop_receipt_cannot_claim_another_requests_real_later_revision(target):
    first = fill(target, create(target), "initial-eight")
    noop = fill(target, first, "original-noop")
    later = fill(target, first, "real-later-write", (8, 8, 8), (9, 9, 9), 3)
    assert noop["changed"] is False and later["changed"] is True
    with closing(sqlite3.connect(target.store.database_path)) as db:
        # Keep original request identity/base/payload hash. Substitute a real,
        # correctly counted result whose durable producer was another request.
        db.execute("UPDATE operation_receipts SET result_version=?,outcome_json=? WHERE request_id='original-noop'",
                   (later["version"], json.dumps(later)))
        db.commit()
    before = rows(target)
    with pytest.raises(DlcOperationError):
        fill(target, first, "original-noop")
    assert rows(target) == before


@pytest.mark.parametrize("operation", ["create", "noop", "undo"])
def test_quota_rejection_keeps_all_tables_and_readable_history(target, monkeypatch, operation):
    first = create(target)
    changed = fill(target, first, "changed")
    before = rows(target)
    module = importlib.import_module(type(target.store).__module__)
    # Scale only the configured quota, not the quota implementation or byte accounting.
    monkeypatch.setattr(module, "MAX_HISTORY_BYTES", 1)
    with pytest.raises(DlcOperationError) as failure:
        if operation == "create":
            create(target, identity="quota-new")
        elif operation == "noop":
            fill(target, changed, "quota-noop")
        else:
            target.operation(target.project, "worlds.undo", {"world_id": first["world_id"], "expected_version": changed["version"], "target_version": 1, "mutation_id": "quota-undo"})
    assert failure.value.code == "HISTORY_QUOTA_EXCEEDED"
    assert rows(target) == before
    assert target.document(target.project, first["world_id"], 1)["nonzero_count"] == 0
    assert target.document(target.project, first["world_id"], 2)["nonzero_count"] == 8


@pytest.fixture
def produced(target):
    case = VoxelCase(case_id="adversarial-source-chain", category="adversarial", prompt="Create a 32-cubed world, fill a two-cell slab and preserve its snapshot.", steps=(
        Step(id="create", tool="voxel_create", arguments={"title": "Adversarial source proof", "size": [32, 32, 32]}),
        Step(id="fill", tool="voxel_fill", arguments={"world_id": "$world_id", "expected_version": "$version", "operation": {
            "kind": "fill", "layer_id": "base", "bounds": {"min": [0, 0, 0], "max": [32, 2, 32]}, "palette_index": 2}}),
        Step(id="export", tool="voxel_export", arguments={"world_id": "$world_id", "version": "$version"}),
    ))
    evidence, target.script = _run_segment(target, case, repetition=1)
    target.case = case
    assert evidence["run_status"] == "completed"
    assert len(evidence["invocations"]) == 3
    assert all(row["status"] == "succeeded" and row["attempts"] == 1 for row in evidence["invocations"])
    target.produced = evidence
    target.project = evidence["project_id"]
    with target.factory() as db:
        artifacts = ArtifactRepository(db).list_for_run(evidence["run_id"])
        artifact = artifacts[-1]
        assert artifact.payload["version"] == 2 and artifact.payload["nonzero_count"] == 2048
        assert ArtifactRepository(db).available_artifact(current_run_id=evidence["run_id"], artifact_id=artifact.id, session_id=evidence["session_id"]) is not None
    return artifact


@pytest.mark.parametrize("fault", ["missing_producer", "wrong_tool", "wrong_turn", "failed_producer", "foreign_refs", "cycle", "dangling_source"])
def test_real_runloop_artifact_rejects_detached_or_forged_source_proof(target, produced, fault):
    with target.factory() as db:
        row = db.get(AgentArtifactRecord, produced.id)
        provenance = json.loads(row.provenance_json)
        if fault == "missing_producer":
            provenance["tool_invocation_id"] = "synthetic-detached-invocation"
            row.provenance_json = json.dumps(provenance)
        elif fault == "wrong_tool":
            provenance["tool_name"] = "voxel_fill"
            row.provenance_json = json.dumps(provenance)
        elif fault == "wrong_turn":
            row.turn_id = "synthetic-detached-turn"
        elif fault == "failed_producer":
            db.get(AgentToolInvocation, provenance["tool_invocation_id"]).status = "failed"
        elif fault == "foreign_refs":
            refs = json.loads(row.resource_refs_json)
            refs[0]["id"] = "world_foreign"
            row.resource_refs_json = json.dumps(refs)
        else:
            row.relations_json = json.dumps([{"relation": "derived_from", "artifact_id": produced.id if fault == "cycle" else "synthetic-missing-source"}])
        db.commit()
        assert ArtifactRepository(db).available_artifact(current_run_id=produced.run_id, artifact_id=produced.id, session_id=produced.session_id) is None


def representation(target, artifact, operation="manifest", parameters=None):
    provider = target.snapshot.get_artifact_representation(artifact.type, "dbfox.voxel.world.v1")
    return provider.provider.execute(artifact, ArtifactRepresentationRequest(operation=operation, parameters=parameters or {}),
        ArtifactRepresentationContext(artifact_loader=lambda key: None))


@pytest.mark.parametrize("parameters", [{"world_id": "world_foreign"}, {"version": 999}, {"path": "../../secret"}, {"url": "https://invalid.example/chunks"}, {"limit": 33}, {"limit": True}])
def test_historical_representation_cannot_override_identity_version_or_external_locator(target, produced, parameters):
    before = rows(target)
    with pytest.raises(ArtifactRepresentationError):
        representation(target, produced, "chunks", parameters)
    assert rows(target) == before


def test_historical_pages_remain_exact_across_delete_and_foreign_cursor_substitution(target, produced):
    manifest = representation(target, produced).payload
    first = representation(target, produced, "chunks", {"limit": 1})
    assert first.source_version == "2" and first.source_fingerprint == manifest["content_hash"]
    world = target.operation(target.project, "worlds.get", {"world_id": manifest["world_id"]})
    deleted = target.operation(target.project, "worlds.delete", {"world_id": world["world_id"], "expected_version": 2, "mutation_id": "delete-between-pages"})
    assert deleted["status"] == "deleted"
    other = fill(target, create(target, identity="foreign-cursor-world"), "foreign-cursor-fill", (0, 0, 0), (32, 2, 32))
    foreign_page = target.operation(target.project, "worlds.chunks", {"world_id": other["world_id"], "version": 2, "limit": 1})
    with pytest.raises(ArtifactRepresentationError):
        representation(target, produced, "chunks", {"after": foreign_page["next_after"], "limit": 1})
    chunks = list(first.payload["chunks"])
    cursor = first.payload["next_after"]
    while cursor is not None:
        result = representation(target, produced, "chunks", {"after": cursor, "limit": 1})
        assert result.source_version == "2" and result.source_fingerprint == manifest["content_hash"]
        chunks.extend(result.payload["chunks"])
        cursor = result.payload["next_after"]
    assert len(chunks) == 4
    historical = target.document(target.project, world["world_id"], 2)
    assert {(chunk["layer_id"], *chunk["coord"]): bytes(chunk["values"]) for chunk in chunks} == historical["chunks"]
    assert representation(target, produced).payload == manifest
    assert target.operation(target.project, "worlds.get", {"world_id": world["world_id"]})["version"] == 3


def test_project_discovery_and_owner_context_reject_foreign_identity_even_with_explicit_selection(target):
    from engine.errors import ToolInputError
    from engine.runtime_composition import authorize_project_resources, discover_project_resources
    from engine.tools.runtime.resource_authority import bind_tool_invocation_resources
    world = create(target)
    tool = next(item.tool for item in target.snapshot.tools if item.tool.name == "voxel_fill")
    with target.factory() as db:
        db.add(Project(id="foreign-project", name="Foreign"))
        db.commit()
        refs = authorize_project_resources(db, target.project, (RequestedResourceRef(kind="dbfox.voxel.world", id=world["world_id"]),), snapshot=target.snapshot)
        assert authorize_project_resources(db, target.project, None, snapshot=target.snapshot) == ()
        with pytest.raises(ValueError):
            authorize_project_resources(db, "foreign-project", (RequestedResourceRef(kind="dbfox.voxel.world", id=world["world_id"]),), snapshot=target.snapshot)
        with pytest.raises(ToolInputError):
            bind_tool_invocation_resources(tool, {"world_id": world["world_id"]}, discovered=discover_project_resources(db, "foreign-project", snapshot=target.snapshot), explicit_authority=refs)
        with pytest.raises(ValueError):
            authorize_project_resources(db, target.project, (RequestedResourceRef(kind="dbfox.scene.world", id=world["world_id"]),), snapshot=target.snapshot)
    contribution = target.snapshot.get_operation("dbfox.voxel", "worlds.get").spec
    with pytest.raises(DlcOperationError, match="Project"):
        contribution.handler(contribution.input_model(world_id=world["world_id"]), DlcOperationContext(dlc_id="dbfox.scene", operation_name="worlds.get", project_id=target.project))
    before = rows(target)
    with pytest.raises(DlcOperationError):
        target.operation("foreign-project", "worlds.delete", {"world_id": world["world_id"], "expected_version": 1, "mutation_id": "foreign-delete"})
    assert rows(target) == before


@pytest.mark.parametrize("operation", ["create", "undo"])
@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_signed_executor_cancel_create_and_undo_reconciles_exact_outcome(target, monkeypatch, operation, phase):
    from engine.tools.runtime import ToolRuntime
    from engine.tools.runtime.executor import ToolExecutor
    from engine.tools.runtime.registry import provider_tool_name
    from engine.tools.runtime.resource_authority import bind_tool_invocation_resources
    world = fill(target, create(target), "seed-undo") if operation == "undo" else None
    payload = {"title": "Cancelled create", "size": [32, 32, 32]} if operation == "create" else {"world_id": world["world_id"], "expected_version": 2, "target_version": 1}
    tool = next(item.tool for item in target.snapshot.tools if item.tool.name == "voxel_" + operation)
    refs = bind_tool_invocation_resources(tool, payload, discovered=target.store.list_resources(target.project))
    resources = {ref.canonical(): (target.store.resolve_library(ref) if operation == "create" else target.store.resolve_world(ref)) for ref in refs}
    runtime = ToolRuntime(target.registry)
    identity = "cancel-" + operation + "-" + phase
    common = dict(tool_name=provider_tool_name("dbfox.voxel", tool.name), raw_input=payload, request=None,
        idempotency_key=identity, invocation_id=identity, scope_refs=refs, resources=resources)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = 0
    method = "_write_receipt" if phase == "before_commit" else "create" if operation == "create" else "mutate"
    original = getattr(target.store, method)
    before = rows(target)
    def delayed(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(target.store, method, delayed)
    def execute(control):
        try:
            return runtime.invoke(**common, cancellation_probe=control.is_cancelled, deadline=control.deadline)
        finally:
            finished.set()
    executor = ToolExecutor(max_workers=1, poll_interval_seconds=0.01)
    try:
        result = executor.execute(tool=tool, scope_key=target.project, operation=execute, should_cancel=entered.is_set, deadline=time.monotonic() + 3)
        assert entered.is_set() and result.error_code == "TOOL_CANCELLED" and result.attempts == 1
        release.set()
        assert finished.wait(5)
        recovered = runtime.reconcile(**common)
        if phase == "before_commit":
            assert recovered.status == "failed" and recovered.error_code == "TOOL_RECONCILIATION_NOT_APPLIED"
            assert rows(target) == before
        else:
            assert recovered.status == "success" and recovered.output["nonzero_count"] == 0
            assert recovered.output["version"] == (1 if operation == "create" else 3)
            committed = rows(target)
            assert runtime.reconcile(**common).output == recovered.output
            assert rows(target) == committed
        assert calls == 1
    finally:
        release.set()
        executor.close()


@pytest.mark.parametrize("operation", ["create", "undo"])
@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_signed_process_exit_create_and_undo_has_atomic_history_and_exact_receipt(target, operation, phase):
    world = fill(target, create(target), "seed-crash-undo") if operation == "undo" else None
    payload = {"title": "Crash create", "size": [32, 32, 32], "mutation_id": "crash-new"} if operation == "create" else {
        "world_id": world["world_id"], "expected_version": 2, "target_version": 1, "mutation_id": "crash-new"}
    request = target.directory / "crash-request.json"
    request.write_text(json.dumps({"project": target.project, "operation": "worlds." + operation, "payload": payload}), encoding="utf-8")
    before = rows(target)
    result = subprocess.run([sys.executable, "-m", "verification.bench.capabilities.dbfox_voxel.adversarial_worker", str(target.directory / "dlcs"), str(request), phase],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    if phase == "before_commit":
        assert rows(target) == before
    else:
        committed = rows(target)
        receipt = target.operation(target.project, "worlds." + operation, payload)
        assert receipt["nonzero_count"] == 0 and receipt["version"] == (1 if operation == "create" else 3)
        assert rows(target) == committed
    with closing(sqlite3.connect(target.store.database_path)) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("parent", [2, 999, None])
def test_valid_geometry_cannot_hide_broken_revision_parent(target, parent):
    world = fill(target, create(target), "parent-corruption")
    with closing(sqlite3.connect(target.store.database_path)) as db:
        db.execute("UPDATE world_revisions SET parent_version=? WHERE world_id=? AND version=2", (parent, world["world_id"]))
        db.commit()
    before = rows(target)
    with pytest.raises(DlcOperationError) as failure:
        target.operation(target.project, "worlds.get", {"world_id": world["world_id"]})
    assert failure.value.code == "CORRUPT_STATE"
    assert rows(target) == before


@pytest.mark.parametrize("fault", ["trailing_stream", "decompression_bomb", "undefined_palette", "outside_padding", "future_document"])
def test_live_reads_validate_deep_chunk_content_even_when_index_fingerprint_is_coherent(target, fault):
    world = fill(target, create(target, size=(17, 17, 17)), "deep-corruption", (16, 16, 16), (17, 17, 17))
    with closing(sqlite3.connect(target.store.database_path)) as db:
        blob, = db.execute("SELECT blob FROM chunk_versions WHERE world_id=? AND version=2", (world["world_id"],)).fetchone()
        document = json.loads(db.execute("SELECT document_json FROM world_revisions WHERE world_id=? AND version=2", (world["world_id"],)).fetchone()[0])
        if fault == "future_document":
            document["schema_version"] = 999
            db.execute("UPDATE world_revisions SET document_json=? WHERE world_id=? AND version=2", (json.dumps(document), world["world_id"]))
        elif fault in ("trailing_stream", "decompression_bomb"):
            bad = blob + b"unconsumed" if fault == "trailing_stream" else zlib.compress(bytes(4 * 1024 * 1024))
            db.execute("UPDATE chunk_versions SET blob=? WHERE world_id=? AND version=2", (bad, world["world_id"]))
        else:
            raw = bytearray(zlib.decompress(blob))
            raw[0 if fault == "undefined_palette" else 2] = 255 if fault == "undefined_palette" else 2
            raw_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
            db.execute("UPDATE chunk_versions SET blob=?,raw_hash=?,nonzero_count=? WHERE world_id=? AND version=2", (zlib.compress(raw), raw_hash, len(raw) - raw.count(0), world["world_id"]))
            canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            fingerprint = "sha256:" + hashlib.sha256((canonical(document) + "\n" + canonical(["base", 1, 1, 1, raw_hash])).encode()).hexdigest()
            db.execute("UPDATE world_revisions SET content_hash=? WHERE world_id=? AND version=2", (fingerprint, world["world_id"]))
        db.commit()
    before = rows(target)
    with pytest.raises(DlcOperationError) as failure:
        target.operation(target.project, "worlds.get", {"world_id": world["world_id"]})
    assert failure.value.code == "CORRUPT_STATE"
    assert rows(target) == before


@pytest.mark.parametrize("extra", [{"path": "../../owner.sqlite"}, {"output_path": "C:\\private\\result"}, {"url": "https://invalid.example/data"}, {"source_world_id": "world_foreign"}])
def test_management_inputs_do_not_accept_external_file_or_cross_world_channels(target, extra):
    world = create(target)
    payload = {"world_id": world["world_id"], "expected_version": 1, "mutation_id": "unsafe-extra", "operation": {"kind": "fill", "layer_id": "base", "bounds": {"min": [0, 0, 0], "max": [1, 1, 1]}, "palette_index": 1}, **extra}
    before = rows(target)
    with pytest.raises(ValueError):
        target.operation(target.project, "worlds.apply", payload)
    assert rows(target) == before


def test_same_run_lineage_requires_explicit_verified_derived_from_edge(target, produced):
    source = next(row for row in target.produced["artifacts"] if row["provenance"]["tool_invocation_id"] == target.produced["invocations"][1]["id"])
    with target.factory() as db:
        row = db.get(AgentArtifactRecord, produced.id)
        # This ref came from a separate, real succeeded fill Invocation. Merely
        # sharing a Run cannot lend it to the later export Invocation.
        row.resource_refs_json = json.dumps(source["resource_refs"])
        db.commit()
        repository = ArtifactRepository(db)
        query = dict(current_run_id=produced.run_id, artifact_id=produced.id, session_id=produced.session_id)
        assert repository.available_artifact(**query) is None
        row.relations_json = json.dumps([{"relation": "derived_from", "artifact_id": source["id"]}])
        db.commit()
        assert repository.available_artifact(**query) is not None
        row.relations_json = json.dumps([{"relation": "supports", "artifact_id": source["id"]}])
        db.commit()
        assert repository.available_artifact(**query) is None


def test_same_run_history_survives_new_head_but_cross_run_uses_exact_admission_fence(target, produced):
    second, _ = _run_segment(target, target.case, repetition=2, script=target.script, project_id=produced.payload["project_id"], session_id=produced.session_id)
    assert second["run_status"] == "completed"
    with target.factory() as db:
        assert ArtifactRepository(db).available_artifact(current_run_id=second["run_id"], artifact_id=produced.id, session_id=produced.session_id) is not None
    latest = target.operation(target.project, "worlds.get", {"world_id": produced.payload["world_id"]})
    fill(target, latest, "advance-context-fence", (8, 8, 8), (9, 9, 9), 3)
    third, _ = _run_segment(target, target.case, repetition=3, script=target.script, project_id=target.project, session_id=produced.session_id)
    assert third["run_status"] == "completed"
    with target.factory() as db:
        repository = ArtifactRepository(db)
        assert repository.available_artifact(current_run_id=produced.run_id, artifact_id=produced.id, session_id=produced.session_id) is not None
        assert repository.available_artifact(current_run_id=third["run_id"], artifact_id=produced.id, session_id=produced.session_id) is None


def test_oversized_geometry_rejects_without_losing_bounded_inspection(target):
    world = create(target, size=(256, 256, 256))
    before = rows(target)
    with pytest.raises(DlcOperationError):
        fill(target, world, "oversized", (0, 0, 0), (256, 256, 256))
    assert rows(target) == before
    public = target.operation(target.project, "worlds.get", {"world_id": world["world_id"]})
    assert public["nonzero_count"] == 0 and public["version"] == 1
    assert len(json.dumps(public).encode()) < 16384


@pytest.mark.parametrize("head", [1, 999])
def test_corrupt_current_head_is_rejected_while_explicit_intact_history_is_readable(target, head):
    world = fill(target, create(target), "head-corruption")
    with closing(sqlite3.connect(target.store.database_path)) as db:
        db.execute("UPDATE worlds SET head_version=? WHERE id=?", (head, world["world_id"]))
        db.commit()
    before = rows(target)
    with pytest.raises(DlcOperationError) as failure:
        target.operation(target.project, "worlds.get", {"world_id": world["world_id"]})
    assert failure.value.code == "CORRUPT_STATE"
    assert target.document(target.project, world["world_id"], 1)["nonzero_count"] == 0
    assert target.document(target.project, world["world_id"], 2)["nonzero_count"] == 8
    assert rows(target) == before


@pytest.mark.parametrize("fault,code", [("foreign_refs", "FORBIDDEN"), ("fingerprint", "SOURCE_CHANGED"), ("missing_revision", "SOURCE_UNAVAILABLE"), ("corrupt_blob", "SOURCE_UNAVAILABLE")])
def test_representation_failures_remain_in_public_catalog_with_no_domain_code_leak(target, produced, fault, code):
    artifact = produced
    if fault == "foreign_refs":
        artifact = produced.model_copy(update={"resource_refs": tuple(ref.model_copy(update={"id": "world_foreign"}) for ref in produced.resource_refs)})
    elif fault in ("fingerprint", "missing_revision"):
        payload = {**produced.payload, **({"content_hash": "sha256:" + "1" * 64} if fault == "fingerprint" else {"version": 999})}
        artifact = produced.model_copy(update={"payload": payload})
    else:
        with closing(sqlite3.connect(target.store.database_path)) as db:
            db.execute("UPDATE chunk_versions SET blob=x'0001' WHERE world_id=? AND version=2", (produced.payload["world_id"],))
            db.commit()
    before = rows(target)
    with pytest.raises(ArtifactRepresentationError) as failure:
        representation(target, artifact)
    assert failure.value.code == code
    assert failure.value.status_code in (403, 409)
    assert rows(target) == before


@pytest.mark.parametrize("ref_version,resource_version,expected", [(1, 2, 2), (2, 2, 1), (1, 1, 2)])
def test_frozen_resource_current_head_and_document_fences_cannot_substitute_for_each_other(target, ref_version, resource_version, expected):
    from dbfox_dlc_api import ResourceScopeRef
    from engine.tools.runtime import ToolRuntime
    from engine.tools.runtime.registry import provider_tool_name
    world = fill(target, create(target), "fence-seed")
    ref = ResourceScopeRef(kind="dbfox.voxel.world", id=world["world_id"], version=ref_version)
    source = target.store.snapshot(target.project, world["world_id"], resource_version)
    payload = {"world_id": world["world_id"], "expected_version": expected, "operation": {"kind": "fill", "layer_id": "base", "bounds": {"min": [8, 8, 8], "max": [9, 9, 9]}, "palette_index": 3}}
    before = rows(target)
    result = ToolRuntime(target.registry).invoke(tool_name=provider_tool_name("dbfox.voxel", "voxel_fill"), raw_input=payload,
        request=None, idempotency_key="mismatched-fence", invocation_id="mismatched-fence", scope_refs=(ref,), resources={ref.canonical(): source})
    assert result.status == "failed" and result.error_code == "TOOL_INPUT_ERROR"
    assert result.output["status"] == "failed" and "world_id" not in result.output
    assert "frozen" in result.output["safe_message"]
    assert rows(target) == before
