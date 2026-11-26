"""Process-interruption recovery must not consume the provider retry budget."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from engine.agent.control import RunControl, RunControlError
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.app.safe_errors import fixed_error_detail
from engine.models import AgentRun, AgentSession


def _admitted_session(db_session):
    db_session.add(AgentSession(id="session_recovery", title="Recovery"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_recovery",
        resource_refs=(),
        content="recover the interrupted run",
        idempotency_key="request_recovery",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_recovery", owner="worker")
    assert lease is not None
    assert sessions.promote_next_input(lease=lease) == admission.run_id
    return sessions, admission, lease


def _start_turn(sessions: SessionRepository, lease, run_id: str) -> None:
    sessions.start_turn(
        lease=lease,
        run_id=run_id,
        agent_definition_version="test",
        prompt_version="test",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={},
        tool_materialization_hash="materialization",
        provider="test",
        model_name="test",
    )


def test_interrupted_turn_uses_recovery_budget_not_provider_retry_budget(db_session) -> None:
    sessions, admission, lease = _admitted_session(db_session)
    repository = RunRepository(db_session)

    _start_turn(sessions, lease, admission.run_id)
    db_session.commit()
    assert repository.recover_interrupted_turns(
        lease=lease, run_id=admission.run_id
    ) == 1
    db_session.commit()

    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    assert run.recovery_count == 1
    assert run.provider_retry_count == 0

    _start_turn(sessions, lease, admission.run_id)
    db_session.commit()
    assert repository.recover_interrupted_turns(
        lease=lease, run_id=admission.run_id
    ) == 1
    db_session.commit()
    db_session.refresh(run)

    assert run.recovery_count == 2
    assert run.provider_retry_count == 0


def test_run_control_stops_after_the_recovery_budget() -> None:
    run = SimpleNamespace(
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        consumed_tokens=0,
        consumed_cost_usd=0.0,
        provider_retry_count=0,
        repair_attempt_count=0,
        recovery_count=4,
    )
    control = RunControl(
        run=run,
        limits=RunLimits(max_recovery_attempts=3),
        cancellation_probe=lambda: False,
    )

    with pytest.raises(RunControlError) as raised:
        control.checkpoint()

    assert raised.value.code == "AGENT_RECOVERY_EXHAUSTED"
    assert fixed_error_detail(raised.value.code)["code"] == "AGENT_RECOVERY_EXHAUSTED"


def test_run_control_allows_recovery_within_the_budget() -> None:
    run = SimpleNamespace(
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        consumed_tokens=0,
        consumed_cost_usd=0.0,
        provider_retry_count=0,
        repair_attempt_count=0,
        recovery_count=3,
    )
    control = RunControl(
        run=run,
        limits=RunLimits(max_recovery_attempts=3),
        cancellation_probe=lambda: False,
    )

    control.checkpoint()
