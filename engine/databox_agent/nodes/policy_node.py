from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from engine.databox_agent.guardrails.policy_gate import PolicyGate
from engine.databox_agent.graph.state import DataBoxAgentState

logger = logging.getLogger("databox.databox_agent.nodes.policy_node")


def _step_name(tool_name: str) -> str:
    step_names = {
        "followup.load_context": "load_follow_up_context",
        "schema.build_context": "build_schema_context",
        "query_plan.build": "build_query_plan",
        "sql.generate": "generate_sql_candidate",
        "sql.validate": "validate_sql",
        "sql.execute_readonly": "execute_sql",
        "sql.skip_execution": "execute_sql",
        "sql.revise": "revise_sql",
        "result.profile": "profile_result",
        "chart.suggest": "suggest_chart",
        "followup.suggest": "suggest_followups",
        "answer.synthesize": "answer_synthesizer",
    }
    return step_names.get(tool_name, tool_name)


def apply_policy(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable") or {}
    registry = configurable.get("registry")
    db = configurable.get("db")

    last = state.get("messages")[-1]
    tool_calls = getattr(last, "tool_calls", []) or []

    allowed = []
    blocked_messages = []

    policy_gate = PolicyGate(registry)

    for call in tool_calls:
        tool_name = call["name"]
        args = call["args"] or {}
        call_id = call["id"]

        decision = policy_gate.check(state, tool_name, args)
        safe_tool_call = {"name": tool_name, "args": decision.safe_args, "id": call_id}

        if decision.status == "allowed":
            allowed.append(safe_tool_call)

        elif decision.status == "approval_required":
            run_id = state.get("run_id") or ""
            thread_id = state.get("thread_id") or state.get("run_id") or ""
            requested_action = {"tool_name": tool_name, "args": decision.safe_args}
            policy_decision = {
                "reason": decision.reason,
                "risk_level": decision.risk_level,
                "requested_action": requested_action,
            }

            if db is not None:
                from engine.agent import persistence as ap
                approval_rec = ap.create_approval(
                    db,
                    run_id=run_id,
                    session_id=thread_id,
                    step_name=_step_name(tool_name),
                    tool_name=tool_name,
                    risk_level=decision.risk_level,
                    reason=decision.reason,
                    policy_decision=policy_decision,
                    requested_action=requested_action,
                )
                pending_app = approval_rec.model_dump(mode="json")
            else:
                pending_app = {
                    "id": f"approval_mock_{uuid4().hex[:8]}",
                    "run_id": run_id,
                    "session_id": thread_id,
                    "step_name": _step_name(tool_name),
                    "tool_name": tool_name,
                    "status": "pending",
                    "risk_level": decision.risk_level,
                    "reason": decision.reason,
                    "policy_decision": policy_decision,
                    "requested_action": requested_action,
                }

            return {
                "status": "waiting_approval",
                "pending_approval": pending_app,
                "allowed_tool_calls": [safe_tool_call],
                "trace_events": [
                    {
                        "type": "agent.approval.required",
                        "tool_name": tool_name,
                        "reason": decision.reason,
                        "approval_id": pending_app.get("id"),
                    }
                ],
            }

        else:
            blocked_messages.append(
                ToolMessage(
                    content=f"Tool call blocked by policy: {decision.reason}",
                    tool_call_id=call_id,
                    name=tool_name,
                )
            )

    if blocked_messages:
        return {
            "messages": blocked_messages,
            "blocked_tool_calls": tool_calls,
            "allowed_tool_calls": [],
            "trace_events": [
                {
                    "type": "agent.policy.blocked",
                    "count": len(blocked_messages),
                }
            ],
        }

    return {
        "allowed_tool_calls": allowed,
        "trace_events": [
            {
                "type": "agent.policy.allowed",
                "tool_names": [c["name"] for c in allowed],
            }
        ],
    }
