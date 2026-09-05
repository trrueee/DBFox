"""Independent adversarial attacks; product fixes must be made by its owner."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import subprocess
import sys
from threading import Barrier

import pytest

from dbfox_dlc_api import ResourceScopeRef, ToolKey
from engine.dlc import BuiltinContributionSet, ContributionCompiler
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_scene.runtime import SceneRuntime


@pytest.fixture
def scene_runtime(tmp_path):
    with SceneRuntime(tmp_path / "scene-adversarial") as runtime:
        yield runtime


def create(runtime):
    return runtime.operation("red-project", "scenes.create", {
        "title": "Adversarial Scene", "request_id": "red-create"})["scene"]


def store(runtime):
    return next(item.tool.store for item in runtime.snapshot.tools if item.tool.name == "scene_create")


def apply(runtime, scene, operation, request_id="red-apply", expected=None):
    return runtime.operation("red-project", "scenes.apply", {"scene_id": scene["id"],
        "expected_version": expected or scene["version"], "request_id": request_id, "operation": operation})


def tool_invoke(runtime, scene, operation, invocation_id):
    ref = ResourceScopeRef(kind="dbfox.scene.document", id=scene["id"], version=scene["version"])
    resolver = build_attempt_resource_resolver(snapshot=runtime.snapshot)
    name = runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.scene", local_name="object_create"))
    return ToolRuntime(runtime.registry).invoke(tool_name=name, raw_input={"scene_id":scene["id"],
        "expected_version":scene["version"], "operation":operation}, request=None,
        invocation_id=invocation_id, idempotency_key=invocation_id,
        scope_refs=(ref,), resources=resolver.resolve((ref,)))


@pytest.mark.parametrize("version", [True, 1.0, "1", None, 2])
def test_canonical_schema_rejects_non_integer_one(scene_runtime, version):
    scene = create(scene_runtime)
    revision = store(scene_runtime).get_revision("red-project", scene["id"])
    payload = revision.document.model_dump(mode="json")
    payload["schema_version"] = version
    with pytest.raises(ValueError):
        type(revision.document).model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_persisted_schema_coercion_cannot_pass_unchanged_hash(scene_runtime, version):
    scene = create(scene_runtime)
    with sqlite3.connect(store(scene_runtime).path) as db:
        value = json.loads(db.execute("SELECT document_json FROM scene_revisions").fetchone()[0])
        value["schema_version"] = version
        db.execute("UPDATE scene_revisions SET document_json=?", (json.dumps(value),))
    with pytest.raises(Exception, match="integrity"):
        scene_runtime.operation("red-project", "scenes.get", {"scene_id":scene["id"]})


@pytest.mark.parametrize("field,value", [
    ("visible", "false"), ("visible", 0), ("position", [True, 0, 0]),
    ("position", ["1", 0, 0]), ("position", None), ("url", "https://example.invalid/model.glb"),
])
def test_typed_mutation_rejects_coercion_unknown_and_null(scene_runtime, field, value):
    scene = create(scene_runtime)
    node = {"id":"red-mesh", "kind":"mesh", "name":"Red Mesh", field:value}
    with pytest.raises(ValueError):
        apply(scene_runtime, scene, {"kind":"object_create", "objects":[node]})
    current = scene_runtime.operation("red-project", "scenes.get", {"scene_id":scene["id"]})
    assert current["scene"]["version"] == 1 and not current["objects"]


@pytest.mark.parametrize("column,value", [("object_count", 9000), ("title", "Forged title"), ("status", "deleted")])
def test_revision_summary_cannot_diverge_from_canonical_document(scene_runtime, column, value):
    scene = create(scene_runtime)
    assert column in {"object_count", "title", "status"}
    with sqlite3.connect(store(scene_runtime).path) as db:
        db.execute(f"UPDATE scene_revisions SET {column}=?", (value,))
    with pytest.raises(Exception, match="integrity"):
        store(scene_runtime).get_revision("red-project", scene["id"])


def test_receipt_failure_rolls_back_revision_head_and_reserved_id(scene_runtime):
    scene = create(scene_runtime)
    database = store(scene_runtime).path
    with sqlite3.connect(database) as db:
        db.execute("CREATE TRIGGER red_fail_receipt BEFORE INSERT ON operation_receipts BEGIN SELECT RAISE(ABORT,'red fault at receipt'); END")
    operation = {"kind":"object_create", "objects":[{"id":"retry-id", "kind":"mesh", "name":"Retry"}]}
    with pytest.raises(Exception):
        apply(scene_runtime, scene, operation)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT head_version FROM scenes").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM scene_revisions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM entity_ids WHERE id='retry-id'").fetchone()[0] == 0
        db.execute("DROP TRIGGER red_fail_receipt")
    assert apply(scene_runtime, scene, operation)["scene"]["version"] == 2


def test_concurrent_typed_human_and_registered_tool_have_one_winner(scene_runtime):
    scene = create(scene_runtime)
    barrier = Barrier(2)
    def human():
        barrier.wait()
        try:
            result = apply(scene_runtime, scene, {"kind":"object_create", "objects":[{"id":"human", "kind":"mesh", "name":"Human"}]})
            return result["changed"], ""
        except Exception as error:
            return False, str(error)
    def agent():
        barrier.wait()
        result = tool_invoke(scene_runtime, scene,
            {"kind":"object_create", "objects":[{"id":"agent", "kind":"mesh", "name":"Agent"}]}, "concurrent-agent")
        return result.status == "success", str(result.error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(human), pool.submit(agent)]
        results = [future.result() for future in futures]
    assert sum(success for success, _ in results) == 1, results
    assert "changed" in next(message.lower() for success, message in results if not success) or "STALE" in str(results)
    current = scene_runtime.operation("red-project", "scenes.get", {"scene_id":scene["id"]})
    assert current["scene"]["version"] == 2 and len(current["objects"]) == 1


def test_receipt_identity_payload_reuse_does_not_mutate(scene_runtime):
    scene = create(scene_runtime)
    one = {"kind":"object_create", "objects":[{"id":"first", "kind":"mesh", "name":"First"}]}
    first = apply(scene_runtime, scene, one, request_id="same-id")
    assert apply(scene_runtime, scene, one, request_id="same-id") == first
    with pytest.raises(Exception, match="different input"):
        apply(scene_runtime, scene, {"kind":"object_create", "objects":[{"id":"forged", "kind":"mesh", "name":"Forged"}]}, request_id="same-id")
    assert scene_runtime.operation("red-project", "scenes.get", {"scene_id":scene["id"]})["scene"]["version"] == 2


def test_tool_cannot_select_an_unbound_scene(scene_runtime):
    scene = create(scene_runtime)
    other = scene_runtime.operation("other-project", "scenes.create", {"title":"Other", "request_id":"other"})["scene"]
    ref = ResourceScopeRef(kind="dbfox.scene.document", id=scene["id"], version=1)
    name = scene_runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.scene", local_name="object_create"))
    result = ToolRuntime(scene_runtime.registry).invoke(tool_name=name, raw_input={"scene_id":other["id"],
        "expected_version":1, "operation":{"kind":"object_create","objects":[{"id":"forged","kind":"mesh","name":"Forged"}]}},
        request=None, invocation_id="private-selector", idempotency_key="private-selector", scope_refs=(ref,),
        resources=build_attempt_resource_resolver(snapshot=scene_runtime.snapshot).resolve((ref,)))
    assert result.status == "failed"
    assert scene_runtime.operation("other-project", "scenes.get", {"scene_id":other["id"]})["scene"]["version"] == 1


@pytest.mark.parametrize("damage", ["head_missing", "head_behind", "head_status", "parent_missing", "parent_skipped", "parent_at_v1", "list_count"])
def test_head_parent_and_library_corruption_fail_closed(scene_runtime, damage):
    scene=create(scene_runtime)
    apply(scene_runtime,scene,{"kind":"object_create","objects":[{"id":"one","kind":"mesh","name":"One"}]})
    with sqlite3.connect(store(scene_runtime).path) as db:
        if damage=="head_missing":db.execute("UPDATE scenes SET head_version=99")
        if damage=="head_behind":db.execute("UPDATE scenes SET head_version=1")
        if damage=="head_status":db.execute("UPDATE scenes SET status='deleted'")
        if damage=="parent_missing":db.execute("DELETE FROM scene_revisions WHERE version=1")
        if damage=="parent_skipped":db.execute("UPDATE scene_revisions SET parent_version=0 WHERE version=2")
        if damage=="parent_at_v1":db.execute("UPDATE scene_revisions SET parent_version=1 WHERE version=1")
        if damage=="list_count":db.execute("UPDATE scene_revisions SET material_count=55 WHERE version=2")
    with pytest.raises(Exception,match="integrity"):
        if damage=="list_count":scene_runtime.operation("red-project","scenes.list",{})
        else:store(scene_runtime).get_revision("red-project",scene["id"],1 if damage=="parent_at_v1" else None)


def test_history_resolution_after_delete_remains_readonly(scene_runtime):
    scene=create(scene_runtime)
    scene_runtime.operation("red-project","scenes.delete",{"scene_id":scene["id"],"expected_version":1,"request_id":"delete"})
    old=store(scene_runtime).resolve_scene(ResourceScopeRef(kind="dbfox.scene.document",id=scene["id"],version=1))
    assert old.scene.status=="active" and old.scene.version==1
    result=tool_invoke(scene_runtime,scene,{"kind":"object_create","objects":[{"id":"late","kind":"mesh","name":"Late"}]},"late")
    assert result.status=="failed" and "DELETED" in result.error
    assert store(scene_runtime).get_revision("red-project",scene["id"]).scene.version==2


def test_process_death_inside_product_transaction_rolls_back(scene_runtime):
    scene=create(scene_runtime)
    script = '''
import os,sys
from dbfox_dlc_api import DlcOperationContext
from engine.dlc import ContributionCompiler, BuiltinContributionSet
from pathlib import Path
snapshot=ContributionCompiler(Path(sys.argv[1])).compile(built_ins=BuiltinContributionSet())
tool=next(item.tool for item in snapshot.tools if item.owner_id=='dbfox.scene' and item.tool.name=='scene_create')
tool.store._save_receipt=lambda *args:os._exit(73)
spec=snapshot.get_operation('dbfox.scene','scenes.apply').spec
payload=spec.input_model.model_validate({'scene_id':sys.argv[2],'expected_version':1,'request_id':'crash-write','operation':{'kind':'object_create','objects':[{'id':'survives-retry','kind':'mesh','name':'Retry'}]}})
spec.handler(payload,DlcOperationContext(dlc_id='dbfox.scene',operation_name='scenes.apply',project_id='red-project'))
'''
    child=subprocess.run([sys.executable,"-c",script,str(scene_runtime.service.storage_root),scene["id"]],capture_output=True,text=True,timeout=30)
    assert child.returncode==73,child.stderr
    current=scene_runtime.operation("red-project","scenes.get",{"scene_id":scene["id"]})
    assert current["scene"]["version"]==1 and current["objects"]==[]
    assert apply(scene_runtime,scene,{"kind":"object_create","objects":[{"id":"survives-retry","kind":"mesh","name":"Retry"}]},request_id="crash-write")["scene"]["version"]==2


def test_cancel_after_revision_insert_before_commit_removes_all_writes(scene_runtime,monkeypatch):
    scene=create(scene_runtime)
    owner_store=store(scene_runtime)
    original=owner_store._save_revision
    cancelled=False
    def cancel_after_insert(*args,**kwargs):
        nonlocal cancelled
        original(*args,**kwargs)
        cancelled=True
    monkeypatch.setattr(owner_store,"_save_revision",cancel_after_insert)
    spec=scene_runtime.snapshot.get_operation("dbfox.scene","scenes.apply").spec
    payload=spec.input_model.model_validate({"scene_id":scene["id"],"expected_version":1,"request_id":"cancel-in-transaction",
        "operation":{"kind":"object_create","objects":[{"id":"cancelled","kind":"mesh","name":"Cancelled"}]}})
    with pytest.raises(ValueError,match="cancelled before commit"):
        owner_store.mutate("red-project",scene["id"],1,"apply",payload,"cancel-in-transaction",operation=payload.operation,cancelled=lambda:cancelled)
    with sqlite3.connect(owner_store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM scene_revisions").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM operation_receipts WHERE invocation_id='cancel-in-transaction'").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM entity_ids WHERE id='cancelled'").fetchone()[0]==0


def test_batch_budget_rejects_before_any_entity_commit(scene_runtime):
    scene=create(scene_runtime)
    with pytest.raises(ValueError):
        apply(scene_runtime,scene,{"kind":"object_create","objects":[{"id":f"n{i}","kind":"mesh","name":"Budget"} for i in range(501)]})
    assert scene_runtime.operation("red-project","scenes.get",{"scene_id":scene["id"]})["scene"]["version"]==1


def test_mutation_response_loss_then_delete_reconciles_original_version(scene_runtime,monkeypatch):
    scene=create(scene_runtime)
    owner_store=store(scene_runtime)
    original=owner_store.mutate
    committed=False
    calls=0
    def lose(*args,**kwargs):
        nonlocal committed,calls
        result=original(*args,**kwargs)
        calls+=1
        committed=True
        return result
    monkeypatch.setattr(owner_store,"mutate",lose)
    ref=ResourceScopeRef(kind="dbfox.scene.document",id=scene["id"],version=1)
    payload={"scene_id":scene["id"],"expected_version":1,"operation":{"kind":"object_create","objects":[{"id":"receipt-object","kind":"mesh","name":"Receipt"}]}}
    resolver=build_attempt_resource_resolver(snapshot=scene_runtime.snapshot)
    name=scene_runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.scene",local_name="object_create"))
    kwargs=dict(tool_name=name,raw_input=payload,request=None,invocation_id="lost-mutation",idempotency_key="lost-mutation",scope_refs=(ref,),resources=resolver.resolve((ref,)))
    result=ToolRuntime(scene_runtime.registry).invoke(**kwargs,cancellation_probe=lambda:committed)
    assert result.error_code=="TOOL_CANCELLED" and calls==1
    monkeypatch.setattr(owner_store,"mutate",original)
    scene_runtime.operation("red-project","scenes.delete",{"scene_id":scene["id"],"expected_version":2,"request_id":"delete-after-loss"})
    kwargs["resources"]=resolver.resolve((ref,))
    reconciled=ToolRuntime(scene_runtime.registry).reconcile(**kwargs)
    assert reconciled.status=="success" and reconciled.output["scene"]["version"]==2
    assert reconciled.artifact_drafts[0].payload["version"]==2 and calls==1
    assert owner_store.get_revision("red-project",scene["id"]).scene.version==3


def test_disabled_owner_cannot_resolve_stored_reference_in_new_snapshot(scene_runtime):
    scene=create(scene_runtime)
    ref=ResourceScopeRef(kind="dbfox.scene.document",id=scene["id"],version=1)
    scene_runtime.service.set_desired_enabled("dbfox.scene",False)
    disabled=ContributionCompiler(scene_runtime.service.storage_root).compile(built_ins=BuiltinContributionSet())
    with pytest.raises(KeyError,match="No resolver is registered"):
        build_attempt_resource_resolver(snapshot=disabled).resolve((ref,))
    scene_runtime.service.set_desired_enabled("dbfox.scene",True)
    restored=ContributionCompiler(scene_runtime.service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert build_attempt_resource_resolver(snapshot=restored).resolve((ref,))
    assert store(scene_runtime).get_revision("red-project",scene["id"]).scene.version==1


def test_oversized_durable_document_rejected_before_normalization(scene_runtime):
    scene=create(scene_runtime)
    with sqlite3.connect(store(scene_runtime).path) as db:
        value=db.execute("SELECT document_json FROM scene_revisions").fetchone()[0]
        db.execute("UPDATE scene_revisions SET document_json=?",(" "*(8*1024*1024)+value,))
    with pytest.raises(Exception,match="integrity"):
        scene_runtime.operation("red-project","scenes.get",{"scene_id":scene["id"]})
