from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.events import RuntimeEventType
from engine.agent.repositories.session import EventHistoryGap, SessionRepository
from engine.agent.run import RunStatus, SessionLeaseConflict
from engine.agent.session import DeliveryMode
from engine.models import AgentMessage, AgentRun, AgentSession, AgentSessionInput, AgentTurn


def _session(db_session, datasource_id: str) -> AgentSession:
    value = AgentSession(id="session_1", datasource_id=datasource_id, title="Test")
    db_session.add(value)
    db_session.commit()
    return value


def _admit(repository: SessionRepository, datasource_id: str, key: str = "request_1"):
    return repository.admit(
        session_id="session_1",
        datasource_id=datasource_id,
        datasource_generation=1,
        content="统计订单数量",
        idempotency_key=key,
        llm_credential_id="credential_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "统计订单数量"},
    )


def test_admission_is_atomic_ordered_and_idempotent(db_session, test_datasource) -> None:
    _session(db_session, str(test_datasource.id))
    repository = SessionRepository(db_session)

    first = _admit(repository, str(test_datasource.id))
    db_session.commit()
    repeated = _admit(repository, str(test_datasource.id))
    db_session.commit()

    assert repeated == first
    assert db_session.query(AgentSessionInput).count() == 1
    assert db_session.query(AgentRun).count() == 1
    assert db_session.query(AgentMessage).count() == 2
    assert [event.event_type for event in repository.list_events("session_1")] == [
        RuntimeEventType.SESSION_INPUT_ADMITTED,
        RuntimeEventType.RUN_CREATED,
    ]


def test_concurrent_admission_serializes_sqlite_aggregate_writes(db_session, test_datasource) -> None:
    datasource_id = str(test_datasource.id)
    _session(db_session, datasource_id)
    session_factory = sessionmaker(bind=db_session.get_bind())
    worker_count = 8
    barrier = Barrier(worker_count)

    def admit(index: int):
        with session_factory() as session:
            barrier.wait(timeout=5)
            value = _admit(SessionRepository(session), datasource_id, key=f"request-{index}")
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


def test_concurrent_idempotent_admission_returns_one_run(db_session, test_datasource) -> None:
    datasource_id = str(test_datasource.id)
    _session(db_session, datasource_id)
    session_factory = sessionmaker(bind=db_session.get_bind())
    worker_count = 6
    barrier = Barrier(worker_count)

    def admit_once(_: int):
        with session_factory() as session:
            barrier.wait(timeout=5)
            value = _admit(SessionRepository(session), datasource_id, key="same-request")
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
    db_session, test_datasource, monkeypatch
) -> None:
    from engine.agent.repositories import session as session_module

    monkeypatch.setattr(session_module, "EVENT_REPLAY_RETAINED", 3)
    monkeypatch.setattr(session_module, "EVENT_COMPACTION_TRIGGER", 4)
    _session(db_session, str(test_datasource.id))
    repository = SessionRepository(db_session)

    for index in range(3):
        _admit(repository, str(test_datasource.id), key=f"compact-{index}")
        db_session.commit()

    aggregate = db_session.get(AgentSession, "session_1")
    assert int(aggregate.event_sequence) == 6
    assert int(aggregate.event_floor_sequence) == 2
    with pytest.raises(EventHistoryGap) as error:
        repository.list_events("session_1", after_sequence=0)
    assert error.value.floor_sequence == 2
    assert [event.sequence for event in repository.list_events("session_1", after_sequence=2)] == [3, 4, 5, 6]


def test_session_lease_fences_old_owner_and_promotes_input(db_session, test_datasource) -> None:
    aggregate = _session(db_session, str(test_datasource.id))
    repository = SessionRepository(db_session)
    admission = _admit(repository, str(test_datasource.id))
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


def test_turn_snapshot_is_frozen_under_the_session_lease(db_session, test_datasource) -> None:
    _session(db_session, str(test_datasource.id))
    repository = SessionRepository(db_session)
    admission = _admit(repository, str(test_datasource.id))
    lease = repository.claim(session_id="session_1", owner="worker_a")
    assert lease is not None
    assert repository.promote_next_input(lease=lease) == admission.run_id

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
    assert repository.list_events("session_1")[-1].event_type is RuntimeEventType.TURN_STARTED


def test_steer_joins_the_active_run_and_is_consumed_at_the_next_turn_boundary(
    db_session, test_datasource
) -> None:
    _session(db_session, str(test_datasource.id))
    repository = SessionRepository(db_session)
    original = _admit(repository, str(test_datasource.id))
    lease = repository.claim(session_id="session_1", owner="worker")
    assert lease is not None
    repository.promote_next_input(lease=lease)
    db_session.commit()

    steered = repository.admit(
        session_id="session_1",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
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


def test_cancel_and_replace_cancels_queued_work_and_admits_one_new_run(
    db_session, test_datasource
) -> None:
    _session(db_session, str(test_datasource.id))
    repository = SessionRepository(db_session)
    first = _admit(repository, str(test_datasource.id), key="request-first")
    second = _admit(repository, str(test_datasource.id), key="request-second")
    db_session.commit()

    replacement = repository.admit(
        session_id="session_1",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="改为统计退款",
        idempotency_key="request-replacement",
        llm_credential_id="credential_1",
        api_base=None,
        model_name="model-test",
        request_payload={},
        delivery_mode=DeliveryMode.CANCEL_AND_REPLACE,
    )
    db_session.commit()

    assert db_session.get(AgentRun, first.run_id).status == "cancelled"
    assert db_session.get(AgentRun, second.run_id).status == "cancelled"
    assert db_session.get(AgentRun, replacement.run_id).status == "queued"
    assert db_session.get(AgentSessionInput, first.input_id).status == "cancelled"
    assert db_session.get(AgentSessionInput, second.input_id).status == "cancelled"
