from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.tools.tool_aliases import STEP_NAME_MAP
from engine.agent.progress.fast_path import (
    check_escalate,
    check_sql_repair_fastpath,
    deterministic_progress_fastpath,
    progress_decision_dict,
)
from engine.agent.progress.llm_judge import call_llm_judge
from engine.agent.progress.lens_formatter import enrich_progress_result
from engine.agent.app.error_boundary import public_agent_failure, safe_agent_log

logger = logging.getLogger("dbfox.dbfox_agent.nodes.progress_node")


def _confirmation_approval_update(state: DBFoxAgentState, ctx: Any) -> dict[str, Any] | None:
    safety = state.get("safety")
    if not isinstance(safety, dict) or not safety.get("requires_confirmation"):
        return None

    blocked_reasons = [str(reason) for reason in (safety.get("blocked_reasons") or [])]
    hard_blockers = [reason for reason in blocked_reasons if reason != "requires_confirmation"]
    safe_sql = str(safety.get("safe_sql") or safety.get("original_sql") or state.get("sql") or "").strip()
    if hard_blockers or not safe_sql:
        return None

    run_id = state.get("run_id") or ""
    session_id = state.get("thread_id") or state.get("session_id") or run_id
    requested_action = {"tool_name": "sql.execute_readonly", "args": {"safe_sql": safe_sql}}
    policy_decision = {
        "reason": "SQL execution requires human approval.",
        "risk_level": safety.get("risk_level") or "warning",
        "requested_action": requested_action,
        "safe_sql": safe_sql,
    }

    if ctx.event_store is not None:
        approval_rec = ctx.event_store.create_approval(
            run_id=run_id,
            session_id=session_id,
            step_name=STEP_NAME_MAP.get("sql.execute_readonly", "sql.execute_readonly"),
            tool_name="sql.execute_readonly",
            risk_level="warning",
            reason="SQL execution requires human approval.",
            policy_decision=policy_decision,
            requested_action=requested_action,
        )
        if approval_rec is not None:
            pending_app = approval_rec.model_dump(mode="json")
        else:
            pending_app = _approval_pending_payload(
                run_id=run_id,
                session_id=session_id,
                policy_decision=policy_decision,
                requested_action=requested_action,
            )
    else:
        pending_app = _approval_pending_payload(
            run_id=run_id,
            session_id=session_id,
            policy_decision=policy_decision,
            requested_action=requested_action,
        )
    pending_app["tool_call_id"] = f"confirm_sql_execute_{uuid4().hex[:8]}"

    return {
        "status": "waiting_approval",
        "pending_approval": pending_app,
        "allowed_tool_calls": [],
        "progress_decision": progress_decision_dict(
            status="continue",
            reason_summary="SQL validation passed but execution requires human approval.",
            user_visible_update="SQL 已通过校验，等待确认后执行。",
        ),
        "trace_events": [
            {
                "type": "agent.approval.required",
                "tool_name": "sql.execute_readonly",
                "reason": "SQL execution requires human approval.",
                "approval_id": pending_app.get("id"),
            }
        ],
    }


def _approval_pending_payload(
    *,
    run_id: str,
    session_id: str,
    policy_decision: dict[str, Any],
    requested_action: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"approval_mock_{uuid4().hex[:8]}",
        "run_id": run_id,
        "session_id": session_id,
        "step_name": STEP_NAME_MAP.get("sql.execute_readonly", "sql.execute_readonly"),
        "tool_name": "sql.execute_readonly",
        "status": "pending",
        "risk_level": "warning",
        "reason": "SQL execution requires human approval.",
        "policy_decision": policy_decision,
        "requested_action": requested_action,
    }


def judge_progress(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Contain every progress-node failure before LangGraph can checkpoint it."""
    try:
        return _judge_progress_impl(state, config)
    except Exception as exc:
        failure = public_agent_failure(exc, operation="run")
        safe_agent_log(logger, operation="run", exc=exc)
        decision = progress_decision_dict(
            status="failed",
            reason_summary=failure.message,
            root_cause=failure.message,
            should_finalize=True,
        )
        return {
            "status": "failed",
            "error": failure.message,
            "progress_decision": decision,
            "trace_events": [
                {
                    "type": "agent.progress.failed",
                    "error": failure.message,
                }
            ],
        }


def _judge_progress_impl(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """LLM Progress Judge — decides whether the task is complete after each observe.

    This node coordinates fast-paths (escalation, SQL repair, ReAct routing) and
    delegates semantic evaluation to the LLM judge when fast-paths do not apply.
    """
    ctx = graph_context(config)

    confirmation_update = _confirmation_approval_update(state, ctx)
    if confirmation_update is not None:
        return confirmation_update

    if not ctx.has_llm_credentials:
        raise RuntimeError("Progress judge requires LLM credentials.")

    # 1. Fast path: escalate.tool_group was called
    escalate_result = check_escalate(state)
    if escalate_result:
        return enrich_progress_result(escalate_result, state)

    # 2. Fast path: SQL / schema repair without LLM judge
    repair_result = check_sql_repair_fastpath(state)
    if repair_result:
        return enrich_progress_result(repair_result, state)

    # 3. Fast path: standard ReAct progress routing (e.g. tool observations, final answers)
    deterministic_result = deterministic_progress_fastpath(state)
    if deterministic_result:
        return enrich_progress_result(deterministic_result, state)

    # 4. Semantic LLM Judge fallback
    llm_result = call_llm_judge(state, config)
    return enrich_progress_result(llm_result, state)

