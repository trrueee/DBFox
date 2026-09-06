"""Game author conformance; engine/installed desktop evidence is separate."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import hashlib
import shutil
import sqlite3
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import Artifact, ArtifactRepresentationContext, ArtifactRepresentationRequest, ArtifactRepresentationResult, DlcOperationContext, DlcRuntimeInfo, RequestedResourceRef, ResourceScopeRef, ToolInputError, ToolKey
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.host import DefaultBackendExtensionHost, StagedDlcContributions
from engine.dlc.manifest import DlcManifest
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import active_runtime_snapshot, authorize_project_resources, build_dlc_action_runs_host, build_product_run_loop, build_product_tool_registry, set_active_runtime_snapshot
from engine.tools.runtime import ToolRegistry, ToolRuntime
from engine.tools.runtime.registry import provider_tool_name
from engine.tools.runtime.resource_authority import bind_tool_invocation_resources
from engine.tools.materialization import materialize_tools
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

SOURCE = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.game"
PROJECT = "game-test-project"


@pytest.fixture(scope="module")
def modules():
    name = "_game_conformance"
    spec = importlib.util.spec_from_file_location(name, SOURCE / "backend" / "__init__.py", submodule_search_locations=[str(SOURCE / "backend")])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".store")


@pytest.fixture
def store(tmp_path, modules):
    return modules.Store(tmp_path / "game")


@pytest.fixture
def harness(tmp_path, modules):
    manifest = json.loads((SOURCE / "manifest.template.json").read_text(encoding="utf-8"))
    manifest["publisherKey"] = base64.b64encode(bytes(32)).decode("ascii")
    staged = StagedDlcContributions(dlc_id="dbfox.game", package_digest="f" * 64, manifest=DlcManifest.model_validate(manifest), runtime_info=DlcRuntimeInfo(dlc_id="dbfox.game", package_version="0.1.0", package_digest="f" * 64, data_path=tmp_path / "state"))
    contributions = importlib.import_module(modules.__package__ + ".contributions")
    contributions.register(DefaultBackendExtensionHost(staged))
    registry = ToolRegistry()
    for tool in staged.tools:
        registry.register(tool, owner="dbfox.game")
    return staged, ToolRuntime(registry)


def invoke(harness, name, payload, *, frozen=None, identity=None):
    staged, runtime = harness
    tool = next(item for item in staged.tools if item.name == name)
    data = tool.input_model.model_validate(payload)
    refs = frozen or bind_tool_invocation_resources(tool, data.model_dump(mode="json", exclude_none=True), discovered=staged.resource_providers[0](PROJECT))
    resolved = {ref.canonical(): staged.tools[0].store.resolve(ref) for ref in refs}
    invocation = identity or str(uuid4())
    return runtime.invoke(tool_name=provider_tool_name("dbfox.game", name), raw_input=payload, request=None, idempotency_key=invocation, invocation_id=invocation, scope_refs=refs, resources=resolved), refs


def create(store, modules, key=None):
    return store.create(PROJECT, "human", key or str(uuid4()), modules.c.CreateInput(title="Fox survival", expected_library_version=store.library(PROJECT).version))


def apply(store, modules, summary, operations, key=None, actor="human", guard=lambda: None):
    value = modules.c.ApplyInput.model_validate({"game_id": summary.id, "expected_version": summary.version, "operations": operations})
    return store.mutate(PROJECT, actor, key or str(uuid4()), "apply", value, guard)


def add_fox(store, modules, created):
    scene = store.get(PROJECT, created.game.id).game.initial_scene_id
    return apply(store, modules, created.game, [{"kind": "entity_create", "entities": [{"scene_id": {"id": scene}, "name": "Fox", "ref": "fox", "tags": ["player"], "components": [{"kind": "transform"}, {"kind": "visual", "shape": "fox"}, {"kind": "body"}, {"kind": "health"}]}]}, {"kind": "behavior_create", "behavior": {"kind": "player_control", "entity_id": {"ref": "fox"}}}])


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None, 0, -1])
def test_strict_versions_and_null(modules, value):
    with pytest.raises(ValueError):
        modules.c.CreateInput.model_validate({"title": "Bad", "expected_library_version": value})
    with pytest.raises(ValueError):
        modules.c.EntityDraft.model_validate({"scene_id": {"id": str(uuid4())}, "name": "Bad", "enabled": None})


def test_generic_refs_schema_and_canonical_rejection(modules):
    c = modules.c
    assert c.ApplyInput.model_json_schema()["properties"]["operations"]
    with pytest.raises(ValueError):
        c.Rule.model_validate({"id": str(uuid4()), "spec": {"scene_id": str(uuid4()), "name": "bad", "trigger": {"kind": "health_compare", "entity_id": "not-an-id"}, "actions": [{"kind": "finish", "result": "won"}]}})
    with pytest.raises(ValueError):
        c.GameProject.model_validate({"id": str(uuid4()), "title": "bad", "schema_version": True, "initial_scene_id": str(uuid4()), "scenes": []})


def test_native_strict_optional_null_normalization(harness, modules):
    registry = ToolRegistry()
    for tool in harness[0].tools:
        registry.register(tool, owner="dbfox.game")
    materialized = materialize_tools(registry, execution_mode="user_requested_read", available_resource_kinds={"dbfox.game.project", "dbfox.game.library"})
    schema = materialized.require(provider_tool_name("dbfox.game", "game_inspect")).input_schema
    assert set(schema["required"]) == set(schema["properties"])
    params = modules.c.GetInput.model_validate({"game_id": str(uuid4()), "version": None, "section": "summary", "scene_id": None, "entity_id": None, "asset_id": None, "offset": 0, "limit": 20})
    assert "version" not in params.data() and "asset_id" not in params.data()
    visual = modules.c.Visual[modules.c.Selector].model_validate({"kind": "visual", "shape": "rect", "asset_id": None, "color": "#ffffff", "opacity": 1, "depth": 0})
    assert "asset_id" not in visual.data()
    with pytest.raises(ValueError):
        modules.c.GetInput.model_validate({"game_id": str(uuid4()), "offset": None})
    with pytest.raises(ValueError):
        modules.c.GetInput.model_validate({"game_id": str(uuid4()), "unknown": None})


def test_all_materialized_game_tools_complete_fields_and_null_contract(harness, modules):
    c = modules.c
    game_id, scene_id, entity_id, component_id = (str(uuid4()) for _ in range(4))
    base = {"game_id": game_id, "expected_version": 1}
    samples = {
        "game_create": {"title": "Native", "expected_library_version": 1},
        "game_modify": {**base, "operations": [{"kind": "entity_modify", "entity_id": {"id": entity_id}}, {"kind": "scene_create", "scene": {"name": "Scene"}}]},
        "game_inspect": {"game_id": game_id},
        "game_diff": {"game_id": game_id, "from_version": 1, "to_version": 1},
        "game_undo": {**base, "target_version": 1},
        "game_delete": base,
        "game_export": base,
        "scene_create": {**base, "operation": {"kind": "scene_create", "scene": {"name": "Scene"}}},
        "entity_create": {**base, "operation": {"kind": "entity_create", "entities": [{"scene_id": {"id": scene_id}, "name": "Fox"}]}},
        "entity_delete": {**base, "operation": {"kind": "entity_delete", "entity_ids": [{"id": entity_id}]}},
        "component_add": {**base, "operation": {"kind": "component_add", "entity_id": {"id": entity_id}, "component": {"kind": "visual"}}},
        "component_modify": {**base, "operation": {"kind": "component_modify", "component_id": {"id": component_id}, "component": {"kind": "visual"}}},
        "behavior_create": {**base, "operation": {"kind": "behavior_create", "behavior": {"kind": "player_control", "entity_id": {"id": entity_id}}}},
        "rule_create": {**base, "operation": {"kind": "rule_create", "rule": {"scene_id": {"id": scene_id}, "name": "Win", "trigger": {"kind": "elapsed_tick", "at_tick": 3600}, "actions": [{"kind": "finish", "result": "won"}]}}},
        "variable_create": {**base, "operation": {"kind": "variable_create", "variable": {"name": "score", "value_type": "int", "initial": 0}}},
        "playtest": base,
        "asset_import": {**base, "name": "Sprite", "source_artifact_id": "source", "frame_id": "frame", "rect": {"x": 0, "y": 0, "width": 32, "height": 32}},
    }
    registry = ToolRegistry()
    for tool in harness[0].tools:
        registry.register(tool, owner="dbfox.game")
    materialized = materialize_tools(registry, execution_mode="user_requested_read", available_resource_kinds={c.RESOURCE, c.LIBRARY})
    def strict_objects(schema):
        if isinstance(schema, dict):
            if "properties" in schema:
                assert set(schema.get("required", [])) == set(schema["properties"])
            for value in schema.values():
                strict_objects(value)
        elif isinstance(schema, list):
            for value in schema:
                strict_objects(value)
    def fields(model, path=()):
        if isinstance(model, c.Contract):
            for name, field in type(model).model_fields.items():
                value = getattr(model, name)
                yield (*path, name), not field.is_required() and field.default is None
                yield from fields(value, (*path, name))
        elif isinstance(model, list):
            for index, value in enumerate(model):
                yield from fields(value, (*path, index))
    seen = 0
    for tool in harness[0].tools:
        model = tool.input_model.model_validate(samples[tool.name])
        complete = model.model_dump(mode="json", exclude_none=False)
        schema = materialized.require(provider_tool_name(c.OWNER, tool.name)).input_schema
        strict_objects(schema)
        assert tool.input_model.model_validate(complete).data() == model.data()
        for path, nullable_default in fields(model):
            provided = json.loads(json.dumps(complete))
            omitted = json.loads(json.dumps(complete))
            left, right = provided, omitted
            for component in path[:-1]:
                left, right = left[component], right[component]
            left[path[-1]] = None
            del right[path[-1]]
            if nullable_default:
                assert tool.input_model.model_validate(provided).data() == tool.input_model.model_validate(omitted).data()
            else:
                with pytest.raises(ValueError):
                    tool.input_model.model_validate(provided)
            seen += 1
    assert seen >= 150


def test_canonical_null_remains_invalid(store, modules):
    made = add_fox(store, modules, create(store, modules))
    raw = store.get(PROJECT, made.game.id).game.data()
    raw["entities"][0]["components"][1]["spec"]["asset_id"] = None
    with pytest.raises(ValueError, match="cannot contain null"):
        modules.c.GameProject.model_validate(raw)


def test_stable_ids_batch_rollback_and_controller_conflict(store, modules):
    created = create(store, modules)
    fox = add_fox(store, modules, created)
    before = store.get(PROJECT, fox.game.id)
    identity = fox.created_refs["fox"]
    with pytest.raises(ValueError, match="one enabled movement"):
        apply(store, modules, fox.game, [{"kind": "game_rename", "title": "Must roll back"}, {"kind": "behavior_create", "behavior": {"kind": "wander", "entity_id": {"id": identity}}}])
    assert store.get(PROJECT, fox.game.id) == before
    shifted = apply(store, modules, fox.game, [{"kind": "entities_transform", "entity_ids": [{"id": identity}], "dx": 24}])
    changed = store.get(PROJECT, fox.game.id)
    assert changed.game.entities[0].id == identity
    assert changed.game.entities[0].components[0].id == before.game.entities[0].components[0].id
    assert changed.game.entities[0].components[0].spec.x == 88
    with pytest.raises(ValueError, match="changed"):
        apply(store, modules, fox.game, [{"kind": "game_rename", "title": "Stale"}])
    assert shifted.game.version == before.version + 1


def test_exact_receipts_noop_actor_and_restart(store, modules):
    made = create(store, modules)
    key = str(uuid4())
    request = modules.c.ApplyInput(game_id=made.game.id, expected_version=1, operations=[modules.c.Rename(kind="game_rename", title=made.game.title)])
    noop = store.mutate(PROJECT, "human", key, "apply", request)
    assert not noop.changed and noop.game.version == 1
    edit = apply(store, modules, made.game, [{"kind": "game_rename", "title": "Agent changed"}], key=key, actor="agent")
    assert edit.changed and edit.game.version == 2
    reopened = modules.Store(store.path.parent)
    assert reopened.mutate(PROJECT, "human", key, "apply", request) == noop
    with pytest.raises(ValueError, match="different input"):
        reopened.receipt(PROJECT, "agent", key, "apply", request)
    with pytest.raises(ValueError, match="different input"):
        reopened.mutate(PROJECT, "human", key, "apply", modules.c.ApplyInput(game_id=made.game.id, expected_version=2, operations=[modules.c.Rename(kind="game_rename", title="Another")]))


def test_delete_restore_undo_repeated_hash_and_library_history(store, modules):
    made = create(store, modules)
    fox = add_fox(store, modules, made)
    deleted = store.mutate(PROJECT, "agent", str(uuid4()), "delete", modules.c.VersionInput(game_id=fox.game.id, expected_version=fox.game.version))
    assert deleted.game.deleted
    with pytest.raises(ValueError, match="deleted"):
        apply(store, modules, deleted.game, [{"kind": "game_rename", "title": "No"}])
    restored = store.mutate(PROJECT, "human", str(uuid4()), "undo", modules.c.UndoInput(game_id=fox.game.id, expected_version=deleted.game.version, target_version=fox.game.version))
    assert restored.game.version == 4 and restored.game.content_hash == fox.game.content_hash
    assert not restored.game.deleted
    _, old = store.list_games(PROJECT, made.library_version)
    assert old[0].version == 1
    _, tombstones = store.list_games(PROJECT, deleted.library_version)
    assert tombstones[0].deleted


def test_concurrent_cas_and_cancel_after_receipt_roll_back(store, modules):
    made = create(store, modules)
    def race(title):
        try:
            return apply(modules.Store(store.path.parent), modules, made.game, [{"kind": "game_rename", "title": title}])
        except ValueError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, ("first", "second")))
    assert sum(not isinstance(item, Exception) for item in results) == 1
    current = store.get(PROJECT, made.game.id)
    calls = 0
    key = str(uuid4())
    def guard():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError("cancelled after receipt")
    with pytest.raises(ValueError, match="cancelled after receipt"):
        apply(store, modules, current.summary(), [{"kind": "game_rename", "title": "Cancelled"}], key=key, guard=guard)
    assert store.get(PROJECT, made.game.id) == current
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM receipts WHERE request_key=?", (key,)).fetchone()[0] == 0


def test_asset_fixed_revision_pages_deletion_and_corruption(store, modules):
    made = create(store, modules)
    rgba = bytes(range(256)) * 256
    uploaded = store.mutate(PROJECT, "human", str(uuid4()), "upload", modules.c.UploadInput(game_id=made.game.id, expected_version=1, name="tile", width=128, height=128, rgba_base64=base64.b64encode(rgba).decode("ascii")))
    version = store.get(PROJECT, made.game.id)
    asset_id = uploaded.created_refs["asset"]
    views = importlib.import_module(modules.__package__ + ".views")
    offset, chunks = 0, []
    while offset < len(rgba):
        result = views.read(store, version, modules.c.GetInput(game_id=made.game.id, version=version.version, section="asset_bytes", asset_id=asset_id, offset=offset, limit=16384))
        assert len(modules.c.encoded(result.data())) <= 32768
        chunks.append(base64.b64decode(result.metadata["rgba_base64"]))
        offset = result.next_offset
    assert b"".join(chunks) == rgba
    apply(store, modules, uploaded.game, [{"kind": "object_remove", "object_id": {"id": asset_id}}])
    assert store.asset_bytes(store.get(PROJECT, made.game.id, version.version), asset_id) == rgba
    with pytest.raises(ValueError, match="does not belong"):
        store.asset_bytes(store.get(PROJECT, made.game.id), asset_id)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE blobs SET payload=?", (b"broken",))
    with pytest.raises(ValueError, match="integrity"):
        store.get(PROJECT, made.game.id, version.version)


def test_quota_and_receipt_corruption_fail_closed(store, modules, monkeypatch):
    made = create(store, modules)
    monkeypatch.setattr(modules.c, "MAX_HISTORY", 1)
    with pytest.raises(ValueError, match="256 MiB"):
        apply(store, modules, made.game, [{"kind": "game_rename", "title": "Too much"}])
    assert store.get(PROJECT, made.game.id).version == 1
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE receipts SET payload=?", (b"{}",))
        key = db.execute("SELECT request_key FROM receipts").fetchone()[0]
    with pytest.raises(ValueError, match="integrity"):
        store.receipt(PROJECT, "human", key, "create", modules.c.CreateInput(title="Fox survival", expected_library_version=1))


def test_registration_real_tool_runtime_frozen_fence_and_human_sync(harness):
    staged, _ = harness
    assert len(staged.tools) == 17 and len(staged.operations) == 16
    for spec in staged.operations:
        spec.input_model.model_json_schema()
        spec.output_model.model_json_schema()
    created, library_refs = invoke(harness, "game_create", {"title": "Runtime game", "expected_library_version": 1})
    assert created.status == "success", created.error
    assert created.artifact_drafts[0].resource_refs == library_refs
    game = created.output["game"]
    inspected, refs = invoke(harness, "game_inspect", {"game_id": game["id"], "section": "summary"})
    assert inspected.status == "success", inspected.error
    scene = inspected.output["metadata"]["initial_scene_id"]
    entity, _ = invoke(harness, "entity_create", {"game_id": game["id"], "expected_version": 1, "operation": {"kind": "entity_create", "entities": [{"scene_id": {"id": scene}, "name": "Fox"}]}})
    assert entity.status == "success", entity.error
    stale, _ = invoke(harness, "game_modify", {"game_id": game["id"], "expected_version": 1, "operations": [{"kind": "game_rename", "title": "Stale"}]}, frozen=refs)
    assert stale.status == "failed" and "STALE_VERSION" in stale.error
    operation = next(item for item in staged.operations if item.name == "games.apply")
    human = operation.handler(operation.input_model.model_validate({"game_id": game["id"], "expected_version": 2, "request_id": str(uuid4()), "operations": [{"kind": "game_rename", "title": "Human"}]}), DlcOperationContext(dlc_id="dbfox.game", operation_name="games.apply", project_id=PROJECT))
    assert human.game.version == 3
    read, _ = invoke(harness, "game_inspect", {"game_id": game["id"]})
    assert read.output["game"]["title"] == "Human"
    projection = staged.tools[0].project_observation(status="success", output=created.output, artifacts=())
    assert projection.summary and projection.facts["game"]["version"] == 1


def attach(harness, modules, client=None, counter=1):
    bridge = harness[0].tools[0].bridge
    attached = bridge.attach(modules.c.AttachInput(client_id=client or str(uuid4()), registration_counter=counter, package_digest="f" * 64, engine=modules.c.ENGINE, available=True))
    return modules.c.Lease.model_validate(attached.model_dump(exclude={"available", "lease_ms"}))


def claim(harness, lease):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        polled = harness[0].tools[0].bridge.next(lease)
        if polled.request is not None:
            return polled.request
        time.sleep(.005)
    raise AssertionError("No Phaser request submitted")


def simulation_boundary(modules, request):
    """Protocol fixture only; this deliberately does not claim real Phaser execution."""
    game = request.snapshot["document"]
    return modules.c.SimulationReport(engine=modules.c.ENGINE, seed=request.input.seed, ticks_requested=request.input.ticks, ticks_completed=request.input.ticks, scene_tick=request.input.ticks, scene_id=game["initial_scene_id"], outcome="exhausted", reason="Protocol fixture completed", event_count=0, events_truncated=False, events=[], entities=[], variables={item["id"]: item["initial"] for item in game["variables"]})


def completion(modules, lease, request, report):
    return modules.c.CompleteInput.model_validate({**lease.data(), **{key: value for key, value in request.data().items() if key in modules.c.Proof.model_fields}, "package_digest": "f" * 64, "report": report.data()})


def test_bridge_real_runtime_claim_bound_report_and_historical_representation(harness, modules):
    created, _ = invoke(harness, "game_create", {"title": "Playtest", "expected_library_version": 1})
    identity = created.output["game"]["id"]
    lease = attach(harness, modules)
    bridge = harness[0].tools[0].bridge
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(invoke, harness, "playtest", {"game_id": identity, "expected_version": 1, "ticks": 120, "seed": 42})
        request = claim(harness, lease)
        report = simulation_boundary(modules, request)
        payload = completion(modules, lease, request, report)
        with pytest.raises(ValueError, match="proof"):
            bridge.complete(payload.model_copy(update={"source_hash": "0" * 64}))
        assert bridge.next(lease).status == "idle"
        assert bridge.complete(payload).accepted
        outcome, refs = future.result(2)
    assert outcome.status == "success", outcome.error
    assert outcome.output["report"]["ticks_completed"] == 120
    assert outcome.artifact_drafts[0].resource_refs == refs
    assert harness[0].tools[0].store.get(PROJECT, identity).version == 1
    invoke(harness, "game_modify", {"game_id": identity, "expected_version": 1, "operations": [{"kind": "game_rename", "title": "Later"}]})
    representation = importlib.import_module(modules.__package__ + ".representation")
    artifact = Artifact(id=str(uuid4()), run_id="test-run", session_id="test-session", turn_id="test-turn", type=modules.c.REPORT_ARTIFACT, schema_version=1, title="Playtest", payload=outcome.artifact_drafts[0].payload, resource_refs=refs)
    result = representation.ReportRepresentation(harness[0].tools[0].store).execute(artifact, ArtifactRepresentationRequest(operation="page", parameters={"section": "summary"}), ArtifactRepresentationContext(artifact_loader=lambda _id: None))
    assert result.payload["game"]["version"] == 1 and result.payload["metadata"]["report"]["seed"] == 42


@pytest.mark.parametrize("change", ["same_game", "other_game", "detach", "cancel", "timeout"])
def test_bridge_stale_cancel_timeout_and_other_game_isolation(harness, modules, change):
    made, _ = invoke(harness, "game_create", {"title": "Source", "expected_library_version": 1})
    identity = made.output["game"]["id"]
    lease = attach(harness, modules)
    bridge = harness[0].tools[0].bridge
    cancelled = threading.Event()
    store = harness[0].tools[0].store
    request = modules.c.PlaytestInput(game_id=identity, expected_version=1, ticks=2)
    source = store.get(PROJECT, identity)
    task = bridge.request(source, request, str(uuid4()), {"document": source.game.data()}, lambda: None)
    claimed = claim(harness, lease)
    if change == "same_game":
        apply(store, modules, source.summary(), [{"kind": "game_rename", "title": "Changed"}])
    elif change == "other_game":
        create(store, modules)
    elif change == "detach":
        bridge.detach(lease)
    elif change == "cancel":
        cancelled.set()
    elif change == "timeout":
        task.deadline = time.monotonic() - 1
    def guard():
        if cancelled.is_set():
            raise ValueError("cancelled")
        bridge.check(task)
    try:
        if change in {"detach", "timeout"}:
            with pytest.raises(ValueError):
                bridge.complete(completion(modules, lease, claimed, simulation_boundary(modules, claimed)))
        else:
            bridge.complete(completion(modules, lease, claimed, simulation_boundary(modules, claimed)))
        if change == "other_game":
            report = bridge.wait(task, guard)
            assert store.save_report(PROJECT, task.invocation_id, request, report, guard).report is not None
        else:
            with pytest.raises(ValueError):
                report = bridge.wait(task, guard)
                store.save_report(PROJECT, task.invocation_id, request, report, guard)
            with sqlite3.connect(store.path) as db:
                assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    finally:
        bridge.finish(task)


def test_action_reservation_unknown_never_replays_and_budget_reserved(store, modules):
    made = create(store, modules)
    key = str(uuid4())
    request = modules.c.VersionInput(game_id=made.game.id, expected_version=1)
    assert store.reserve_action(PROJECT, key, "game_export", request) is None
    with pytest.raises(ValueError, match="do not replay"):
        store.reserve_action(PROJECT, key, "game_export", request)
    result = modules.c.ActionResult(session_id="s", run_id="r", artifact_ids=["a"], outcome={"done": True})
    store.finish_action(PROJECT, key, "game_export", request, result)
    assert store.reserve_action(PROJECT, key, "game_export", request) == result
    with pytest.raises(ValueError, match="different input"):
        store.reserve_action(PROJECT, key, "playtest", request)


@pytest.mark.parametrize("failure", [None, "version", "boolean", "cancel", "project"])
def test_public_pixel_rgba_import_stitch_provenance_and_failures(harness, modules, failure):
    store = harness[0].tools[0].store
    made = create(store, modules)
    source_game = store.get(PROJECT, made.game.id)
    game_ref = ResourceScopeRef(kind=modules.c.RESOURCE, id=made.game.id, version=1)
    pixel_ref = ResourceScopeRef(kind="dbfox.pixel.document", id="pixel-source", version="3")
    source = Artifact(id="pixel-artifact", run_id="source-run", session_id="source-session", turn_id="source-turn", type="dbfox.pixel.revision", schema_version=1, title="Sprite", payload={"project_id": "foreign" if failure == "project" else PROJECT}, resource_refs=(pixel_ref,))
    class Context:
        invocation_id = str(uuid4())
        count = 0
        cancelled = False
        def scopes(self, kind):
            return (game_ref,) if kind == game_ref.kind else ()
        def resource(self, ref):
            assert ref == game_ref
            return source_game
        def artifact(self, identity):
            assert identity == source.id
            return source
        def is_cancelled(self):
            return self.cancelled
        def read_artifact_representation(self, identity, representation_type, request):
            assert identity == source.id and representation_type == "dbfox.pixel.sprite.v1" and request.operation == "frame"
            self.count += 1
            rect = request.parameters["rect"]
            rgba = [(x + y * 40 + channel) % 256 for y in range(rect["y"], rect["y"] + rect["height"]) for x in range(rect["x"], rect["x"] + rect["width"]) for channel in range(4)]
            if failure == "boolean":
                rgba[0] = True
            if failure == "cancel" and self.count == 4:
                self.cancelled = True
            return ArtifactRepresentationResult(representation_type=representation_type, representation_version=1, operation="frame", payload={"frame_id": "frame", "rect": rect, "rgba": rgba}, consistency="durable_snapshot", read_at="2026-09-06T00:00:00Z", read_id=str(uuid4()), source_version="4" if failure == "version" and self.count == 2 else "3", source_fingerprint="a" * 64)
    context = Context()
    tool = next(item for item in harness[0].tools if item.name == "asset_import")
    request = modules.c.ImportInput(game_id=made.game.id, expected_version=1, name="Sprite", source_artifact_id=source.id, frame_id="frame", rect=modules.c.PixelRect(x=0, y=0, width=40, height=36))
    if failure:
        with pytest.raises(ToolInputError):
            tool.run(request, context)
        assert store.get(PROJECT, made.game.id).version == 1
        with sqlite3.connect(store.path) as db:
            assert db.execute("SELECT count(*) FROM blobs").fetchone()[0] == 0
        return
    outcome = tool.run(request, context)
    expected = bytes((x + y * 40 + channel) % 256 for y in range(36) for x in range(40) for channel in range(4))
    revision = store.get(PROJECT, made.game.id)
    assert store.asset_bytes(revision, outcome.output.created_refs["asset"]) == expected
    assert outcome.artifacts[0].relations[0].artifact_id == source.id
    assert outcome.artifacts[0].resource_refs == (game_ref, pixel_ref)
    assert revision.game.assets[0].source.frame_id == "frame"
    count = context.count
    restored = tool.reconcile(request, context)
    assert restored.status == "succeeded" and context.count == count


def backend_snapshot(tmp_path):
    """Explicit backend-only signed package gate; not a complete desktop package test."""
    source = tmp_path / "backend-package"
    source.mkdir()
    shutil.copytree(SOURCE / "backend", source / "backend", ignore=shutil.ignore_patterns("__pycache__"))
    manifest = json.loads((SOURCE / "manifest.template.json").read_text(encoding="utf-8"))
    manifest["entrypoints"].pop("frontend")
    (source / "manifest.template.json").write_text(json.dumps(manifest), encoding="utf-8")
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Game test signing key; not a production publisher").digest())
    built = build_dlc_package_from_source(source, private_key=key)
    archive = tmp_path / "game-backend.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled("dbfox.game", True)
    snapshot = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert snapshot.activation_failures == ()
    return service, snapshot


def test_backend_signed_lifecycle_and_actual_action_run_receipt(tmp_path, db_session):
    db_session.add(Project(id=PROJECT, name="Game action"))
    db_session.commit()
    service, snapshot = backend_snapshot(tmp_path)
    spec = snapshot.get_operation("dbfox.game", "games.create").spec
    created = spec.handler(spec.input_model.model_validate({"title": "Installed Game", "expected_library_version": 1, "request_id": str(uuid4())}), DlcOperationContext(dlc_id="dbfox.game", operation_name="games.create", project_id=PROJECT))
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    actions = build_dlc_action_runs_host(dlc_id="dbfox.game", project_id=PROJECT, snapshot=snapshot, session_factory=factory)
    export = snapshot.get_operation("dbfox.game", "games.export").spec
    request = export.input_model.model_validate({"game_id": created.game.id, "expected_version": 1, "request_id": str(uuid4())})
    context = DlcOperationContext(dlc_id="dbfox.game", operation_name="games.export", project_id=PROJECT, action_runs=actions)
    prior = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        result = export.handler(request, context)
        assert export.handler(request, context) == result
    finally:
        set_active_runtime_snapshot(prior)
    with factory() as db:
        assert db.get(AgentRun, result.run_id).status == "completed"
        assert db.query(AgentRun).count() == 1
        artifacts = ArtifactRepository(db).list_for_run(result.run_id)
        assert [item.id for item in artifacts] == result.artifact_ids
    service.set_desired_enabled("dbfox.game", False)
    disabled = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert not disabled.tools and not disabled.operations and not disabled.resource_resolvers
    service.set_desired_enabled("dbfox.game", True)
    restored = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert not restored.activation_failures
    head = restored.get_operation("dbfox.game", "games.head").spec
    found = head.handler(head.input_model.model_validate({"game_id": created.game.id}), DlcOperationContext(dlc_id="dbfox.game", operation_name="games.head", project_id=PROJECT))
    assert found.game.version == 1 and found.game.title == "Installed Game"


def test_actual_product_factory_same_run_create_inspect_edit_stale_undo_export(tmp_path, db_session):
    _, snapshot = backend_snapshot(tmp_path)
    db_session.add(Project(id=PROJECT, name="Game RunLoop"))
    db_session.flush()
    db_session.add(AgentSession(id="game-session", project_id=PROJECT))
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    registry = build_product_tool_registry(snapshot)
    observed, calls = {}, []
    class Provider:
        def stream(self, *, messages, tools, **kwargs):
            for message in messages:
                if message.get("type") == "function_call_output":
                    observed[message["call_id"]] = json.loads(message["output"])
            step = len(calls)
            if step == 0:
                name, payload = "game_create", {"title": "Fox game", "expected_library_version": 1}
            else:
                first = observed["step-0"]
                assert first["status"] == "succeeded", first
                game = first["facts"]["game"]
                if step == 1:
                    name, payload = "game_inspect", {"game_id": game["id"], "section": "summary"}
                elif step == 2:
                    scene = observed["step-1"]["facts"]["metadata"]["initial_scene_id"]
                    name, payload = "game_modify", {"game_id": game["id"], "expected_version": 1, "operations": [{"kind": "entity_create", "entities": [{"scene_id": {"id": scene}, "name": "Fox", "ref": "fox"}]}, {"kind": "rule_create", "rule": {"scene_id": {"id": scene}, "name": "Survive 60 seconds", "trigger": {"kind": "elapsed_tick", "at_tick": 3600}, "actions": [{"kind": "finish", "result": "won"}]}}]}
                elif step == 3:
                    assert observed["step-2"]["status"] == "succeeded", observed["step-2"]
                    name, payload = calls[2]
                elif step == 4:
                    assert observed["step-3"]["status"] == "failed" and "STALE_VERSION" in observed["step-3"]["error_message"]
                    name, payload = "game_inspect", {"game_id": game["id"]}
                elif step == 5:
                    name, payload = "game_undo", {"game_id": game["id"], "expected_version": observed["step-4"]["facts"]["game"]["version"], "target_version": 1}
                elif step == 6:
                    assert observed["step-5"]["status"] == "succeeded", observed["step-5"]
                    name, payload = "game_export", {"game_id": game["id"], "expected_version": observed["step-5"]["facts"]["game"]["version"]}
                else:
                    assert observed["step-6"]["status"] == "succeeded", observed["step-6"]
                    yield from ScriptedProvider(answer_events("Created, inspected, edited and restored the Game; its immutable revision was exported. Playtest was not requested.")).stream()
                    return
            wire = registry.provider_name_for_key(ToolKey("dbfox.game", name))
            assert wire in {tool["name"] for tool in tools}
            calls.append((name, payload))
            yield from ScriptedProvider(tool_call_events(call_id=f"step-{step}", tool_name=wire, arguments=payload)).stream()
    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        with factory() as db:
            refs = authorize_project_resources(db, PROJECT, (RequestedResourceRef(kind="dbfox.game.library", id=PROJECT),), snapshot=snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id="game-session", resource_refs=refs, content="Create and edit a Game incrementally, restore the original, and export it.", idempotency_key="game-loop", llm_credential_id="scripted", api_base=None, model_name="scripted", request_payload={})
            lease = sessions.claim(session_id="game-session", owner="game-test", ttl_seconds=600)
            sessions.promote_next_input(lease=lease)
            db.commit()
        loop = build_product_run_loop(session_factory=factory, snapshot=snapshot)
        loop.model_factory = lambda settings: Provider()
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
    finally:
        set_active_runtime_snapshot(previous)
    assert len(calls) == len(observed) == 7
    with factory() as db:
        assert db.get(AgentRun, admission.run_id).status == "completed"
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        assert len(invocations) == 7
        artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
        for artifact in artifacts:
            producer = next(item for item in invocations if item.id == artifact.provenance["tool_invocation_id"])
            assert artifact.resource_refs[0].model_dump() in json.loads(producer.resource_refs_json)
