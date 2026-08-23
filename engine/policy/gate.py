from __future__ import annotations
import logging
from typing import Any, Callable, Literal
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from engine.agent.repositories.artifact import ArtifactRepository
from engine.policy.authority import canonical_hash
from engine.resource import ResourceScopeRef
from engine.tools.runtime.admission import (
    ToolAdmissionContext,
    ToolAdmissionDecision,
)
from engine.tools.runtime.registry import ToolRegistry

logger = logging.getLogger("dbfox.policy.gate")


class PolicyDecision(BaseModel):
    status: Literal["allowed", "blocked", "approval_required"]
    reason: str
    safe_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["safe", "warning", "danger"] = "safe"
    approval: dict[str, Any] | None = None
    error_code: Literal["TOOL_INPUT_INVALID"] | None = None


def _safe_input_contract_reason(
    tool_name: str,
    error: ValidationError,
) -> str:
    """Project Pydantic failures without reflecting model-authored values."""

    issues: list[str] = []
    for item in error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in item.get("loc") or ()) or "root"
        issue_type = str(item.get("type") or "invalid")
        issue = f"{location} ({issue_type})"
        if issue not in issues:
            issues.append(issue)
    summary = ", ".join(issues[:8]) or "arguments (invalid)"
    return (
        f"Tool {tool_name} arguments violate its declared input contract. "
        f"Correct these schema locations and submit a complete call: {summary}."
    )


# ── Rule chain infrastructure ────────────────────────────────────────────────────
#
# Each rule receives (gate, state, tool_name, args, execution_mode, tool, policy)
# and returns a PolicyDecision to short-circuit, or None to let the next rule run.


_RuleFunc = Callable[..., PolicyDecision | None]
_AGENT_KERNEL_CAPABILITIES = frozenset(
    {
        "metadata_read",
        "metadata_write",
        "database_read",
        "filesystem_read",
        "filesystem_write",
        "network",
    }
)


def _rule_unknown_tool(
    _gate: PolicyGate, _state: dict, tool_name: str, _args: dict, _mode: str,
    tool: Any | None, _policy: Any,
) -> PolicyDecision | None:
    if tool is None:
        return PolicyDecision(status="blocked", reason=f"Unknown tool: {tool_name}", risk_level="danger")
    return None


def _rule_capabilities(
    _gate: PolicyGate, _state: dict, tool_name: str, _args: dict, _mode: str,
    tool: Any, _policy: Any,
) -> PolicyDecision | None:
    capabilities = set(tool.spec.execution.capabilities)
    forbidden = sorted(capabilities - _AGENT_KERNEL_CAPABILITIES)
    if forbidden:
        return PolicyDecision(
            status="blocked",
            reason=(
                f"Tool {tool_name} requires capabilities that are forbidden in the "
                f"Agent Kernel: {', '.join(forbidden)}."
            ),
            risk_level="danger",
        )
    return None


def _rule_tool_group(
    _gate: PolicyGate, state: dict, tool_name: str, _args: dict, _mode: str,
    tool: Any, _policy: Any,
) -> PolicyDecision | None:
    allowed_groups = state.get("allowed_tool_groups") or []
    if allowed_groups:
        group = tool.spec.group
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
    reads_database = "database_read" in set(_tool.spec.execution.capabilities)
    allowed_modes = set(policy.allowed_execution_modes)
    if allowed_modes and execution_mode not in allowed_modes:
        return PolicyDecision(
            status="blocked",
            reason=f"Tool execution is not allowed in {execution_mode} mode.",
            risk_level="danger",
        )
    if reads_database:
        effective_mode = execution_mode
        if execution_mode == "user_requested_read" and not state.get("execute", True):
            effective_mode = "suggest_only"
        if effective_mode in ("none", "suggest_only"):
            return PolicyDecision(
                status="blocked",
                reason=f"Live data reads are not allowed in {effective_mode} mode.",
                risk_level="danger",
            )
    return None


def _rule_tool_admission(
    gate: PolicyGate,
    state: dict,
    tool_name: str,
    args: dict,
    _execution_mode: str,
    tool: Any,
    policy: Any,
) -> PolicyDecision | None:
    if not policy.requires_admission:
        return None
    session_id = str(state.get("session_id") or "")
    run_id = str(state.get("run_id") or "")
    resource_refs = tuple(
        ref
        for ref in state.get("resource_refs") or ()
        if isinstance(ref, ResourceScopeRef)
    )
    repository = ArtifactRepository(gate.db)
    context = ToolAdmissionContext(
        session_id=session_id,
        run_id=run_id,
        resource_refs=resource_refs,
        artifact_loader=lambda artifact_id: repository.get_for_run(
            session_id=session_id,
            run_id=run_id,
            artifact_id=artifact_id,
        ),
        artifact_relation_loader=lambda artifact_id, relation: (
            repository.artifacts_relating_to_for_run(
                session_id=session_id,
                run_id=run_id,
                artifact_id=artifact_id,
                relation=relation,
            )
        ),
    )
    try:
        tool_input = tool.input_model.model_validate(args)
        admission = ToolAdmissionDecision.model_validate(
            tool.admit(tool_input, context)
        )
    except Exception as exc:
        logger.error(
            "Tool admission failed closed: tool=%s type=%s",
            tool_name,
            type(exc).__name__,
        )
        return PolicyDecision(
            status="blocked",
            reason="Tool admission could not validate the requested action.",
            risk_level="danger",
        )
    if admission.resource_ref is not None and admission.resource_ref not in resource_refs:
        return PolicyDecision(
            status="blocked",
            reason="Tool admission selected a resource outside the frozen Run authority.",
            risk_level="danger",
        )
    if admission.status == "blocked":
        return PolicyDecision(
            status="blocked",
            reason=admission.reason,
            risk_level=admission.risk_level,
        )
    if admission.status == "approval_required":
        subject = admission.approval_subject or {}
        return PolicyDecision(
            status="approval_required",
            reason=admission.reason,
            risk_level=admission.risk_level,
            safe_args=args,
            approval={
                "kind": "tool_admission",
                "subject_fingerprint": canonical_hash(subject),
                "resource_ref": (
                    admission.resource_ref.model_dump(mode="json")
                    if admission.resource_ref is not None
                    else None
                ),
            },
        )
    return None


def _rule_agent_read_approval(
    _gate: PolicyGate, state: dict, tool_name: str, args: dict, execution_mode: str,
    _tool: Any, policy: Any,
) -> PolicyDecision | None:
    reads_database = "database_read" in set(_tool.spec.execution.capabilities)
    if reads_database and execution_mode == "agent_autonomous_read":
        env_profile = state.get("environment_profile") or {}
        env = env_profile.get("env", "unknown")
        if env in {"prod", "unknown"} or policy.risk_level in ("warning", "danger"):
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
# Core safety checks (tool existence, capabilities, group allowlist, execution mode)
# MUST run before any fast-path allow rules so that dangerous tools cannot
# slip past them by name alone.
_RULES: list[_RuleFunc] = [
    _rule_unknown_tool,
    _rule_capabilities,
    _rule_tool_group,
    _rule_execution_mode,
    _rule_tool_admission,
    _rule_agent_read_approval,
    _rule_requires_approval,
]


# ── PolicyGate ───────────────────────────────────────────────────────────────────


class PolicyGate:
    def __init__(self, registry: ToolRegistry, db: Session):
        self.registry = registry
        self.db = db

    def check(
        self,
        state: dict[str, Any],
        tool_name: str,
        args: dict[str, Any],
        execution_mode: str = "user_requested_read",
    ) -> PolicyDecision:
        tool = self.registry.get(tool_name)
        policy = tool.spec.policy if tool else None
        if tool is not None:
            try:
                args = tool.input_model.model_validate(args).model_dump(
                    mode="json",
                    exclude_none=True,
                )
            except ValidationError as exc:
                return PolicyDecision(
                    status="blocked",
                    reason=_safe_input_contract_reason(tool_name, exc),
                    risk_level="danger",
                    error_code="TOOL_INPUT_INVALID",
                )

        for rule in _RULES:
            decision = rule(self, state, tool_name, args, execution_mode, tool, policy)
            if decision is not None:
                if decision.status != "allowed":
                    logger.warning(
                        "PolicyGate: %s → %s (reason=%s)",
                        tool_name, decision.status, decision.reason,
                    )
                return decision

        logger.debug("PolicyGate: %s → allowed", tool_name)
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
