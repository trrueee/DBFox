"""Animation author verification; independent red-team and UI validation are separate."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
from pathlib import Path
import sys
from uuid import uuid4
import pytest

SOURCE = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.animation"
PACKAGE = "_animation_verification"
spec = importlib.util.spec_from_file_location(PACKAGE, SOURCE / "backend/__init__.py", submodule_search_locations=[str(SOURCE / "backend")])
module = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = module
spec.loader.exec_module(module)
c = importlib.import_module(PACKAGE + ".contracts")
s = importlib.import_module(PACKAGE + ".store")
t = importlib.import_module(PACKAGE + ".contributions")
r = importlib.import_module(PACKAGE + ".representation")


@pytest.fixture
def store(tmp_path):
    return s.AnimationStore(tmp_path)


def edit(store, summary, operation, invocation=None, **kwargs):
    payload = c.MutationInput(animation_id=summary.id, expected_version=summary.version, operation=operation)
    return store.mutate(summary.project_id, "apply", payload, invocation or uuid4().hex, **kwargs)


def timeline(store):
    result = store.create("project", c.CreateInput(title="Fox gesture"), "create")
    result = edit(store, result.animation, {"kind":"target_create", "target":{"id":"fox","name":"Fox"}})
    return edit(store, result.animation, {"kind":"track_create", "track":{"id":"x","name":"Move X","target_id":"fox","property":"position.x"}})


def test_tool_definitions_build_and_have_exact_resources(store):
    tools = t.build_tools(store)
    assert {"track_create","keyframe_add","keyframe_move","easing_set","clip_create","clip_trim","timing_modify","scene_bind"} <= {tool.name for tool in tools}
    for tool in tools:
        assert tool.execution.required_resources
        assert tool.input_model.model_json_schema()


def test_twelve_step_incremental_workload_reload_undo_diff_and_fixed_history(store):
    result = timeline(store)
    first = result.animation
    steps = [
        {"kind":"keyframe_add","keyframes":[{"id":"k0","track_id":"x","tick":0,"value":0},{"id":"k1","track_id":"x","tick":4000,"value":8}]},
        {"kind":"easing_set","curve":{"id":"ease","kind":"bezier","x1":.25,"y1":0,"x2":.75,"y2":0},"keyframe_ids":["k0"]},
        {"kind":"clip_create","clip":{"id":"clip","name":"Gesture","track_ids":["x"],"start":0,"end":4000}},
        {"kind":"clip_trim","clip_id":"clip","start":500,"end":3000},
        {"kind":"marker_set","marker":{"id":"beat","name":"Anticipation","tick":1000}},
        {"kind":"marker_set","marker":{"id":"beat","name":"Contact","tick":2000}},
        {"kind":"keyframe_move","keyframes":[{"id":"k1","tick":5000,"value":10}]},
        {"kind":"timing_modify","timing":{"duration":6000,"fps":60,"rate":.5,"loop":True}},
        {"kind":"animation_rename","title":"Fox refined"},
        {"kind":"entity_delete","section":"markers","ids":["beat"]},
        {"kind":"keyframe_add","keyframes":[{"id":"settle","track_id":"x","tick":6000,"value":0}]},
        {"kind":"keyframe_move","keyframes":[{"id":"settle","tick":6000,"value":1}]},
    ]
    for operation in steps:
        result = edit(store, result.animation, operation)
    reopened = s.AnimationStore(store.path.parent)
    doc = reopened.get("project", result.animation.id).document
    assert doc.curves[0].y1 == 0 and doc.clips[0].start == 500 and len(doc.keyframes) == 3
    assert reopened.get("project", first.id, first.version).document.keyframes == []
    undo = c.UndoInput(animation_id=first.id,expected_version=result.animation.version,target_version=first.version)
    restored = reopened.mutate("project","undo",undo,"undo")
    assert restored.animation.version == result.animation.version + 1
    assert reopened.get("project", first.id).document.keyframes == []
    diff = reopened.diff("project", c.DiffInput(animation_id=first.id,from_version=first.version,to_version=result.animation.version))
    assert any(item.id == "k0" and item.change == "added" for item in diff.differences)


def test_cas_conflict_duplicate_receipt_and_noop(store):
    initial = timeline(store)
    operation = {"kind":"marker_set","marker":{"id":"beat","name":"Beat","tick":1000}}
    result = edit(store, initial.animation, operation, "same")
    assert edit(store, initial.animation, operation, "same") == result
    with pytest.raises(s.AnimationError, match="already used"):
        edit(store, result.animation, operation, "same")
    with pytest.raises(s.AnimationError, match="changed"):
        edit(store, initial.animation, operation)
    noop = edit(store, result.animation, operation)
    assert not noop.changed and noop.animation.version == result.animation.version


def test_racing_writers_only_one_commits(store):
    initial = timeline(store)
    def write(index):
        try:
            return edit(store, initial.animation,{"kind":"marker_set","marker":{"id":f"m{index}","name":"Beat","tick":index}}).changed
        except s.AnimationError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(write,[1,2])) == 1


def test_cancel_after_receipt_rolls_back_and_restart_reconciles(store):
    initial = timeline(store)
    calls = []
    def cancelled():
        calls.append(1)
        return len(calls) > 1
    operation = {"kind":"marker_set","marker":{"id":"beat","name":"Beat","tick":0}}
    with pytest.raises(s.AnimationError, match="cancelled"):
        edit(store, initial.animation, operation,"cancel",cancelled=cancelled)
    assert store.get("project",initial.animation.id).animation.version == initial.animation.version
    result = edit(store,initial.animation,operation,"cancel")
    assert result.changed


@pytest.mark.parametrize("operation",[
    {"kind":"keyframe_add","keyframes":[{"id":"a","track_id":"x","tick":1,"value":0},{"id":"b","track_id":"x","tick":1,"value":1}]},
    {"kind":"keyframe_add","keyframes":[{"id":"a","track_id":"missing","tick":1,"value":0}]},
    {"kind":"keyframe_move","keyframes":[{"id":"unknown","tick":1,"value":0}]},
    {"kind":"entity_delete","section":"targets","ids":["fox"]},
    {"kind":"track_create","track":{"id":"x2","name":"Ambiguous","target_id":"fox","property":"position.x"}},
])
def test_invalid_mutations_are_atomic(store,operation):
    initial = timeline(store)
    with pytest.raises(s.AnimationError):
        edit(store,initial.animation,operation)
    assert store.get("project",initial.animation.id).animation == initial.animation


def test_tombstones_cascade_and_project_cleanup(store):
    initial = timeline(store)
    deleted = edit(store, initial.animation,{"kind":"entity_delete","section":"targets","ids":["fox"],"cascade":True})
    assert deleted.animation.counts["tracks"] == 0
    with pytest.raises(s.AnimationError,match="cannot be reused"):
        edit(store,deleted.animation,{"kind":"target_create","target":{"id":"fox","name":"New"}})
    store.delete_project("project")
    with pytest.raises(s.AnimationError,match="unavailable"):
        store.get("project",initial.animation.id)
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0


def test_duration_rejects_loss_and_curve_time_monotonicity(store):
    initial = timeline(store)
    result = edit(store, initial.animation,{"kind":"keyframe_add","keyframes":[{"id":"a","track_id":"x","tick":8000,"value":0}]})
    with pytest.raises(s.AnimationError):
        edit(store,result.animation,{"kind":"timing_modify","timing":{"duration":7000}})
    with pytest.raises(ValueError):
        c.Curve(id="curve",kind="bezier",x1=.8,x2=.2)
    with pytest.raises(ValueError):
        c.Keyframe(id="a",track_id="x",tick=True,value=0)


def test_pages_freeze_version_and_bound_thousands_of_keys(store):
    result = timeline(store)
    for offset in range(0,2048,256):
        result = edit(store,result.animation,{"kind":"keyframe_add","keyframes":[{"id":f"k{index:04}","track_id":"x","tick":index,"value":index} for index in range(offset,offset+256)]})
    page = store.page("project",c.InspectInput(animation_id=result.animation.id,version=result.animation.version,section="keyframes",track_id="x"))
    assert len(page.items) == 100 and page.next_offset == 100 and page.total == 2048
    assert len(s.canonical(page).encode()) < 24000


def test_corrupt_document_rejected(store):
    initial = timeline(store)
    with store.connect() as connection:
        connection.execute("UPDATE revisions SET document='{}' WHERE id=? AND version=?",(initial.animation.id,initial.animation.version))
    with pytest.raises(s.AnimationError,match="integrity"):
        store.get("project",initial.animation.id)


def test_complete_signed_package_activates_and_disable_removes_contributions(tmp_path):
    import hashlib
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
    from engine.dlc.package_builder import build_dlc_package_from_source
    private = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Animation author test-only publisher").digest())
    built = build_dlc_package_from_source(SOURCE, private_key=private)
    archive = tmp_path / "animation.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(c.OWNER, True)
    compiler = ContributionCompiler(service.storage_root)
    activated = compiler.compile(built_ins=BuiltinContributionSet())
    assert activated.activation_failures == ()
    assert len(activated.tools) == 20
    assert {item.spec.name for item in activated.operations} >= {"animations.apply", "animations.artifact"}
    service.set_desired_enabled(c.OWNER, False)
    disabled = compiler.compile(built_ins=BuiltinContributionSet())
    assert disabled.tools == () and disabled.operations == () and disabled.artifact_representations == ()
    service.set_desired_enabled(c.OWNER, True)
    assert compiler.compile(built_ins=BuiltinContributionSet()).activation_failures == ()


def test_fixed_representation_download_hash_survives_later_edits_and_delete(store):
    from dbfox_dlc_api import Artifact, ArtifactRepresentationRequest, ArtifactRepresentationContext
    initial = timeline(store)
    payload = c.RevisionArtifact(animation_id=initial.animation.id,project_id="project",version=initial.animation.version,
        content_hash=initial.animation.content_hash,title=initial.animation.title)
    artifact = Artifact(id="fixed",session_id="session",run_id="run",type=c.ARTIFACT_TYPE,schema_version=1,title="Fixed",payload=payload.model_dump(mode="json"))
    representation = r.AnimationRepresentation(store)
    expected = s.canonical(store.get("project",initial.animation.id).document).encode()
    changed = edit(store,initial.animation,{"kind":"marker_set","marker":{"id":"later","name":"Later","tick":10}})
    store.mutate("project","delete",c.VersionInput(animation_id=initial.animation.id,expected_version=changed.animation.version),"delete")
    result = representation.execute(artifact,ArtifactRepresentationRequest(operation="summary",parameters={}),ArtifactRepresentationContext(artifact_loader=lambda identity: None))
    assert result.source_version == str(initial.animation.version)
    stream = representation.execute(artifact,ArtifactRepresentationRequest(operation="export_json",parameters={}),ArtifactRepresentationContext(artifact_loader=lambda identity: None))
    assert b"".join(stream.chunks) == expected
    assert s.sha256(expected).hexdigest() == initial.animation.content_hash


def test_public_scene_representation_binding_uses_exact_fixed_ids_and_rejects_changed_identity(store,tmp_path):
    from dbfox_dlc_api import Artifact, ArtifactRepresentationContext
    scene_source = SOURCE.parent / "dbfox.scene" / "backend"
    scene_spec = importlib.util.spec_from_file_location("_animation_scene_source",scene_source/"__init__.py",submodule_search_locations=[str(scene_source)])
    scene_module = importlib.util.module_from_spec(scene_spec)
    sys.modules["_animation_scene_source"] = scene_module
    scene_spec.loader.exec_module(scene_module)
    sc = importlib.import_module("_animation_scene_source.contracts")
    ss = importlib.import_module("_animation_scene_source.store")
    sr = importlib.import_module("_animation_scene_source.representation")
    scene_store = ss.SceneStore(tmp_path/"scene")
    scene = scene_store.create("project",sc.CreateInput(title="Source"),"Source","scene-create")
    payload = sc.MutationInput(scene_id=scene.scene.id,expected_version=scene.scene.version,operation={"kind":"object_create","objects":[{"kind":"group","id":"stable-fox","name":"Fox","position":[3,2,1]}]})
    scene = scene_store.mutate("project",scene.scene.id,scene.scene.version,"apply",payload,"scene-edit",operation=payload.operation)
    fixed = Artifact(id="scene-artifact",session_id="session",run_id="run",type="dbfox.scene.revision",schema_version=1,title="Scene",payload=sc.RevisionArtifact(scene_id=scene.scene.id,project_id="project",version=scene.scene.version,content_hash=scene.scene.content_hash,title="Source",object_count=1,material_count=0).model_dump(mode="json"))
    representation = sr.SceneRepresentation(scene_store)
    calls = []
    class Context:
        def artifact(self,identity):
            assert identity == fixed.id
            return fixed
        def is_cancelled(self):
            return False
        def read_artifact_representation(self,identity,kind,request):
            assert identity == fixed.id and kind == "dbfox.scene.document.v1"
            calls.append(request.operation)
            return representation.execute(fixed,request,ArtifactRepresentationContext(artifact_loader=lambda identity: None))
    initial = timeline(store)
    request = c.BindInput(animation_id=initial.animation.id,expected_version=initial.animation.version,artifact_id=fixed.id,object_ids=["stable-fox"])
    bound = t.bind_scene(request,Context())
    assert bound[0].source.object_id == "stable-fox" and bound[0].position == (3,2,1)
    assert bound[0].source.version == scene.scene.version and calls == ["summary","objects_page"]
    result = store.mutate("project","bind",request,"bind",bound_targets=bound)
    assert result.animation.counts["targets"] == 2
    class StaleContext(Context):
        def read_artifact_representation(self,identity,kind,request):
            result = super().read_artifact_representation(identity,kind,request)
            return result.model_copy(update={"source_fingerprint":"0"*64})
    with pytest.raises(s.AnimationError,match="fixed version"):
        t.bind_scene(request,StaleContext())


def test_track_enable_and_clip_membership_are_incremental_and_validate_references(store):
    initial = timeline(store)
    track = store.get("project",initial.animation.id).document.tracks[0].model_dump(mode="json")
    disabled = edit(store,initial.animation,{"kind":"track_modify","track":{**track,"enabled":False}})
    assert not store.get("project",initial.animation.id).document.tracks[0].enabled
    enabled = edit(store,disabled.animation,{"kind":"track_modify","track":{**track,"name":"Renamed"}})
    clip = {"id":"clip","name":"First","track_ids":["x"],"start":0,"end":8000}
    created = edit(store,enabled.animation,{"kind":"clip_create","clip":clip})
    changed = edit(store,created.animation,{"kind":"clip_modify","clip":{**clip,"name":"Second","start":500}})
    assert store.get("project",initial.animation.id).document.clips[0].name == "Second"
    with pytest.raises(s.AnimationError):
        edit(store,changed.animation,{"kind":"clip_modify","clip":{**clip,"track_ids":["foreign-track"]}})
    assert store.get("project",initial.animation.id).animation == changed.animation


def test_unknown_storage_schema_fails_closed(store):
    with store.connect() as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(s.AnimationError,match="unsupported"):
        s.AnimationStore(store.path.parent)
