"""Deterministic conformance for the Voxel owner, public Host and Tool Runtime."""
from __future__ import annotations

import ast
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import threading
from types import ModuleType
import zlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import (
    Artifact, ArtifactRepresentationContext, ArtifactRepresentationError,
    ArtifactRepresentationRequest, ContextContributionInput, DlcOperationContext,
    DlcOperationError, DlcRuntimeInfo, RequestedResourceRef, ResourceScopeRef, ToolKey,
)
from engine.agent.completion import CompletionGate
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.host import DefaultBackendExtensionHost, StagedDlcContributions
from engine.dlc.manifest import DlcManifest
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.agent.repositories.artifact import ArtifactRepository
from engine.models import AgentObservationRecord, AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import (
    active_runtime_snapshot, authorize_project_resources, build_attempt_resource_resolver,
    build_default_completion_policy, build_dlc_action_runs_host, build_product_tool_registry,
    default_capability_guidance, default_context_contributors, set_active_runtime_snapshot,
)
from engine.tools.runtime import ToolRegistry, ToolRuntime
from engine.tools.runtime.registry import provider_tool_name
from engine.tools.runtime.resource_authority import bind_tool_invocation_resources
from verification.testkit.scripted_provider import ScriptedProvider, answer_events, tool_call_events

SOURCE = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.voxel"
OWNER = "dbfox.voxel"
WORLD = "dbfox.voxel.world"
LIBRARY = "dbfox.voxel.library"
EXPECTED_TOOLS = {
    "voxel_create", "voxel_inspect", "voxel_fill", "voxel_box", "voxel_sphere",
    "voxel_extrude", "voxel_replace", "voxel_copy_region", "voxel_mirror",
    "voxel_boolean", "voxel_configure", "voxel_undo", "voxel_delete", "voxel_export",
    "voxel_diff",
}


@pytest.fixture(scope="module")
def modules() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    name = "_voxel_conformance_owner"
    spec = importlib.util.spec_from_file_location(name, SOURCE / "backend" / "__init__.py", submodule_search_locations=[str(SOURCE / "backend")])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    contributions = importlib.import_module(name + ".contributions")
    contracts = importlib.import_module(name + ".contracts")
    store = importlib.import_module(name + ".store")
    geometry = importlib.import_module(name + ".geometry")
    return contributions, contracts, store, geometry


@dataclass
class Harness:
    staged: StagedDlcContributions
    models: ModuleType
    store_module: ModuleType
    geometry: ModuleType
    runtime: ToolRuntime

    @property
    def store(self):
        return next(t for t in self.staged.tools if t.name == "voxel_fill").store

    def operation(self, name: str, payload: dict, project: str = "project-voxel"):
        spec = next(item for item in self.staged.operations if item.name == name)
        result = spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(dlc_id=OWNER, operation_name=name, project_id=project))
        return spec.output_model.model_validate(result)

    def invoke(self, name: str, payload: dict, invocation: str):
        tool = next(item for item in self.staged.tools if item.name == name)
        refs = bind_tool_invocation_resources(tool, tool.input_model.model_validate(payload).model_dump(mode="json"),
            discovered=self.staged.resource_providers[0]("project-voxel"))
        resolvers = dict(self.staged.resource_resolvers)
        result = self.runtime.invoke(tool_name=provider_tool_name(OWNER, name), raw_input=payload,
            request=None, idempotency_key=invocation, invocation_id=invocation, scope_refs=refs,
            resources={ref.canonical(): resolvers[ref.kind](ref) for ref in refs})
        return result, refs

    def create(self, size: list[int] | None = None):
        return self.operation("worlds.create", {"title": "Conformance world", "size": size or [32, 32, 32], "mutation_id": "create"})

    def apply(self, world, operation: dict, mutation_id: str):
        return self.operation("worlds.apply", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": mutation_id, "operation": operation})

    def values(self, world, layer="base", coord=(0, 0, 0)) -> bytes:
        return self.store.read_chunk(self.store.snapshot("project-voxel", world.world_id, world.version), (layer, *coord))


@pytest.fixture
def harness(tmp_path: Path, modules) -> Harness:
    contributions, contracts, store_module, geometry = modules
    manifest_data = json.loads((SOURCE / "manifest.template.json").read_text(encoding="utf-8"))
    manifest_data["publisherKey"] = base64.b64encode(bytes(32)).decode("ascii")
    staged = StagedDlcContributions(dlc_id=OWNER, package_digest="f" * 64,
        manifest=DlcManifest.model_validate(manifest_data),
        runtime_info=DlcRuntimeInfo(dlc_id=OWNER, package_version="0.1.0", package_digest="f" * 64, data_path=tmp_path / "voxel"))
    contributions.register(DefaultBackendExtensionHost(staged))
    registry = ToolRegistry()
    for tool in staged.tools:
        registry.register(tool, owner=OWNER)
    return Harness(staged, contracts, store_module, geometry, ToolRuntime(registry))


def bounds(lo, hi) -> dict:
    return {"min": lo, "max": hi}


def fill(lo, hi, index=1, layer="base") -> dict:
    return {"kind": "fill", "layer_id": layer, "bounds": bounds(lo, hi), "palette_index": index}


def project_result(harness: Harness, name: str, result):
    tool = next(item for item in harness.staged.tools if item.name == name)
    projection = tool.project_observation(status=result.status, output=result.output or {}, artifacts=[])
    for value, budget in ((projection.facts, 32_768), (projection.provider_payload, 65_536)):
        assert len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= budget
    if result.status == "success":
        assert projection.facts == projection.provider_payload == result.output
    return projection


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_all_voxel_tools_reject_success_facts_on_failure(harness: Harness, name: str) -> None:
    tool = next(item for item in harness.staged.tools if item.name == name)
    for status in ("failed", "cancelled", "unknown"):
        projection = tool.project_observation(status=status, output={"world_id": "uncommitted", "version": 99}, artifacts=[])
        assert projection.facts == projection.provider_payload == {}
        assert "did not complete" in projection.summary


def test_all_voxel_tool_success_projections_preserve_the_typed_output(harness: Harness) -> None:
    world = harness.create()
    inspector, _ = harness.invoke("voxel_inspect", {"world_id": world.world_id}, "inspect-projection")
    difference, _ = harness.invoke("voxel_diff", {"world_id": world.world_id, "from_version": 1, "to_version": 1}, "diff-projection")
    exported, _ = harness.invoke("voxel_export", {"world_id": world.world_id}, "export-projection")
    for tool in harness.staged.tools:
        if tool.name == "voxel_inspect":
            output = inspector.output
        elif tool.name == "voxel_diff":
            output = difference.output
        elif tool.name == "voxel_export":
            output = exported.output
        else:
            output = world.model_dump(mode="json")
        projection = tool.project_observation(status="success", output=output, artifacts=[])
        assert projection.facts == projection.provider_payload == output
        with pytest.raises(ValueError):
            tool.project_observation(status="success", output={"world_id": "incomplete"}, artifacts=[])


def test_backend_imports_only_sdk_and_standard_library() -> None:
    for path in (SOURCE / "backend").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            assert all(name in sys.stdlib_module_names or name == "dbfox_dlc_api" for name in names), (path, names)


@pytest.mark.parametrize(("operation", "expected"), [
    (fill([1, 1, 1], [3, 3, 3], 2), 8),
    ({"kind": "box", "layer_id": "base", "bounds": bounds([1, 1, 1], [6, 6, 6]), "palette_index": 1, "hollow": True}, 98),
    ({"kind": "sphere", "layer_id": "base", "center": [5, 5, 5], "radius": 2, "palette_index": 3}, 33),
])
def test_fill_box_sphere_have_exact_integer_geometry(harness: Harness, operation, expected) -> None:
    world = harness.apply(harness.create(), operation, "geometry")
    assert world.changed_voxel_count == expected
    assert world.nonzero_count == expected
    assert world.version == 2


def test_overlap_copy_mirror_extrude_replace_and_boolean(harness: Harness) -> None:
    world = harness.apply(harness.create(), fill([0, 0, 0], [1, 1, 1], 2), "a")
    world = harness.apply(world, fill([1, 0, 0], [2, 1, 1], 3), "b")
    world = harness.apply(world, {"kind": "copy_region", "layer_id": "base", "source_layer_id": "base", "bounds": bounds([0, 0, 0], [2, 1, 1]), "destination": [1, 0, 0]}, "copy")
    assert harness.values(world)[:3] == bytes([2, 2, 3])
    world = harness.apply(world, {"kind": "mirror", "layer_id": "base", "source_layer_id": "base", "bounds": bounds([0, 0, 0], [3, 1, 1]), "destination": [0, 0, 0], "axis": "x"}, "mirror")
    assert harness.values(world)[:3] == bytes([3, 2, 2])
    world = harness.apply(world, {"kind": "extrude", "layer_id": "base", "source_layer_id": "base", "bounds": bounds([0, 0, 0], [3, 1, 1]), "axis": "y", "depth": 2}, "extrude")
    assert world.nonzero_count == 9
    world = harness.apply(world, {"kind": "replace", "layer_id": "base", "bounds": bounds([0, 0, 0], [3, 3, 1]), "from_index": 2, "to_index": 4}, "replace")
    assert harness.values(world)[256:259] == bytes([3, 4, 4])
    world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": "layer", "operation": {"kind": "layer_put", "layer": {"id": "source", "name": "Source"}}})
    world = harness.apply(world, fill([0, 0, 0], [2, 3, 1], layer="source"), "source-fill")
    world = harness.apply(world, {"kind": "boolean", "layer_id": "base", "source_layer_id": "source", "bounds": bounds([0, 0, 0], [3, 3, 1]), "mode": "difference"}, "difference")
    assert harness.values(world)[:3] == bytes([0, 0, 4])
    assert harness.values(world, "source")[:3] == bytes([1, 1, 0])


@pytest.mark.parametrize(("mode", "expected"), [("union", [2, 2, 3]), ("intersection", [0, 2, 0]), ("difference", [2, 0, 0]), ("xor", [2, 0, 3])])
def test_boolean_colors_and_explicit_source(harness: Harness, mode, expected) -> None:
    world = harness.apply(harness.create(), fill([0, 0, 0], [2, 1, 1], 2), "a")
    world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": "layer", "operation": {"kind": "layer_put", "layer": {"id": "other", "name": "Other"}}})
    world = harness.apply(world, fill([1, 0, 0], [3, 1, 1], 3, "other"), "b")
    world = harness.apply(world, {"kind": "boolean", "layer_id": "base", "source_layer_id": "other", "bounds": bounds([0, 0, 0], [3, 1, 1]), "mode": mode}, mode)
    assert harness.values(world)[:3] == bytes(expected)


def test_new_invocations_bind_current_world_and_reconcile_original_after_delete(harness: Harness) -> None:
    assert {tool.name for tool in harness.staged.tools} == EXPECTED_TOOLS
    created, _ = harness.invoke("voxel_create", {"title": "Runtime world", "size": [32, 32, 32]}, "create-tool")
    assert created.status == "success"
    world_id = project_result(harness, "voxel_create", created).provider_payload["world_id"]
    payload = {"world_id": world_id, "expected_version": 1, "operation": fill([0, 0, 0], [4, 4, 4], 2)}
    changed, frozen = harness.invoke("voxel_fill", payload, "fill-tool")
    assert changed.status == "success" and frozen[0].version == 1
    project_result(harness, "voxel_fill", changed)
    inspected, current_refs = harness.invoke("voxel_inspect", {"world_id": world_id}, "inspect-tool")
    assert inspected.status == "success" and inspected.output["version"] == 2
    project_result(harness, "voxel_inspect", inspected)
    assert current_refs[0].version == 2
    stale, _ = harness.invoke("voxel_fill", payload, "stale-new-invocation")
    assert stale.status == "failed" and "STALE_VERSION" in stale.error
    assert project_result(harness, "voxel_fill", stale).facts == {}
    second, _ = harness.invoke("voxel_fill", {"world_id": world_id, "expected_version": 2, "operation": fill([4, 0, 0], [5, 4, 4], 3)}, "second-tool")
    assert second.status == "success" and second.output["version"] == 3
    project_result(harness, "voxel_fill", second)
    deleted, _ = harness.invoke("voxel_delete", {"world_id": world_id, "expected_version": 3}, "delete-tool")
    assert deleted.status == "success"
    assert project_result(harness, "voxel_delete", deleted).facts["status"] == "deleted"
    resolvers = dict(harness.staged.resource_resolvers)
    recovered = harness.runtime.reconcile(tool_name=provider_tool_name(OWNER, "voxel_fill"), raw_input=payload, request=None,
        idempotency_key="fill-tool", invocation_id="fill-tool", scope_refs=frozen,
        resources={ref.canonical(): resolvers[ref.kind](ref) for ref in frozen})
    assert recovered.status == "success"
    assert recovered.output == changed.output
    assert recovered.artifact_drafts == changed.artifact_drafts
    assert project_result(harness, "voxel_fill", recovered).provider_payload["version"] == 2
    assert harness.store.snapshot("project-voxel", world_id).version == 4


def test_human_receipts_noop_undo_and_restart_preserve_one_history(harness: Harness) -> None:
    initial = harness.create()
    filled = harness.apply(initial, fill([0, 0, 0], [16, 16, 16], 1), "fill")
    assert harness.apply(initial, fill([0, 0, 0], [16, 16, 16], 1), "fill") == filled
    with pytest.raises(DlcOperationError, match="different voxel input"):
        harness.apply(initial, fill([0, 0, 0], [16, 16, 16], 2), "fill")
    noop = harness.apply(filled, fill([0, 0, 0], [16, 16, 16], 1), "noop")
    assert noop.version == filled.version and not noop.changed
    undone = harness.operation("worlds.undo", {"world_id": filled.world_id, "expected_version": 2, "target_version": 1, "mutation_id": "undo"})
    redone = harness.operation("worlds.undo", {"world_id": filled.world_id, "expected_version": 3, "target_version": 2, "mutation_id": "redo"})
    assert undone.nonzero_count == 0
    assert redone.version == 4 and redone.content_hash == filled.content_hash
    assert harness.create() == initial  # creation receipt must not return the later head
    reopened = harness.store_module.VoxelStore(harness.store.database_path.parent)
    assert reopened.snapshot("project-voxel", filled.world_id, 2).content_hash == filled.content_hash
    delta = harness.operation("worlds.chunks", {"world_id": filled.world_id, "version": 3, "since_version": 2})
    assert len(delta.chunks) == 1 and delta.chunks[0].values is None


def test_two_connections_cannot_lose_an_update(harness: Harness) -> None:
    initial = harness.create()
    barrier = threading.Barrier(2)
    request = harness.models.ApplyInput(world_id=initial.world_id, expected_version=1, operation=fill([0, 0, 0], [16, 16, 16]))
    def writer(index):
        store = harness.store_module.VoxelStore(harness.store.database_path.parent)
        barrier.wait(timeout=5)
        try:
            return store.mutate("project-voxel", request, kind="fill", origin="human", request_id=f"writer-{index}").version
        except harness.geometry.VoxelError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(writer, [0, 1]))
    assert outcomes.count(2) == 1 and outcomes.count("STALE_VERSION") == 1


def test_partial_failure_and_cancellation_leave_no_revision(harness: Harness, monkeypatch) -> None:
    initial = harness.create()
    request = harness.models.ApplyInput(world_id=initial.world_id, expected_version=1, operation=fill([0, 0, 0], [32, 32, 32]))
    original = harness.store._write_receipt
    def fail_receipt(*args):
        raise RuntimeError("injected failure after chunk/head writes")
    monkeypatch.setattr(harness.store, "_write_receipt", fail_receipt)
    with pytest.raises(RuntimeError, match="injected failure"):
        harness.store.mutate("project-voxel", request, kind="fill", origin="human", request_id="partial")
    monkeypatch.setattr(harness.store, "_write_receipt", original)
    assert harness.store.snapshot("project-voxel", initial.world_id).version == 1
    assert harness.store.receipt("project-voxel", "human", "partial", "fill", request) is None
    checks = 0
    def cancelled():
        nonlocal checks
        checks += 1
        return checks > 3
    with pytest.raises(harness.geometry.VoxelError) as failure:
        harness.store.mutate("project-voxel", request, kind="fill", origin="human", request_id="cancelled", cancelled=cancelled)
    assert failure.value.code == "CANCELLED"
    assert harness.store.snapshot("project-voxel", initial.world_id).version == 1
    with closing(sqlite3.connect(harness.store.database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM world_revisions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM chunk_versions").fetchone()[0] == 0


@pytest.mark.parametrize("corruption", ["bomb", "trailing", "wrong_hash", "truncated"])
def test_corrupt_chunks_fail_closed(harness: Harness, corruption) -> None:
    world = harness.apply(harness.create(), fill([0, 0, 0], [16, 16, 16], 2), "fill")
    snapshot = harness.store.snapshot("project-voxel", world.world_id)
    raw = harness.values(world)
    encoded = zlib.compress(raw)
    blobs = {"bomb": zlib.compress(bytes(100_000)), "trailing": encoded + b"extra", "wrong_hash": zlib.compress(bytes([1]) * 4096), "truncated": encoded[:-2]}
    with closing(sqlite3.connect(harness.store.database_path)) as connection:
        connection.execute("UPDATE chunk_versions SET blob=? WHERE world_id=?", (blobs[corruption], world.world_id))
        connection.commit()
    with pytest.raises(harness.geometry.VoxelError) as failure:
        harness.store.read_chunk(snapshot, ("base", 0, 0, 0))
    assert failure.value.code == "CORRUPT_STATE"


def test_unknown_schema_refused_without_rewriting_it(harness: Harness) -> None:
    with closing(sqlite3.connect(harness.store.database_path)) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(harness.geometry.VoxelError) as failure:
        harness.store_module.VoxelStore(harness.store.database_path.parent)
    assert failure.value.code == "UNSUPPORTED_SCHEMA"
    with closing(sqlite3.connect(harness.store.database_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


@pytest.mark.parametrize("schema", [True, 1.0, "1"])
def test_metadata_schema_requires_exact_integer_one(harness: Harness, schema) -> None:
    world = harness.create()
    document = harness.store.snapshot("project-voxel", world.world_id).document.model_dump(mode="json")
    document["schema_version"] = schema
    encoded = json.dumps(document)
    with closing(sqlite3.connect(harness.store.database_path)) as connection:
        connection.execute("UPDATE world_revisions SET document_json=? WHERE world_id=?", (encoded, world.world_id))
        connection.commit()
    with pytest.raises(harness.geometry.VoxelError) as failure:
        harness.store.snapshot("project-voxel", world.world_id)
    assert failure.value.code == "CORRUPT_STATE"
    with closing(sqlite3.connect(harness.store.database_path)) as connection:
        assert connection.execute("SELECT document_json FROM world_revisions WHERE world_id=?", (world.world_id,)).fetchone()[0] == encoded
    with pytest.raises(ValueError):
        harness.models.WorldDocument.model_validate(document)


def test_bounds_palette_locks_project_and_size_budgets(harness: Harness, monkeypatch) -> None:
    world = harness.create([128, 128, 128])
    world = harness.apply(world, fill([0, 0, 0], [128, 128, 128]), "million")
    assert world.nonzero_count == 2_097_152 and world.chunk_count == 512
    with pytest.raises(DlcOperationError) as outside:
        harness.apply(world, fill([0, 0, 0], [129, 128, 128]), "outside")
    assert outside.value.code == "OUT_OF_BOUNDS"
    with pytest.raises(DlcOperationError) as palette:
        harness.apply(world, fill([0, 0, 0], [1, 1, 1], 255), "undefined")
    assert palette.value.code == "PALETTE_NOT_FOUND"
    with pytest.raises(DlcOperationError) as project:
        harness.operation("worlds.get", {"world_id": world.world_id}, project="another-project")
    assert project.value.code == "WORLD_NOT_FOUND"
    locked = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": "lock", "operation": {"kind": "layer_put", "layer": {"id": "base", "name": "Base", "locked": True}}})
    with pytest.raises(DlcOperationError) as lock:
        harness.apply(locked, fill([0, 0, 0], [1, 1, 1]), "locked")
    assert lock.value.code == "LAYER_LOCKED"
    monkeypatch.setattr(harness.store_module, "MAX_HISTORY_BYTES", 1)
    with pytest.raises(DlcOperationError) as quota:
        harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": locked.version, "mutation_id": "quota", "operation": {"kind": "rename", "title": "New title"}})
    assert quota.value.code == "HISTORY_QUOTA_EXCEEDED"
    assert harness.store.snapshot("project-voxel", world.world_id).version == locked.version


def test_candidate_budget_rejects_large_scan_before_writing(harness: Harness) -> None:
    world = harness.create([256, 256, 256])
    with pytest.raises(DlcOperationError) as failure:
        harness.apply(world, fill([0, 0, 0], [129, 129, 129]), "oversize")
    assert failure.value.code == "OPERATION_TOO_LARGE"
    assert harness.store.snapshot("project-voxel", world.world_id).version == 1
    with pytest.raises(ValueError):
        harness.models.ExtrudeOperation(layer_id="base", source_layer_id="base", bounds=bounds([0, 0, 0], [1, 1, 1]), axis="x", depth=1, direction=True)


def test_snapshot_representation_and_pages_are_revision_pinned(harness: Harness) -> None:
    initial = harness.create([64, 64, 64])
    filled = harness.apply(initial, fill([0, 0, 0], [64, 64, 64]), "fill")
    exported, _ = harness.invoke("voxel_export", {"world_id": filled.world_id, "version": filled.version}, "export")
    assert exported.status == "success"
    draft = exported.artifact_drafts[0]
    artifact = Artifact(id="voxel-artifact", session_id="session", run_id="run", type=draft.type, title=draft.title, payload=draft.payload, resource_refs=draft.resource_refs)
    provider = harness.staged.artifact_representations[0][2]
    context = ArtifactRepresentationContext(artifact_loader=lambda _id: None)
    first = provider.execute(artifact, ArtifactRepresentationRequest(operation="chunks", parameters={"limit": 16}), context)
    assert len(first.payload["chunks"]) == 16 and first.payload["next_after"]
    erased = harness.apply(filled, fill([0, 0, 0], [64, 64, 64], 0), "erase")
    harness.operation("worlds.delete", {"world_id": erased.world_id, "expected_version": erased.version, "mutation_id": "delete"})
    second = provider.execute(artifact, ArtifactRepresentationRequest(operation="chunks", parameters={"limit": 16, "after": first.payload["next_after"]}), context)
    assert second.source_fingerprint == first.source_fingerprint == filled.content_hash
    assert all(row["values"] == [1] * 4096 for row in second.payload["chunks"])
    manifest = provider.execute(artifact, ArtifactRepresentationRequest(operation="manifest"), context)
    assert manifest.payload["version"] == 2 and manifest.payload["status"] == "active"
    with pytest.raises(ArtifactRepresentationError):
        provider.execute(artifact, ArtifactRepresentationRequest(operation="chunks", parameters={"version": erased.version}), context)
    with pytest.raises(DlcOperationError) as cursor:
        harness.operation("worlds.chunks", {"world_id": filled.world_id, "version": 3, "after": first.payload["next_after"]})
    assert cursor.value.code == "INVALID_CURSOR"


@pytest.mark.parametrize("long_name", ["🦊" * 80, "\x00" * 80], ids=["four-byte-unicode", "json-escaped"])
def test_context_and_inspect_are_bounded_with_long_object_names(harness: Harness, long_name: str) -> None:
    world = harness.create()
    world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version,
        "mutation_id": "long-title", "operation": {"kind": "rename", "title": long_name}})
    for index in range(1, 33):
        world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": f"palette{index}", "operation": {"kind": "palette_put", "entry": {"index": index, "name": long_name, "color": "#abcdef"}}})
        world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": f"region{index}", "operation": {"kind": "region_put", "region": {"id": f"r{index:03d}" + "x" * 124, "name": long_name, "bounds": bounds([0, 0, 0], [1, 1, 1])}}})
    for index in range(1, 16):
        world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version, "mutation_id": f"layer{index}", "operation": {"kind": "layer_put", "layer": {"id": f"l{index:03d}" + "x" * 124, "name": long_name}}})
    inspected, _ = harness.invoke("voxel_inspect", {"world_id": world.world_id, "object_limit": 32}, "inspect-budget")
    assert inspected.status == "success" and inspected.output["truncated"]
    assert len(json.dumps(inspected.output, ensure_ascii=False).encode("utf-8")) < 16_384
    first = project_result(harness, "voxel_inspect", inspected)
    assert first.facts["next_object_offset"] < 32  # Complete-page byte budget, not just the requested row count.
    assert "Continue at object_offset=" in first.summary
    collected = {"layers": [], "palette": [], "regions": []}
    offset = 0
    while True:
        result, _ = harness.invoke("voxel_inspect", {"world_id": first.facts["world_id"], "version": first.facts["version"],
            "object_offset": offset, "object_limit": 32}, f"inspect-page-{offset}")
        page = project_result(harness, "voxel_inspect", result).provider_payload
        assert len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 12_000
        for field in collected:
            collected[field].extend(page[field])
        if page["next_object_offset"] is None:
            assert page["truncated"] is False
            break
        assert page["next_object_offset"] > offset and page["truncated"] is True
        offset = page["next_object_offset"]
    document = harness.operation("worlds.get", {"world_id": world.world_id, "version": first.facts["version"]}).document.model_dump(mode="json")
    assert collected == {field: document[field] for field in collected}
    assert all(item["name"] == long_name for item in collected["regions"])
    contributor = harness.staged.context_contributors[0]
    fragments = contributor.build(ContextContributionInput(session_id="session", run_id="run", current_request="Inspect this world.",
        resource_refs=(ResourceScopeRef(kind=LIBRARY, id="project-voxel", version=1), ResourceScopeRef(kind=WORLD, id=world.world_id, version=world.version))))
    assert all(len(fragment.content) <= 4000 for fragment in fragments)
    assert sum(len(fragment.content) for fragment in fragments) < 8000
    assert all('"values"' not in fragment.content and '"chunks"' not in fragment.content for fragment in fragments)
    context = fragments[-1].content
    assert "voxel_inspect" in context and "object_offset=0" in context
    context_facts = json.loads(context.split("\n", 1)[0])
    assert context_facts["truncated"] is True and context_facts["title"] == long_name
    assert context_facts["world_id"] == world.world_id and context_facts["version"] == world.version
    for field in collected:
        for item in context_facts[field]:
            assert any(all(original[key] == value for key, value in item.items()) for original in collected[field])


def test_diff_observations_keep_complete_chunks_and_revision_pinned_cursor(harness: Harness) -> None:
    world = harness.create([128, 128, 128])
    long_layer = "layer" + "x" * 123
    world = harness.operation("worlds.configure", {"world_id": world.world_id, "expected_version": world.version,
        "mutation_id": "long-layer", "operation": {"kind": "layer_put", "layer": {"id": long_layer, "name": "🦊" * 80}}})
    before = harness.apply(world, fill([0, 0, 0], [128, 128, 128], 1, long_layer), "before-diff")
    after = harness.apply(before, fill([0, 0, 0], [128, 128, 128], 2, long_layer), "after-diff")
    first, _ = harness.invoke("voxel_diff", {"world_id": world.world_id, "from_version": before.version, "to_version": after.version, "limit": 64}, "diff-budget")
    projection = project_result(harness, "voxel_diff", first)
    assert first.status == "success" and projection.facts["truncated"] is True
    assert len(projection.facts["chunks"]) < 64  # Long IDs and two full hashes exercise byte pagination.
    assert "Continue with next_after" in projection.summary
    chunks = []
    cursor = None
    cursors = set()
    while True:
        result, _ = harness.invoke("voxel_diff", {"world_id": projection.facts["world_id"], "from_version": projection.facts["from_version"],
            "to_version": projection.facts["to_version"], "limit": 64, "after": cursor}, f"diff-page-{len(cursors)}")
        page = project_result(harness, "voxel_diff", result).provider_payload
        assert len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 12_000
        assert page["changed_chunk_count"] == 512
        chunks.extend(page["chunks"])
        cursor = page["next_after"]
        if cursor is None:
            assert page["truncated"] is False
            break
        assert cursor not in cursors and page["truncated"] is True
        cursors.add(cursor)
    assert len(chunks) == len({tuple(item["coord"]) for item in chunks}) == 512
    before_hash = "sha256:" + hashlib.sha256(bytes([1]) * 4096).hexdigest()
    after_hash = "sha256:" + hashlib.sha256(bytes([2]) * 4096).hexdigest()
    assert all(item["layer_id"] == long_layer and item["before_hash"] == before_hash and item["after_hash"] == after_hash for item in chunks)
    invalid, _ = harness.invoke("voxel_diff", {"world_id": world.world_id, "from_version": 1, "to_version": after.version,
        "after": projection.facts["next_after"]}, "foreign-revision-cursor")
    assert invalid.status == "failed" and "INVALID_CURSOR" in invalid.error
    assert project_result(harness, "voxel_diff", invalid).facts == {}


def _signed_snapshot(tmp_path: Path):
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Voxel conformance fixture key; never use in production").digest())
    built = build_dlc_package_from_source(SOURCE, private_key=key)
    archive = tmp_path / "voxel.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(OWNER, True)
    active = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert active.activation_failures == ()
    return service, active


def test_signed_package_activation_cleanup_and_persistence(tmp_path: Path) -> None:
    service, active = _signed_snapshot(tmp_path)
    assert {item.tool.name for item in active.tools} == EXPECTED_TOOLS
    assert len(active.operations) == 11
    create = active.get_operation(OWNER, "worlds.create").spec
    output = create.handler(create.input_model.model_validate({"title": "Persisted", "mutation_id": "create"}), DlcOperationContext(dlc_id=OWNER, operation_name="worlds.create", project_id="p"))
    service.set_desired_enabled(OWNER, False)
    disabled = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert not disabled.tools and not disabled.operations and not disabled.resource_resolvers and not disabled.context_contributors
    service.set_desired_enabled(OWNER, True)
    reactivated = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert reactivated.activation_failures == ()
    get = reactivated.get_operation(OWNER, "worlds.get").spec
    restored = get.handler(get.input_model.model_validate({"world_id": output.world_id}), DlcOperationContext(dlc_id=OWNER, operation_name="worlds.get", project_id="p"))
    assert restored.title == "Persisted" and restored.version == 1


def test_snapshot_operation_creates_a_durable_host_action_run(tmp_path: Path, db_session) -> None:
    project_id = "project-voxel-action"
    db_session.add(Project(id=project_id, name="Voxel action", status="active"))
    db_session.commit()
    _service, snapshot = _signed_snapshot(tmp_path)
    create = snapshot.get_operation(OWNER, "worlds.create").spec
    world = create.handler(create.input_model.model_validate({"title": "Action snapshot", "mutation_id": "create"}),
        DlcOperationContext(dlc_id=OWNER, operation_name="worlds.create", project_id=project_id))
    factory = sessionmaker(bind=db_session.get_bind())
    action_runs = build_dlc_action_runs_host(dlc_id=OWNER, project_id=project_id, snapshot=snapshot, session_factory=factory)
    export = snapshot.get_operation(OWNER, "worlds.snapshot").spec
    set_active_runtime_snapshot(snapshot)
    try:
        result = export.handler(export.input_model.model_validate({"world_id": world.world_id, "version": 1, "mutation_id": "snapshot-action"}),
            DlcOperationContext(dlc_id=OWNER, operation_name="worlds.snapshot", project_id=project_id, action_runs=action_runs))
    finally:
        set_active_runtime_snapshot(None)
    with factory() as db:
        run = db.get(AgentRun, result.run_id)
        assert run is not None and run.status == "completed"
        artifacts = ArtifactRepository(db).list_for_run(result.run_id)
    assert [artifact.type for artifact in artifacts] == ["dbfox.voxel.snapshot"]
    assert result.artifact_ids == [artifacts[0].id]
    assert artifacts[0].payload["world_id"] == world.world_id
    assert artifacts[0].payload["version"] == 1


@pytest.mark.parametrize("continue_edits", [False, True], ids=["create-inspect", "incremental"])
def test_signed_runloop_observations_drive_incremental_voxel_edits(tmp_path: Path, db_session, continue_edits: bool) -> None:
    """Only formal function_call_output supplies model world IDs and revisions."""
    project_id = "voxel-observation-project"
    session_id = "voxel-observation-session"
    _service, snapshot = _signed_snapshot(tmp_path)
    registry = build_product_tool_registry(snapshot)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    db_session.add(Project(id=project_id, name="Observation regression"))
    db_session.flush()
    db_session.add(AgentSession(id=session_id, project_id=project_id))
    db_session.commit()
    observed: dict[str, dict] = {}
    requests: list[tuple[str, dict]] = []
    names = {name: registry.provider_name_for_key(ToolKey(owner_id=OWNER, local_name=name)) for name in EXPECTED_TOOLS}

    class Provider:
        def stream(self, *, messages, tools, **kwargs):
            for message in messages:
                if message.get("type") == "function_call_output":
                    observed[message["call_id"]] = json.loads(message["output"])
            index = len(requests)
            if index == 2 and not continue_edits:
                assert observed["step-1"]["facts"]["world_id"] == observed["step-0"]["facts"]["world_id"]
                yield from ScriptedProvider(answer_events("Created and inspected the voxel world using its observed identity and version.")).stream()
                return
            if index == 0:
                name, payload = "voxel_create", {"title": "Observation world", "size": [32, 32, 32]}
            elif index == 1:
                created = observed["step-0"]["facts"]
                name, payload = "voxel_inspect", {"world_id": created["world_id"], "version": created["version"]}
            else:
                inspected = observed["step-1"]["facts"]
                world_id = inspected["world_id"]
                operation = fill([0, 0, 0], [2, 2, 2], inspected["palette"][1]["index"], inspected["layers"][0]["id"])
                if index in (2, 3):
                    if index == 3:
                        assert observed["step-2"]["status"] == "succeeded", observed["step-2"]
                    # The second request deliberately uses the old observed revision.
                    name, payload = "voxel_fill", {"world_id": world_id, "expected_version": inspected["version"], "operation": operation}
                elif index == 4:
                    failure = observed["step-3"]
                    assert failure["status"] == "failed" and "STALE_VERSION" in failure["error_message"]
                    assert failure["facts"] == {} and failure["artifact_ids"] == []
                    name, payload = "voxel_inspect", {"world_id": world_id}
                elif index == 5:
                    name, payload = "voxel_fill", {"world_id": world_id, "expected_version": observed["step-4"]["facts"]["version"], "operation": operation}
                elif index == 6:
                    assert observed["step-5"]["facts"]["changed"] is False
                    name, payload = "voxel_configure", {"world_id": world_id, "expected_version": observed["step-5"]["facts"]["version"],
                        "operation": {"kind": "rename", "title": "Renamed from observation"}}
                elif index == 7:
                    name, payload = "voxel_undo", {"world_id": world_id, "expected_version": observed["step-6"]["facts"]["version"],
                        "target_version": observed["step-0"]["facts"]["version"]}
                elif index == 8:
                    name, payload = "voxel_diff", {"world_id": world_id, "from_version": observed["step-0"]["facts"]["version"],
                        "to_version": observed["step-2"]["facts"]["version"]}
                elif index == 9:
                    name, payload = "voxel_export", {"world_id": world_id, "version": observed["step-2"]["facts"]["version"]}
                else:
                    assert observed["step-9"]["facts"]["version"] == observed["step-2"]["facts"]["version"]
                    assert observed["step-9"]["artifact_ids"]
                    yield from ScriptedProvider(answer_events("Created, inspected, edited, recovered from a stale request, restored, compared, and exported the voxel world.")).stream()
                    return
            assert names[name] in {tool["name"] for tool in tools}
            requests.append((name, payload))
            yield from ScriptedProvider(tool_call_events(call_id=f"step-{index}", tool_name=names[name], arguments=payload)).stream()

    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        with factory() as db:
            refs = authorize_project_resources(db, project_id, (RequestedResourceRef(kind=LIBRARY, id=project_id),), snapshot=snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id=session_id, resource_refs=refs, content="Create a voxel world, incrementally edit it, and verify its saved snapshot.",
                idempotency_key="voxel-observation", llm_credential_id="voxel-scripted", api_base=None, model_name="scripted", request_payload={})
            lease = sessions.claim(session_id=session_id, owner="voxel-observation-test", ttl_seconds=600)
            assert lease is not None
            sessions.promote_next_input(lease=lease)
            db.commit()
        loop = RunLoop(session_factory=factory, model_factory=lambda settings: Provider(), registry=registry,
            context_contributors=default_context_contributors(snapshot), capability_guidance=default_capability_guidance(snapshot),
            resource_providers=snapshot.resource_providers, resource_resolver=build_attempt_resource_resolver(snapshot=snapshot),
            artifact_payload_contract_resolver=lambda kind, version: snapshot.get_artifact_contract(kind, version).validator,
            runtime_snapshot_id=snapshot.snapshot_id, completion=CompletionGate(build_default_completion_policy(snapshot)),
            definition=AgentDefinition(limits=RunLimits(max_turns=20, max_tool_invocations=20, max_repair_attempts=3,
                finalization_turn_reserve=1, finalization_tool_reserve=1, max_prompt_tokens=128_000)), live_stream=LiveStreamHub())
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
    finally:
        set_active_runtime_snapshot(previous)
    expected_count = 10 if continue_edits else 2
    assert len(requests) == len(observed) == expected_count
    if continue_edits:
        assert observed["step-7"]["facts"]["version"] == 4
        assert observed["step-7"]["facts"]["nonzero_count"] == 0
        assert observed["step-8"]["facts"]["changed_chunk_count"] == 1
    with factory() as db:
        run = db.get(AgentRun, admission.run_id)
        assert run is not None and run.status == "completed"
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        records = db.query(AgentObservationRecord).filter_by(run_id=admission.run_id).all()
        assert len(invocations) == len(records) == expected_count
        for record in records:
            invocation = next(item for item in invocations if item.id == record.tool_invocation_id)
            assert json.loads(record.facts_json) == observed[invocation.provider_call_id]["facts"]
        artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
        if continue_edits:
            exported = next(item for item in artifacts if item.id in observed["step-9"]["artifact_ids"])
            assert exported.payload["version"] == 2 and exported.payload["nonzero_count"] == 8
