"""Developer-facing hierarchical traces derived from durable runtime state."""

from __future__ import annotations

from typing import Any

from engine.json_codec import JsonCodecError, loads

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.models import AgentApproval, AgentRun, AgentToolInvocation, AgentTurn


def _loads(value: str | None) -> dict[str, Any]:
    try:
        parsed = loads(value or "{}")
    except JsonCodecError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def build_run_trace(db: Session, *, session_id: str, run_id: str) -> dict[str, Any] | None:
    run = db.get(AgentRun, run_id)
    if run is None or str(run.session_id) != session_id:
        return None
    turns = list(db.execute(
        select(AgentTurn)
        .where(AgentTurn.run_id == run_id)
        .order_by(AgentTurn.sequence)
    ).scalars().all())
    invocations = list(db.execute(
        select(AgentToolInvocation)
        .where(AgentToolInvocation.run_id == run_id)
        .order_by(AgentToolInvocation.created_at)
    ).scalars().all())
    approvals = {
        str(item.tool_invocation_id): item
        for item in db.execute(
            select(AgentApproval).where(AgentApproval.run_id == run_id)
        ).scalars().all()
    }

    spans: list[dict[str, Any]] = [{
        "id": f"span:run:{run.id}",
        "parent_id": None,
        "kind": "run",
        "name": "Agent Run",
        "status": str(run.status),
        "started_at": _iso(run.started_at or run.created_at),
        "ended_at": _iso(run.completed_at),
        "attributes": {
            "run_id": str(run.id),
            "session_id": str(run.session_id),
            "model_name": str(run.model_name or ""),
            "consumed_tokens": int(run.consumed_tokens or 0),
            "consumed_cost_usd": float(run.consumed_cost_usd or 0),
        },
    }]
    for turn in turns:
        turn_span_id = f"span:turn:{turn.id}"
        spans.append({
            "id": turn_span_id,
            "parent_id": f"span:run:{run.id}",
            "kind": "turn",
            "name": f"Turn {turn.sequence}",
            "status": str(turn.status),
            "started_at": _iso(turn.created_at),
            "ended_at": _iso(turn.completed_at),
            "attributes": {
                "turn_id": str(turn.id),
                "usage": _loads(str(turn.usage_json or "{}")),
                "error_code": str(turn.error_code or ""),
            },
        })
        spans.append({
            "id": f"span:model:{turn.id}",
            "parent_id": turn_span_id,
            "kind": "model",
            "name": str(turn.model_name or "Model generation"),
            "status": str(turn.status),
            "started_at": _iso(turn.created_at),
            "ended_at": _iso(turn.completed_at),
            "attributes": {
                "provider": str(turn.provider or ""),
                "prompt_hash": str(turn.prompt_hash or ""),
            },
        })

    for invocation in invocations:
        tool_span_id = f"span:tool:{invocation.id}"
        turn_span_id = f"span:turn:{invocation.turn_id}"
        policy = _loads(str(invocation.policy_json or "{}"))
        spans.append({
            "id": tool_span_id,
            "parent_id": turn_span_id,
            "kind": "tool",
            "name": str(invocation.tool_name),
            "status": str(invocation.status),
            "started_at": _iso(invocation.started_at or invocation.created_at),
            "ended_at": _iso(invocation.completed_at),
            "attributes": {
                "invocation_id": str(invocation.id),
                "attempt_count": int(invocation.attempt_count or 0),
                "error_code": str(invocation.error_code or ""),
            },
        })
        spans.append({
            "id": f"span:policy:{invocation.id}",
            "parent_id": tool_span_id,
            "kind": "policy",
            "name": "Policy decision",
            "status": str(policy.get("status") or "unknown"),
            "started_at": _iso(invocation.created_at),
            "ended_at": _iso(invocation.started_at or invocation.created_at),
            "attributes": {
                "risk_level": policy.get("risk_level"),
                "requires_approval": policy.get("status") == "approval_required",
                "reason": str(policy.get("reason") or "")[:500],
            },
        })
        approval = approvals.get(str(invocation.id))
        if approval is not None:
            spans.append({
                "id": f"span:approval:{approval.id}",
                "parent_id": tool_span_id,
                "kind": "approval",
                "name": "Human approval",
                "status": str(approval.status),
                "started_at": _iso(approval.created_at),
                "ended_at": _iso(approval.decided_at),
                "attributes": {
                    "approval_id": str(approval.id),
                    "risk_level": str(approval.risk_level),
                    "decided_by": str(approval.decided_by or ""),
                },
            })
    return {
        "trace_id": f"trace:{run.id}",
        "session_id": session_id,
        "run_id": run_id,
        "spans": spans,
    }
