"""Independent package/runtime fault verification, separate from author domain tests."""
from __future__ import annotations

import hashlib
import io
import sqlite3
import time
import zipfile

import pytest

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, ResourceScopeRef, ToolKey
from engine.agent.repositories.artifact import ArtifactRepository
from engine.dlc import BuiltinContributionSet, ContributionCompiler
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_scene.runtime import HERE, SOURCE, SceneRuntime, run_case
from verification.bench.capabilities.dbfox_scene.schema import load_cases


@pytest.fixture
def signed_scene(tmp_path):
    with SceneRuntime(tmp_path / "runtime") as runtime:
        yield runtime


def invoke(runtime, tool, payload, ref, key, **options):
    name = runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.scene", local_name=tool))
    resolver = build_attempt_resource_resolver(snapshot=runtime.snapshot)
    return ToolRuntime(runtime.registry).invoke(tool_name=name, raw_input=payload, request=None,
        invocation_id=key, idempotency_key=key, scope_refs=(ref,), resources=resolver.resolve((ref,)), **options)


def library():
    return ResourceScopeRef(kind="dbfox.scene.library", id="independent-project", version=1)


def create(runtime):
    result = invoke(runtime, "scene_create", {"title": "Independent faults"}, library(), "create")
    assert result.status == "success"
    return result.output["scene"]


def test_complete_signed_payload_lifecycle_retains_state(signed_scene):
    runtime = signed_scene
    with zipfile.ZipFile(io.BytesIO(runtime.package.archive_bytes)) as archive:
        for relative in ("frontend/index.js", "frontend/model.js", "frontend/viewport.js", "frontend/vendor/three.js", "backend/primitives.json"):
            assert archive.read(relative) == (SOURCE / relative).read_bytes()
        assert len(archive.read("frontend/vendor/three.js")) > 700_000
    scene = create(runtime)
    compiler = ContributionCompiler(runtime.service.storage_root)
    runtime.service.set_desired_enabled("dbfox.scene", False)
    disabled = compiler.compile(built_ins=BuiltinContributionSet())
    assert not disabled.tools and not disabled.resource_providers and not disabled.resource_resolvers
    assert not disabled.context_contributors and not disabled.operations and not disabled.artifact_representations
    assert not disabled.active_dlcs
    runtime.service.set_desired_enabled("dbfox.scene", True)
    restored = compiler.compile(built_ins=BuiltinContributionSet())
    assert not restored.activation_failures
    op = restored.get_operation("dbfox.scene", "scenes.get")
    assert op is not None
    runtime.snapshot = restored
    reread = runtime.operation("independent-project", "scenes.get", {"scene_id": scene["id"]})
    assert reread["scene"]["content_hash"] == scene["content_hash"]


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
def test_runtime_rejects_before_start_without_durable_write(signed_scene, failure):
    options = {"cancellation_probe": lambda: True} if failure == "cancel" else {"deadline": time.monotonic() - 1}
    result = invoke(signed_scene, "scene_create", {"title": "Must not exist"}, library(), failure, **options)
    assert result.error_code == ("TOOL_CANCELLED" if failure == "cancel" else "TOOL_TIMEOUT")
    assert signed_scene.operation("independent-project", "scenes.list", {})["total"] == 0


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
def test_commit_then_unknown_result_reconciles_exact_receipt(signed_scene, monkeypatch, failure):
    runtime = signed_scene
    contribution = next(item for item in runtime.snapshot.tools if item.tool.name == "scene_create")
    store = contribution.tool.store
    original = store.create
    committed = False
    calls = 0

    def commit_then_lose_response(*args, **kwargs):
        nonlocal committed, calls
        result = original(*args, **kwargs)
        calls += 1
        committed = True
        if failure == "timeout":
            time.sleep(0.03)
        return result

    monkeypatch.setattr(store, "create", commit_then_lose_response)
    payload = {"title": "Committed before response loss"}
    options = {"cancellation_probe": lambda: committed} if failure == "cancel" else {"deadline": time.monotonic() + 0.02}
    result = invoke(runtime, "scene_create", payload, library(), "uncertain", **options)
    assert result.error_code == ("TOOL_CANCELLED" if failure == "cancel" else "TOOL_TIMEOUT")
    scenes = runtime.operation("independent-project", "scenes.list", {})["scenes"]
    assert len(scenes) == 1
    initial = scenes[0]
    runtime.operation("independent-project", "scenes.apply", {"scene_id": initial["id"], "expected_version": 1,
        "request_id": "later-human", "operation": {"kind": "object_create", "objects": [{"id": "fox", "kind": "mesh", "name": "Fox"}]}})
    resolver = build_attempt_resource_resolver(snapshot=runtime.snapshot)
    name = runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.scene", local_name="scene_create"))
    reconciled = ToolRuntime(runtime.registry).reconcile(tool_name=name, raw_input=payload, request=None,
        invocation_id="uncertain", idempotency_key="uncertain", scope_refs=(library(),), resources=resolver.resolve((library(),)))
    assert reconciled.status == "success" and reconciled.output["scene"]["version"] == 1
    assert reconciled.output["scene"]["content_hash"] == initial["content_hash"]
    assert calls == 1 and reconciled.artifact_drafts[0].payload["version"] == 1
    assert runtime.operation("independent-project", "scenes.get", {"scene_id": initial["id"]})["scene"]["version"] == 2


def test_signed_runtime_checks_both_current_head_fences(signed_scene):
    scene = create(signed_scene)
    signed_scene.operation("independent-project", "scenes.apply", {"scene_id": scene["id"], "expected_version": 1,
        "request_id": "human", "operation": {"kind": "object_create", "objects": [{"id": "fox", "kind": "mesh", "name": "Fox"}]}})
    for expected, frozen in ((1, 2), (2, 1)):
        ref = ResourceScopeRef(kind="dbfox.scene.document", id=scene["id"], version=frozen)
        result = invoke(signed_scene, "object_transform", {"scene_id": scene["id"], "expected_version": expected,
            "operation": {"kind": "object_transform", "transforms": [{"object_id": "fox", "position": [10, 0, 0]}]}}, ref, f"stale-{expected}")
        assert result.status == "failed" and "SCENE_STALE" in result.error
    current = signed_scene.operation("independent-project", "scenes.get", {"scene_id": scene["id"]})
    assert current["scene"]["version"] == 2 and current["objects"][0]["position"] == [0, 0, 0]


@pytest.mark.parametrize("damage", ["content", "future_schema"])
def test_restart_fails_closed_for_signed_owner_corruption(signed_scene, damage):
    scene = create(signed_scene)
    tool = next(item.tool for item in signed_scene.snapshot.tools if item.tool.name == "scene_create")
    with sqlite3.connect(tool.store.path) as db:
        if damage == "content":
            db.execute("UPDATE scene_revisions SET content_hash=?", (hashlib.sha256(b"bad-content").hexdigest(),))
        else:
            db.execute("PRAGMA user_version=999")
    if damage == "content":
        with pytest.raises(Exception, match="integrity"):
            signed_scene.operation("independent-project", "scenes.get", {"scene_id": scene["id"]})
    else:
        reloaded = ContributionCompiler(signed_scene.service.storage_root).compile(built_ins=BuiltinContributionSet())
        assert reloaded.activation_failures and not reloaded.tools and not reloaded.resource_providers


def test_formal_artifact_stays_pinned_after_human_edit_and_soft_delete(signed_scene):
    case = next(case for case in load_cases(HERE / "cases.json").cases if case.case_id == "simple-creation")
    outcome = run_case(signed_scene, case)
    assert outcome.verdict == "pass", outcome.failed_checks
    evidence = outcome.evidence
    artifact_id = evidence["artifacts"][0]["id"]
    with signed_scene.factory() as db:
        artifact = ArtifactRepository(db).get(artifact_id)
    assert artifact is not None
    scene_id = artifact.payload["scene_id"]
    project_id = evidence["project_id"]
    signed_scene.operation(project_id, "scenes.apply", {"scene_id": scene_id, "expected_version": 1,
        "request_id": "later", "operation": {"kind": "object_create", "objects": [{"id": "new", "kind": "mesh", "name": "New"}]}})
    signed_scene.operation(project_id, "scenes.delete", {"scene_id": scene_id, "expected_version": 2, "request_id": "delete"})
    provider = signed_scene.snapshot.get_artifact_representation("dbfox.scene.revision", "dbfox.scene.document.v1").provider
    context = ArtifactRepresentationContext(artifact_loader=lambda key: None)
    result = provider.execute(artifact, ArtifactRepresentationRequest(operation="objects_page"), context)
    assert result.source_version == "1" and result.payload["objects"] == []
    assert result.source_fingerprint == artifact.payload["content_hash"]
    with pytest.raises(Exception, match="Invalid Scene"):
        provider.execute(artifact, ArtifactRepresentationRequest(operation="objects_page", parameters={"version": 3}), context)
    forged = artifact.model_copy(update={"payload": {**artifact.payload, "project_id": "other-project"}})
    with pytest.raises(Exception, match="Project"):
        provider.execute(forged, ArtifactRepresentationRequest(operation="objects_page"), context)
