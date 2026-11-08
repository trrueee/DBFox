"""Visibility frontiers, cleanup replay, and recovery of derived workbook data."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from types import SimpleNamespace
from uuid import uuid4

from engine.agent.context import ContextAssembler
from engine.agent.references import ConversationInputReference
from engine.agent.repositories.session import SessionRepository
from engine.agent.session import DeliveryMode
from engine.attachments import ATTACHMENT_RESOURCE_KIND, AttachmentService
from engine.models import AgentRunItemRecord, Project, SessionResourceRetirement
from engine.runtime_composition import discover_run_resources, deliver_session_resource_retirements


def attach(db, service, session_id, data):
    temporary = service.root / ("upload_" + uuid4().hex + ".tmp")
    temporary.write_bytes(data)
    file = service.publish(session_id, temporary=temporary, name="orders.xlsx", media_type="application/octet-stream",
                           size=len(data), digest=hashlib.sha256(data).hexdigest(), key=uuid4().hex)
    return ConversationInputReference(label="orders.xlsx", object={"kind": ATTACHMENT_RESOURCE_KIND,
        "id": file.id, "version": file.content_sha256})


def admit(db, session_id, reference, mode=DeliveryMode.QUEUE):
    value = SessionRepository(db).admit(session_id=session_id, resource_refs=(), references=(reference,),
        content="分析这个文件", idempotency_key=uuid4().hex, llm_credential_id="scripted", api_base=None,
        model_name="gpt-5.4", request_payload={}, delivery_mode=mode)
    AttachmentService(db).admit(session_id, value.input_id, (reference,))
    db.commit()
    return value


def test_consumed_steer_changes_explicit_subject_but_queued_file_stays_hidden(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("engine.attachments.private_runtime_dir", lambda _name: tmp_path)
    db_session.add(Project(id="frontier", name="frontier")); db_session.flush()
    repo = SessionRepository(db_session)
    conversation = repo.create(project_id="frontier", title="frontier")
    service = AttachmentService(db_session)
    first_ref = attach(db_session, service, conversation.id, b"one")
    first = admit(db_session, conversation.id, first_ref)
    lease = repo.claim(session_id=conversation.id, owner="frontier-worker", ttl_seconds=120)
    repo.promote_next_input(lease=lease); db_session.commit()
    steer_ref = attach(db_session, service, conversation.id, b"two")
    admit(db_session, conversation.id, steer_ref, DeliveryMode.STEER)
    future_ref = attach(db_session, service, conversation.id, b"three")
    admit(db_session, conversation.id, future_ref)
    context = lambda: ContextAssembler(db_session, resource_discovery=discover_run_resources).build(first.run_id)
    assert context().input_references == [first_ref]
    visible = lambda: {r.id for r in context().resource_directory if r.kind == ATTACHMENT_RESOURCE_KIND}
    assert visible() == {first_ref.object.id}
    repo.consume_steering_inputs(lease=lease, run_id=first.run_id); db_session.commit()
    assert context().input_references == [steer_ref]
    assert visible() == {first_ref.object.id, steer_ref.object.id}
    assert future_ref.object.id not in visible()
    items = db_session.query(AgentRunItemRecord).filter_by(run_id=first.run_id).all()
    assert any(steer_ref.object.id in item.item_json for item in items)


def test_retirement_replays_after_owner_reactivation_and_failure(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("engine.attachments.private_runtime_dir", lambda _name: tmp_path)
    file_id = "att_" + uuid4().hex
    path = AttachmentService(db_session).path(file_id); path.write_bytes(b"original")
    db_session.add(SessionResourceRetirement(session_id="deleted-conversation", attachment_ids_json=json.dumps([file_id])))
    db_session.commit()
    deliver_session_resource_retirements(db_session, SimpleNamespace(session_resource_contributions=()))
    assert not path.exists()
    calls = []
    def retire(session_id):
        calls.append(session_id)
        if len(calls) == 1:
            raise OSError("owner storage temporarily busy")
    enabled = SimpleNamespace(session_resource_contributions=(SimpleNamespace(owner_id="dbfox.data", retire=retire),))
    deliver_session_resource_retirements(db_session, enabled)
    row = db_session.get(SessionResourceRetirement, "deleted-conversation")
    assert "dbfox.data" not in json.loads(row.delivered_owners_json)
    deliver_session_resource_retirements(db_session, enabled)
    deliver_session_resource_retirements(db_session, enabled)
    assert calls == ["deleted-conversation", "deleted-conversation"]
    assert set(json.loads(row.delivered_owners_json)) == {"dbfox.core", "dbfox.data"}


def test_collect_abandoned_uploads_keeps_sent_bytes(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr("engine.attachments.private_runtime_dir", lambda _name: tmp_path)
    db_session.add(Project(id="collect", name="collect")); db_session.flush()
    conversation = SessionRepository(db_session).create(project_id="collect", title="collect")
    service = AttachmentService(db_session)
    sent = attach(db_session, service, conversation.id, b"sent")
    admit(db_session, conversation.id, sent)
    staged = attach(db_session, service, conversation.id, b"staged")
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    service.owned(conversation.id, staged.object.id).created_at = old
    temporary = tmp_path / ("upload_" + uuid4().hex + ".tmp"); temporary.write_bytes(b"partial")
    for path in (temporary, service.path(staged.object.id), service.path(sent.object.id)):
        os.utime(path, (old.timestamp(), old.timestamp()))
    db_session.commit()
    service.collect(); db_session.commit()
    assert service.path(sent.object.id).exists()
    assert not service.path(staged.object.id).exists() and not temporary.exists()
