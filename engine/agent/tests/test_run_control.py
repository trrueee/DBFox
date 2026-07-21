from datetime import UTC, datetime, timedelta

import pytest

from engine.agent.control import ModelPricing, RunControl, RunControlError
from engine.agent.run import RunLimits
from engine.models import AgentRun


def _run(**values) -> AgentRun:
    started_at = values.pop("started_at", datetime.now(UTC))
    return AgentRun(
        id="run_budget",
        session_id="session_budget",
        datasource_id="datasource_budget",
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
