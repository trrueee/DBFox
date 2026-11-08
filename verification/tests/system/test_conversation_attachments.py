"""Real HTTP bytes, durable admission, and private Input visibility frontiers."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from engine.agent.references import ConversationInputReference
from engine.agent.repositories.session import SessionRepository
from engine.attachments import ATTACHMENT_RESOURCE_KIND, AttachmentService, AttachmentError
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.models import AgentRun, ConversationAttachment, Project
from engine.runtime_composition import discover_run_resources


@pytest.fixture
def conversations(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("engine.attachments.private_runtime_dir", lambda _name: tmp_path / "bytes")
    monkeypatch.setattr(app.state, "agent_coordinator", SimpleNamespace(available=True, wake=lambda _id: None), raising=False)
    # HTTP storage/admission tests use a declared consumer; actual signed Data
    # contributions and SQL execution are covered in test_workbook_analysis.
    monkeypatch.setattr("engine.api.conversation_commands.get_active_runtime_snapshot", lambda: SimpleNamespace(
        tools=(SimpleNamespace(tool=SimpleNamespace(execution=SimpleNamespace(required_resources=(
            SimpleNamespace(kind=ATTACHMENT_RESOURCE_KIND),
        )))),)))
    db_session.add(Project(id="attachment-project", name="Attachment tests"))
    db_session.flush()
    repo = SessionRepository(db_session)
    a = repo.create(project_id="attachment-project", title="A")
    b = repo.create(project_id="attachment-project", title="B")
    db_session.commit()
    return str(a.id), str(b.id)


def headers(**extra):
    return {"X-Local-Token": LOCAL_SECURE_TOKEN, **extra}


def upload(client, session_id, *, key="upload-request-001", content=b"first immutable snapshot", name="orders.xlsx"):
    return client.post(f"/api/v1/conversations/{session_id}/attachments", content=content, headers=headers(**{
        "X-File-Name": quote(name), "X-Upload-Key": key,
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }))


def reference(file):
    return {"label": file["display_name"], "object": {
        "kind": ATTACHMENT_RESOURCE_KIND, "id": file["id"], "version": file["content_sha256"],
    }}


def send(client, session_id, file, *, key="input-request-001"):
    return client.post(f"/api/v1/conversations/{session_id}/inputs", json={
        "content": "分析这份表格", "idempotency_key": key, "llm_credential_id": "credential-1",
        "api_base": "https://api.openai.com/v1", "model_name": "gpt-4.1-mini",
        "references": [reference(file)],
    }, headers=headers())


def test_upload_identity_and_checked_retry(client, db_session, conversations):
    a, _ = conversations
    first = upload(client, a)
    assert first.status_code == 201, first.text
    snapshot = first.json()
    assert snapshot["content_sha256"] == hashlib.sha256(b"first immutable snapshot").hexdigest()
    assert snapshot["available"] and snapshot["first_input_id"] is None
    # SQLite round trips must satisfy the generated client's z.iso.datetime().
    assert snapshot["created_at"].endswith("Z")
    listing = client.get(f"/api/v1/conversations/{a}/attachments", headers=headers()).json()
    assert listing[0]["created_at"] == snapshot["created_at"]
    assert "path" not in snapshot
    assert upload(client, a).json()["id"] == snapshot["id"]
    assert upload(client, a, content=b"changed").status_code == 409
    second = upload(client, a, key="upload-request-002").json()
    assert second["id"] != snapshot["id"]  # Same bytes and name still have different identities.
    assert len(AttachmentService(db_session).listing(a, staged=True)) == 2


def test_atomic_attachment_admission_and_retry_conflict(client, db_session, conversations):
    a, _ = conversations
    one = upload(client, a).json()
    two = upload(client, a, key="upload-request-002", content=b"revision").json()
    accepted = send(client, a, one)
    assert accepted.status_code == 202, accepted.text
    assert send(client, a, one).json()["input_id"] == accepted.json()["input_id"]
    assert send(client, a, two).status_code == 400
    db_session.expire_all()
    assert db_session.get(ConversationAttachment, one["id"]).first_input_id == accepted.json()["input_id"]
    assert db_session.get(ConversationAttachment, two["id"]).first_input_id is None
    assert client.delete(f"/api/v1/conversations/{a}/attachments/{one['id']}", headers=headers()).status_code == 409


def test_cross_conversation_and_future_input_fail_closed(client, db_session, conversations):
    a, b = conversations
    one = upload(client, a).json()
    assert send(client, b, one).status_code == 400
    assert client.delete(f"/api/v1/conversations/{b}/attachments/{one['id']}", headers=headers()).status_code == 404
    first = send(client, a, one).json()
    two = upload(client, a, key="upload-request-002", content=b"second").json()
    second = send(client, a, two, key="input-request-002").json()
    db_session.expire_all()
    private = lambda run_id: {r.id for r in discover_run_resources(db_session, run_id) if r.kind == ATTACHMENT_RESOURCE_KIND}
    assert private(first["run_id"]) == {one["id"]}
    assert private(second["run_id"]) == {one["id"], two["id"]}
    assert db_session.get(AgentRun, first["run_id"]).input_id != second["input_id"]


def test_invalid_versions_and_multiple_new_files_roll_back(client, db_session, conversations):
    a, _ = conversations
    one = upload(client, a).json()
    forged = {**one, "content_sha256": "0" * 64}
    assert send(client, a, forged).status_code == 409
    two = upload(client, a, key="upload-request-002").json()
    response = client.post(f"/api/v1/conversations/{a}/inputs", json={
        "content": "分析", "idempotency_key": "two-new-files-request", "llm_credential_id": "credential-1",
        "references": [reference(one), reference(two)],
    }, headers=headers())
    assert response.status_code == 400
    db_session.expire_all()
    assert all(r.first_input_id is None for r in AttachmentService(db_session).listing(a, staged=True))


def test_stream_limits_metadata_and_missing_source(client, db_session, conversations, monkeypatch):
    a, _ = conversations
    assert upload(client, a, content=b"").status_code == 400
    assert upload(client, a, name="../orders.xlsx").status_code == 400
    monkeypatch.setattr("engine.api.attachments.MAX_ATTACHMENT_BYTES", 4)
    assert upload(client, a, content=b"12345").status_code == 413
    one = upload(client, a, content=b"1234").json()
    service = AttachmentService(db_session)
    service.path(one["id"]).unlink()
    assert not service.summary(service.owned(a, one["id"])).available
    with pytest.raises(AttachmentError, match="缺失"):
        service.resolve(ConversationInputReference.model_validate(reference(one)).object.model_copy(update={"version": one["content_sha256"]}))


def test_disabled_processor_does_not_admit_an_unusable_input(client, db_session, conversations, monkeypatch):
    a, _ = conversations
    file = upload(client, a).json()
    monkeypatch.setattr("engine.api.conversation_commands.get_active_runtime_snapshot", lambda: SimpleNamespace(tools=()))
    result = send(client, a, file)
    assert result.status_code == 409
    assert result.json()["code"] == "ATTACHMENT_PROCESSOR_UNAVAILABLE"
    assert AttachmentService(db_session).owned(a, file["id"]).first_input_id is None


def test_ten_attachment_quota_releases_only_deleted_drafts(client, conversations):
    a, _ = conversations
    files = [upload(client, a, key=f"quota-upload-{index:03d}").json() for index in range(10)]
    assert len({file["id"] for file in files}) == 10
    rejected = upload(client, a, key="quota-upload-overflow")
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "ATTACHMENT_QUOTA_EXCEEDED"
    assert client.delete(f"/api/v1/conversations/{a}/attachments/{files[0]['id']}", headers=headers()).status_code == 204
    replacement = upload(client, a, key="quota-upload-replacement")
    assert replacement.status_code == 201
    assert replacement.json()["id"] not in {file["id"] for file in files}
