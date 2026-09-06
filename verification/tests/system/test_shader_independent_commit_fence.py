"""Independent cancellation at the actual receipt/SQLite commit boundary."""
from __future__ import annotations

from threading import Event
from concurrent.futures import ThreadPoolExecutor
import time
from uuid import uuid4

from dbfox_dlc_api import ResourceScopeRef, ToolKey
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


def test_cancel_after_receipt_insert_before_commit_leaves_no_created_document(tmp_path, monkeypatch):
    with ShaderRuntime(tmp_path) as runtime:
        owner = next(item.tool for item in runtime.snapshot.tools if item.owner_id == "dbfox.shader" and item.tool.name == "shader_create")
        cancelled = Event()
        entered = Event()
        save_receipt = owner.store.save_receipt

        def cancel_before_commit(*args, **kwargs):
            save_receipt(*args, **kwargs)
            entered.set()
            cancelled.set()

        # Retain the actual receipt insert and charge; inject only the cancellation
        # signal while its original transaction is still uncommitted.
        monkeypatch.setattr(owner.store, "save_receipt", cancel_before_commit)
        project_id = str(uuid4())
        scope = ResourceScopeRef(kind="dbfox.shader.studio", id=project_id, version=0)
        resources = build_attempt_resource_resolver(snapshot=runtime.snapshot).resolve((scope,))
        identity = str(uuid4())
        result = ToolRuntime(runtime.registry).invoke(
            tool_name=runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.shader", local_name="shader_create")),
            raw_input={"title": "Must roll back before commit", "expected_generation": 0}, request=None,
            invocation_id=identity, idempotency_key=identity, scope_refs=(scope,), resources=resources,
            cancellation_probe=cancelled.is_set,
        )
        assert entered.is_set() and result.status == "failed"
        visible = runtime.operation(project_id, "documents.list", {})
        assert visible["studio_generation"] == 0 and visible["items"] == [], visible
        with owner.store.connection() as db:
            assert db.execute("SELECT count(*) FROM receipts WHERE request_id=?", (identity,)).fetchone()[0] == 0


def test_cancel_after_report_receipt_insert_does_not_publish_even_failure_evidence(tmp_path, monkeypatch):
    """Controlled negative bridge reply is protocol evidence, never successful GPU proof."""
    with ShaderRuntime(tmp_path) as runtime:
        project_id = str(uuid4())
        created = runtime.operation(project_id, "documents.create", {
            "title": "Cancellation report boundary", "expected_generation": 0, "request_id": str(uuid4())})
        owner = next(item.tool for item in runtime.snapshot.tools if item.owner_id == "dbfox.shader" and item.tool.name == "compile")
        lease = runtime.operation(project_id, "compute.attach", {"client_id": str(uuid4()), "registration_counter": 1,
            "package_digest": runtime.package.package_digest, "available": True, "capabilities": {
                "version": "independent negative protocol fixture", "shading_language_version": "no real GPU claimed",
                "max_texture_size": 4096, "max_renderbuffer_size": 4096, "max_texture_image_units": 16,
                "max_combined_texture_image_units": 32, "max_fragment_uniform_vectors": 1024,
                "max_vertex_uniform_vectors": 1024, "parallel_shader_compile": False}})
        lease_input = {"epoch": lease["epoch"], "lease": lease["lease"], "registration_counter": 1}
        cancelled, entered = Event(), Event()
        save_receipt = owner.store.save_receipt

        def cancel_before_commit(*args, **kwargs):
            save_receipt(*args, **kwargs)
            entered.set()
            cancelled.set()

        monkeypatch.setattr(owner.store, "save_receipt", cancel_before_commit)
        scope = ResourceScopeRef(kind="dbfox.shader.studio", id=project_id, version=1)
        resources = build_attempt_resource_resolver(snapshot=runtime.snapshot).resolve((scope,))
        identity = str(uuid4())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(ToolRuntime(runtime.registry).invoke,
                tool_name=runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.shader", local_name="compile")),
                raw_input={"document_id": created["document"]["id"], "expected_version": 1}, request=None,
                invocation_id=identity, idempotency_key=identity, scope_refs=(scope,), resources=resources,
                cancellation_probe=cancelled.is_set)
            request = None
            deadline = time.monotonic() + 3
            while request is None and time.monotonic() < deadline:
                request = runtime.operation(project_id, "compute.next", lease_input)["request"]
                if request is None and future.done():
                    raise AssertionError(future.result())
            assert request is not None
            proof = {key: request[key] for key in ("request_id", "claim", "invocation_id", "document_id", "version", "content_hash", "request_hash")}
            runtime.operation(project_id, "compute.complete", {**lease_input, **proof, "package_digest": runtime.package.package_digest,
                "result": {"compiled": False, "rendered": False, "diagnostics": [{"severity": "error", "code": "INDEPENDENT_NEGATIVE_FIXTURE", "message": "Controlled negative protocol response"}], "logs": [], "log_truncated": 0}})
            result = future.result(timeout=5)
        assert entered.is_set() and result.status == "failed"
        with owner.store.connection() as db:
            assert db.execute("SELECT count(*) FROM reports WHERE project=?", (project_id,)).fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM receipts WHERE request_id=?", (identity,)).fetchone()[0] == 0
