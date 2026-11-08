"""Shader author conformance. Simulated bridge receipts are not real GPU evidence."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import json
import shutil
from pathlib import Path
import sqlite3
import sys
import threading
import time
import struct
import zlib
from types import ModuleType
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import (
    Artifact, ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest, ContextContributionInput,
    DlcOperationContext, DlcOperationError, DlcRuntimeInfo, RequestedResourceRef, ResourceScopeRef, ToolKey,
)
from engine.agent.completion import CompletionGate
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.host import DefaultBackendExtensionHost, StagedDlcContributions
from engine.dlc.manifest import DlcManifest
from engine.dlc.package_builder import build_dlc_package_from_source
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

SOURCE = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.shader"
OWNER = "dbfox.shader"
STUDIO = OWNER + ".studio"
PROJECT = "shader-project"
DIGEST = "f" * 64


@pytest.fixture(scope="module")
def modules() -> ModuleType:
    name = "_shader_conformance"
    spec = importlib.util.spec_from_file_location(name, SOURCE / "backend" / "__init__.py", submodule_search_locations=[str(SOURCE / "backend")])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".contributions")


@dataclass
class Harness:
    staged: StagedDlcContributions
    modules: ModuleType
    runtime: ToolRuntime

    @property
    def c(self):
        return self.modules.c

    @property
    def store(self):
        return self.staged.tools[0].store

    @property
    def bridge(self):
        return self.staged.tools[0].bridge

    def operation(self, name, payload, project=PROJECT):
        spec = next(item for item in self.staged.operations if item.name == name)
        value = spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(dlc_id=OWNER, operation_name=name, project_id=project if spec.scope == "project" else None))
        return spec.output_model.model_validate(value)

    def create(self, title="Shader"):
        generation = self.store.list_resources(PROJECT)[0].version
        return self.operation("documents.create", {"title": title, "expected_generation": generation, "request_id": str(uuid4())})

    def apply(self, document, ops, request_id=None):
        return self.operation("documents.apply", {"document_id": document.id, "expected_version": document.version, "operations": ops, "request_id": request_id or str(uuid4())})

    def invoke(self, name, payload, identity=None, frozen=None):
        tool = next(item for item in self.staged.tools if item.name == name)
        validated = tool.input_model.model_validate(payload)
        refs = frozen or bind_tool_invocation_resources(tool, validated.model_dump(mode="json", exclude_none=True), discovered=self.staged.resource_providers[0](PROJECT))
        resolved = {ref.canonical(): self.store.resolve(ref) for ref in refs}
        invocation = identity or str(uuid4())
        return self.runtime.invoke(tool_name=provider_tool_name(OWNER, name), raw_input=payload, request=None, idempotency_key=invocation, invocation_id=invocation, scope_refs=refs, resources=resolved), refs


@pytest.fixture
def harness(tmp_path, modules):
    manifest = json.loads((SOURCE / "manifest.template.json").read_text(encoding="utf-8"))
    manifest["publisherKey"] = base64.b64encode(bytes(32)).decode("ascii")
    staged = StagedDlcContributions(dlc_id=OWNER, package_digest=DIGEST, manifest=DlcManifest.model_validate(manifest), runtime_info=DlcRuntimeInfo(dlc_id=OWNER, package_version="0.1.0", package_digest=DIGEST, data_path=tmp_path / "state"))
    modules.register(DefaultBackendExtensionHost(staged))
    registry = ToolRegistry()
    for tool in staged.tools:
        registry.register(tool, owner=OWNER)
    return Harness(staged, modules, ToolRuntime(registry))


def caps():
    return {"version": "WebGL 2.0 test boundary", "shading_language_version": "WebGL GLSL ES 3.00 test boundary", "max_texture_size": 4096, "max_renderbuffer_size": 4096, "max_texture_image_units": 16, "max_combined_texture_image_units": 32, "max_fragment_uniform_vectors": 1024, "max_vertex_uniform_vectors": 1024, "parallel_shader_compile": True}


def attach(h, counter=1, client=None):
    result = h.operation("compute.attach", {"client_id": client or str(uuid4()), "registration_counter": counter, "package_digest": DIGEST, "available": True, "capabilities": caps()})
    return {"epoch": result.epoch, "lease": result.lease, "registration_counter": counter}


def claim(h, lease):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        result = h.operation("compute.next", lease)
        if result.status == "request":
            return result.request
        time.sleep(.005)
    raise AssertionError("Tool did not submit GPU request")


def complete_payload(lease, request, result):
    fields = request.model_dump(exclude={"snapshot", "kind", "remaining_ms"})
    return {**lease, **fields, "package_digest": DIGEST, "result": result}


def test_registration_and_machine_schemas(harness):
    h = harness
    assert len(h.staged.tools) == 13 and len(h.staged.operations) == 16
    assert h.store.list_resources(PROJECT)[0].version == 0
    with sqlite3.connect(h.store.path) as db:
        assert db.execute("SELECT count(*) FROM studios").fetchone()[0] == 0
    for spec in h.staged.operations:
        spec.input_model.model_json_schema()
        spec.output_model.model_json_schema()
        if spec.scope == "machine":
            assert "project_id" not in spec.input_model.model_fields
    assert next(item for item in h.staged.operations if item.name == "compute.next").max_output_bytes == 8_388_608


@pytest.mark.parametrize("bad", [True, False, -1, 1.0, "1", None])
def test_strict_generation_and_null(harness, bad):
    with pytest.raises(ValueError):
        harness.c.CreateInput.model_validate({"title": "x", "expected_generation": bad})
    assert harness.c.InspectInput.model_validate({"section": "documents", "document_id": None}).document_id is None


def test_public_runtime_observation_incremental_stale_noop_undo(harness):
    h = harness
    created, refs = h.invoke("shader_create", {"title": "Runtime", "expected_generation": 0})
    assert created.status == "success", created.error
    projection = h.staged.tools[0].project_observation(status="success", output=created.output, artifacts=())
    result = projection.facts
    assert result["created_refs"]["fragment"] and result["studio_generation"] == 1
    document = result["document"]
    edit = {"document_id": document["id"], "expected_version": document["version"], "operations": [{"kind": "rename_document", "title": "Edited"}]}
    applied, applied_refs = h.invoke("shader_modify", edit)
    assert applied.status == "success", applied.error
    assert applied.output["document"]["version"] == 2
    assert applied.artifact_drafts[0].resource_refs == applied_refs
    stale, _ = h.invoke("shader_modify", edit)
    assert stale.status == "failed" and "STALE_VERSION" in stale.error
    noop, _ = h.invoke("shader_modify", {**edit, "expected_version": 2})
    assert noop.status == "success" and noop.output["changed"] is False
    undone, _ = h.invoke("shader_undo", {"document_id": document["id"], "expected_version": 2, "target_version": 1})
    assert undone.status == "success" and undone.output["document"]["version"] == 3
    assert undone.output["document"]["content_hash"] == document["content_hash"]
    assert h.store.resolve(refs[0]).generation == 0
    page, _ = h.invoke("shader_inspect", {"document_id": document["id"], "section": "summary", "version": 1})
    assert page.status == "success", page.error
    assert page.output["document"]["title"] == "Runtime"


def test_receipt_exact_actor_input_and_reopen(harness):
    h = harness
    invocation = str(uuid4())
    data = {"title": "Receipt", "expected_generation": 0}
    created, refs = h.invoke("shader_create", data, invocation)
    assert created.status == "success", created.error
    repeated, _ = h.invoke("shader_create", data, invocation, frozen=refs)
    assert repeated.output == created.output
    conflict, _ = h.invoke("shader_create", {**data, "title": "Other"}, invocation, frozen=refs)
    assert conflict.status == "failed" and "REQUEST_CONFLICT" in conflict.error
    human = h.operation("documents.create", {"title": "Human", "expected_generation": 1, "request_id": invocation})
    assert human.document.id != created.output["document"]["id"]
    store = h.modules.Store(h.store.path.parent)
    old = store.get(PROJECT, created.output["document"]["id"], 1)
    assert old.document.title == "Receipt"
    assert store.reconcile(PROJECT, "agent", str(uuid4()), "create", h.c.CreateInput(**data), 0) is None


def test_final_batch_validation_refs_and_atomicity(harness):
    h = harness
    first = h.create()
    fragment = first.created_refs["fragment"]
    source = "#version 300 es\nprecision highp float;\nout vec4 color;\nvoid main(){color=vec4(1.0);}\n"
    changed = h.apply(first.document, [{"kind": "stage_create", "stage_kind": "fragment", "title": "Replacement", "source": source, "ref": "replacement"}, {"kind": "pass_update", "pass_id": {"id": first.created_refs["pass"]}, "fragment_stage_id": {"ref": "replacement"}}, {"kind": "stage_remove", "stage_id": {"id": fragment}}])
    assert changed.document.version == 2
    for op in ({"kind": "stage_remove", "stage_id": {"id": changed.created_refs["replacement"]}}, {"kind": "stage_patch", "stage_id": {"id": changed.created_refs["replacement"]}, "old_text": "absent", "new_text": "x"}, {"kind": "pass_update", "pass_id": {"ref": "future"}, "title": "bad"}):
        with pytest.raises(DlcOperationError):
            h.apply(changed.document, [{"kind": "rename_document", "title": "Must roll back"}, op])
        assert h.store.get(PROJECT, first.document.id).document.title == "Shader"
        assert h.store.head(PROJECT, first.document.id).version == 2


def test_uniform_types_and_bool_cannot_be_number(harness):
    h = harness
    created = h.create()
    base = {"kind": "uniform_create", "pass_id": {"id": created.created_refs["pass"]}, "name": "strength", "type": "float", "value": 1.0, "ref": "strength"}
    updated = h.apply(created.document, [base])
    result, _ = h.invoke("uniform_set", {"document_id": created.document.id, "expected_version": 2, "uniform_id": updated.created_refs["strength"], "value": 0.8})
    assert result.status == "success", result.error
    for type_, value in (("float", True), ("int", 1.1), ("bool", 1), ("vec3", [1, 2]), ("vec3", [1, True, 2])):
        with pytest.raises(ValueError):
            h.c.Uniform(id=str(uuid4()), pass_id=created.created_refs["pass"], name="test", type=type_, value=value)
    assert h.c.PreviewSet.model_validate({"kind": "preview_set", "time_seconds": None}).time_seconds is None


def test_single_winner_concurrency_and_studio_fence(harness):
    h = harness
    created = h.create()
    frozen = (h.store.list_resources(PROJECT)[0].to_scope_ref(),)
    h.create("Unrelated")
    result, _ = h.invoke("shader_modify", {"document_id": created.document.id, "expected_version": 1, "operations": [{"kind": "rename_document", "title": "Old studio"}]}, frozen=frozen)
    assert result.status == "failed" and "STALE_VERSION" in result.error
    def writer(title):
        try:
            return h.apply(created.document, [{"kind": "rename_document", "title": title}]).document.version
        except DlcOperationError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(writer, ["A", "B"]))
    assert sorted(map(str, outcomes)) == ["2", "STALE_VERSION"]


def test_texture_version_pages_and_removed_history(harness):
    h = harness
    created = h.create()
    raw = bytes(range(256)) * 512
    uploaded = h.apply(created.document, [{"kind": "texture_create", "ref": "image", "title": "Image", "width": 256, "height": 128, "rgba_base64": base64.b64encode(raw).decode("ascii")}])
    texture = uploaded.created_refs["image"]
    parameters = {"document_id": created.document.id, "version": 2, "section": "texture_bytes", "texture_id": texture, "limit": 16384}
    result = bytearray()
    while len(result) < len(raw):
        page = h.operation("documents.get", {**parameters, "offset": len(result)})
        assert len(h.c.encoded(page.model_dump(mode="json", exclude_none=True))) <= 32768
        result.extend(base64.b64decode(page.texture_bytes.rgba_base64))
        assert page.texture_bytes.content_hash == sha256(raw).hexdigest()
        assert page.next_offset == len(result)
    assert bytes(result) == raw and page.has_more is False
    removed = h.apply(uploaded.document, [{"kind": "texture_remove", "texture_id": {"id": texture}}])
    assert h.operation("documents.get", parameters).texture_bytes.total_bytes == len(raw)
    with pytest.raises(DlcOperationError):
        h.operation("documents.get", {**parameters, "version": removed.document.version})
    with pytest.raises(DlcOperationError):
        h.operation("documents.get", parameters, project="foreign")
    for extra in ({"version": None}, {"offset": True}, {"offset": -1}, {"content_hash": "0"*64}):
        with pytest.raises(ValueError):
            h.operation("documents.get", {**parameters, **extra})
    inspection = importlib.import_module(h.modules.__package__ + ".inspection")
    with pytest.raises(ValueError, match="cancelled"):
        inspection.get_page(h.store, PROJECT, h.c.GetInput(**parameters), lambda: True)


def test_history_quota_and_corrupt_payload_fail_closed(harness):
    h = harness
    created = h.create()
    with sqlite3.connect(h.store.path) as db:
        charged = db.execute("SELECT payload_bytes FROM quota").fetchone()[0]
    h.store.history_limit = charged + 5
    with pytest.raises(DlcOperationError, match="quota"):
        h.apply(created.document, [{"kind": "rename_document", "title": "Refused"}])
    assert h.store.get(PROJECT, created.document.id).version == 1
    with sqlite3.connect(h.store.path) as db:
        db.execute("UPDATE quota SET payload_bytes=payload_bytes+1")
    with pytest.raises(ValueError, match="accounting"):
        h.store.get(PROJECT, created.document.id)


def test_simulated_preview_contract_pixels_and_reconcile(harness):
    h = harness
    created = h.create()
    resized = h.apply(created.document, [{"kind": "preview_set", "width": 2, "height": 2}])
    lease = attach(h)
    invocation = str(uuid4())
    request_input = {"document_id": created.document.id, "expected_version": resized.document.version}
    bottom_left = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "render_preview", request_input, invocation)
        request = claim(h, lease)
        receipt = complete_payload(lease, request, {"compiled": True, "rendered": True, "diagnostics": [], "logs": [], "rgba_base64": base64.b64encode(bottom_left).decode("ascii"), "width": 2, "height": 2, "row_order": "bottom-left"})
        assert h.operation("compute.complete", receipt).accepted
        result, refs = future.result(timeout=3)
    assert result.status == "success", result.error
    assert len(result.artifact_drafts) == 2
    report, pixels = h.store.report(PROJECT, result.output["report_id"])
    assert pixels == bottom_left[8:] + bottom_left[:8]
    assert report.pixel_hash == sha256(pixels).hexdigest()
    repeated, _ = h.invoke("render_preview", request_input, invocation, frozen=refs)
    assert repeated.output == result.output and h.bridge.pending is None
    with pytest.raises(DlcOperationError):
        h.operation("compute.complete", receipt)
    representation = importlib.import_module(h.modules.__package__ + ".representation")
    encoded = representation.png_bytes(2, 2, pixels)
    png = importlib.import_module(h.modules.__package__ + ".vendor.png")
    width, height, rows, info = png.Reader(bytes=encoded).asRGBA8()
    assert (width, height) == (2, 2) and bytes(value for row in rows for value in row) == pixels
    # Independent stdlib framing/CRC/DEFLATE check, separate from PyPNG's decoder.
    assert encoded[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed = 8, bytearray()
    while offset < len(encoded):
        length = struct.unpack_from(">I", encoded, offset)[0]
        kind = encoded[offset+4:offset+8]
        body = encoded[offset+8:offset+8+length]
        assert zlib.crc32(kind+body) == struct.unpack_from(">I", encoded, offset+8+length)[0]
        if kind == b"IHDR":
            assert struct.unpack(">IIBBBBB", body) == (2, 2, 8, 6, 0, 0, 0)
        elif kind == b"IDAT":
            compressed.extend(body)
        offset += 12+length
    assert zlib.decompress(compressed) == b"\x00"+pixels[:8]+b"\x00"+pixels[8:]
    draft = result.artifact_drafts[-1]
    artifact = Artifact(id="preview", session_id="s", run_id="r", type=draft.type, title=draft.title, payload=draft.payload, resource_refs=draft.resource_refs)
    provider = representation.Representation(h.store, h.c.PREVIEW_ARTIFACT, "dbfox.shader.preview.v1")
    sample = provider.execute(artifact, ArtifactRepresentationRequest(operation="sample", parameters={"width": 2, "height": 2}), ArtifactRepresentationContext(artifact_loader=lambda _: None))
    assert bytes(sample.payload["rgba"]) == pixels and sample.consistency == "durable_snapshot"


@pytest.mark.parametrize("field,bad", [("claim", "0"*64), ("invocation_id", "foreign"), ("version", 999), ("document_id", "00000000-0000-0000-0000-000000000000"), ("content_hash", "0"*64), ("request_hash", "0"*64), ("package_digest", "0"*64)])
def test_compute_claim_fences(harness, field, bad):
    h = harness
    created = h.create()
    lease = attach(h)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "compile", {"document_id": created.document.id, "expected_version": 1})
        request = claim(h, lease)
        receipt = complete_payload(lease, request, {"compiled": True, "rendered": False})
        with pytest.raises(DlcOperationError):
            h.operation("compute.complete", {**receipt, field: bad})
        h.operation("compute.complete", receipt)
        result, _ = future.result(timeout=3)
    assert result.status == "success", result.error


def test_compile_error_report_and_edit_during_compute(harness):
    h = harness
    created = h.create()
    lease = attach(h)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "compile", {"document_id": created.document.id, "expected_version": 1})
        request = claim(h, lease)
        h.operation("compute.complete", complete_payload(lease, request, {"compiled": False, "rendered": False, "diagnostics": [{"severity": "error", "code": "COMPILE_ERROR", "message": "Test boundary compiler error", "stage_id": created.created_refs["fragment"]}]}))
        result, _ = future.result(timeout=3)
        assert result.status == "success" and result.output["compiled"] is False
        future = pool.submit(h.invoke, "compile", {"document_id": created.document.id, "expected_version": 1})
        request = claim(h, lease)
        h.apply(created.document, [{"kind": "rename_document", "title": "Changed"}])
        h.operation("compute.complete", complete_payload(lease, request, {"compiled": True, "rendered": False}))
        stale, _ = future.result(timeout=3)
    assert stale.status == "failed" and "STALE_VERSION" in stale.error
    with sqlite3.connect(h.store.path) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 1


def test_compute_busy_epoch_timeout_cancel_restart(harness):
    h = harness
    created = h.create()
    client = str(uuid4())
    lease = attach(h, client=client)
    with pytest.raises(DlcOperationError):
        attach(h, client=client)
    with pytest.raises(DlcOperationError):
        attach(h)
    newer = attach(h, counter=2, client=client)
    with pytest.raises(DlcOperationError):
        h.operation("compute.detach", {"epoch": lease["epoch"], "lease": lease["lease"], "reason": "deactivate"})
    h.bridge.deadline_seconds = .1
    result, _ = h.invoke("compile", {"document_id": created.document.id, "expected_version": 1})
    assert result.status == "failed" and "TIMEOUT" in result.error
    assert h.bridge.pending is None
    revision, snapshot = h.store.compute_snapshot(PROJECT, h.c.VersionInput(document_id=created.document.id, expected_version=1), 1)
    cancelled = threading.Event()
    h.bridge.deadline_seconds = 10
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.bridge.execute, "cancelled-invocation", revision, snapshot, "compile", cancelled.is_set)
        request = claim(h, newer)
        cancelled.set()
        with pytest.raises(ValueError, match="cancelled"):
            future.result(timeout=2)
    with pytest.raises(DlcOperationError):
        h.operation("compute.complete", complete_payload(newer, request, {"compiled": True, "rendered": False}))
    restarted = h.modules.ComputeBridge(DIGEST)
    with pytest.raises(ValueError, match="unknown"):
        restarted.next(h.c.LeaseInput(**newer))


def test_source_observation_and_context_budgets(harness):
    h = harness
    created = h.create("Title " * 20)
    source = "//" + "界" * 500 + "\n"
    changed = h.apply(created.document, [{"kind": "stage_replace", "stage_id": {"id": created.created_refs["fragment"]}, "source": source * 100}])
    result, _ = h.invoke("shader_inspect", {"document_id": created.document.id, "version": changed.document.version, "section": "source", "stage_id": created.created_refs["fragment"], "limit": 50})
    assert result.status == "success", result.error
    tool = next(item for item in h.staged.tools if item.name == "shader_inspect")
    observation = tool.project_observation(status="success", output=result.output, artifacts=())
    assert len(h.c.encoded(observation.facts)) <= 8192
    assert len(h.c.encoded(observation.provider_payload)) <= 16384
    assert "source" not in observation.facts and observation.provider_payload["has_more"]
    contributor = h.modules.ShaderContext(h.store)
    fragments = contributor.build(ContextContributionInput(session_id="s", run_id="r", current_request="x", resource_refs=(ResourceScopeRef(kind=STUDIO, id=PROJECT, version=2),)))
    assert len(fragments) == 1 and len(fragments[0].content) <= 4000
    assert source not in fragments[0].content and "not_compiled" in fragments[0].content


def signed_snapshot(tmp_path):
    """Sign actual owner backend. Frontend is tested only once its real entry exists."""
    if (SOURCE / "frontend" / "index.js").is_file():
        source = SOURCE
    else:
        source = tmp_path / "backend-package-source"
        source.mkdir()
        shutil.copytree(SOURCE / "backend", source / "backend", ignore=shutil.ignore_patterns("__pycache__"))
        manifest = json.loads((SOURCE / "manifest.template.json").read_text(encoding="utf-8"))
        manifest["entrypoints"].pop("frontend")
        (source / "manifest.template.json").write_text(json.dumps(manifest), encoding="utf-8")
    key = Ed25519PrivateKey.from_private_bytes(sha256(b"Shader test fixture; never a production signing key").digest())
    built = build_dlc_package_from_source(source, private_key=key)
    archive = tmp_path / "shader.dbfox-dlc"
    archive.write_bytes(built.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest, expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(OWNER, True)
    active = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert active.activation_failures == ()
    return service, active


def test_signed_package_activation_persistence_and_backend_epoch_reset(tmp_path):
    service, active = signed_snapshot(tmp_path)
    assert len(active.tools) == 13 and len(active.operations) == 16
    create = active.get_operation(OWNER, "documents.create").spec
    created = create.handler(create.input_model.model_validate({"title": "Installed", "expected_generation": 0, "request_id": str(uuid4())}), DlcOperationContext(dlc_id=OWNER, operation_name="documents.create", project_id=PROJECT))
    service.set_desired_enabled(OWNER, False)
    disabled = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert not disabled.tools and not disabled.operations and not disabled.resource_resolvers
    service.set_desired_enabled(OWNER, True)
    restored = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert restored.activation_failures == ()
    operation = restored.get_operation(OWNER, "documents.get").spec
    page = operation.handler(operation.input_model.model_validate({"document_id": created.document.id}), DlcOperationContext(dlc_id=OWNER, operation_name="documents.get", project_id=PROJECT))
    assert page.document.title == "Installed" and page.document.version == 1
    assert restored.tools[0].tool.bridge.executor is None


def test_actual_action_run_and_historical_representation(tmp_path, db_session):
    db_session.add(Project(id=PROJECT, name="Shader action"))
    db_session.commit()
    _, snapshot = signed_snapshot(tmp_path)
    create = snapshot.get_operation(OWNER, "documents.create").spec
    created = create.handler(create.input_model.model_validate({"title": "Action", "expected_generation": 0, "request_id": str(uuid4())}), DlcOperationContext(dlc_id=OWNER, operation_name="documents.create", project_id=PROJECT))
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    action_runs = build_dlc_action_runs_host(dlc_id=OWNER, project_id=PROJECT, snapshot=snapshot, session_factory=factory)
    operation = snapshot.get_operation(OWNER, "documents.export").spec
    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        exported = operation.handler(operation.input_model.model_validate({"document_id": created.document.id, "expected_version": 1, "request_id": str(uuid4())}), DlcOperationContext(dlc_id=OWNER, operation_name="documents.export", project_id=PROJECT, action_runs=action_runs))
    finally:
        set_active_runtime_snapshot(previous)
    with factory() as db:
        run = db.get(AgentRun, exported.run_id)
        assert run.status == "completed"
        artifacts = ArtifactRepository(db).list_for_run(exported.run_id)
        assert [a.id for a in artifacts] == exported.artifact_ids
        assert artifacts[0].resource_refs[0].kind == STUDIO
    delete = snapshot.get_operation(OWNER, "documents.delete").spec
    deleted = delete.handler(delete.input_model.model_validate({"document_id": created.document.id, "expected_version": 1, "request_id": str(uuid4())}), DlcOperationContext(dlc_id=OWNER, operation_name="documents.delete", project_id=PROJECT))
    assert deleted.document.deleted
    provider = next(item.provider for item in snapshot.artifact_representations if item.representation_type == "dbfox.shader.document.v1")
    result = provider.execute(artifacts[0], ArtifactRepresentationRequest(operation="page", parameters={"section": "source", "stage_id": created.created_refs["fragment"]}), ArtifactRepresentationContext(artifact_loader=lambda _: None))
    assert result.payload["document"]["version"] == 1 and "#version 300 es" in result.payload["source"]
    with pytest.raises(ArtifactRepresentationError):
        provider.execute(artifacts[0], ArtifactRepresentationRequest(operation="page", parameters={"document_id": str(uuid4())}), ArtifactRepresentationContext(artifact_loader=lambda _: None))


def test_signed_runloop_only_observations_drive_same_run_edits(tmp_path, db_session):
    _, snapshot = signed_snapshot(tmp_path)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    registry = build_product_tool_registry(snapshot)
    db_session.add(Project(id=PROJECT, name="Shader RunLoop"))
    db_session.flush()
    db_session.add(AgentSession(id="shader-session", project_id=PROJECT))
    db_session.commit()
    observed = {}
    requests = []

    class Provider:
        def stream(self, *, messages, tools, **kwargs):
            for message in messages:
                if message.get("type") == "function_call_output":
                    observed[message["call_id"]] = json.loads(message["output"])
            index = len(requests)
            if index == 0:
                name, payload = "shader_create", {"title": "Observed", "expected_generation": 0}
            else:
                created = observed["step-0"]["facts"]
                document = created["document"]
                if index == 1:
                    name, payload = "shader_inspect", {"document_id": document["id"], "version": document["version"], "section": "source", "stage_id": created["created_refs"]["fragment"]}
                elif index == 2:
                    assert observed["step-1"]["status"] == "succeeded", observed["step-1"]
                    name, payload = "shader_modify", {"document_id": document["id"], "expected_version": document["version"], "operations": [{"kind": "stage_patch", "stage_id": {"id": created["created_refs"]["fragment"]}, "old_text": "0.5", "new_text": "0.8"}]}
                elif index == 3:
                    name, payload = requests[2]
                elif index == 4:
                    assert observed["step-3"]["status"] == "failed" and "STALE_VERSION" in observed["step-3"]["error_message"]
                    name, payload = "shader_inspect", {"document_id": document["id"], "section": "summary"}
                elif index == 5:
                    current = observed["step-4"]["facts"]["document"]
                    name, payload = "shader_modify", {"document_id": current["id"], "expected_version": current["version"], "operations": [{"kind": "rename_document", "title": current["title"]}]}
                elif index == 6:
                    assert observed["step-5"]["facts"]["changed"] is False
                    name, payload = "shader_undo", {"document_id": document["id"], "expected_version": observed["step-5"]["facts"]["document"]["version"], "target_version": document["version"]}
                elif index == 7:
                    name, payload = "shader_diff", {"document_id": document["id"], "from_version": document["version"], "to_version": observed["step-2"]["facts"]["document"]["version"], "section": "source", "stage_id": created["created_refs"]["fragment"]}
                elif index == 8:
                    current = observed["step-6"]["facts"]["document"]
                    name, payload = "shader_export", {"document_id": current["id"], "expected_version": current["version"]}
                else:
                    assert observed["step-8"]["status"] == "succeeded", observed["step-8"]
                    yield from ScriptedProvider(answer_events("Created, inspected, incrementally edited, restored, compared, and exported the Shader document. GPU compilation was not requested.")).stream()
                    return
            wire = registry.provider_name_for_key(ToolKey(owner_id=OWNER, local_name=name))
            assert wire in {tool["name"] for tool in tools}
            requests.append((name, payload))
            yield from ScriptedProvider(tool_call_events(call_id=f"step-{index}", tool_name=wire, arguments=payload)).stream()

    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        with factory() as db:
            refs = authorize_project_resources(db, PROJECT, (RequestedResourceRef(kind=STUDIO, id=PROJECT),), snapshot=snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id="shader-session", resource_refs=refs, content="Create and edit a shader document; export its revision without GPU compilation.", idempotency_key="shader-runloop", llm_credential_id="scripted", api_base=None, model_name="scripted", request_payload={})
            lease = sessions.claim(session_id="shader-session", owner="shader-test", ttl_seconds=600)
            sessions.promote_next_input(lease=lease)
            db.commit()
        loop = RunLoop(session_factory=factory, model_factory=lambda settings: Provider(), registry=registry, context_contributors=default_context_contributors(snapshot), capability_guidance=default_capability_guidance(snapshot), resource_providers=snapshot.resource_providers, resource_resolver=build_attempt_resource_resolver(snapshot=snapshot), artifact_payload_contract_resolver=lambda kind, version: snapshot.get_artifact_contract(kind, version).validator, runtime_snapshot_id=snapshot.snapshot_id, completion=CompletionGate(build_default_completion_policy(snapshot)), definition=AgentDefinition(limits=RunLimits(max_turns=20, max_tool_invocations=20, max_repair_attempts=3, finalization_turn_reserve=1, finalization_tool_reserve=1, max_prompt_tokens=128_000)), live_stream=LiveStreamHub())
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
    finally:
        set_active_runtime_snapshot(previous)
    assert len(requests) == len(observed) == 9
    assert observed["step-6"]["facts"]["document"]["version"] == 3
    with factory() as db:
        assert db.get(AgentRun, admission.run_id).status == "completed"
        calls = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        records = db.query(AgentObservationRecord).filter_by(run_id=admission.run_id).all()
        assert len(calls) == len(records) == 9
        artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
        for artifact in artifacts:
            invocation = next(item for item in calls if item.id == artifact.provenance["tool_invocation_id"])
            assert artifact.resource_refs[0].model_dump() in json.loads(invocation.resource_refs_json)


def test_limits_schema_source_and_pass_graph(harness):
    h = harness
    created = h.create()
    doc = h.store.get(PROJECT, created.document.id).document.model_dump(mode="json")
    for invalid in (True, 1., "1", 2):
        with pytest.raises(ValueError):
            h.c.Document.model_validate({**doc, "schema_version": invalid})
    for source in ("x"*2049, "\n"*16384, ("界"*680+"\n")*129):
        with pytest.raises(ValueError):
            h.c.Stage(id=str(uuid4()), kind="fragment", title="x", source=source)
    vertex, fragment, first = (created.created_refs[name] for name in ("vertex", "fragment", "pass"))
    operations = [{"kind": "pass_update", "pass_id": {"id": first}, "width": 1, "height": 1}]
    operations.extend({"kind": "pass_create", "title": "pass", "vertex_stage_id": {"id": vertex}, "fragment_stage_id": {"id": fragment}, "width": 1, "height": 1, "clear_color": [0, 0, 0, 1], "ref": f"p{i}"} for i in range(31))
    maximum = h.apply(created.document, operations)
    assert len(h.store.get(PROJECT, created.document.id).document.passes) == 32
    with pytest.raises(DlcOperationError):
        h.apply(maximum.document, [operations[-1]])
    with pytest.raises(DlcOperationError):
        h.apply(maximum.document, [{"kind": "binding_set", "pass_id": {"id": first}, "name": "image", "source": {"kind": "pass", "pass_id": {"id": maximum.created_refs["p0"]}}}])
    valid = h.apply(maximum.document, [{"kind": "binding_set", "pass_id": {"id": maximum.created_refs["p0"]}, "name": "image", "source": {"kind": "pass", "pass_id": {"id": first}}}])
    ids = [value.id for value in h.store.get(PROJECT, created.document.id).document.passes]
    with pytest.raises(DlcOperationError):
        h.apply(valid.document, [{"kind": "pass_reorder", "pass_ids": [{"id": value} for value in reversed(ids)]}])
    with pytest.raises(ValueError):
        h.c.ApplyInput(document_id=created.document.id, expected_version=valid.document.version, operations=[{"kind": "rename_document", "title": "x"}]*65)


@pytest.mark.parametrize("corruption", ["payload_hash", "head", "generation", "identity", "blob_type"])
def test_corruption_fails_closed_before_use(harness, corruption):
    h = harness
    created = h.create()
    with sqlite3.connect(h.store.path) as db:
        if corruption == "payload_hash":
            db.execute("UPDATE revisions SET hash=?", ("0"*64,))
        elif corruption == "head":
            db.execute("UPDATE heads SET version=2")
        elif corruption == "generation":
            db.execute("UPDATE studios SET generation=2")
        elif corruption == "identity":
            db.execute("DELETE FROM identities WHERE id=?", (created.created_refs["fragment"],))
        else:
            db.execute("UPDATE revisions SET payload=CAST(payload AS TEXT)")
    with pytest.raises(ValueError):
        h.store.get(PROJECT, created.document.id)


def test_atomic_report_receipt_failure_and_lost_settlement_recovery(harness, monkeypatch):
    h = harness
    created = h.create()
    lease = attach(h)
    original = h.store.save_receipt
    def crash(*args, **kwargs):
        raise RuntimeError("Simulated crash before transaction commit")
    monkeypatch.setattr(h.store, "save_receipt", crash)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "compile", {"document_id": created.document.id, "expected_version": 1})
        request = claim(h, lease)
        h.operation("compute.complete", complete_payload(lease, request, {"compiled": True, "rendered": False}))
        result, _ = future.result(timeout=3)
    assert result.status == "failed"
    with sqlite3.connect(h.store.path) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    monkeypatch.setattr(h.store, "save_receipt", original)
    invocation = str(uuid4())
    payload = {"document_id": created.document.id, "expected_version": 1}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "compile", payload, invocation)
        request = claim(h, lease)
        h.operation("compute.complete", complete_payload(lease, request, {"compiled": True, "rendered": False}))
        result, refs = future.result(timeout=3)
    assert result.status == "success"
    # No executor is available after restart, so successful recovery cannot rerun GPU.
    h.bridge.executor = None
    recovered = h.runtime.reconcile(tool_name=provider_tool_name(OWNER, "compile"), raw_input=payload, request=None, invocation_id=invocation, idempotency_key=invocation, scope_refs=refs, resources={ref.canonical(): h.store.resolve(ref) for ref in refs})
    assert recovered.status == "success" and recovered.output == result.output
    unknown = h.runtime.reconcile(tool_name=provider_tool_name(OWNER, "compile"), raw_input=payload, request=None, invocation_id=str(uuid4()), idempotency_key="unknown", scope_refs=refs, resources={ref.canonical(): h.store.resolve(ref) for ref in refs})
    assert unknown.status == "failed"


def test_unrelated_document_edit_does_not_stale_compute_but_detach_before_commit_does(harness, monkeypatch):
    h = harness
    first, other = h.create("First"), h.create("Other")
    lease = attach(h)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "compile", {"document_id": first.document.id, "expected_version": 1})
        request = claim(h, lease)
        h.apply(other.document, [{"kind": "rename_document", "title": "Other changed"}])
        h.operation("compute.complete", complete_payload(lease, request, {"compiled": True, "rendered": False}))
        result, _ = future.result(timeout=3)
        assert result.status == "success", result.error
        original = h.store.make_report
        def detach_first(*args, **kwargs):
            h.operation("compute.detach", {"epoch": lease["epoch"], "lease": lease["lease"], "reason": "hidden"})
            return original(*args, **kwargs)
        monkeypatch.setattr(h.store, "make_report", detach_first)
        future = pool.submit(h.invoke, "compile", {"document_id": first.document.id, "expected_version": 1})
        request = claim(h, lease)
        h.operation("compute.complete", complete_payload(lease, request, {"compiled": True, "rendered": False}))
        result, _ = future.result(timeout=3)
        assert result.status == "failed" and "EXECUTOR_UNAVAILABLE" in result.error
    with sqlite3.connect(h.store.path) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 1


def test_final_contract_schema_matches_actual_operations(harness):
    h = harness
    expected = json.loads((SOURCE / "contracts.schema.json").read_text(encoding="utf-8"))
    for spec in h.staged.operations:
        assert expected["operations"][spec.name] == {"scope": spec.scope, "max_output_bytes": spec.max_output_bytes, "input": spec.input_model.model_json_schema(), "output": spec.output_model.model_json_schema()}
    assert expected["document"] == h.c.Document.model_json_schema()
    assert expected["representation_parameters"] == h.c.ReadParameters.model_json_schema()


def test_active_document_cap_tombstone_restore_and_undo_of_undo(harness):
    h = harness
    first = h.create("First")
    for _ in range(127):
        h.create("Other")
    with pytest.raises(DlcOperationError, match="128"):
        h.create("Too many")
    deleted = h.operation("documents.delete", {"document_id": first.document.id, "expected_version": 1, "request_id": str(uuid4())})
    h.create("Freed active slot")
    with pytest.raises(DlcOperationError, match="128"):
        h.operation("documents.undo", {"document_id": first.document.id, "expected_version": 2, "target_version": 1, "request_id": str(uuid4())})
    assert h.store.get(PROJECT, first.document.id).deleted
    page = h.operation("documents.list", {"limit": 50})
    assert page.total == 128 and len(page.items) == 50 and page.has_more
    assert deleted.document.version == 2


@pytest.mark.parametrize("action", ["compile", "preview"])
def test_actual_action_run_compute_protocol_with_simulated_gpu_receipt(tmp_path, db_session, action):
    """Real signed action/Tool/settlement; the receipt is explicitly not real WebGL."""
    db_session.add(Project(id=PROJECT, name="Shader action compute"))
    db_session.commit()
    _, snapshot = signed_snapshot(tmp_path)
    def operation(name, payload, action_runs=None):
        spec = snapshot.get_operation(OWNER, name).spec
        return spec.handler(spec.input_model.model_validate(payload), DlcOperationContext(dlc_id=OWNER, operation_name=name, project_id=PROJECT if spec.scope == "project" else None, action_runs=action_runs))
    created = operation("documents.create", {"title": "Action compute", "expected_generation": 0, "request_id": str(uuid4())})
    updated = operation("documents.apply", {"document_id": created.document.id, "expected_version": 1, "request_id": str(uuid4()), "operations": [{"kind": "preview_set", "width": 1, "height": 1}]})
    package = snapshot.tools[0].tool.bridge.package_digest
    attached = operation("compute.attach", {"client_id": str(uuid4()), "registration_counter": 1, "package_digest": package, "available": True, "capabilities": caps()})
    lease = {"epoch": attached.epoch, "lease": attached.lease, "registration_counter": 1}
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    action_runs = build_dlc_action_runs_host(dlc_id=OWNER, project_id=PROJECT, snapshot=snapshot, session_factory=factory)
    previous = active_runtime_snapshot()
    set_active_runtime_snapshot(snapshot)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(operation, "documents." + action, {"document_id": created.document.id, "expected_version": updated.document.version, "request_id": str(uuid4())}, action_runs)
            deadline = time.monotonic()+3
            request = None
            while time.monotonic() < deadline:
                page = operation("compute.next", lease)
                if page.status == "request":
                    request = page.request
                    break
                time.sleep(.005)
            assert request is not None
            observed = {"compiled": True, "rendered": action == "preview"}
            if action == "preview":
                observed.update(rgba_base64="/wAA/w==", width=1, height=1, row_order="bottom-left")
            payload = complete_payload(lease, request, observed)
            payload["package_digest"] = package
            operation("compute.complete", payload)
            completed = future.result(timeout=5)
    finally:
        set_active_runtime_snapshot(previous)
    with factory() as db:
        run = db.get(AgentRun, completed.run_id)
        assert run.status == "completed"
        artifacts = ArtifactRepository(db).list_for_run(completed.run_id)
        assert len(artifacts) == (2 if action == "preview" else 1)
        assert completed.outcome["compiled"] is True
        assert completed.outcome["rendered"] is (action == "preview")


@pytest.mark.parametrize("result", [
    {"compiled": False, "rendered": True, "rgba_base64": "/wAA/w==", "width": 1, "height": 1, "row_order": "bottom-left"},
    {"compiled": True, "rendered": False, "rgba_base64": "/wAA/w=="},
    {"compiled": True, "rendered": False, "diagnostics": [{"severity": "error", "code": "TYPE_MISMATCH", "message": "error"}]},
    {"compiled": False, "rendered": False},
])
def test_compute_result_combinations_fail_closed(harness, result):
    h = harness
    created = h.create()
    lease = attach(h)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(h.invoke, "compile", {"document_id": created.document.id, "expected_version": 1})
        request = claim(h, lease)
        with pytest.raises(DlcOperationError):
            h.operation("compute.complete", complete_payload(lease, request, result))
        h.operation("compute.detach", {"epoch": lease["epoch"], "lease": lease["lease"], "reason": "context_lost"})
        failed, _ = future.result(timeout=3)
    assert failed.status == "failed"
    with sqlite3.connect(h.store.path) as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
