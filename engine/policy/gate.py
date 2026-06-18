from __future__ import annotations

from typing import Any, Callable, Literal
from pydantic import BaseModel, Field

from engine.agent_core.tool_registry import ToolRegistry, tool_to_group


class PolicyDecision(BaseModel):
    status: Literal["allowed", "blocked", "approval_required"]
    reason: str
    safe_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    approval: dict[str, Any] | None = None


# ── Rule chain infrastructure ────────────────────────────────────────────────────
#
# Each rule receives (gate, state, tool_name, args, execution_mode, tool, policy)
# and returns a PolicyDecision to short-circuit, or None to let the next rule run.


_RuleFunc = Callable[..., PolicyDecision | None]


def _rule_unknown_tool(
    _gate: PolicyGate, _state: dict, tool_name: str, _args: dict, _mode: str,
    tool: Any | None, _policy: Any,
) -> PolicyDecision | None:
    if tool is None:
        return PolicyDecision(status="blocked", reason=f"Unknown tool: {tool_name}", risk_level="danger")
    return None


def _rule_side_effects(
    _gate: PolicyGate, _state: dict, tool_name: str, _args: dict, _mode: str,
    _tool: Any, policy: Any,
) -> PolicyDecision | None:
    if policy.side_effect in {"write", "destructive"}:
        return PolicyDecision(
            status="blocked",
            reason=f"Tool {tool_name} has forbidden side effects for Agent Kernel.",
            risk_level="danger",
        )
    return None


def _rule_escalate_tool(
    _gate: PolicyGate, _state: dict, tool_name: str, args: dict, _mode: str,
    _tool: Any, _policy: Any,
) -> PolicyDecision | None:
    if tool_name == "escalate.tool_group":
        return PolicyDecision(
            status="allowed",
            reason="Tool group escalation is a no-side-effect control operation.",
            safe_args=args,
            risk_level="safe",
        )
    return None


def _rule_tool_group(
    _gate: PolicyGate, state: dict, tool_name: str, _args: dict, _mode: str,
    tool: Any, _policy: Any,
) -> PolicyDecision | None:
    allowed_groups = state.get("allowed_tool_groups") or []
    if allowed_groups:
        group = tool.spec.group or tool_to_group(tool_name)
        if group not in allowed_groups:
            return PolicyDecision(
                status="blocked",
                reason=f"Tool '{tool_name}' (group={group}) is not in allowed_tool_groups: {allowed_groups}.",
                risk_level="danger",
            )
    return None


def _rule_execution_mode(
    _gate: PolicyGate, state: dict, tool_name: str, _args: dict, execution_mode: str,
    _tool: Any, policy: Any,
) -> PolicyDecision | None:
    data_read_tools = {"db.preview", "db.query"}
    if tool_name in data_read_tools or policy.requires_validated_sql:
        effective_mode = execution_mode
        if execution_mode == "user_requested_read" and not state.get("execute", True):
            effective_mode = "suggest_only"
        if effective_mode in ("none", "suggest_only"):
            label = "Live data reads" if tool_name in data_read_tools else "SQL execution"
            return PolicyDecision(
                status="blocked",
                reason=f"{label} are not allowed in {effective_mode} mode.",
                risk_level="danger",
            )
    return None


def _rule_validated_sql(
    _gate: PolicyGate, state: dict, _tool_name: str, args: dict, execution_mode: str,
    _tool: Any, policy: Any,
) -> PolicyDecision | None:
    if not policy.requires_validated_sql:
        return None

    raw_safety = state.get("safety")
    safety: dict[str, Any] = raw_safety if isinstance(raw_safety, dict) else {}
    can_execute = bool(safety.get("can_execute"))
    safe_sql = str(safety.get("safe_sql") or "").strip()
    original_sql = str(safety.get("original_sql") or state.get("sql") or "").strip()

    # SQL argument must match the validated statement
    args_sql = str(args.get("sql") or "").strip()
    if args_sql:
        norm_args = " ".join(args_sql.lower().split())
        norm_safe = " ".join(safe_sql.lower().split())
        norm_orig = " ".join(original_sql.lower().split())
        if not ((safe_sql and norm_args == norm_safe) or (original_sql and norm_args == norm_orig)):
            return PolicyDecision(
                status="blocked",
                reason="SQL parameter does not match the validated safe_sql or original_sql.",
                risk_level="danger",
            )

    blocked_reasons = [str(r) for r in safety.get("blocked_reasons", [])]
    hard_blockers = [r for r in blocked_reasons if r != "requires_confirmation"]

    # agent_autonomous_read + prod → approval
    if _rule_agent_autonomous_read(state, execution_mode, safe_sql, original_sql, policy):
        return _rule_agent_autonomous_read(state, execution_mode, safe_sql, original_sql, policy)

    if hard_blockers:
        return PolicyDecision(status="blocked", reason=f"SQL blocked by TrustGate: {hard_blockers}", risk_level="danger")
    if not can_execute or not safe_sql:
        return PolicyDecision(status="blocked", reason="SQL execution requires a previous successful sql.validate result.", risk_level="danger")
    if safety.get("requires_confirmation"):
        return PolicyDecision(status="approval_required", reason="This SQL execution requires human approval.", risk_level="warning", safe_args={"sql": safe_sql})

    return PolicyDecision(status="allowed", reason="SQL was validated by TrustGate.", risk_level="safe", safe_args={"sql": safe_sql})


def _rule_agent_autonomous_read(
    state: dict, execution_mode: str, safe_sql: str, original_sql: str, policy: Any,
) -> PolicyDecision | None:
    env_profile = state.get("environment_profile") or {}
    env = env_profile.get("env", "unknown")
    if execution_mode == "agent_autonomous_read" and (env == "prod" or policy.risk_level in ("warning", "danger")):
        return PolicyDecision(
            status="approval_required",
            reason=f"Agent-autonomous data read on {env} datasource requires human approval.",
            risk_level="warning",
            safe_args={"sql": safe_sql or original_sql},
        )
    return None


def _rule_agent_read_approval(
    _gate: PolicyGate, state: dict, tool_name: str, args: dict, execution_mode: str,
    _tool: Any, policy: Any,
) -> PolicyDecision | None:
    if tool_name in {"db.preview", "db.query"} and execution_mode == "agent_autonomous_read":
        env_profile = state.get("environment_profile") or {}
        env = env_profile.get("env", "unknown")
        if env == "prod" or policy.risk_level in ("warning", "danger"):
            return PolicyDecision(
                status="approval_required",
                reason=f"Agent-autonomous data read with {tool_name} on {env} datasource requires human approval.",
                risk_level="warning",
                safe_args=args,
            )
    return None


def _rule_requires_approval(
    _gate: PolicyGate, _state: dict, tool_name: str, args: dict, _mode: str,
    _tool: Any, policy: Any,
) -> PolicyDecision | None:
    if policy.requires_approval:
        return PolicyDecision(
            status="approval_required",
            reason=f"Tool {tool_name} requires approval.",
            risk_level=policy.risk_level,
            safe_args=args,
        )
    return None


# Ordered list: each rule gets a chance to block/approve.  First non-None wins.
_RULES: list[_RuleFunc] = [
    _rule_unknown_tool,
    _rule_side_effects,
    _rule_escalate_tool,
    _rule_tool_group,
    _rule_execution_mode,
    _rule_validated_sql,
    _rule_agent_read_approval,
    _rule_requires_approval,
]


# ── PolicyGate ───────────────────────────────────────────────────────────────────


class PolicyGate:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def check(
        self,
        state: dict[str, Any],
        tool_name: str,
        args: dict[str, Any],
        execution_mode: str = "user_requested_read",
    ) -> PolicyDecision:
        tool = self.registry.get(tool_name)
        policy = tool.spec.policy if tool else None

        for rule in _RULES:
            decision = rule(self, state, tool_name, args, execution_mode, tool, policy)
            if decision is not None:
                return decision

        return PolicyDecision(
            status="allowed",
            reason=f"Tool {tool_name} is allowed by policy.",
            risk_level=policy.risk_level if policy else "safe",
            safe_args=args,
        )

    @property
    def rules(self) -> list[_RuleFunc]:
        """Exposed for introspection / testing."""
        return list(_RULES)
