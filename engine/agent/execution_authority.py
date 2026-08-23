"""Verification of durable approvals before a tool leaf is entered."""

from __future__ import annotations

from typing import Any

from engine.agent.tool import ToolInvocation
from engine.json_codec import JsonCodecError, loads
from engine.policy.authority import ExecutionAuthority, canonical_hash
from engine.policy.gate import PolicyDecision
from engine.resource import ResourceScopeRef


class ApprovalAuthorityError(RuntimeError):
    pass


def _object(value: str | None) -> dict[str, Any]:
    try:
        loaded = loads(value or "{}")
    except JsonCodecError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


class ApprovalAuthorityVerifier:
    """Turn an approved database record into a scoped execution capability."""

    def verify(
        self,
        *,
        invocation: ToolInvocation,
        approval: Any,
        decision: PolicyDecision,
        resource_ref: ResourceScopeRef | None,
    ) -> ExecutionAuthority:
        if approval is None or str(approval.status) != "approved":
            raise ApprovalAuthorityError("The invocation has no active approval grant")
        if str(approval.tool_invocation_id) != invocation.id:
            raise ApprovalAuthorityError("Approval is bound to another invocation")
        if str(approval.tool_name) != invocation.tool_name:
            raise ApprovalAuthorityError("Approval is bound to another tool")

        requested_action = _object(str(approval.requested_action_json or "{}"))
        requested_arguments = requested_action.get("arguments")
        if not isinstance(requested_arguments, dict):
            raise ApprovalAuthorityError("Approval has no canonical action payload")
        if canonical_hash(requested_arguments) != invocation.authorized_input_hash:
            raise ApprovalAuthorityError("Approved action differs from the durable invocation")
        if canonical_hash(decision.safe_args) != invocation.authorized_input_hash:
            raise ApprovalAuthorityError("Current policy authorizes a different action")

        persisted_decision = _object(str(approval.policy_decision_json or "{}"))
        persisted_contract = persisted_decision.get("approval")
        current_contract = decision.approval
        if persisted_contract != current_contract:
            raise ApprovalAuthorityError("Approval policy contract is stale")
        if isinstance(current_contract, dict):
            approved_resource = current_contract.get("resource_ref")
            if approved_resource is not None:
                if ResourceScopeRef.model_validate(approved_resource) != resource_ref:
                    raise ApprovalAuthorityError("Resource version changed after approval")

        return ExecutionAuthority(
            approval_id=str(approval.id),
            invocation_id=invocation.id,
            tool_name=invocation.tool_name,
            authorized_input_hash=invocation.authorized_input_hash,
            policy_fingerprint=canonical_hash(decision.model_dump(mode="json")),
            approval_subject_fingerprint=(
                str(current_contract.get("subject_fingerprint"))
                if isinstance(current_contract, dict)
                and current_contract.get("subject_fingerprint")
                else None
            ),
            resource_ref=(
                ResourceScopeRef.model_validate(current_contract["resource_ref"])
                if isinstance(current_contract, dict)
                and current_contract.get("resource_ref") is not None
                else None
            ),
        )
