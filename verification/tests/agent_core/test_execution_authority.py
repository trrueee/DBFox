from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engine.errors import GuardrailValidationError
from engine.agent.execution_authority import (
    ApprovalAuthorityError,
    ApprovalAuthorityVerifier,
)
from engine.agent.tool import ToolInvocation, ToolInvocationStatus
from engine.policy.authority import (
    ExecutionAuthority,
    canonical_hash,
)
from engine.policy.gate import PolicyDecision
from engine.resource import ResourceScopeRef
from engine.tools.runtime.base import ToolRecoveryPolicy
from engine.tools.db.sql_execution import sql_execute_readonly


def _decision(*, generation: int = 4, subject: str = "subject-v1") -> PolicyDecision:
    safe_args = {"safe_sql": "SELECT 1"}
    return PolicyDecision(
        status="approval_required",
        reason="approval required",
        safe_args=safe_args,
        risk_level="warning",
        approval={
            "kind": "tool_admission",
            "subject_fingerprint": canonical_hash({"subject": subject}),
            "resource_ref": {
                "kind": "dbfox.data.database",
                "id": "datasource-1",
                "version": generation,
            },
        },
    )


def _invocation(decision: PolicyDecision) -> ToolInvocation:
    return ToolInvocation(
        id="invocation-1",
        session_id="session-1",
        run_id="run-1",
        turn_id="turn-1",
        provider_call_id="provider-call-1",
        tool_name="sql_execute_readonly",
        declared_version="1",
        contract_hash="sha256:1",
        authorized_input=decision.safe_args,
        authorized_input_hash=canonical_hash(decision.safe_args),
        idempotency_key="idempotency-1",
        status=ToolInvocationStatus.REQUESTED,
        policy=decision.model_dump(mode="json"),
        recovery_policy=ToolRecoveryPolicy.RETRY_SAFE,
    )


def _approval(invocation: ToolInvocation, decision: PolicyDecision):
    return SimpleNamespace(
        id="approval-1",
        status="approved",
        tool_invocation_id=invocation.id,
        tool_name=invocation.tool_name,
        requested_action_json=json.dumps({
            "tool_name": invocation.tool_name,
            "arguments": decision.safe_args,
        }),
        policy_decision_json=decision.model_dump_json(),
    )


def test_approved_action_becomes_scoped_execution_authority() -> None:
    decision = _decision()
    invocation = _invocation(decision)

    authority = ApprovalAuthorityVerifier().verify(
        invocation=invocation,
        approval=_approval(invocation, decision),
        decision=decision,
        resource_ref=ResourceScopeRef(
            kind="dbfox.data.database", id="datasource-1", version=4
        ),
    )

    assert authority.approval_id == "approval-1"
    assert authority.authorized_input_hash == invocation.authorized_input_hash
    assert authority.approval_subject_fingerprint == canonical_hash(
        {"subject": "subject-v1"}
    )
    assert authority.resource_ref == ResourceScopeRef(
        kind="dbfox.data.database", id="datasource-1", version=4
    )


@pytest.mark.parametrize(
    ("current_decision", "generation"),
    [
        (_decision(generation=5), 5),
        (_decision(subject="subject-v2"), 4),
    ],
)
def test_stale_approval_cannot_authorize_changed_policy_contract(
    current_decision: PolicyDecision,
    generation: int,
) -> None:
    approved_decision = _decision()
    invocation = _invocation(approved_decision)

    with pytest.raises(ApprovalAuthorityError):
        ApprovalAuthorityVerifier().verify(
            invocation=invocation,
            approval=_approval(invocation, approved_decision),
            decision=current_decision,
            resource_ref=ResourceScopeRef(
                kind="dbfox.data.database", id="datasource-1", version=generation
            ),
        )


def test_sql_leaf_accepts_matching_approval_authority(monkeypatch) -> None:
    safety = {
        "can_execute": True,
        "safe_sql": "SELECT 1",
        "original_sql": "SELECT 1",
        "requires_confirmation": True,
        "blocked_reasons": ["requires_confirmation"],
    }
    approval_subject = {"validationArtifactId": "artifact-1", "safety": safety}
    authority = ExecutionAuthority(
        approval_id="approval-1",
        invocation_id="invocation-1",
        tool_name="sql_execute_readonly",
        authorized_input_hash=canonical_hash({"safe_sql": "SELECT 1"}),
        policy_fingerprint="policy-1",
        approval_subject_fingerprint=canonical_hash(approval_subject),
        resource_ref=ResourceScopeRef(
            kind="dbfox.data.database", id="datasource-1", version=4
        ),
    )
    monkeypatch.setattr(
        "engine.tools.db.sql_execution.execute_query",
        lambda *_args, **_kwargs: {
            "rows": [{"value": 1}],
            "columns": ["value"],
            "latencyMs": 1,
        },
    )

    result = sql_execute_readonly(
        db=SimpleNamespace(),
        datasource_id="datasource-1",
        safety=safety,
        expected_connection_generation=4,
        execution_authority=authority,
        approval_subject=approval_subject,
    )

    assert result["success"] is True
    assert result["rowCount"] == 1


def test_sql_leaf_rejects_authority_from_another_generation() -> None:
    safety = {
        "can_execute": True,
        "safe_sql": "SELECT 1",
        "original_sql": "SELECT 1",
        "requires_confirmation": True,
        "blocked_reasons": ["requires_confirmation"],
    }
    approval_subject = {"validationArtifactId": "artifact-1", "safety": safety}
    authority = ExecutionAuthority(
        approval_id="approval-1",
        invocation_id="invocation-1",
        tool_name="sql_execute_readonly",
        authorized_input_hash=canonical_hash({"safe_sql": "SELECT 1"}),
        policy_fingerprint="policy-1",
        approval_subject_fingerprint=canonical_hash(approval_subject),
        resource_ref=ResourceScopeRef(
            kind="dbfox.data.database", id="datasource-1", version=3
        ),
    )

    with pytest.raises(GuardrailValidationError, match="approval workflow"):
        sql_execute_readonly(
            db=SimpleNamespace(),
            datasource_id="datasource-1",
            safety=safety,
            expected_connection_generation=4,
            execution_authority=authority,
            approval_subject=approval_subject,
        )
