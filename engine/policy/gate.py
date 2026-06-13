from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from engine.agent_core.tool_registry import ToolRegistry, tool_to_group


class PolicyDecision(BaseModel):
    status: Literal["allowed", "blocked", "approval_required"]
    reason: str
    safe_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    # To support wait approval state creation
    approval: dict[str, Any] | None = None


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
        if tool is None:
            return PolicyDecision(
                status="blocked",
                reason=f"Unknown tool: {tool_name}",
                risk_level="danger",
            )

        policy = tool.spec.policy
        if policy.side_effect in {"write", "destructive"}:
            return PolicyDecision(
                status="blocked",
                reason=f"Tool {tool_name} has forbidden side effects for Agent Kernel.",
                risk_level="danger",
            )

        # ---- Special: escalate.tool_group is always allowed (control tool) ----
        if tool_name == "escalate.tool_group":
            return PolicyDecision(
                status="allowed",
                reason="Tool group escalation is a no-side-effect control operation.",
                safe_args=args,
                risk_level="safe",
            )

        # ---- Hard boundary: check tool group against Planner's allowed_tool_groups ----
        allowed_groups = state.get("allowed_tool_groups") or []
        if allowed_groups:
            # Prefer spec.group from the tool definition over static mapping fallback
            group = tool.spec.group or tool_to_group(tool_name)
            if group not in allowed_groups:
                return PolicyDecision(
                    status="blocked",
                    reason=f"Tool '{tool_name}' (group={group}) is not in allowed_tool_groups: {allowed_groups}.",
                    risk_level="danger",
                )

        # ---- SQL execution gating via execution_mode ----
        data_read_tools = {"db.preview", "db.query"}
        if tool_name in data_read_tools:
            effective_mode = execution_mode
            if execution_mode == "user_requested_read" and not state.get("execute", True):
                effective_mode = "suggest_only"
            if effective_mode in ("none", "suggest_only"):
                return PolicyDecision(
                    status="blocked",
                    reason=f"Live data reads are not allowed in {effective_mode} mode.",
                    risk_level="danger",
                )

        if policy.requires_validated_sql:
            effective_mode = execution_mode
            if execution_mode == "user_requested_read" and not state.get("execute", True):
                effective_mode = "suggest_only"
            if effective_mode in ("none", "suggest_only"):
                return PolicyDecision(
                    status="blocked",
                    reason=f"SQL execution is not allowed in {effective_mode} mode.",
                    risk_level="danger",
                )

            raw_safety = state.get("safety")
            safety: dict[str, Any] = raw_safety if isinstance(raw_safety, dict) else {}
            can_execute = bool(safety.get("can_execute"))
            safe_sql = str(safety.get("safe_sql") or "").strip()
            original_sql = str(safety.get("original_sql") or state.get("sql") or "").strip()

            args_sql = str(args.get("sql") or "").strip()
            if args_sql:
                normalized_args_sql = " ".join(args_sql.lower().split())
                normalized_safe_sql = " ".join(safe_sql.lower().split())
                normalized_orig_sql = " ".join(original_sql.lower().split())
                is_match = False
                if safe_sql and normalized_args_sql == normalized_safe_sql:
                    is_match = True
                elif original_sql and normalized_args_sql == normalized_orig_sql:
                    is_match = True

                if not is_match:
                    return PolicyDecision(
                        status="blocked",
                        reason="SQL parameter in arguments does not match the validated safe_sql or original_sql.",
                        risk_level="danger",
                    )

            blocked_reasons = [str(reason) for reason in safety.get("blocked_reasons", [])]
            hard_blockers = [reason for reason in blocked_reasons if reason != "requires_confirmation"]

            # agent_autonomous_read: enforce stricter approval even when SQL is valid
            if tool_name == "sql.execute_readonly":
                if effective_mode == "agent_autonomous_read":
                    env_profile = state.get("environment_profile") or {}
                    env = env_profile.get("env", "unknown")
                    if env == "prod" or policy.risk_level in ("warning", "danger"):
                        return PolicyDecision(
                            status="approval_required",
                            reason=f"Agent-autonomous data read on {env} datasource requires human approval.",
                            risk_level="warning",
                            safe_args={"sql": safe_sql or original_sql},
                        )

            if safety.get("requires_confirmation") and not hard_blockers and original_sql:
                return PolicyDecision(
                    status="approval_required",
                    reason="This SQL execution requires human approval.",
                    risk_level="warning",
                    safe_args={"sql": safe_sql or original_sql},
                )

            if not can_execute or not safe_sql:
                return PolicyDecision(
                    status="blocked",
                    reason="SQL execution requires a previous successful sql.validate result.",
                    risk_level="danger",
                )

            if safety.get("requires_confirmation"):
                return PolicyDecision(
                    status="approval_required",
                    reason="This SQL execution requires human approval.",
                    risk_level="warning",
                    safe_args={"sql": safe_sql},
                )

            return PolicyDecision(
                status="allowed",
                reason="SQL was validated by TrustGate.",
                risk_level="safe",
                safe_args={"sql": safe_sql},
            )

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

        if policy.requires_approval:
            return PolicyDecision(
                status="approval_required",
                reason=f"Tool {tool_name} requires approval.",
                risk_level=policy.risk_level,
                safe_args=args,
            )

        return PolicyDecision(
            status="allowed",
            reason=f"Tool {tool_name} is allowed by policy.",
            risk_level=policy.risk_level,
            safe_args=args,
        )
