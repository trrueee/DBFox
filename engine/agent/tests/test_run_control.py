from datetime import UTC, datetime, timedelta

import pytest

from engine.agent.control import (
    ModelPricing,
    RunCancellationRequested,
    RunControl,
    RunControlError,
    RunLeaseLost,
)
from engine.agent.run import RunLimits
from engine.models import AgentRun


def _run(**values) -> AgentRun:
    started_at = values.pop("started_at", datetime.now(UTC))
    return AgentRun(
        id="run_budget",
        session_id="session_budget",
        question="test",
        status="running",
        started_at=started_at,
        **values,
    )


def test_run_control_restores_and_charges_persisted_usage() -> None:
    control = RunControl(
        run=_run(consumed_tokens=80, consumed_cost_usd=0.001),
        limits=RunLimits(token_budget=100, cost_budget_usd=0.01),
        cancellation_probe=lambda: False,
    )
    charge = control.charge_usage(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        pricing=ModelPricing(input_per_million=1, output_per_million=2),
    )
    assert charge.total_tokens == 15
    assert control.consumed_tokens == 95
    assert control.consumed_cost_usd > 0.001


def test_run_control_enforces_token_provider_and_repair_budgets() -> None:
    control = RunControl(
        run=_run(),
        limits=RunLimits(token_budget=5, max_provider_retries=1, max_repair_attempts=1),
        cancellation_probe=lambda: False,
    )
    with pytest.raises(RunControlError, match="Token") as token_error:
        control.charge_usage({"total_tokens": 6}, pricing=None)
    assert token_error.value.code == "AGENT_TOKEN_BUDGET"

    control.record_provider_failure()
    with pytest.raises(RunControlError) as provider_error:
        control.record_provider_failure()
    assert provider_error.value.code == "AGENT_PROVIDER_RETRY_BUDGET"

    control.record_repair()
    with pytest.raises(RunControlError) as repair_error:
        control.record_repair()
    assert repair_error.value.code == "AGENT_REPAIR_BUDGET"


def test_run_control_uses_original_run_deadline() -> None:
    control = RunControl(
        run=_run(started_at=datetime.now(UTC) - timedelta(seconds=20)),
        limits=RunLimits(timeout_seconds=10),
        cancellation_probe=lambda: False,
    )
    with pytest.raises(RunControlError) as error:
        control.checkpoint()
    assert error.value.code == "AGENT_DEADLINE_EXCEEDED"


def test_cost_budget_requires_explicit_model_pricing() -> None:
    control = RunControl(
        run=_run(),
        limits=RunLimits(cost_budget_usd=1),
        cancellation_probe=lambda: False,
    )
    with pytest.raises(RunControlError) as error:
        control.charge_usage({"total_tokens": 1}, pricing=None)
    assert error.value.code == "AGENT_COST_PRICING_UNAVAILABLE"


def test_enabled_budget_fails_closed_when_provider_usage_is_missing() -> None:
    control = RunControl(
        run=_run(),
        limits=RunLimits(token_budget=100),
        cancellation_probe=lambda: False,
    )

    with pytest.raises(RunControlError) as error:
        control.charge_usage({}, pricing=None)

    assert error.value.code == "AGENT_USAGE_UNAVAILABLE"
    assert control.consumed_tokens == 0


def test_lease_loss_preempts_user_cancellation_and_stops_external_probes() -> None:
    lost = False
    control = RunControl(
        run=_run(),
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=lambda: lost,
    )
    assert control.is_cancel_requested() is False
    lost = True
    assert control.is_cancel_requested() is True
    with pytest.raises(RunLeaseLost):
        control.checkpoint()


def test_provider_backoff_is_cooperatively_cancellable(monkeypatch: pytest.MonkeyPatch) -> None:
    cancelled = False
    now = 0.0
    monkeypatch.setattr("engine.agent.control.time.monotonic", lambda: now)
    control = RunControl(
        run=_run(),
        limits=RunLimits(max_provider_retries=2),
        cancellation_probe=lambda: cancelled,
        probe_interval_seconds=0.01,
        provider_retry_base_seconds=1,
    )
    control.record_provider_failure()

    def cancel_during_sleep(_duration: float) -> None:
        nonlocal cancelled, now
        cancelled = True
        now += 0.02

    monkeypatch.setattr("engine.agent.control.time.sleep", cancel_during_sleep)

    with pytest.raises(RunCancellationRequested):
        control.wait_for_provider_retry()


def test_provider_backoff_honors_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0.0
    sleeps: list[float] = []
    control = RunControl(
        run=_run(),
        limits=RunLimits(max_provider_retries=2, timeout_seconds=120),
        cancellation_probe=lambda: False,
        probe_interval_seconds=1,
        provider_retry_base_seconds=0.5,
        provider_retry_max_seconds=30,
    )
    control.record_provider_failure()

    def monotonic() -> float:
        return now

    def sleep(duration: float) -> None:
        nonlocal now
        sleeps.append(duration)
        now += duration

    monkeypatch.setattr("engine.agent.control.time.monotonic", monotonic)
    monkeypatch.setattr("engine.agent.control.time.sleep", sleep)
    control.deadline = 120
    control.wait_for_provider_retry(3)

    assert sum(sleeps) == pytest.approx(3)
