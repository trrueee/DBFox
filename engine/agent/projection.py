"""Read-optimized conversation snapshot from the canonical Agent tables."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.repositories.artifact import ArtifactRepository
from engine.models import (
    AgentApproval,
    AgentEvidenceRecord,
    AgentMessage,
    AgentObservationRecord,
    AgentQuestionRequest,
    AgentRun,
    AgentSession,
    AgentToolInvocation,
    AgentTaskPlanRecord,
    AgentTurn,
)


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def conversation_snapshot(db: Session, session_id: str) -> dict[str, Any] | None:
    aggregate = db.get(AgentSession, session_id)
    if aggregate is None:
        return None
    messages = db.execute(
        select(AgentMessage).where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.sequence)
    ).scalars().all()
    runs = db.execute(
        select(AgentRun).where(AgentRun.session_id == session_id)
        .order_by(AgentRun.session_sequence)
    ).scalars().all()
    turns = db.execute(
        select(AgentTurn).where(AgentTurn.session_id == session_id)
        .order_by(AgentTurn.created_at)
    ).scalars().all()
    invocations = db.execute(
        select(AgentToolInvocation).where(AgentToolInvocation.session_id == session_id)
        .order_by(AgentToolInvocation.created_at)
    ).scalars().all()
    observations = db.execute(
        select(AgentObservationRecord).where(AgentObservationRecord.session_id == session_id)
        .order_by(AgentObservationRecord.created_at)
    ).scalars().all()
    approvals = db.execute(
        select(AgentApproval).where(AgentApproval.session_id == session_id)
        .order_by(AgentApproval.created_at)
    ).scalars().all()
    questions = db.execute(
        select(AgentQuestionRequest).where(AgentQuestionRequest.session_id == session_id)
        .order_by(AgentQuestionRequest.created_at)
    ).scalars().all()
    evidence = db.execute(
        select(AgentEvidenceRecord).where(AgentEvidenceRecord.session_id == session_id)
        .order_by(AgentEvidenceRecord.created_at)
    ).scalars().all()
    artifacts = []
    artifact_repository = ArtifactRepository(db)
    for run in runs:
        artifacts.extend(artifact_repository.list_for_run(str(run.id)))
    plans = db.execute(
        select(AgentTaskPlanRecord).where(AgentTaskPlanRecord.session_id == session_id)
        .order_by(AgentTaskPlanRecord.updated_at)
    ).scalars().all()

    activities: list[dict[str, Any]] = []
    invocation_by_turn: dict[str, list[AgentToolInvocation]] = {}
    observation_by_invocation = {
        str(observation.tool_invocation_id): observation
        for observation in observations
    }
    for invocation in invocations:
        invocation_by_turn.setdefault(str(invocation.turn_id), []).append(invocation)
    for turn in turns:
        activities.append({
            "id": f"activity:{turn.id}:analysis",
            "run_id": str(turn.run_id), "turn_id": str(turn.id), "kind": "analysis",
            "title": _analysis_activity_title(
                str(turn.status), bool(invocation_by_turn.get(str(turn.id))),
                recovered=str(turn.error_code or "") == "MODEL_STREAM_INTERRUPTED",
            ),
            "summary": str(turn.reasoning_summary or "").strip()[:280] or None,
            "status": "completed" if turn.status == "completed" else str(turn.status),
            "started_at": turn.created_at.isoformat() if turn.created_at else None,
            "completed_at": turn.completed_at.isoformat() if turn.completed_at else None,
            "artifact_ids": [],
        })
        for invocation in invocation_by_turn.get(str(turn.id), []):
            observation = observation_by_invocation.get(str(invocation.id))
            activities.append({
                "id": f"activity:{invocation.id}",
                "run_id": str(invocation.run_id), "turn_id": str(turn.id), "kind": "tool",
                "title": _tool_activity_title(str(invocation.tool_name)),
                "summary": _tool_activity_summary(invocation, observation),
                "status": _activity_status(str(invocation.status)),
                "tool_invocation_id": str(invocation.id),
                "artifact_ids": (
                    _loads(str(observation.artifact_ids_json or "[]"), [])
                    if observation is not None else []
                ),
                "started_at": (
                    invocation.started_at.isoformat() if invocation.started_at
                    else invocation.created_at.isoformat() if invocation.created_at else None
                ),
                "completed_at": invocation.completed_at.isoformat() if invocation.completed_at else None,
            })

    for plan in plans:
        steps = _loads(str(plan.steps_json or "[]"), [])
        completed = sum(1 for step in steps if step.get("status") in {"completed", "skipped"})
        current = next((step for step in steps if step.get("status") == "in_progress"), None)
        activities.append({
            "id": f"activity:plan:{plan.id}",
            "run_id": str(plan.run_id),
            "turn_id": str(plan.turn_id),
            "kind": "plan",
            "title": str(plan.objective),
            "summary": str(plan.summary or "").strip() or f"{completed}/{len(steps)} 个步骤已完成",
            "status": (
                "completed" if str(plan.status) == "completed"
                else "waiting" if str(plan.status) == "blocked"
                else "running"
            ),
            "artifact_ids": list(dict.fromkeys(
                artifact_id for step in steps for artifact_id in step.get("artifact_ids", [])
            )),
            "steps": steps,
            "current_step_id": str(current.get("id")) if current else None,
            "started_at": plan.created_at.isoformat() if plan.created_at else None,
            "completed_at": plan.updated_at.isoformat() if str(plan.status) == "completed" else None,
        })

    activities.sort(key=lambda item: str(item.get("started_at") or ""))

    return {
        "protocol_version": 1,
        "session": {
            "id": str(aggregate.id), "datasource_id": str(aggregate.datasource_id),
            "title": str(aggregate.title), "context_epoch": int(aggregate.context_epoch or 0),
            "selected_artifact_id": str(aggregate.selected_artifact_id) if aggregate.selected_artifact_id else None,
            "context_tables": _loads(str(aggregate.context_tables_json or "[]"), []),
        },
        "messages": [{
            "id": str(row.id), "role": str(row.role), "content": str(row.content),
            "status": str(row.status), "sequence": int(row.sequence),
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        } for row in messages],
        "runs": [{
            "id": str(row.id), "input_id": str(row.input_id), "status": str(row.status),
            "version": int(row.version or 0), "session_sequence": int(row.session_sequence),
            "datasource_id": str(row.datasource_id), "question": str(row.question),
            "user_message_id": str(row.user_message_id),
            "assistant_message_id": str(row.assistant_message_id),
            "current_turn_id": str(row.current_turn_id) if row.current_turn_id else None,
            "cancel_requested": bool(row.cancel_requested),
            "result": _loads(str(row.result_json or "{}"), {}),
            "error": ({"code": str(row.error_code), "message": str(row.error_message or "")}
                      if row.error_code else None),
        } for row in runs],
        "turns": [{
            "id": str(row.id), "run_id": str(row.run_id), "sequence": int(row.sequence),
            "status": str(row.status), "reasoning_summary": str(row.reasoning_summary or ""),
            "usage": _loads(str(row.usage_json or "{}"), {}),
        } for row in turns],
        "activities": activities,
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
        "evidence": [{
            "id": str(row.id), "session_id": str(row.session_id), "run_id": str(row.run_id),
            "claim_id": str(row.claim_id), "artifact_id": str(row.artifact_id),
            "label": str(row.label), "locator": _loads(str(row.locator_json), {}),
            "query_fingerprint": str(row.query_fingerprint),
            "observed_at": row.observed_at.isoformat(),
            "value": _loads(str(row.value_json), None) if row.value_json else None,
        } for row in evidence],
        "approvals": [{
            "id": str(row.id), "session_id": str(row.session_id), "run_id": str(row.run_id),
            "turn_id": str(row.turn_id), "tool_invocation_id": str(row.tool_invocation_id),
            "tool_name": str(row.tool_name), "status": str(row.status), "version": int(row.version or 0),
            "risk_level": str(row.risk_level), "reason": str(row.reason or ""),
            "policy_decision": _loads(str(row.policy_decision_json or "{}"), {}),
            "requested_action": _loads(str(row.requested_action_json or "{}"), {}),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "decided_by": str(row.decided_by) if row.decided_by else None,
            "decision_note": str(row.decision_note) if row.decision_note else None,
        } for row in approvals],
        "questions": [{
            "id": str(row.id), "session_id": str(row.session_id), "run_id": str(row.run_id),
            "turn_id": str(row.turn_id), "status": str(row.status), "version": int(row.version or 0),
            "question": str(row.question), "reason": str(row.reason),
            "options": _loads(str(row.options_json or "[]"), []),
            "allow_free_text": bool(row.allow_free_text),
            "response": _loads(str(row.response_json or "{}"), None) if row.response_json else None,
        } for row in questions],
        "cursor": int(aggregate.event_sequence or 0),
    }


def _activity_status(status: str) -> str:
    return {
        "requested": "pending", "running": "running", "waiting_approval": "waiting",
        "succeeded": "completed", "failed": "failed", "rejected": "failed", "unknown": "failed",
    }.get(status, status)


def _tool_activity_title(tool_name: str) -> str:
    labels = {
        "db.observe": "了解数据库结构", "db.search": "查找相关表和字段",
        "db.inspect": "检查表结构", "db.preview": "查看数据样例",
        "sql.validate": "验证分析 SQL", "sql.execute_readonly": "执行只读查询",
        "chart.suggest": "生成结果图表", "analysis.review": "复核分析覆盖度",
        "plan.update": "更新分析计划",
    }
    return labels.get(tool_name, f"运行 {tool_name}")


def _tool_activity_summary(
    invocation: AgentToolInvocation,
    observation: AgentObservationRecord | None,
) -> str | None:
    policy = _loads(str(invocation.policy_json or "{}"), {})
    if invocation.status in {"waiting_approval", "rejected"}:
        return str(policy.get("reason") or "") or None
    if invocation.error_code:
        return str(invocation.error_message or "操作未完成")
    if observation is not None:
        return str(observation.model_visible_summary or "") or None
    return None


def _analysis_activity_title(status: str, has_tools: bool, *, recovered: bool = False) -> str:
    if recovered:
        return "已恢复中断的分析"
    if status == "running":
        return "正在理解问题并规划分析"
    if status == "failed":
        return "本轮分析未完成"
    if has_tools:
        return "已确定下一步分析动作"
    return "已完成结果分析"
