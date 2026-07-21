"""Durable Run budget accounting and cooperative cancellation boundaries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from engine.agent.run import RunLimits
from engine.models import AgentRun


class RunControlError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RunCancellationRequested(RunControlError):
    def __init__(self) -> None:
        super().__init__("AGENT_CANCELLED", "分析已取消。")


@dataclass(frozen=True)
class ModelPricing:
    """USD prices per one million input/output tokens."""

    input_per_million: float
    output_per_million: float

    def charge(self, *, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million
            + output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class UsageCharge:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


class RunControl:
    """Own the in-memory view of the Run's persisted execution budget."""

    def __init__(
        self,
        *,
        run: AgentRun,
        limits: RunLimits,
        cancellation_probe: Callable[[], bool],
        probe_interval_seconds: float = 0.1,
    ) -> None:
        started_at = run.started_at or run.created_at or datetime.now(UTC)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        elapsed = max(0.0, (datetime.now(UTC) - started_at).total_seconds())
        self.deadline = time.monotonic() + max(0.0, limits.timeout_seconds - elapsed)
        self.limits = limits
        self.consumed_tokens = int(run.consumed_tokens or 0)
        self.consumed_cost_usd = float(run.consumed_cost_usd or 0.0)
        self.provider_retry_count = int(run.provider_retry_count or 0)
        self.repair_attempt_count = int(run.repair_attempt_count or 0)
        self._cancellation_probe = cancellation_probe
        self._probe_interval = max(0.01, probe_interval_seconds)
        self._last_probe = 0.0
        self._cancelled = False

    def checkpoint(self) -> None:
        if time.monotonic() >= self.deadline:
            raise RunControlError("AGENT_DEADLINE_EXCEEDED", "分析已达到本次运行时限。")
        if self.is_cancel_requested():
            raise RunCancellationRequested()

    def is_cancel_requested(self) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if now - self._last_probe >= self._probe_interval:
            self._last_probe = now
            self._cancelled = bool(self._cancellation_probe())
        return self._cancelled

    def remaining_seconds(self) -> float:
        self.checkpoint()
        return max(0.01, self.deadline - time.monotonic())

    def charge_usage(
        self,
        usage: dict[str, int],
        *,
        pricing: ModelPricing | None,
    ) -> UsageCharge:
        input_tokens = max(0, int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0))
        output_tokens = max(0, int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0))
        total_tokens = max(0, int(usage.get("total_tokens", input_tokens + output_tokens) or 0))
        cost = pricing.charge(input_tokens=input_tokens, output_tokens=output_tokens) if pricing else 0.0
        self.consumed_tokens += total_tokens
        self.consumed_cost_usd += cost
        charge = UsageCharge(input_tokens, output_tokens, total_tokens, cost)
        if self.limits.token_budget is not None and self.consumed_tokens > self.limits.token_budget:
            raise RunControlError("AGENT_TOKEN_BUDGET", "分析已达到本次 Token 预算。")
        if self.limits.cost_budget_usd is not None:
            if pricing is None:
                raise RunControlError(
                    "AGENT_COST_PRICING_UNAVAILABLE",
                    "当前模型未配置可核算价格，无法执行带费用上限的分析。",
                )
            if self.consumed_cost_usd > self.limits.cost_budget_usd:
                raise RunControlError("AGENT_COST_BUDGET", "分析已达到本次费用预算。")
        return charge

    def record_provider_failure(self) -> None:
        self.provider_retry_count += 1
        if self.provider_retry_count > self.limits.max_provider_retries:
            raise RunControlError("AGENT_PROVIDER_RETRY_BUDGET", "模型服务连续失败，已停止重试。")

    def record_repair(self) -> None:
        self.repair_attempt_count += 1
        if self.repair_attempt_count > self.limits.max_repair_attempts:
            raise RunControlError("AGENT_REPAIR_BUDGET", "分析修复次数已达到上限。")
