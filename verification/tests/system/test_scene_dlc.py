"""Backend-owned Scene verification; independent product verification is separate."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import threading

from cryptography.hazmat.primitives.asymmetric import ed25519
import pytest

from dbfox_dlc_api import Artifact, ArtifactRepresentationContext, ArtifactRepresentationRequest, ContextContributionInput, ResourceScopeRef
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.tools.runtime import ToolRunContext
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.runtime import ToolRuntime

SOURCE = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.scene"
PACKAGE = "_scene_backend_verification"
if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(PACKAGE, SOURCE / "backend" / "__init__.py",
                                                submodule_search_locations=[str(SOURCE / "backend")])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
c = importlib.import_module(PACKAGE + ".contracts")
s = importlib.import_module(PACKAGE + ".store")
t = importlib.import_module(PACKAGE + ".contributions")
r = importlib.import_module(PACKAGE + ".representation")


@pytest.fixture
def store(tmp_path):
    return s.SceneStore(tmp_path / "scene-data")


def create(store, title="Fox Temple"):
    payload = c.CreateInput(title=title)
    return store.create("project-scene", payload, title, "create-1")


def edit(store, scene, operation, key="edit-1", expected=None, **kwargs):
    payload = c.MutationInput(scene_id=scene.id, expected_version=expected or scene.version, operation=operation)
    return store.mutate(scene.project_id, scene.id, payload.expected_version, "apply", payload, key,
                        operation=payload.operation, **kwargs)


def objects(*items):
    return {"kind": "object_create", "objects": list(items)}


def mesh(identity="fox", **fields):
    return {"id": identity, "name": identity, "kind": "mesh", **fields}


def test_scene_sources_use_public_sdk_and_no_dynamic_execution():
    for path in (SOURCE / "backend").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from engine" not in text and "import engine" not in text
        assert "Any" not in text and "eval(" not in text and "exec(" not in text


def test_create_reload_mutate_and_fixed_geometry_catalog(store):
    initial = create(store)
    assert initial.scene.version == 1
    changed = edit(store, initial.scene, objects(mesh()))
    assert changed.scene.version == 2 and changed.changed_ids == ["fox"]
    restarted = s.SceneStore(store.path.parent)
    assert restarted.get_revision("project-scene", initial.scene.id, 1).document.objects == []
    assert restarted.get_revision("project-scene", initial.scene.id).document.objects[0].id == "fox"
    assert {g.primitive for g in restarted.get_revision("project-scene", initial.scene.id).document.geometries} == {
        "box", "sphere", "cylinder", "cone", "plane", "torus"}


def test_all_scene_tools_project_identifiers_versions_and_failures(store):
    initial = create(store)
    for tool in t.build_tools(store):
        if tool.output_model is c.MutationResult:
            projection = tool.project_observation(status="success", output=initial.model_dump(mode="json"), artifacts=())
            assert projection.facts["scene"]["id"] == initial.scene.id
            assert projection.facts["scene"]["version"] == 1
            assert projection.provider_payload == projection.facts
            assert len(json.dumps(projection.facts).encode()) < 32_768
        failed = tool.project_observation(status="error", output={}, artifacts=())
        assert failed.facts == {} and failed.provider_payload == {}


def test_inspection_observation_preserves_complete_entities_and_continuation(store):
    initial = create(store)
    changed = edit(store, initial.scene, objects(*(
        mesh(f"node-{index}", name="狐" * 120) for index in range(100))))
    tool = t.SceneInspectTool(store)
    offset = 0
    seen = []
    while offset < 100:
        result = store.page("project-scene", c.InspectInput(scene_id=changed.scene.id, version=2, offset=offset))
        projection = tool.project_observation(status="success", output=result.model_dump(mode="json"), artifacts=())
        facts = projection.facts
        assert facts["scene"]["id"] == changed.scene.id and facts["scene"]["version"] == 2
        assert len(json.dumps(facts, ensure_ascii=False).encode()) < 32_768
        assert 0 < facts["returned"] <= 100 and facts["next_offset"] == offset + facts["returned"]
        assert facts["observation_truncated"] == (facts["returned"] < len(result.objects))
        for item in facts["objects"]:
            assert c.Mesh.model_validate(item).name == "狐" * 120
            seen.append(item["id"])
        assert facts["has_more"] == (facts["next_offset"] < 100)
        offset = facts["next_offset"]
    assert len(seen) == len(set(seen)) == 100
    diff = store.diff("project-scene", c.DiffInput(scene_id=changed.scene.id, from_version=1, to_version=2))
    projected = t.SceneDiffTool(store).project_observation(status="success", output=diff.model_dump(mode="json"), artifacts=())
    assert projected.facts["scene_id"] == changed.scene.id
    assert projected.facts["from_version"] == 1 and projected.facts["to_version"] == 2
    assert projected.facts["returned"] == 100 and not projected.facts["has_more"]


def test_receipt_returns_original_revision_after_later_edits(store):
    initial = create(store)
    first = edit(store, initial.scene, objects(mesh()))
    second = edit(store, first.scene, {"kind": "object_transform", "transforms": [{"object_id": "fox", "position": [1, 2, 3]}]}, "edit-2")
    repeated = edit(store, initial.scene, objects(mesh()))
    assert second.scene.version == 3 and repeated == first
    assert create(store) == initial
    with pytest.raises(s.SceneError, match="different input"):
        edit(store, initial.scene, objects(mesh("other")))


def test_undo_appends_previously_seen_content_hash(store):
    initial = create(store)
    first = edit(store, initial.scene, objects(mesh()))
    payload = c.UndoInput(scene_id=first.scene.id, expected_version=2, target_version=1)
    undone = store.mutate("project-scene", first.scene.id, 2, "undo", payload, "undo-1", target_version=1)
    assert undone.scene.version == 3 and undone.scene.content_hash == initial.scene.content_hash
    restored = c.UndoInput(scene_id=first.scene.id, expected_version=3, target_version=2)
    redone = store.mutate("project-scene", first.scene.id, 3, "undo", restored, "undo-2", target_version=2)
    assert redone.scene.version == 4 and redone.scene.content_hash == first.scene.content_hash


def test_stale_expected_and_frozen_version_both_reject(store):
    initial = create(store)
    first = edit(store, initial.scene, objects(mesh()))
    operation = {"kind": "object_update", "object_id": "fox", "name": "Renamed"}
    for expected, frozen in ((1, 2), (2, 1)):
        with pytest.raises(s.SceneError, match="version changed"):
            edit(store, first.scene, operation, f"stale-{expected}", expected=expected, frozen_version=frozen)
    assert store.get_revision("project-scene", first.scene.id).scene.version == 2


def test_two_connections_race_has_one_winner(store):
    initial = create(store)
    barrier = threading.Barrier(2)
    def contender(index):
        other = s.SceneStore(store.path.parent)
        barrier.wait()
        try:
            return edit(other, initial.scene, objects(mesh(f"node-{index}")), f"race-{index}").scene.version
        except s.SceneError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(contender, [1, 2]))
    assert sorted(map(str, outcomes)) == ["2", "SCENE_STALE"]
    assert store.get_revision("project-scene", initial.scene.id).scene.object_count == 1


@pytest.mark.parametrize("node", [
    mesh(position=[float("nan"), 0, 0]), mesh(scale=[-1, 1, 1]),
    mesh(geometry_id="https://example.com/a.glb"), mesh(parent_id="missing"),
    mesh(kind="script", code="exec('bad')"), mesh(scale=[0, 1, 1]),
])
def test_invalid_nodes_never_commit(store, node):
    initial = create(store)
    with pytest.raises(ValueError):
        edit(store, initial.scene, objects(node))
    assert store.get_revision("project-scene", initial.scene.id).scene.version == 1


def test_hierarchy_cycle_and_world_scale_overflow_are_rejected(store):
    initial = create(store)
    for nodes in (
        [mesh("a", parent_id="b"), mesh("b", parent_id="a")],
        [mesh("a", scale=[100000, 100000, 100000]), mesh("b", parent_id="a", scale=[100000, 100000, 100000])],
        [mesh(f"n{i}", parent_id=f"n{i-1}" if i else None, scale=[0.0001, 0.0001, 0.0001]) for i in range(4)],
    ):
        with pytest.raises(s.SceneError):
            edit(store, initial.scene, objects(*nodes))
    assert store.get_revision("project-scene", initial.scene.id).scene.version == 1


def test_delete_subtree_duplicate_and_diff_preserve_locality(store):
    initial = create(store)
    first = edit(store, initial.scene, objects({"kind": "group", "id": "parent", "name": "Parent"},
        mesh("child", parent_id="parent"), mesh("unrelated")))
    with pytest.raises(s.SceneError, match="subtree"):
        edit(store, first.scene, {"kind": "object_delete", "object_ids": ["parent"]}, "bad-delete")
    duplicate = edit(store, first.scene, {"kind": "object_duplicate", "object_ids": ["parent"], "include_subtree": True}, "duplicate")
    assert duplicate.scene.object_count == 5
    deleted = edit(store, duplicate.scene, {"kind": "object_delete", "object_ids": ["parent"], "include_subtree": True}, "delete")
    assert deleted.scene.object_count == 3
    delta = store.diff("project-scene", c.DiffInput(scene_id=first.scene.id, from_version=2, to_version=4))
    assert "unrelated" not in {item.id for item in delta.differences}
    with pytest.raises(s.SceneError, match="cannot be reused"):
        edit(store, deleted.scene, objects(mesh("parent")), "reuse")


def test_noop_does_not_advance_version(store):
    first = edit(store, create(store).scene, objects(mesh()))
    noop = edit(store, first.scene, {"kind": "object_transform", "transforms": [{"object_id": "fox", "position": [0, 0, 0]}]}, "noop")
    assert not noop.changed and noop.scene.version == first.scene.version


def test_light_and_camera_patches_keep_ids_and_validate_combined_parameters(store):
    first = edit(store, create(store).scene, objects(
        {"kind": "light", "id": "key", "name": "Key light", "intensity": 100, "range": 20},
        {"kind": "camera", "id": "view", "name": "View"}))
    changed = edit(store, first.scene, {"kind": "light_update", "light_id": "key", "intensity": 80}, "light-20pct")
    document = store.get_revision("project-scene", first.scene.id).document
    assert document.objects[0].id == "key" and document.objects[0].intensity == 80 and document.objects[0].range == 20
    cleared = edit(store, changed.scene, {"kind": "light_update", "light_id": "key", "clear_range": True}, "clear-range")
    assert store.get_revision("project-scene", first.scene.id).document.objects[0].range is None
    with pytest.raises(s.SceneError):
        edit(store, cleared.scene, {"kind": "camera_update", "camera_id": "view", "znear": 2000}, "invalid-camera")


def test_midtransaction_failure_rolls_back_revision_and_receipt(store, monkeypatch):
    initial = create(store)
    def fail(*_args):
        raise RuntimeError("injected before receipt")
    monkeypatch.setattr(store, "_save_receipt", fail)
    with pytest.raises(RuntimeError, match="injected"):
        edit(store, initial.scene, objects(mesh()))
    restarted = s.SceneStore(store.path.parent)
    assert restarted.get_revision("project-scene", initial.scene.id).scene.version == 1
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM scene_revisions").fetchone()[0] == 1


def test_cancel_before_commit_rolls_back(store):
    initial = create(store)
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls == 2
    with pytest.raises(s.SceneError, match="cancelled"):
        edit(store, initial.scene, objects(mesh()), cancelled=cancelled)
    assert store.get_revision("project-scene", initial.scene.id).scene.version == 1


def test_cross_project_and_deleted_scene_do_not_allow_writes(store):
    initial = create(store)
    with pytest.raises(s.SceneError, match="this Project"):
        store.get_revision("other-project", initial.scene.id)
    payload = c.VersionInput(scene_id=initial.scene.id, expected_version=1)
    deleted = store.mutate("project-scene", initial.scene.id, 1, "delete", payload, "delete-scene")
    assert deleted.scene.version == 2
    assert len(store.list_resources("project-scene")) == 1
    assert store.resolve_scene(ResourceScopeRef(kind=c.SCENE_KIND, id=initial.scene.id, version=1)).scene.version == 1
    with pytest.raises(s.SceneError, match="deleted"):
        edit(store, deleted.scene, objects(mesh()))


def test_corrupt_content_and_unknown_schema_fail_closed(store):
    initial = create(store)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE scene_revisions SET content_hash=?", ("0" * 64,))
    with pytest.raises(s.SceneError, match="integrity"):
        store.get_revision("project-scene", initial.scene.id)
    with sqlite3.connect(store.path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(s.SceneError, match="newer"):
        s.SceneStore(store.path.parent)


@pytest.mark.parametrize("corruption", ["head_rollback", "head_missing", "parent_self", "parent_missing"])
def test_corrupt_revision_head_or_parent_fails_closed(store, corruption):
    initial = create(store)
    edit(store, initial.scene, objects(mesh()))
    with sqlite3.connect(store.path) as db:
        if corruption == "head_rollback":
            db.execute("UPDATE scenes SET head_version=1")
        elif corruption == "head_missing":
            db.execute("UPDATE scenes SET head_version=99")
        elif corruption == "parent_self":
            db.execute("UPDATE scene_revisions SET parent_version=2 WHERE version=2")
        else:
            db.execute("DELETE FROM scene_revisions WHERE version=1")
    with pytest.raises(s.SceneError) as failure:
        store.get_revision(initial.scene.project_id, initial.scene.id)
    assert failure.value.code == "SCENE_CORRUPT"


def test_real_tool_runtime_create_edit_reconcile_and_authority(store):
    tools = t.build_tools(store)
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    runtime = ToolRuntime(registry)
    library_ref = ResourceScopeRef(kind=c.LIBRARY_KIND, id="project-scene", version=1)
    created = runtime.invoke(tool_name="scene_create", raw_input={"title": "Runtime temple"}, request=None,
        idempotency_key="run-create", invocation_id="run-create", scope_refs=(library_ref,),
        resources={library_ref.canonical(): store.resolve_library(library_ref)})
    assert created.status == "success"
    scene_id = created.output["scene"]["id"]
    scope = ResourceScopeRef(kind=c.SCENE_KIND, id=scene_id, version=1)
    payload = {"scene_id": scene_id, "expected_version": 1, "operation": objects(mesh())}
    kwargs = dict(tool_name="object_create", raw_input=payload, request=None, idempotency_key="run-edit",
        invocation_id="run-edit", scope_refs=(scope,), resources={scope.canonical(): store.resolve_scene(scope)})
    edited = runtime.invoke(**kwargs)
    assert edited.status == "success", edited.error
    # Simulate worker restart: resolver must still load v1 before receipt reconciliation.
    kwargs["resources"] = {scope.canonical(): store.resolve_scene(scope)}
    reconciled = runtime.reconcile(**kwargs)
    assert reconciled.status == "success" and reconciled.output == edited.output
    assert edited.artifact_drafts[0].resource_refs == (scope,)
    missing = runtime.invoke(tool_name="object_create", raw_input=payload, request=None, idempotency_key="missing",
                             invocation_id="missing", scope_refs=(), resources={})
    assert missing.status == "failed"


def test_light_patch_survives_host_input_normalization(store):
    first = edit(store, create(store).scene, objects({"kind": "light", "id": "key", "name": "Key", "intensity": 100, "range": 20}))
    tool = next(tool for tool in t.build_tools(store) if tool.name == "light_update")
    scope = ResourceScopeRef(kind=c.SCENE_KIND, id=first.scene.id, version=2)
    payload = {"scene_id": first.scene.id, "expected_version": 2,
               "operation": {"light_id": "key", "intensity": 80}}
    normalized = tool.input_model.model_validate(payload).model_dump(mode="json", exclude_none=True)
    # Same normalization performed by Dispatcher and PolicyGate, then worker revalidation.
    reparsed = tool.input_model.model_validate(normalized)
    context = ToolRunContext.for_invocation(request=None, invocation_id="normalized-light", idempotency_key="normalized-light",
        scope_refs=(scope,), resources={scope.canonical(): store.resolve_scene(scope)})
    result = tool.run(reparsed, context)
    assert result.output.scene.version == 3
    light = store.get_revision("project-scene", first.scene.id).document.objects[0]
    assert light.id == "key" and light.intensity == 80 and light.range == 20


def test_maximum_scene_size_and_page_revision_stability(store):
    current = create(store)
    for batch in range(20):
        current = edit(store, current.scene,
            objects(*(mesh(f"node-{batch * 500 + i}") for i in range(500))), f"batch-{batch}")
    assert current.scene.object_count == 10000 and current.scene.version == 21
    with pytest.raises(s.SceneError):
        edit(store, current.scene, objects(mesh("too-many")), "overflow")
    old_page = store.page("project-scene", c.InspectInput(scene_id=current.scene.id, version=2, offset=400))
    assert old_page.total == 500 and old_page.scene.version == 2 and len(old_page.objects) == 100
    current_page = store.page("project-scene", c.InspectInput(scene_id=current.scene.id, version=21, offset=9900))
    assert current_page.total == 10000 and len(current_page.objects) == 100


def test_expanding_a_subtree_cannot_bypass_batch_limit(store):
    first = edit(store, create(store).scene, objects(
        {"kind": "group", "id": "root", "name": "Root"},
        *(mesh(f"child-{i}", parent_id="root") for i in range(499))))
    second = edit(store, first.scene, objects(mesh("last-child", parent_id="root")), "extra-child")
    with pytest.raises(s.SceneError, match="500"):
        edit(store, second.scene, {"kind": "object_duplicate", "object_ids": ["root"], "include_subtree": True}, "oversized-subtree")
    assert store.get_revision("project-scene", first.scene.id).scene.version == 3


def test_pages_context_and_large_batch_are_bounded(store):
    initial = create(store)
    current = edit(store, initial.scene, objects(*(mesh(f"n{i}") for i in range(500))))
    page = store.page("project-scene", c.InspectInput(scene_id=current.scene.id, version=2))
    assert len(page.objects) == 100 and page.total == 500
    with pytest.raises(ValueError):
        c.InspectInput(scene_id=current.scene.id, limit=101)
    with pytest.raises(ValueError):
        c.CreateObjects(objects=[mesh(f"n{i}") for i in range(501)])
    context = t.SceneContextContributor(store).build(ContextContributionInput(session_id="s", run_id="r", current_request="inspect",
        resource_refs=(ResourceScopeRef(kind=c.SCENE_KIND, id=current.scene.id, version=2),)))
    assert sum(len(item.content) for item in context) <= 4000
    assert "position" not in context[0].content


def test_gltf_and_glb_export_cover_all_primitives_and_shared_buffers(store):
    initial = create(store)
    created = edit(store, initial.scene, objects(*(mesh(kind, geometry_id=f"geometry.{kind}") for kind in
        ("box", "sphere", "cylinder", "cone", "plane", "torus")), mesh("other-box"),
        {"kind": "light", "id": "sun", "name": "Sun", "light_type": "directional"},
        {"kind": "camera", "id": "camera", "name": "Camera"}))
    revision = store.get_revision("project-scene", created.scene.id)
    gltf = json.loads(r.export_scene(revision, False))
    glb = r.export_scene(revision, True)
    assert len(gltf["meshes"]) == 6 and len(gltf["accessors"]) == 18
    assert gltf["extensionsUsed"] == ["KHR_lights_punctual"]
    assert gltf["buffers"][0]["uri"].startswith("data:")
    magic, version, length = struct.unpack("<4sII", glb[:12])
    assert (magic, version, length) == (b"glTF", 2, len(glb))
    json_length = struct.unpack("<I", glb[12:16])[0]
    tree = json.loads(glb[20:20 + json_length])
    assert "uri" not in tree["buffers"][0]
    assert len(glb) < c.MAX_EXPORT_BYTES


def test_immutable_representation_is_revision_pinned(store):
    first = edit(store, create(store).scene, objects(mesh()))
    scope = ResourceScopeRef(kind=c.SCENE_KIND, id=first.scene.id, version=1)
    draft = t.revision_artifact(first.scene, scope)
    artifact = Artifact(id="scene-artifact", session_id="session", run_id="run",
        **draft.model_dump(exclude={"key", "select_if_none", "payload_draft_refs", "visibility"}))
    edit(store, first.scene, {"kind": "object_transform", "transforms": [{"object_id": "fox", "position": [20, 0, 0]}]}, "later")
    provider = r.SceneRepresentation(store)
    result = provider.execute(artifact, ArtifactRepresentationRequest(operation="objects_page"), ArtifactRepresentationContext(artifact_loader=lambda _id: None))
    assert result.source_version == "2" and result.payload["objects"][0]["position"] == [0, 0, 0]
    with pytest.raises(Exception, match="Invalid Scene"):
        provider.execute(artifact, ArtifactRepresentationRequest(operation="objects_page", parameters={"scene_id": "other"}), ArtifactRepresentationContext(artifact_loader=lambda _id: None))


def test_backend_signed_package_activation_disable_reactivate(tmp_path):
    # The frontend stub isolates backend registration; it is not frontend product validation.
    fixture = tmp_path / "source"
    shutil.copytree(SOURCE / "backend", fixture / "backend", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(SOURCE / "manifest.template.json", fixture / "manifest.template.json")
    (fixture / "frontend").mkdir()
    (fixture / "frontend" / "index.js").write_text("export function register() {}", encoding="utf-8")
    private = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Scene test-only publisher key").digest())
    built = build_dlc_package_from_source(fixture, private_key=private)
    archive = tmp_path / "scene.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest,
                                     expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(c.OWNER, True)
    compiler = ContributionCompiler(service.storage_root)
    active = compiler.compile(built_ins=BuiltinContributionSet())
    assert active.activation_failures == ()
    assert {item.tool.name for item in active.tools} >= {"scene_create", "object_transform", "light_update", "scene_export"}
    assert {item.spec.name for item in active.operations} == {
        "scenes.list", "scenes.get", "scenes.create", "scenes.apply", "scenes.undo", "scenes.delete", "scenes.diff", "scenes.artifact"}
    service.set_desired_enabled(c.OWNER, False)
    disabled = compiler.compile(built_ins=BuiltinContributionSet())
    assert disabled.tools == () and disabled.operations == () and disabled.artifact_representations == ()
    service.set_desired_enabled(c.OWNER, True)
    assert compiler.compile(built_ins=BuiltinContributionSet()).activation_failures == ()
