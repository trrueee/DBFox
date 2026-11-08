"""Separate signed-owner protocol attacks, NOT real GPU/driver evidence.

Every controlled executor response reports an explicit fixture compiler error.
Only timing/fault boundaries are injected; registered operations and ToolRuntime
perform all computation admission, receipt settlement and reconciliation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json
import sqlite3
import time
from uuid import uuid4

import pytest

from dbfox_dlc_api import DlcOperationError, ResourceScopeRef, ToolKey
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


class Protocol:
    def __init__(self, runtime):
        self.runtime = runtime
        self.project = str(uuid4())
        self.created = runtime.operation(self.project, "documents.create", {
            "title": "Negative protocol fixture", "expected_generation": 0, "request_id": str(uuid4())})
        self.document = self.created["document"]
        self.owner = next(item.tool for item in runtime.snapshot.tools
            if item.owner_id == "dbfox.shader" and item.tool.name == "compile")
        self.client = str(uuid4())
        self.attach_input = {"client_id": self.client, "registration_counter": 1,
            "package_digest": runtime.package.package_digest, "available": True,
            "capabilities": {"version": "Adversarial protocol fault fixture", "shading_language_version": "No GPU success claimed",
                "max_texture_size": 4096, "max_renderbuffer_size": 4096,
                "max_texture_image_units": 16, "max_combined_texture_image_units": 32,
                "max_fragment_uniform_vectors": 1024, "max_vertex_uniform_vectors": 1024,
                "parallel_shader_compile": False}}
        lease = self.machine("compute.attach", self.attach_input)
        self.lease = {"epoch": lease["epoch"], "lease": lease["lease"], "registration_counter": 1}
        self.scope = ResourceScopeRef(kind="dbfox.shader.studio", id=self.project, version=1)
        self.invocation = str(uuid4())
        self.payload = {"document_id": self.document["id"], "expected_version": 1}

    def machine(self, name, payload):
        return self.runtime.operation(None, name, payload)

    def invoke(self, *, recover=False, name="compile", payload=None, invocation=None):
        resources = build_attempt_resource_resolver(snapshot=self.runtime.snapshot).resolve((self.scope,))
        method = ToolRuntime(self.runtime.registry).reconcile if recover else ToolRuntime(self.runtime.registry).invoke
        return method(tool_name=self.runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.shader", local_name=name)),
            raw_input=payload if payload is not None else self.payload, request=None,
            invocation_id=invocation or self.invocation, idempotency_key=invocation or self.invocation,
            scope_refs=(self.scope,), resources=resources)

    @contextmanager
    def requested(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.invoke)
            deadline = time.monotonic() + 3
            request = None
            while time.monotonic() < deadline:
                request = self.machine("compute.next", self.lease)["request"]
                if request is not None:
                    break
                assert not future.done(), future.result() if future.done() else ""
                time.sleep(.005)
            assert request is not None
            proof = {key: request[key] for key in ("request_id", "claim", "invocation_id", "document_id", "version", "content_hash", "request_hash")}
            reply = {**self.lease, **proof, "package_digest": self.runtime.package.package_digest,
                "result": {"compiled": False, "rendered": False, "diagnostics": [{
                    "severity": "error", "code": "ADVERSARIAL_NEGATIVE_FIXTURE", "message": "Controlled negative reply; not a GPU observation"}],
                    "logs": [], "log_truncated": 0}}
            try:
                yield future, request, reply
            finally:
                if not future.done():
                    try:
                        self.machine("compute.detach", {"epoch": self.lease["epoch"], "lease": self.lease["lease"], "reason": "deactivate"})
                    except DlcOperationError:
                        pass

    def ledger_counts(self):
        with sqlite3.connect(self.owner.store.path) as db:
            return (db.execute("SELECT count(*) FROM reports WHERE project=?", (self.project,)).fetchone()[0],
                db.execute("SELECT count(*) FROM receipts WHERE request_id=?", (self.invocation,)).fetchone()[0])


@pytest.fixture
def protocol(tmp_path):
    with ShaderRuntime(tmp_path) as runtime:
        yield Protocol(runtime)


def test_head_aba_after_claim_rejects_even_when_content_hash_is_restored(protocol):
    p = protocol
    with p.requested() as (future, request, reply):
        assert request["content_hash"] == p.document["content_hash"]
        p.runtime.operation(p.project, "documents.apply", {**p.payload, "request_id": str(uuid4()),
            "operations": [{"kind": "rename_document", "title": "Intervening human version"}]})
        restored = p.runtime.operation(p.project, "documents.undo", {"document_id": p.document["id"],
            "expected_version": 2, "target_version": 1, "request_id": str(uuid4())})
        assert restored["document"]["content_hash"] == request["content_hash"]
        assert restored["document"]["version"] == 3
        p.machine("compute.complete", reply)
        outcome = future.result(timeout=3)
    assert outcome.status == "failed" and "STALE_VERSION" in outcome.error
    assert p.ledger_counts() == (0, 0)
    assert p.invoke(recover=True).status == "failed"


@pytest.mark.parametrize("fence", ["deadline", "same-client-reactivation"])
def test_receipt_insert_cannot_outlive_compute_deadline_or_registration(protocol, monkeypatch, fence):
    p = protocol
    moment = [100.]
    if fence == "deadline":
        monkeypatch.setattr(p.owner.bridge, "clock", lambda: moment[0])
        # Start a fresh registration using the controlled monotonic clock.
        attached = p.machine("compute.attach", {**p.attach_input, "registration_counter": 2})
        p.lease = {"epoch": attached["epoch"], "lease": attached["lease"], "registration_counter": 2}
    original = p.owner.store.save_receipt

    def trip_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        if fence == "deadline":
            moment[0] = 104.
            p.machine("compute.next", p.lease)
            moment[0] = 108.
            p.machine("compute.next", p.lease)
            # Healthy lease now lasts until 113, but this request ended at 110.
            moment[0] = 111.
        else:
            p.machine("compute.attach", {**p.attach_input, "registration_counter": 2})

    monkeypatch.setattr(p.owner.store, "save_receipt", trip_after_insert)
    with p.requested() as (future, _, reply):
        p.machine("compute.complete", reply)
        outcome = future.result(timeout=3)
    expected = "SHADER_COMPUTE_TIMEOUT" if fence == "deadline" else "SHADER_EXECUTOR_UNAVAILABLE"
    assert outcome.status == "failed" and expected in outcome.error, outcome
    assert p.ledger_counts() == (0, 0)
    assert p.invoke(recover=True).status == "failed"


def test_real_committed_report_recovers_after_lost_tool_return_and_deleted_head(protocol, monkeypatch):
    p = protocol
    original = p.owner.store.save_report

    def lost_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("Adversarial lost result after owner SQLite commit")

    monkeypatch.setattr(p.owner.store, "save_report", lost_after_commit)
    with p.requested() as (future, _, reply):
        p.machine("compute.complete", reply)
        failed = future.result(timeout=3)
    assert failed.status == "failed" and not failed.artifact_drafts
    assert p.ledger_counts() == (1, 1)
    p.runtime.operation(p.project, "documents.delete", {**p.payload, "request_id": str(uuid4())})
    p.machine("compute.detach", {"epoch": p.lease["epoch"], "lease": p.lease["lease"], "reason": "deactivate"})
    recovered = p.invoke(recover=True)
    assert recovered.status == "success" and recovered.output["compiled"] is False
    assert recovered.output["document"] == p.document
    assert len(recovered.artifact_drafts) == 1
    assert recovered.artifact_drafts[0].resource_refs == (p.scope,)
    assert p.ledger_counts() == (1, 1)
    with pytest.raises(DlcOperationError):
        p.machine("compute.complete", reply)


@pytest.mark.parametrize("fault", ["compiled", "stage-id", "diagnostic-absence", "operational-error"])
def test_durable_report_cannot_change_semantics_while_retaining_source_identity(protocol, fault):
    p = protocol
    with p.requested() as (future, _, reply):
        p.machine("compute.complete", reply)
        outcome = future.result(timeout=3)
    assert outcome.status == "success" and outcome.output["compiled"] is False
    report_id = outcome.output["report_id"]
    with sqlite3.connect(p.owner.store.path) as db:
        old = db.execute("SELECT payload FROM reports WHERE id=?", (report_id,)).fetchone()[0]
        body = json.loads(old)
        if fault == "compiled":
            body["compiled"] = True
        elif fault == "stage-id":
            body["diagnostics"][0]["stage_id"] = str(uuid4())
        elif fault == "diagnostic-absence":
            body["diagnostics"] = []
        else:
            body["diagnostics"][0]["code"] = "CONTEXT_LOST"
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        db.execute("UPDATE reports SET payload=?,hash=? WHERE id=?", (payload, sha256(payload).hexdigest(), report_id))
        db.execute("UPDATE quota SET payload_bytes=payload_bytes+?", (len(payload)-len(old),))
    read = p.invoke(name="inspect_compile_error", payload={"report_id": report_id}, invocation=str(uuid4()))
    assert read.status == "failed" and "SHADER_CORRUPT" in read.error, read
    assert p.invoke(recover=True).status == "failed"


def test_nonrendered_evidence_cannot_commit_preview_layout_fields(protocol, monkeypatch):
    p = protocol
    original = p.owner.store.make_report

    def corrupt_derived_layout(*args, **kwargs):
        report, pixels = original(*args, **kwargs)
        return report.model_copy(update={"width": 1, "height": 1, "pixel_format": "rgba8-unorm"}), pixels

    # Fault at the derived report boundary; this is not reachable through a
    # well-formed machine CompleteInput (which already rejects these fields).
    monkeypatch.setattr(p.owner.store, "make_report", corrupt_derived_layout)
    with p.requested() as (future, _, reply):
        p.machine("compute.complete", reply)
        outcome = future.result(timeout=3)
    assert outcome.status == "failed", outcome
    assert p.ledger_counts() == (0, 0)
