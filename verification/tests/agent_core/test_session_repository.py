from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.events import RuntimeEventType
from engine.agent.repositories.events import EventHistoryGap, EventRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.run import RunStatus, SessionLeaseConflict
from engine.agent.session import DeliveryMode
from engine.models import (
    AgentEventRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentTurn,
)
from engine.tools.runtime.attempt import ResourceScopeRef


def _session(db_session, resource_id: str, project_id: str | None = None) -> AgentSession:
    value = AgentSession(id="session_1", project_id=project_id, title="Test")
    db_session.add(value)
    db_session.commit()
    return value


def _admit(repository: SessionRepository, resource_id: str, key: str = "request_1"):
    resource_refs = (
        ResourceScopeRef(kind="verification.resource", id=resource_id, version="1:1"),
    ) if resource_id else ()
    return repository.admit(
        session_id="session_1",
        resource_refs=resource_refs,
        content="统计订单数量",
        idempotency_key=key,
        llm_credential_id="credential_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "统计订单数量"},
    )


def test_admission_is_atomic_ordered_and_idempotent(db_session, test_resource) -> None:
    _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)

    first = _admit(repository, str(test_resource.id))
    db_session.commit()
    repeated = _admit(repository, str(test_resource.id))
    db_session.commit()

    assert repeated == first
    assert db_session.query(AgentSessionInput).count() == 1
    assert db_session.query(AgentRun).count() == 1
    assert db_session.query(AgentMessage).count() == 2
    assert [event.event_type for event in repository.events.list("session_1")] == [
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.RUN_ITEM_COMPLETED,
    ]


def test_admit_persists_the_already_authorized_frozen_resource_set(
    db_session,
    test_resource,
) -> None:
    """Project authorization happens before the persistence repository boundary."""

    _session(db_session, str(test_resource.id))

    admission = _admit(SessionRepository(db_session), "ds-b")
    stored = db_session.get(AgentSessionInput, admission.input_id)
    assert stored is not None
    assert '"id":"ds-b"' in str(stored.resource_refs_json)
    assert '"kind":"verification.resource"' in str(stored.resource_refs_json)
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    assert not hasattr(run, "resource_id")
    assert not hasattr(run, "datasource_generation")


def test_concurrent_admission_serializes_sqlite_aggregate_writes(db_session, test_resource) -> None:
    resource_id = str(test_resource.id)
    _session(db_session, resource_id)
    session_factory = sessionmaker(bind=db_session.get_bind())
    worker_count = 8
    barrier = Barrier(worker_count)

    def admit(index: int):
        with session_factory() as session:
            barrier.wait(timeout=5)
            value = _admit(SessionRepository(session), resource_id, key=f"request-{index}")
            session.commit()
            return value

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        admissions = list(executor.map(admit, range(worker_count)))

    db_session.expire_all()
    aggregate = db_session.get(AgentSession, "session_1")
    assert aggregate is not None
    assert int(aggregate.input_sequence) == worker_count
    assert int(aggregate.message_sequence) == worker_count * 2
    assert int(aggregate.event_sequence) == worker_count * 2
    assert sorted(item.input_sequence for item in admissions) == list(range(1, worker_count + 1))
    assert db_session.query(AgentSessionInput).count() == worker_count


def test_begin_agent_write_tracks_the_physical_sqlite_transaction(db_session) -> None:
    connection = db_session.connection()
    driver_connection = connection.connection.driver_connection

    # SQLAlchemy autobegin owns a logical transaction as soon as the Session
    # acquires a Connection.  SQLite has not acquired its writer lock yet.
    assert db_session.in_transaction()
    assert not driver_connection.in_transaction

    begin_agent_write(db_session)
    assert driver_connection.in_transaction

    # Repository methods compose inside one physical writer transaction.
    begin_agent_write(db_session)
    assert driver_connection.in_transaction

    db_session.rollback()
    assert not driver_connection.in_transaction


def test_direct_event_append_serializes_sqlite_sequence_writes(db_session, test_resource) -> None:
    resource_id = str(test_resource.id)
    _session(db_session, resource_id)
    repository = SessionRepository(db_session)
    lease = repository.claim(session_id="session_1", owner="worker")
    assert lease is not None
    db_session.commit()

    session_factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    worker_count = 8
    barrier = Barrier(worker_count)

    def append_event(index: int) -> int:
        with session_factory() as session:
            barrier.wait(timeout=5)
            sequence = EventRepository(session).append(
                lease=lease,
                event_type=RuntimeEventType.RUN_UPDATED,
                run_id=None,
                payload={"worker": index},
            )
            session.commit()
            return sequence

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        sequences = list(executor.map(append_event, range(worker_count)))

    db_session.expire_all()
    aggregate = db_session.get(AgentSession, "session_1")
    assert aggregate is not None
    assert sorted(sequences) == list(range(1, worker_count + 1))
    assert int(aggregate.event_sequence) == worker_count
    stored_sequences = [
        int(record.sequence)
        for record in (
            db_session.query(AgentEventRecord)
            .filter(AgentEventRecord.session_id == "session_1")
            .order_by(AgentEventRecord.sequence)
        )
    ]
    assert stored_sequences == list(range(1, worker_count + 1))


def test_concurrent_idempotent_admission_returns_one_run(db_session, test_resource) -> None:
    resource_id = str(test_resource.id)
    _session(db_session, resource_id)
    session_factory = sessionmaker(bind=db_session.get_bind())
    worker_count = 6
    barrier = Barrier(worker_count)

    def admit_once(_: int):
        with session_factory() as session:
            barrier.wait(timeout=5)
            value = _admit(SessionRepository(session), resource_id, key="same-request")
            session.commit()
            return value

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        admissions = list(executor.map(admit_once, range(worker_count)))

    assert len({item.run_id for item in admissions}) == 1
    assert len({item.input_id for item in admissions}) == 1
    assert db_session.query(AgentSessionInput).count() == 1
    assert db_session.query(AgentRun).count() == 1
    assert db_session.query(AgentMessage).count() == 2


def test_event_history_compacts_to_a_snapshot_replay_boundary(
    db_session, test_resource, monkeypatch
) -> None:
    from engine.agent.repositories import events as events_module

    monkeypatch.setattr(events_module, "EVENT_REPLAY_RETAINED", 3)
    monkeypatch.setattr(events_module, "EVENT_COMPACTION_TRIGGER", 4)
    _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)

    for index in range(3):
        _admit(repository, str(test_resource.id), key=f"compact-{index}")
        db_session.commit()

    aggregate = db_session.get(AgentSession, "session_1")
    assert int(aggregate.event_sequence) == 6
    assert int(aggregate.event_floor_sequence) == 2
    with pytest.raises(EventHistoryGap) as error:
        repository.events.list("session_1", after_sequence=0)
    assert error.value.floor_sequence == 2
    assert [event.sequence for event in repository.events.list("session_1", after_sequence=2)] == [3, 4, 5, 6]


def test_session_lease_fences_old_owner_and_promotes_input(db_session, test_resource) -> None:
    aggregate = _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)
    admission = _admit(repository, str(test_resource.id))
    db_session.commit()

    now = datetime.now(UTC)
    first = repository.claim(session_id="session_1", owner="worker_a", now=now, ttl_seconds=30)
    assert first is not None
    assert repository.claim(session_id="session_1", owner="worker_b", now=now, ttl_seconds=30) is None
    db_session.commit()

    aggregate = db_session.get(AgentSession, "session_1")
    aggregate.lease_expires_at = now - timedelta(seconds=1)
    db_session.commit()
    second = repository.claim(session_id="session_1", owner="worker_b", now=now, ttl_seconds=30)
    assert second is not None
    assert second.token == first.token + 1

    with pytest.raises(SessionLeaseConflict):
        repository.promote_next_input(lease=first)
    assert repository.promote_next_input(lease=second) == admission.run_id
    db_session.commit()

    run = db_session.get(AgentRun, admission.run_id)
    assert run.status == RunStatus.RUNNING.value
    assert run.lease_token == second.token


def test_turn_snapshot_is_frozen_under_the_session_lease(db_session, test_resource) -> None:
    _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)
    admission = _admit(repository, str(test_resource.id))
    lease = repository.claim(session_id="session_1", owner="worker_a")
    assert lease is not None
    assert repository.promote_next_input(lease=lease) == admission.run_id

    events_before_turn = repository.events.list("session_1")
    turn = repository.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="analyst@1",
        prompt_version="prompt@1",
        prompt_hash="prompt-hash",
        context_snapshot={"messages": []},
        context_hash="context-hash",
        tool_materialization={"tools": []},
        tool_materialization_hash="tools-hash",
        provider="openai-compatible",
        model_name="model-test",
    )
    db_session.commit()

    stored = db_session.get(AgentTurn, turn.id)
    assert stored.sequence == 1
    assert stored.context_hash == "context-hash"
    assert stored.tool_materialization_hash == "tools-hash"
    assert repository.events.list("session_1") == events_before_turn


def test_admit_rejects_a_soft_deleted_session_at_the_domain_boundary(
    db_session,
    test_resource,
) -> None:
    session = _session(db_session, str(test_resource.id))
    session.deleted_at = datetime.now(UTC)
    db_session.commit()

    with pytest.raises(ValueError, match="deleted Session"):
        _admit(SessionRepository(db_session), str(test_resource.id))


def test_steer_joins_the_active_run_and_is_consumed_at_the_next_turn_boundary(
    db_session, test_resource
) -> None:
    _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)
    original = _admit(repository, str(test_resource.id))
    lease = repository.claim(session_id="session_1", owner="worker")
    assert lease is not None
    repository.promote_next_input(lease=lease)
    db_session.commit()

    steered = repository.admit(
        session_id="session_1",
        resource_refs=(
            ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),
        ),
        content="只看华东区域",
        idempotency_key="request-steer",
        llm_credential_id="credential_1",
        api_base=None,
        model_name="model-test",
        request_payload={},
        delivery_mode=DeliveryMode.STEER,
    )
    db_session.commit()

    assert steered.run_id == original.run_id
    assert db_session.query(AgentRun).count() == 1
    assert repository.consume_steering_inputs(lease=lease, run_id=original.run_id) == ["只看华东区域"]
    db_session.commit()
    stored = db_session.get(AgentSessionInput, steered.input_id)
    assert stored.status == "consumed"


def test_orphaned_steer_cannot_revive_a_terminal_run(
    db_session, test_resource
) -> None:
    _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)
    original = _admit(repository, str(test_resource.id))
    lease = repository.claim(session_id="session_1", owner="worker")
    assert lease is not None
    assert repository.promote_next_input(lease=lease) == original.run_id
    steered = repository.admit(
        session_id="session_1",
        resource_refs=(
            ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),
        ),
        content="改成按地区统计",
        idempotency_key="request-orphan-steer",
        llm_credential_id="credential_1",
        api_base=None,
        model_name="model-test",
        request_payload={},
        delivery_mode=DeliveryMode.STEER,
    )
    run = db_session.get(AgentRun, original.run_id)
    assert run is not None
    run.status = RunStatus.COMPLETED.value
    run.completed_at = datetime.now(UTC)
    db_session.commit()

    assert repository.promote_next_input(lease=lease) is None
    db_session.commit()
    db_session.expire_all()

    stored_run = db_session.get(AgentRun, original.run_id)
    stored_input = db_session.get(AgentSessionInput, steered.input_id)
    assert stored_run is not None and stored_run.status == RunStatus.COMPLETED.value
    assert stored_input is not None
    assert stored_input.status == "cancelled"


def test_cancel_and_replace_requests_cancellation_before_admitting_one_new_run(
    db_session, test_resource
) -> None:
    _session(db_session, str(test_resource.id))
    repository = SessionRepository(db_session)
    first = _admit(repository, str(test_resource.id), key="request-first")
    second = _admit(repository, str(test_resource.id), key="request-second")
    db_session.commit()

    replacement = repository.admit(
        session_id="session_1",
        resource_refs=(
            ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),
        ),
        content="改为统计退款",
        idempotency_key="request-replacement",
        llm_credential_id="credential_1",
        api_base=None,
        model_name="model-test",
        request_payload={},
        delivery_mode=DeliveryMode.CANCEL_AND_REPLACE,
    )
    db_session.commit()

    assert db_session.get(AgentRun, first.run_id).status == "cancelling"
    assert db_session.get(AgentRun, second.run_id).status == "cancelling"
    assert db_session.get(AgentRun, replacement.run_id).status == "queued"
    assert db_session.get(AgentSessionInput, first.input_id).status == "admitted"
    assert db_session.get(AgentSessionInput, second.input_id).status == "admitted"
