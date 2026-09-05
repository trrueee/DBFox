"""Pixel Backend Engineer's author tests; not independent benchmark/red-team evidence."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

from cryptography.hazmat.primitives.asymmetric import ed25519
from PIL import Image
import pytest

from dbfox_dlc_api import (Artifact, ArtifactRepresentationContext, ArtifactRepresentationRequest,
    ContextContributionInput, DlcOperationContext, ResourceScopeRef)
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.runtime import ToolRuntime

SOURCE = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.pixel"
PACKAGE = "_pixel_backend_verification"
if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(PACKAGE, SOURCE / "backend" / "__init__.py",
                                                submodule_search_locations=[str(SOURCE / "backend")])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
c = importlib.import_module(PACKAGE + ".contracts")
s = importlib.import_module(PACKAGE + ".store")
d = importlib.import_module(PACKAGE + ".domain")
t = importlib.import_module(PACKAGE + ".contributions")
r = importlib.import_module(PACKAGE + ".representation")


@pytest.fixture
def store(tmp_path):
    return s.PixelStore(tmp_path / "pixel")


def create(store, key="create", **fields):
    payload = c.CreateInput(title="Fox Knight", width=8, height=8, expected_version=0, **fields)
    return store.create("project-pixel", payload, key)


def edit(store, current, *ops, key=None, **kwargs):
    payload = c.ApplyInput(document_id=current.document_id, expected_version=current.revision, operations=list(ops))
    return store.mutate("project-pixel", payload, key or f"edit-{current.revision}", **kwargs)


def rect(color=1, **fields):
    return {"kind": "rect", "frame_id": "frame_1", "layer_id": "layer_1", "palette_index": color,
            "rect": {"x": 1, "y": 1, "width": 3, "height": 3}, **fields}


def read(store, current, revision=None):
    return store.get_revision("project-pixel", current.document_id, revision)


def artifact(current):
    scope = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=current.document_id, version=str(max(1, current.revision - 1)))
    draft = t.revision_artifact(current, scope)
    return Artifact(id="pixel-artifact", session_id="session", run_id="run",
        **draft.model_dump(exclude={"key", "select_if_none", "payload_draft_refs", "visibility"}))


def representation(store, current, operation, **params):
    return r.PixelRepresentation(store).execute(artifact(current), ArtifactRepresentationRequest(operation=operation, parameters=params),
        ArtifactRepresentationContext(artifact_loader=lambda _: None))


def test_strict_types_null_defaults_and_host_normalization(store):
    for value in (True, 1.1, "1", None):
        with pytest.raises(ValueError):
            c.CreateInput(title="bad", width=value, height=8, expected_version=0)
        with pytest.raises(ValueError):
            c.ApplyInput(document_id="id", expected_version=value, operations=[rect()])
    with pytest.raises(ValueError):
        c.Rectangle.model_validate(rect(filled=1))
    normalized = c.Rectangle.model_validate(rect(filled=None))
    assert normalized.filled is True
    assert c.Rectangle.model_validate(normalized.model_dump(mode="json", exclude_none=True)) == normalized
    with pytest.raises(ValueError):
        c.FrameUpdate(kind="frame_update", frame_id="frame_1", duration_ms=None)
    initial = read(store, create(store)).document.model_dump()
    initial["schema_version"] = True
    with pytest.raises(ValueError):
        c.PixelDocument.model_validate(initial)
    with pytest.raises(ValueError):
        c.ApplyInput(document_id="id", expected_version=1, operations=[{**rect(), "unknown": 1}])


def test_create_edit_restart_noop_and_receipt(store):
    initial = create(store)
    changed = edit(store, initial, rect())
    assert changed.revision == 2 and changed.changed_pixel_count == 9
    assert edit(store, initial, rect()) == changed
    restarted = s.PixelStore(store.path.parent)
    assert read(restarted, initial, 1).document.frames[0].cels[0].pixels == [0] * 64
    assert read(restarted, initial).summary.revision == 2
    noop = edit(store, changed, rect())
    assert not noop.changed and noop.revision == 2
    assert create(store) == initial
    with pytest.raises(d.PixelError, match="different input"):
        edit(store, initial, rect(2))
    assert len(store.revisions("project-pixel", c.RevisionsInput(document_id=initial.document_id)).revisions) == 2


def test_all_drawing_operations_and_overlap_snapshot(store):
    initial = create(store)
    changed = edit(store, initial,
        {**rect(), "filled": False},
        {"kind": "fill", "frame_id": "frame_1", "layer_id": "layer_1", "x": 2, "y": 2, "palette_index": 2},
        {"kind": "line", "frame_id": "frame_1", "layer_id": "layer_1", "x0": 0, "y0": 7, "x1": 7, "y1": 0, "palette_index": 2})
    pixels = read(store, changed).document.frames[0].cels[0].pixels
    assert pixels[2 * 8 + 2] == 2 and pixels[1 * 8 + 1] == 1 and pixels[7 * 8] == 2
    stamped = edit(store, changed, {"kind": "stamp", "frame_id": "frame_1", "layer_id": "layer_1",
        "rect": {"x": 0, "y": 0, "width": 3, "height": 1}, "pixels": [1, 2, 1]})
    moved = edit(store, stamped, {"kind": "region_transform", "frame_id": "frame_1", "layer_id": "layer_1",
        "rect": {"x": 0, "y": 0, "width": 3, "height": 1}, "transform": "translate", "destination": {"x": 1, "y": 0}, "mode": "move"})
    assert read(store, moved).document.frames[0].cels[0].pixels[:4] == [0, 1, 2, 1]
    with pytest.raises(d.PixelError, match="explicit clip"):
        edit(store, moved, {"kind": "region_transform", "frame_id": "frame_1", "layer_id": "layer_1",
            "rect": {"x": 1, "y": 0, "width": 3, "height": 1}, "transform": "rotate_cw", "destination": {"x": 7, "y": 7}})


@pytest.mark.parametrize("transform,expected", [("flip_x", [2, 1, 0, 1]), ("flip_y", [1, 0, 1, 2]), ("rotate_cw", [1, 1, 0, 2])])
def test_region_transforms_are_exact(store, transform, expected):
    current = edit(store, create(store), {"kind": "stamp", "frame_id": "frame_1", "layer_id": "layer_1",
        "rect": {"x": 0, "y": 0, "width": 2, "height": 2}, "pixels": [1, 2, 1, 0]})
    changed = edit(store, current, {"kind": "region_transform", "frame_id": "frame_1", "layer_id": "layer_1",
        "rect": {"x": 0, "y": 0, "width": 2, "height": 2}, "transform": transform, "destination": {"x": 0, "y": 0}})
    pixels = read(store, changed).document.frames[0].cels[0].pixels
    assert pixels[:2] + pixels[8:10] == expected


def test_structure_tags_palette_layers_and_lock_semantics(store):
    initial = create(store)
    current = edit(store, initial, rect(), {"kind": "frame_duplicate", "source_frame_id": "frame_1", "frame_id": "attack", "position": 1},
        {"kind": "layer_create", "layer_id": "armor", "name": "Armor", "position": 1},
        {"kind": "tag_set", "tag_id": "idle", "name": "Idle", "frame_ids": ["frame_1", "attack"]},
        {"kind": "palette_set", "index": 3, "name": "Fox", "color": "#ff8800ff"},
        {"kind": "layer_update", "layer_id": "armor", "locked": True})
    assert current.palette_count == 4 and current.frame_count == 2 and current.layer_count == 2
    for op in (rect(layer_id="armor"), {"kind": "layer_delete", "layer_id": "armor"},
               {"kind": "frame_delete", "frame_id": "attack", "remove_from_tags": True}):
        with pytest.raises(d.PixelError, match="Unlock"):
            edit(store, current, op)
    unlocked = edit(store, current, {"kind": "layer_update", "layer_id": "armor", "locked": False, "visible": False, "position": 0},
        {"kind": "frame_update", "frame_id": "attack", "duration_ms": 80, "position": 0})
    assert read(store, unlocked).document.frames[0].cels[0].layer_id == "armor"
    with pytest.raises(d.PixelError, match="tag"):
        edit(store, unlocked, {"kind": "frame_delete", "frame_id": "attack"})
    deleted = edit(store, unlocked, {"kind": "frame_delete", "frame_id": "attack", "remove_from_tags": True}, {"kind": "layer_delete", "layer_id": "armor"})
    assert read(store, deleted).document.tags[0].frame_ids == ["frame_1"]
    with pytest.raises(d.PixelError, match="already used"):
        edit(store, deleted, {"kind": "frame_create", "frame_id": "attack", "position": 1})


def test_atomic_rollback_and_birth_ids_in_noop_batch(store):
    initial = create(store)
    with pytest.raises(d.PixelError):
        edit(store, initial, rect(), {"kind": "layer_delete", "layer_id": "layer_1"})
    assert read(store, initial).summary.revision == 1
    result = edit(store, initial, {"kind": "frame_create", "frame_id": "temporary", "position": 1}, {"kind": "frame_delete", "frame_id": "temporary"})
    assert result.changed is False and result.revision == 1
    with pytest.raises(d.PixelError, match="already used"):
        edit(store, initial, {"kind": "frame_create", "frame_id": "temporary", "position": 1}, key="reuse")


def test_undo_and_tombstone_restore_preserve_history(store):
    initial = create(store)
    changed = edit(store, initial, rect())
    undo = c.UndoInput(document_id=initial.document_id, expected_version=2, restore_revision=1)
    restored = store.mutate("project-pixel", undo, "undo", "undo")
    assert restored.revision == 3 and restored.content_hash == initial.content_hash
    redo = store.mutate("project-pixel", c.UndoInput(document_id=initial.document_id, expected_version=3, restore_revision=2), "redo", "undo")
    assert redo.revision == 4 and redo.content_hash == changed.content_hash
    deleted = store.mutate("project-pixel", c.VersionInput(document_id=initial.document_id, expected_version=4), "delete", "delete")
    assert deleted.status == "deleted" and len(store.list_resources("project-pixel")) == 1
    assert store.list_documents("project-pixel", c.ListInput(include_deleted=True)).documents[0].revision == 5
    restored = store.mutate("project-pixel", c.VersionInput(document_id=initial.document_id, expected_version=5), "restore", "restore")
    assert restored.status == "active" and restored.revision == 6
    with pytest.raises(d.PixelError, match="Project"):
        store.mutate("other", c.VersionInput(document_id=initial.document_id, expected_version=6), "outside", "delete")


def test_concurrent_writers_and_exact_duplicate(store):
    initial = create(store)
    barrier = threading.Barrier(2)
    def write(key, color):
        barrier.wait()
        try:
            return edit(store, initial, rect(color), key=key)
        except d.PixelError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda args: write(*args), [("a", 1), ("b", 2)]))
    assert sum(isinstance(value, c.MutationResult) for value in outcomes) == 1 and "PIXEL_CONFLICT" in outcomes
    current = read(store, initial).summary
    barrier = threading.Barrier(2)
    def duplicate(_):
        barrier.wait()
        return edit(store, current, {"kind": "rename", "title": "Concurrent"}, key="same")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(duplicate, range(2)))
    assert outcomes[0] == outcomes[1] and outcomes[0].revision == 3


def test_cancel_before_commit_and_commit_receipt_reconciliation(store):
    initial = create(store)
    checks = 0
    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 3
    with pytest.raises(d.PixelError, match="cancelled"):
        edit(store, initial, rect(), cancelled=cancelled)
    assert read(store, initial).summary.revision == 1
    payload = c.ApplyInput(document_id=initial.document_id, expected_version=1, operations=[rect()])
    assert store.reconcile("project-pixel", "human", "edit-1", "apply", payload) is None
    committed = edit(store, initial, rect())
    assert store.reconcile("project-pixel", "human", "edit-1", "apply", payload) == committed


def test_unknown_schema_corrupt_hash_missing_cel_and_quota_fail_closed(store, tmp_path, monkeypatch):
    initial = create(store)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE revisions SET content_hash=?", ("0" * 64,))
    with pytest.raises(d.PixelError, match="hash"):
        read(store, initial)
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    with sqlite3.connect(unknown / "state.sqlite3") as db:
        db.execute("PRAGMA user_version=9")
    with pytest.raises(d.PixelError, match="schema"):
        s.PixelStore(unknown)
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "state.sqlite3").write_bytes(b"this is not SQLite")
    with pytest.raises(d.PixelError, match="storage"):
        s.PixelStore(corrupt)
    other = s.PixelStore(tmp_path / "quota")
    current = create(other)
    monkeypatch.setattr(c, "MAX_HISTORY_BYTES", 1)
    with pytest.raises(d.PixelError, match="quota"):
        edit(other, current, rect())
    assert read(other, current).summary.revision == 1
    assert create(other) == current  # exact receipts do not add quota costs


def test_slot_budget_valid_maximum_and_input_budget(store):
    large = store.create("project-pixel", c.CreateInput(title="Large", width=128, height=128, expected_version=0), "large")
    ops = [{"kind": "frame_create", "frame_id": f"frame_{i}", "position": i - 1} for i in range(2, 17)]
    large = edit(store, large, *ops)
    assert large.frame_count == 16
    with pytest.raises(d.PixelError, match="budget"):
        edit(store, large, {"kind": "frame_create", "frame_id": "overflow", "position": 16})
    with pytest.raises(ValueError):
        c.ApplyInput(document_id=large.document_id, expected_version=large.revision, operations=[rect()] * 129)
    with pytest.raises(ValueError):
        c.ApplyInput(document_id=large.document_id, expected_version=large.revision,
            operations=[{"kind": "stamp", "frame_id": "frame_1", "layer_id": "layer_1", "rect": {"x": 0, "y": 0, "width": 64, "height": 64}, "pixels": [255] * 4096}] * 5)


def test_png_palette_alpha_visibility_sheet_order_and_immutable_artifacts(store):
    initial = create(store)
    current = edit(store, initial, rect(1), {"kind": "frame_duplicate", "source_frame_id": "frame_1", "frame_id": "attack", "position": 1},
        rect(2, frame_id="attack"), {"kind": "frame_update", "frame_id": "attack", "duration_ms": 60},
        {"kind": "tag_set", "tag_id": "reversed", "name": "Reverse", "frame_ids": ["attack", "frame_1"]})
    png = b"".join(representation(store, current, "png", frame_id="frame_1").chunks)
    decoded = Image.open(BytesIO(png)).convert("RGBA")
    assert decoded.size == (8, 8) and decoded.getpixel((0, 0)) == (0, 0, 0, 0)
    assert decoded.getpixel((1, 1)) == (24, 24, 37, 255)
    sheet = Image.open(BytesIO(b"".join(representation(store, current, "sheet", tag_id="reversed").chunks))).convert("RGBA")
    assert sheet.size == (16, 8) and sheet.getpixel((1, 1)) == (255, 255, 255, 255)
    assert sheet.getpixel((9, 1)) == (24, 24, 37, 255)
    layout = representation(store, current, "sheet_layout", tag_id="reversed").payload
    assert [frame["duration_ms"] for frame in layout["frames"]] == [60, 100]
    changed = edit(store, current, {"kind": "palette_set", "index": 1, "name": "Red", "color": "#FF0000FF"})
    assert b"".join(representation(store, current, "png", frame_id="frame_1").chunks) == png
    hidden = edit(store, changed, {"kind": "layer_update", "layer_id": "layer_1", "visible": False})
    image = Image.open(BytesIO(b"".join(representation(store, hidden, "png", frame_id="frame_1").chunks)))
    assert image.getbbox() is None
    with pytest.raises(Exception, match="parameters"):
        representation(store, current, "png", frame_id="frame_1", path="C:/secret")
    tampered = artifact(current).model_copy(update={"payload": {**artifact(current).payload, "content_hash": "0" * 64}})
    with pytest.raises(Exception, match="immutable"):
        r.PixelRepresentation(store).execute(tampered, ArtifactRepresentationRequest(operation="metadata"), ArtifactRepresentationContext(artifact_loader=lambda _: None))


def test_bounded_inspection_diff_context_and_observation(store):
    initial = create(store)
    current = edit(store, initial, rect(), {"kind": "frame_create", "frame_id": "f2", "position": 1},
        {"kind": "tag_set", "tag_id": "idle", "name": "待机", "frame_ids": ["frame_1", "f2"]})
    page = store.inspect("project-pixel", c.InspectInput(document_id=current.document_id, frame_id="frame_1", layer_id="layer_1",
        rect={"x": 0, "y": 0, "width": 8, "height": 8}))
    assert page.summary.revision == 2 and len(page.pixels) == 64
    diff = store.diff("project-pixel", c.DiffInput(document_id=current.document_id, from_revision=1, to_revision=2))
    assert diff.total == 2 and diff.items[0]["changed_pixel_count"] == 64
    tools = t.build_tools(store)
    for tool in tools:
        if tool.output_model is c.MutationResult:
            projection = tool.project_observation(status="success", output=current.model_dump(mode="json"), artifacts=())
            assert projection.facts["document_id"] == current.document_id and projection.provider_payload["revision"] == 2
            assert len(json.dumps(projection.provider_payload, ensure_ascii=False).encode("utf-8")) < 16384
        assert tool.project_observation(status="failed", output={}, artifacts=()).facts == {}
    inspect = next(tool for tool in tools if tool.name == "pixel_inspect")
    projection = inspect.project_observation(status="success", output=page.model_dump(mode="json"), artifacts=())
    assert "pixels" not in projection.facts and projection.provider_payload["pixels"] == page.pixels
    fragments = t.PixelContext(store).build(ContextContributionInput(session_id="s", run_id="r", current_request="inspect",
        resource_refs=(ResourceScopeRef(kind=c.DOCUMENT_KIND, id=current.document_id, version="2"),)))
    assert len(fragments) <= 4 and all(len(item.content) <= 2000 for item in fragments)
    assert "pixels" not in fragments[0].content and current.document_id in fragments[0].content


def test_formal_tool_runtime_frozen_versions_observation_and_reconcile(store):
    registry = ToolRegistry()
    for tool in t.build_tools(store):
        registry.register(tool)
    runtime = ToolRuntime(registry)
    library = ResourceScopeRef(kind=c.LIBRARY_KIND, id="project-pixel", version="1")
    result = runtime.invoke(tool_name="pixel_create", raw_input={"library_id": "project-pixel", "title": "Knight", "width": 8, "height": 8, "expected_version": 0},
        request=None, invocation_id="tool-create", idempotency_key="tool-create", scope_refs=(library,), resources={library.canonical(): store.resolve_library(library)})
    assert result.status == "success", result.error
    identity = result.output["document_id"]
    scope = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=identity, version="1")
    kwargs = dict(tool_name="pixel_rect", raw_input={"document_id": identity, "expected_version": 1, "operation": rect()},
        request=None, invocation_id="tool-edit", idempotency_key="tool-edit", scope_refs=(scope,), resources={scope.canonical(): store.resolve_document(scope)})
    edited = runtime.invoke(**kwargs)
    assert edited.status == "success", edited.error
    assert edited.artifact_drafts[0].resource_refs == (scope,)
    kwargs["resources"] = {scope.canonical(): store.resolve_document(scope)}
    reconciled = runtime.reconcile(**kwargs)
    assert reconciled.status == "success" and reconciled.output == edited.output
    bad = runtime.invoke(**{**kwargs, "invocation_id": "stale", "idempotency_key": "stale"})
    assert bad.status == "failed"
    missing = runtime.invoke(**{**kwargs, "invocation_id": "missing", "idempotency_key": "missing", "scope_refs": (), "resources": {}})
    assert missing.status == "failed"
    # This is ToolRuntime evidence, not yet the independent same-Run RunLoop gate.


def test_export_reservation_unknown_and_exact_result(store):
    initial = create(store)
    request = c.VersionRequest(document_id=initial.document_id, expected_version=1, mutation_id="export")
    assert store.reserve_export("project-pixel", request) is None
    with pytest.raises(d.PixelError, match="unknown"):
        store.reserve_export("project-pixel", request)
    result = c.ExportResult(run_id="run", session_id="session", artifact_ids=["artifact"])
    store.finish_export("project-pixel", request, result)
    assert store.reserve_export("project-pixel", request) == result


def test_export_reserves_result_capacity_before_starting_action_run(store, monkeypatch):
    current = create(store)
    request = c.VersionRequest(document_id=current.document_id, expected_version=1, mutation_id="export")
    monkeypatch.setattr(c, "MAX_HISTORY_BYTES", c.MAX_OUTPUT_BYTES)
    with pytest.raises(d.PixelError, match="quota"):
        store.reserve_export("project-pixel", request)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM receipts WHERE identity='export'").fetchone()[0] == 0
    assert read(store, current).summary.revision == 1


def test_backend_signed_package_activation_disable_reactivate(tmp_path):
    # Isolated frontend fixture validates Backend packaging only. No product
    # frontend placeholder is created or presented as a Pixel Workbench.
    fixture = tmp_path / "source"
    shutil.copytree(SOURCE / "backend", fixture / "backend", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(SOURCE / "manifest.template.json", fixture / "manifest.template.json")
    (fixture / "frontend").mkdir()
    (fixture / "frontend" / "index.js").write_text("export function register() {}", encoding="utf-8")
    private = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Pixel test-only publisher key").digest())
    built = build_dlc_package_from_source(fixture, private_key=private)
    archive = tmp_path / "pixel.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(c.OWNER, True)
    compiler = ContributionCompiler(service.storage_root)
    active = compiler.compile(built_ins=BuiltinContributionSet())
    assert active.activation_failures == ()
    assert len(active.tools) == 18 and len(active.operations) == 12
    operation = next(item.spec for item in active.operations if item.spec.name == "documents.create")
    created = operation.handler(operation.input_model(title="Persist", width=8, height=8, expected_version=0, mutation_id="persist"),
                                DlcOperationContext(dlc_id=c.OWNER, operation_name="documents.create", project_id="project-pixel"))
    service.set_desired_enabled(c.OWNER, False)
    disabled = compiler.compile(built_ins=BuiltinContributionSet())
    assert disabled.tools == () and disabled.operations == () and disabled.artifact_representations == ()
    service.set_desired_enabled(c.OWNER, True)
    active = compiler.compile(built_ins=BuiltinContributionSet())
    assert active.activation_failures == ()
    get = next(item.spec for item in active.operations if item.spec.name == "documents.get")
    current = get.handler(get.input_model(document_id=created.document_id), DlcOperationContext(dlc_id=c.OWNER, operation_name="documents.get", project_id="project-pixel"))
    assert current.summary.revision == 1 and current.summary.title == "Persist"


def test_public_sdk_only_and_unmodified_codec():
    for path in (SOURCE / "backend").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from engine" not in text and "import engine" not in text and "PIL" not in text
        assert "eval(" not in text and "exec(" not in text
    assert hashlib.sha256((SOURCE / "backend/vendor/png.py").read_bytes()).hexdigest() == "b1c6211078af892bbe975f948d40e19f2e9ec064994f635b6e431b5c55e56830"


def test_process_exit_uncommitted_and_receipt_failure_roll_back(store):
    current = create(store)
    # A separate process exits without running cleanup after corrupting head in
    # an uncommitted transaction. SQLite must recover the original revision.
    script = "import sqlite3,os,sys; db=sqlite3.connect(sys.argv[1]); db.execute('BEGIN IMMEDIATE'); db.execute('UPDATE documents SET head=99'); os._exit(7)"
    process = subprocess.run([sys.executable, "-c", script, str(store.path)], capture_output=True, check=False)
    assert process.returncode == 7 and read(s.PixelStore(store.path.parent), current).summary.revision == 1
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'injected fault'); END")
    with pytest.raises(d.PixelError, match="storage"):
        edit(store, current, rect())
    assert read(store, current).summary.revision == 1
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] == 1
        db.execute("DROP TRIGGER reject_receipt")
    assert edit(store, current, rect()).revision == 2


@pytest.mark.parametrize("corruption", ["missing_cel", "palette_index", "unknown_schema", "duplicate_key", "birth_record", "receipt", "oversized_document", "oversized_receipt"])
def test_corrupted_owner_rows_do_not_become_blank_documents(store, corruption):
    current = create(store)
    with sqlite3.connect(store.path) as db:
        body = json.loads(db.execute("SELECT body FROM revisions").fetchone()[0])
        if corruption == "missing_cel":
            body["frames"][0]["cels"] = []
        elif corruption == "palette_index":
            body["frames"][0]["cels"][0]["pixels"][0] = 255
        elif corruption == "unknown_schema":
            body["schema_version"] = 2
        elif corruption == "birth_record":
            db.execute("DELETE FROM object_identities WHERE kind='frame'")
        elif corruption == "receipt":
            db.execute("UPDATE receipts SET result_body=?", (b'{}',))
        elif corruption == "oversized_receipt":
            db.execute("UPDATE receipts SET input_body=zeroblob(?)", (c.MAX_INPUT_BYTES + 4097,))
        encoded = c.canonical(body).encode("utf-8")
        if corruption == "duplicate_key":
            encoded = encoded[:-1] + b',"schema_version":1}'
        db.execute("UPDATE revisions SET body=?,content_hash=?", (encoded, s.digest(encoded)))
        if corruption == "oversized_document":
            db.execute("UPDATE revisions SET body=zeroblob(?)", (c.MAX_DOCUMENT_BYTES + 1,))
    with pytest.raises(d.PixelError):
        if corruption in ("receipt", "oversized_receipt"):
            create(store)
        else:
            read(store, current)


def test_runtime_deadline_and_cancel_after_commit_reconcile(store):
    registry = ToolRegistry()
    for tool in t.build_tools(store):
        registry.register(tool)
    runtime = ToolRuntime(registry)
    current = create(store)
    scope = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=current.document_id, version="1")
    kwargs = dict(tool_name="pixel_rect", raw_input={"document_id": current.document_id, "expected_version": 1, "operation": rect()},
        request=None, invocation_id="late-cancel", idempotency_key="late-cancel", scope_refs=(scope,), resources={scope.canonical(): store.resolve_document(scope)})
    result = runtime.invoke(**kwargs, deadline=time.monotonic() - 1)
    assert result.error_code == "TOOL_TIMEOUT" and read(store, current).summary.revision == 1
    def cancelled():
        return store.head("project-pixel", c.HeadInput(document_id=current.document_id)).revision > 1
    result = runtime.invoke(**kwargs, cancellation_probe=cancelled)
    assert result.error_code == "TOOL_CANCELLED" and read(store, current).summary.revision == 2
    result = runtime.reconcile(**kwargs)
    assert result.status == "success" and result.output["revision"] == 2


def test_authority_and_receipts_bind_frozen_scope_actor_and_whole_input(store):
    current = create(store)
    payload = c.ApplyInput(document_id=current.document_id, expected_version=1, operations=[rect()])
    stale = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=current.document_id, version="2")
    with pytest.raises(d.PixelError, match="frozen"):
        store.mutate("project-pixel", payload, "write", actor="agent", scope=stale)
    scope = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=current.document_id, version="1")
    committed = store.mutate("project-pixel", payload, "write", actor="agent", scope=scope)
    assert store.reconcile("project-pixel", "agent", "write", "apply", payload, scope) == committed
    with pytest.raises(d.PixelError, match="different input"):
        store.reconcile("project-pixel", "agent", "write", "apply", payload, stale)
    assert store.reconcile("project-pixel", "human", "write", "apply", payload) is None


def test_largest_frame_read_budget_and_tag_metadata_paging(store):
    current = store.create("project-pixel", c.CreateInput(title="狐" * 160, width=128, height=128, expected_version=0), "maximum")
    current = edit(store, current, *({"kind": "layer_create", "layer_id": "layer_" + str(i), "name": "狐" * 80, "position": i - 1} for i in range(2, 17)))
    frame = store.read_frame("project-pixel", c.FrameReadInput(document_id=current.document_id, revision=2, frame_id="frame_1"))
    assert len(frame.frame.cels) == 16 and len(c.canonical(frame).encode("utf-8")) < c.MAX_DOCUMENT_BYTES
    png = b"".join(representation(store, current, "png", frame_id="frame_1").chunks)
    assert Image.open(BytesIO(png)).size == (128, 128)
    small = create(store, key="tags")
    small = edit(store, small, *({"kind": "frame_create", "frame_id": "f" + str(i), "position": i} for i in range(1, 32)), key="many-frames")
    ids = ["frame_1"] + ["f" + str(i) for i in range(1, 32)]
    small = edit(store, small, {"kind": "tag_set", "tag_id": "all", "name": "All", "frame_ids": ids}, key="all-tag")
    preview = representation(store, small, "metadata", kind="tags").payload["items"][0]
    assert preview["truncated"] and preview["frame_count"] == 32 and len(preview["frame_ids"]) == 8
    pages = [representation(store, small, "metadata", kind="tags", tag_id="all", page=p).payload for p in range(2)]
    assert [item["frame_id"] for page in pages for item in page["items"]] == ids


def test_signed_package_same_run_incremental_and_actual_observation(tmp_path):
    from sqlalchemy.orm import sessionmaker
    from dbfox_dlc_api import RequestedResourceRef, ToolKey
    from engine.agent.completion import CompletionGate
    from engine.agent.definition import AgentDefinition
    from engine.agent.events import LiveStreamHub
    from engine.agent.loop import RunLoop
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.run import RunLimits
    from engine.dlc.action_runs import DlcActionRunsHostImpl
    from engine.models import AgentObservationRecord, AgentRun, AgentSession, AgentToolInvocation, Project
    from engine.runtime_composition import (active_runtime_snapshot, authorize_project_resources, build_attempt_resource_resolver,
        build_default_completion_policy, build_product_tool_registry, default_capability_guidance,
        default_context_contributors, initialize_runtime_snapshot, set_active_runtime_snapshot)
    from verification.support.metadata import create_migrated_metadata_engine
    from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

    fixture = tmp_path / "source"
    shutil.copytree(SOURCE / "backend", fixture / "backend", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(SOURCE / "manifest.template.json", fixture / "manifest.template.json")
    (fixture / "frontend").mkdir()
    (fixture / "frontend/index.js").write_text("export function register() {}", encoding="utf-8")
    key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Pixel author RunLoop test key").digest())
    built = build_dlc_package_from_source(fixture, private_key=key)
    archive = tmp_path / "pixel.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "dlcs")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(c.OWNER, True)
    previous = active_runtime_snapshot()
    engine = create_migrated_metadata_engine(tmp_path / "metadata.sqlite")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        snapshot = initialize_runtime_snapshot(storage_root=service.storage_root)
        assert snapshot.activation_failures == ()
        registry = build_product_tool_registry(snapshot)
        project_id, session_id = "pixel-runloop-project", "pixel-runloop-session"
        with factory() as db:
            db.add(Project(id=project_id, name="Pixel"))
            db.flush()
            db.add(AgentSession(id=session_id, project_id=project_id, title="Pixel actual observation"))
            db.commit()
            refs = authorize_project_resources(db, project_id, (RequestedResourceRef(kind=c.LIBRARY_KIND, id=project_id),), snapshot=snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id=session_id, resource_refs=refs, content="Create then incrementally draw and export a Pixel knight.",
                idempotency_key="pixel-runloop", llm_credential_id="scripted", api_base=None, model_name="scripted", request_payload={})
            lease = sessions.claim(session_id=session_id, owner="pixel-author", ttl_seconds=120)
            assert lease is not None
            sessions.promote_next_input(lease=lease)
            db.commit()

        class Model:
            def __init__(self):
                self.index = 0
                self.facts = {}
                self.outputs = []
            def stream(self, *, messages, tools, **kwargs):
                del kwargs
                for item in messages:
                    if item.get("type") == "function_call_output" and item["call_id"] not in {v[0] for v in self.outputs}:
                        value = json.loads(item["output"])
                        self.outputs.append((item["call_id"], value, item["output"]))
                        assert value["status"] == "succeeded", value
                        facts = value["facts"]
                        self.facts = facts.get("summary", facts) if isinstance(facts.get("summary"), dict) else facts
                if self.index == 0:
                    name, payload = "pixel_create", {"library_id": project_id, "title": "Knight", "width": 32, "height": 32, "expected_version": 0}
                elif self.index == 1:
                    name, payload = "pixel_rect", {"document_id": self.facts["document_id"], "expected_version": self.facts["revision"], "operation": rect()}
                elif self.index == 2:
                    name, payload = "pixel_inspect", {"document_id": self.facts["document_id"], "frame_id": "frame_1", "layer_id": "layer_1", "rect": {"x": 0, "y": 0, "width": 8, "height": 8}}
                elif self.index == 3:
                    name, payload = "pixel_line", {"document_id": self.facts["document_id"], "expected_version": self.facts["revision"],
                        "operation": {"kind": "line", "frame_id": "frame_1", "layer_id": "layer_1", "x0": 3, "y0": 3, "x1": 7, "y1": 7, "palette_index": 2}}
                elif self.index == 4:
                    name, payload = "pixel_export", {"document_id": self.facts["document_id"], "expected_version": self.facts["revision"]}
                else:
                    yield from ScriptedProvider(answer_events("Pixel knight revision is ready.")).stream()
                    return
                wire_name = registry.provider_name_for_key(ToolKey(owner_id=c.OWNER, local_name=name))
                assert wire_name in {tool["name"] for tool in tools}
                self.index += 1
                yield from ScriptedProvider(tool_call_events(call_id=f"pixel-step-{self.index}", tool_name=wire_name, arguments=payload)).stream()

        model = Model()
        loop = RunLoop(session_factory=factory, model_factory=lambda settings: model, registry=registry,
            context_contributors=default_context_contributors(snapshot), capability_guidance=default_capability_guidance(snapshot),
            resource_providers=snapshot.resource_providers, resource_resolver=build_attempt_resource_resolver(snapshot=snapshot),
            artifact_payload_contract_resolver=lambda kind, version: snapshot.get_artifact_contract(kind, version).validator,
            runtime_snapshot_id=snapshot.snapshot_id, completion=CompletionGate(build_default_completion_policy(snapshot)),
            definition=AgentDefinition(limits=RunLimits(max_turns=10, max_tool_invocations=10, max_repair_attempts=2,
                finalization_turn_reserve=1, finalization_tool_reserve=1, max_prompt_tokens=64000)), live_stream=LiveStreamHub())
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
        with factory() as db:
            run = db.get(AgentRun, admission.run_id)
            invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
            observations = db.query(AgentObservationRecord).filter_by(run_id=admission.run_id).order_by(AgentObservationRecord.sequence).all()
            assert str(run.status) == "completed", [(v.status, v.error_code, v.error_message) for v in invocations]
            assert len(invocations) == 5 and len(observations) == 5
            assert all(v.status == "succeeded" for v in invocations)
            assert len({v.run_id for v in invocations}) == 1
            assert model.facts["revision"] == 3 and len(model.outputs) == 5
            assert all(len(encoded.encode("utf-8")) <= 18000 and len(encoded) <= 18000 for _, _, encoded in model.outputs)
            assert all(len(v.model_output_json.encode("utf-8")) <= 18000 for v in observations)
            assert all("pixels" not in json.loads(v.facts_json) for v in observations)
            assert model.outputs[2][1]["facts"]["pixels"] is not None
        action_runs = DlcActionRunsHostImpl(dlc_id=c.OWNER, project_id=project_id, snapshot=snapshot,
            session_factory=factory, registry=registry, resource_resolver=build_attempt_resource_resolver(snapshot=snapshot),
            resource_authorizer=lambda db, project, requested: authorize_project_resources(db, project, requested, snapshot=snapshot))
        export = snapshot.get_operation(c.OWNER, "documents.export").spec
        request = export.input_model(document_id=model.facts["document_id"], expected_version=3, mutation_id="human-export")
        context = DlcOperationContext(dlc_id=c.OWNER, operation_name="documents.export", project_id=project_id, action_runs=action_runs)
        exported = export.handler(request, context)
        repeated = export.handler(request, context)
        assert exported == repeated and exported.artifact_ids and exported.run_id != admission.run_id
        with factory() as db:
            assert db.get(AgentRun, exported.run_id).status == "completed"
            assert db.query(AgentRun).count() == 2  # exact export receipt did not create a third Run
    finally:
        set_active_runtime_snapshot(previous)
        engine.dispose()
