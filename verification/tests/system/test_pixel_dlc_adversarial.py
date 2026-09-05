"""New Pixel red-team attacks, separate from the completed independent verification."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4
import zipfile

import pytest
from PIL import Image

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, DlcOperationContext, DlcOperationError, ResourceScopeRef, ToolKey
from engine.agent.repositories.artifact import ArtifactRepository
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.models import Project
from engine.runtime_composition import build_attempt_resource_resolver, build_dlc_action_runs_host
from engine.tools.runtime.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_pixel.runtime import PixelRuntime


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    with PixelRuntime(tmp_path_factory.mktemp("pixel-redteam") / "runtime") as value:
        yield value


def owner_store(runtime):
    return next(item.tool.store for item in runtime.snapshot.tools if item.tool.name == "pixel_create")


def create(runtime, *, width=8, height=8):
    project = "redteam-" + uuid4().hex
    return runtime.operation(project, "documents.create", {
        "title": "Pixel adversarial", "width": width, "height": height,
        "expected_version": 0, "mutation_id": "create"})


def apply(runtime, current, operations, *, mutation_id=None):
    return runtime.operation(current["project_id"], "documents.apply", {
        "document_id": current["document_id"], "expected_version": current["revision"],
        "mutation_id": mutation_id or uuid4().hex, "operations": operations})


def read(runtime, current):
    return runtime.operation(current["project_id"], "documents.get", {"document_id": current["document_id"]})


def invoke(runtime, current, name, payload):
    ref = ResourceScopeRef(kind="dbfox.pixel.document", id=current["document_id"], version=str(current["revision"]))
    resolver = build_attempt_resource_resolver(snapshot=runtime.snapshot)
    wire = runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.pixel", local_name=name))
    return ToolRuntime(runtime.registry).invoke(tool_name=wire, raw_input=payload, request=None,
        invocation_id=uuid4().hex, idempotency_key=uuid4().hex, scope_refs=(ref,), resources=resolver.resolve((ref,)))


def export_artifact(runtime, current):
    with runtime.factory() as db:
        if db.get(Project, current["project_id"]) is None:
            db.add(Project(id=current["project_id"], name=current["project_id"]))
            db.commit()
    spec = runtime.snapshot.get_operation("dbfox.pixel", "documents.export").spec
    value = spec.input_model(document_id=current["document_id"], expected_version=current["revision"], mutation_id=uuid4().hex)
    result = spec.handler(value, DlcOperationContext(dlc_id="dbfox.pixel", operation_name="documents.export", project_id=current["project_id"],
        action_runs=build_dlc_action_runs_host(dlc_id="dbfox.pixel", project_id=current["project_id"], snapshot=runtime.snapshot, session_factory=runtime.factory)))
    with runtime.factory() as db:
        artifact = ArtifactRepository(db).available_artifact(session_id=result.session_id, current_run_id=result.run_id, artifact_id=result.artifact_ids[0])
        assert artifact is not None
        return artifact


def representation(runtime, artifact, operation, **parameters):
    provider = runtime.snapshot.get_artifact_representation("dbfox.pixel.revision", "dbfox.pixel.sprite.v1").provider
    return provider.execute(artifact, ArtifactRepresentationRequest(operation=operation, parameters=parameters),
        ArtifactRepresentationContext(artifact_loader=lambda _: None))


@pytest.mark.parametrize("path,value", [
    (("schema_version",), 1.0), (("schema_version",), "1"),
    (("frames", 0, "duration_ms"), True), (("frames", 0, "duration_ms"), 100.0),
    (("layers", 0, "visible"), 1), (("layers", 0, "locked"), None),
    (("frames", 0, "cels", 0, "pixels", 0), "0"),
])
def test_canonical_scalar_corruption_is_rejected_even_with_recomputed_hash(runtime, path, value):
    current = create(runtime)
    with sqlite3.connect(owner_store(runtime).path) as db:
        body = json.loads(db.execute("SELECT body FROM revisions WHERE document_id=? AND revision=1", (current["document_id"],)).fetchone()[0])
        target = body
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        db.execute("UPDATE revisions SET body=?,content_hash=? WHERE document_id=?", (encoded, hashlib.sha256(encoded).hexdigest(), current["document_id"]))
    with pytest.raises(DlcOperationError) as error:
        read(runtime, current)
    assert error.value.code == "PIXEL_CORRUPT_STATE"


@pytest.mark.parametrize("created_revision", [0, -1, 0.5])
def test_invalid_object_birth_revision_cannot_authorize_canonical_identity(runtime, created_revision):
    current = create(runtime)
    with sqlite3.connect(owner_store(runtime).path) as db:
        db.execute("UPDATE object_identities SET created_revision=? WHERE document_id=? AND kind='frame'", (created_revision, current["document_id"]))
    with pytest.raises(DlcOperationError) as error:
        read(runtime, current)
    assert error.value.code == "PIXEL_CORRUPT_STATE"


def test_native_inspect_can_recover_complete_existing_tag_order_before_replacing_it(runtime):
    current = create(runtime)
    ids = ["frame_1"] + [f"frame_{index}" for index in range(2, 21)]
    current = apply(runtime, current, [{"kind": "frame_create", "frame_id": identity, "position": index}
        for index, identity in enumerate(ids[1:], 1)])
    tag_order = ids[:8] + list(reversed(ids[8:]))
    current = apply(runtime, current, [{"kind": "tag_set", "tag_id": "attack", "name": "Attack",
                                     "frame_ids": tag_order, "loop": False}])
    directory = invoke(runtime, current, "pixel_inspect", {
        "document_id": current["document_id"], "kind": "tags", "page_size": 1})
    assert directory.status == "success"
    preview = directory.output["items"][0]
    assert preview["truncated"] is True and preview["frame_ids"] == tag_order[:8]
    # Explicit contract change after the original failure: observe the tag ID
    # from the directory, then use the new bounded membership selector. Preserve
    # the complete original sequence assertion; do not accept the preview as data.
    observed = []
    for page in range(2):
        result = invoke(runtime, current, "pixel_inspect", {
            "document_id": current["document_id"], "kind": "tags", "tag_id": preview["id"],
            "page": page, "page_size": 16})
        assert result.status == "success" and result.output["tag_id"] == preview["id"]
        assert result.output["has_more"] is (page == 0)
        observed.extend(item["frame_id"] for item in result.output["items"])
    assert observed == tag_order


@pytest.mark.parametrize("extra", [
    {"kind": "frames"}, {"kind": "layers"},
    {"frame_id": "frame_1", "layer_id": "layer_1", "rect": {"x": 0, "y": 0, "width": 1, "height": 1}},
    {"page": True}, {"page_size": 17}, {"tag_id": "missing"},
])
def test_tag_member_selector_rejects_ambiguous_unbounded_and_missing_targets(runtime, extra):
    current = apply(runtime, create(runtime), [{"kind": "tag_set", "tag_id": "idle", "name": "Idle", "frame_ids": ["frame_1"]}])
    result = invoke(runtime, current, "pixel_inspect", {"document_id": current["document_id"], "kind": "tags", "tag_id": "idle", **extra})
    assert result.status != "success"
    assert read(runtime, current)["summary"]["revision"] == current["revision"]


def test_member_pages_stay_at_explicit_history_when_current_tag_order_changes(runtime):
    current = create(runtime)
    ids = ["frame_1"] + [f"member_{index}" for index in range(19)]
    current = apply(runtime, current, [{"kind": "frame_create", "frame_id": identity, "position": index}
        for index, identity in enumerate(ids[1:], 1)])
    previous = apply(runtime, current, [{"kind": "tag_set", "tag_id": "all", "name": "All", "frame_ids": ids}])
    current = apply(runtime, previous, [{"kind": "tag_set", "tag_id": "all", "name": "All", "frame_ids": list(reversed(ids))}])
    historical = []
    for page in range(2):
        result = invoke(runtime, current, "pixel_inspect", {"document_id": current["document_id"],
            "revision": previous["revision"], "kind": "tags", "tag_id": "all", "page": page})
        assert result.status == "success" and result.output["summary"]["revision"] == previous["revision"]
        historical.extend(item["frame_id"] for item in result.output["items"])
    assert historical == ids
    latest = invoke(runtime, current, "pixel_inspect", {"document_id": current["document_id"], "kind": "tags", "tag_id": "all"})
    assert [item["frame_id"] for item in latest.output["items"]] == list(reversed(ids))[:16]
    future = invoke(runtime, current, "pixel_inspect", {"document_id": current["document_id"],
        "revision": current["revision"] + 1, "kind": "tags", "tag_id": "all"})
    assert future.status != "success"


@pytest.mark.parametrize("count,dimensions", [(251, (128, 2008)), (256, (8192, 32))])
def test_prime_and_maximum_frame_sheets_match_tag_order_at_fixed_revision(runtime, count, dimensions):
    current = create(runtime, width=128, height=8)
    identities = ["frame_1"] + [f"long_frame_{index:03d}_" + "x" * 40 for index in range(1, count)]
    for start in range(1, count, 128):
        current = apply(runtime, current, [{"kind": "frame_create", "frame_id": identities[index], "position": index}
            for index in range(start, min(start + 128, count))])
    marked = {identities[index] for index in (0, 1, 62, 63, 64, count - 1)}
    current = apply(runtime, current, [{"kind": "rect", "frame_id": identity, "layer_id": "layer_1", "palette_index": 1,
        "rect": {"x": 7, "y": 3, "width": 1, "height": 1}} for identity in sorted(marked)])
    tag_order = list(reversed(identities))
    current = apply(runtime, current, [{"kind": "tag_set", "tag_id": "reverse", "name": "Reverse", "frame_ids": tag_order}])
    artifact = export_artifact(runtime, current)
    before = current
    current = apply(runtime, current, [{"kind": "tag_set", "tag_id": "reverse", "name": "Forward", "frame_ids": identities}])
    layout = representation(runtime, artifact, "sheet_layout", tag_id="reverse").payload
    assert (layout["width"], layout["height"]) == dimensions
    assert [item["frame_id"] for item in layout["frames"]] == tag_order
    png = b"".join(representation(runtime, artifact, "sheet", tag_id="reverse").chunks)
    image = Image.open(BytesIO(png)).convert("RGBA")
    assert image.size == dimensions and len(png) <= 2 * 1024 * 1024
    for item in layout["frames"]:
        assert image.getpixel((item["x"] + 7, item["y"] + 3))[3] == (255 if item["frame_id"] in marked else 0)
        assert image.getpixel((item["x"], item["y"])) == (0, 0, 0, 0)
    observed = []
    for page in range((count + 15) // 16):
        metadata = representation(runtime, artifact, "metadata", kind="tags", tag_id="reverse", page=page).payload
        tool = invoke(runtime, current, "pixel_inspect", {"document_id": current["document_id"], "revision": before["revision"],
            "kind": "tags", "tag_id": "reverse", "page": page})
        assert tool.status == "success" and tool.output["items"] == metadata["items"]
        assert len(json.dumps(tool.output).encode()) <= 16384
        observed.extend(item["frame_id"] for item in metadata["items"])
    assert observed == tag_order
    if count == 256:
        assert current["width"] * current["height"] * current["frame_count"] * current["layer_count"] == 262144
        for operation in ({"kind": "layer_create", "layer_id": "over-budget", "name": "Extra", "position": 1},
                          {"kind": "frame_create", "frame_id": "over-budget", "position": 255}):
            with pytest.raises(DlcOperationError) as error:
                apply(runtime, current, [operation])
            assert error.value.code == "PIXEL_LIMIT"
            assert read(runtime, current)["summary"]["revision"] == current["revision"]
        # A rejected allocation must not burn its proposed identity.
        recovered = apply(runtime, current, [{"kind": "tag_delete", "tag_id": "reverse"},
            {"kind": "frame_delete", "frame_id": identities[-1]}, {"kind": "frame_create", "frame_id": "over-budget", "position": 255}])
        assert recovered["frame_count"] == 256


@pytest.mark.parametrize("count", [127, 128, 129])
def test_changed_frame_boundary_and_undo_of_undo_preserve_complete_paged_diff(runtime, count):
    current = create(runtime, width=1, height=1)
    ids = ["frame_1"] + [f"frame_{index:03d}" for index in range(1, count)]
    for start in range(1, count, 128):
        current = apply(runtime, current, [{"kind": "frame_create", "frame_id": ids[index], "position": index}
            for index in range(start, min(start + 128, count))])
    before = current
    # Creating a layer changes every frame through one public operation.
    changed = apply(runtime, current, [{"kind": "layer_create", "layer_id": "all", "name": "All", "position": 1}])
    assert changed["changed_frame_ids"] == sorted(ids)[:128]
    assert changed["changed_frame_ids_truncated"] is (count > 128)
    seen = []
    for page in range((count + 15) // 16):
        delta = runtime.operation(current["project_id"], "documents.diff", {"document_id": current["document_id"],
            "from_revision": before["revision"], "to_revision": changed["revision"], "kind": "frames", "page": page})
        assert delta["total"] == count and delta["has_more"] is (page + 1 < (count + 15) // 16)
        seen.extend(item["id"] for item in delta["items"])
    assert seen == sorted(ids)
    undone = runtime.operation(current["project_id"], "documents.undo", {"document_id": current["document_id"],
        "expected_version": changed["revision"], "restore_revision": before["revision"], "mutation_id": uuid4().hex})
    restored = runtime.operation(current["project_id"], "documents.undo", {"document_id": current["document_id"],
        "expected_version": undone["revision"], "restore_revision": changed["revision"], "mutation_id": uuid4().hex})
    assert undone["content_hash"] == before["content_hash"] and restored["content_hash"] == changed["content_hash"]
    assert undone["revision"] == changed["revision"] + 1 and restored["revision"] == undone["revision"] + 1
    assert restored["changed_frame_ids_truncated"] is (count > 128)


def test_project_document_quota_delete_restore_and_failed_identity_are_atomic(runtime):
    initial = create(runtime, width=1, height=1)
    project = initial["project_id"]
    for index in range(127):
        runtime.operation(project, "documents.create", {"title": str(index), "width": 1, "height": 1,
            "expected_version": 0, "mutation_id": "quota-" + str(index)})
    request = {"title": "Overflow", "width": 1, "height": 1, "expected_version": 0, "mutation_id": "overflow"}
    with pytest.raises(DlcOperationError) as error:
        runtime.operation(project, "documents.create", request)
    assert error.value.code == "PIXEL_LIMIT"
    deleted = runtime.operation(project, "documents.delete", {"document_id": initial["document_id"],
        "expected_version": 1, "mutation_id": "delete"})
    replacement = runtime.operation(project, "documents.create", request)
    assert replacement["revision"] == 1
    with pytest.raises(DlcOperationError) as error:
        runtime.operation(project, "documents.restore", {"document_id": initial["document_id"],
            "expected_version": deleted["revision"], "mutation_id": "restore"})
    assert error.value.code == "PIXEL_LIMIT"
    assert read(runtime, deleted)["summary"]["status"] == "deleted"
    pages = [runtime.operation(project, "documents.list", {"page": page, "page_size": 32}) for page in range(4)]
    identities = [item["document_id"] for page in pages for item in page["documents"]]
    assert len(set(identities)) == 128 and initial["document_id"] not in identities
    assert pages[-1]["has_more"] is False
    assert create(runtime, width=1, height=1)["revision"] == 1  # another Project has its own active-document cap


def test_foreign_project_selector_and_wrong_owner_cannot_inherit_document_scope(runtime):
    selected, foreign = create(runtime), create(runtime)
    result = invoke(runtime, selected, "pixel_inspect", {"document_id": foreign["document_id"], "kind": "frames"})
    assert result.status != "success"
    with pytest.raises(DlcOperationError):
        runtime.operation(selected["project_id"], "documents.get", {"document_id": foreign["document_id"]})
    spec = runtime.snapshot.get_operation("dbfox.pixel", "documents.apply").spec
    request = spec.input_model(document_id=selected["document_id"], expected_version=1, mutation_id="wrong-owner",
        operations=[{"kind": "rename", "title": "Should not write"}])
    with pytest.raises(DlcOperationError):
        spec.handler(request, DlcOperationContext(dlc_id="dbfox.scene", operation_name="documents.apply", project_id=selected["project_id"]))
    assert read(runtime, selected)["summary"]["revision"] == read(runtime, foreign)["summary"]["revision"] == 1


def _crash_after_commit(directory, project, document_id):
    """Child owns only this fixture runtime; exit after the real store COMMIT."""
    with PixelRuntime(Path(directory), existing=True) as runtime:
        store = owner_store(runtime)
        original = store.mutate
        def commit_then_exit(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(27)
        store.mutate = commit_then_exit
        ref = ResourceScopeRef(kind="dbfox.pixel.document", id=document_id, version="1")
        resolver = build_attempt_resource_resolver(snapshot=runtime.snapshot)
        ToolRuntime(runtime.registry).invoke(tool_name=runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.pixel", local_name="pixel_rect")),
            raw_input={"document_id": document_id, "expected_version": 1, "operation": {"kind": "rect", "frame_id": "frame_1",
                "layer_id": "layer_1", "palette_index": 1, "rect": {"x": 0, "y": 0, "width": 1, "height": 1}}},
            request=None, invocation_id="crash-committed", idempotency_key="crash-committed", scope_refs=(ref,), resources=resolver.resolve((ref,)))
        raise AssertionError("The process did not exit at the commit boundary")


def test_real_process_death_after_commit_cold_reconcile_keeps_later_human_edit(tmp_path):
    directory = tmp_path / "crash-runtime"
    with PixelRuntime(directory) as runtime:
        original = create(runtime)
    child = subprocess.run([sys.executable, "-c", "from verification.tests.system.test_pixel_dlc_adversarial import _crash_after_commit; import sys; _crash_after_commit(*sys.argv[1:])",
        str(directory), original["project_id"], original["document_id"]], cwd=Path(__file__).resolve().parents[3], capture_output=True, timeout=40, check=False)
    assert child.returncode == 27, child.stderr.decode(errors="replace")[-2000:]
    with PixelRuntime(directory, existing=True) as reopened:
        committed = read(reopened, original)["summary"]
        assert committed["revision"] == 2
        human = apply(reopened, committed, [{"kind": "rename", "title": "Later human title"}])
        ref = ResourceScopeRef(kind="dbfox.pixel.document", id=original["document_id"], version="1")
        resolver = build_attempt_resource_resolver(snapshot=reopened.snapshot)
        result = ToolRuntime(reopened.registry).reconcile(tool_name=reopened.registry.provider_name_for_key(ToolKey(owner_id="dbfox.pixel", local_name="pixel_rect")),
            raw_input={"document_id": original["document_id"], "expected_version": 1, "operation": {"kind": "rect", "frame_id": "frame_1",
                "layer_id": "layer_1", "palette_index": 1, "rect": {"x": 0, "y": 0, "width": 1, "height": 1}}},
            request=None, invocation_id="crash-committed", idempotency_key="crash-committed", scope_refs=(ref,), resources=resolver.resolve((ref,)))
        assert result.status == "success" and result.output["revision"] == 2
        assert result.artifact_drafts[0].payload["revision"] == 2
        assert read(reopened, human)["summary"] == {key: value for key, value in human.items()
            if key not in ("changed", "changed_pixel_count", "changed_frame_ids", "changed_frame_ids_truncated", "changed_layer_ids")}


@pytest.mark.parametrize("entry", ["frontend/model.js", "backend/vendor/png.py"])
def test_signature_rejects_source_or_codec_changes_without_new_publisher_proof(runtime, tmp_path, entry):
    archive = BytesIO()
    with zipfile.ZipFile(BytesIO(runtime.package.archive_bytes)) as original, zipfile.ZipFile(archive, "w") as damaged:
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == entry:
                content += b"\n"  # Semantically harmless still changes the signed bytes.
            damaged.writestr(info, content)
    path = tmp_path / "tampered.dbfox-dlc"
    path.write_bytes(archive.getvalue())
    with pytest.raises(DlcError) as error:
        runtime.service.install_from_file(path)
    assert error.value.code == DlcErrorCode.HASH_MISMATCH
    record = runtime.service.registry.get_installed_dlc("dbfox.pixel")
    assert record is not None and record.selected_digest == runtime.package.package_digest and record.desired_enabled
