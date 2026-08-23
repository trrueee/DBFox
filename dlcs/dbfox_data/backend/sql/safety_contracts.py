"""Immutable SQL safety decision contracts owned by the Data capability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .guardrail import GuardrailResult

RiskLevel = Literal["safe", "warning", "danger"]
ExecutionPolicy = Literal[
    "readonly",
    "user_readonly",
    "agent_readonly",
    "table_preview",
    "schema_introspection",
    "explain",
    "export",
]


@dataclass(frozen=True)
class DatabaseSafetyScope:
    """Immutable database resource facts used by one safety decision.

    The gate consumes this value instead of reaching through the Runtime for
    ORM models. ``exists`` keeps an unresolved requested identity explicit so
    admission failures cannot be mistaken for a default database.
    """

    resource_id: str
    exists: bool
    dialect: str = "mysql"
    environment: str = "unknown"
    is_read_only: bool | None = None
    project_id: str | None = None


class ExecutionSafetyDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"safety-{uuid4()}")
    datasource_id: str
    policy: ExecutionPolicy = "readonly"
    original_sql: str
    safe_sql: str | None
    passed: bool
    can_execute: bool
    requires_confirmation: bool
    risk_level: RiskLevel = "safe"
    guardrail: GuardrailResult
    schema_warnings: list[str] = Field(default_factory=list)
    scope_state: dict[str, Any] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    parameter_fingerprint: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def requires_human_confirmation(
    *,
    env: str,
    policy: ExecutionPolicy,
    risk_level: RiskLevel,
) -> bool:
    """Determine whether a safe SQL decision still requires human approval."""

    if policy in {"table_preview", "schema_introspection", "explain"}:
        return False
    if policy == "user_readonly":
        return False
    if policy == "agent_readonly":
        return env == "prod" or risk_level == "warning"
    if policy == "export":
        return False
    return False


def is_auto_limit_only_warning(guardrail: GuardrailResult) -> bool:
    if guardrail.get("result") != "warn":
        return False
    checks = guardrail.get("checks") or []
    if not isinstance(checks, list) or not checks:
        return False
    warning_rules = {
        str(check.get("rule") or "").strip()
        for check in checks
        if isinstance(check, dict) and str(check.get("level") or "").strip() == "warn"
    }
    non_warning_rules = {
        str(check.get("rule") or "").strip()
        for check in checks
        if isinstance(check, dict) and str(check.get("level") or "").strip() != "warn"
    }
    return warning_rules.issubset({"auto_limit", "limit_hard_cap"}) and not non_warning_rules
