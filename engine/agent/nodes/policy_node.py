from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from engine.policy.gate import PolicyGate
from engine.agent.graph.state import DBFoxAgentState
from engine.agent.graph.context import graph_context
from engine.agent.graph.message_utils import message_tool_calls
from engine.agent.tools.tool_aliases import STEP_NAME_MAP, to_internal

logger = logging.getLogger("dbfox.dbfox_agent.nodes.policy_node")


_BATCHABLE_DISCOVERY_TOOLS = {
    "db.search",
    "db.inspect",
    "schema.describe_table",
    "schema.expand_related_tables",
    "schema.list_tables_page",
    "memory.search",
}


def _step_name(tool_name: str) -> str:
    """Return a human-readable step label for trace events.

    Delegates to the single source of truth in ``STEP_NAME_MAP`` so that
    new tools only need to be registered in one place.
    """
    return STEP_NAME_MAP.get(tool_name, tool_name)


def apply_policy(state: DBFoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    ctx = graph_context(config)
    registry = ctx.registry
    db = ctx.db

    last = state.get("messages")[-1]
    tool_calls = message_tool_calls(last)

    allowed = []
    blocked_messages: list[Any] = []
    deferred_messages: list[Any] = []

    policy_gate = PolicyGate(registry)
    execution_mode = state.get("execution_mode", "user_requested_read")

    # Most tool calls stay one-per-turn because later calls may depend on
    # state produced by earlier calls. Independent discovery reads can be
    # grouped so schema search does not become a slow multi-turn loop.
    if len(tool_calls) > 1 and not _can_batch_tool_calls(tool_calls, registry):
        first = tool_calls[0]
        others = tool_calls[1:]
        for c in others:
            deferred_messages.append(
                ToolMessage(
                    content=(
                        f"Tool calls must be issued one at a time because later "
                        f"tools depend on state produced by earlier tools. "
                        f"Please wait for the result of '{first['name']}' before "
                        f"calling '{c['name']}'."
                    ),
                    tool_call_id=c["id"],
                    name=c["name"],
                )
            )
        # Only process the first tool_call; the rest are deferred
        tool_calls = [first]

    for call in tool_calls:
        alias_name = call["name"]
        internal_name = to_internal(alias_name)
        args = call["args"] or {}
        call_id = call["id"]

        decision = policy_gate.check(state, internal_name, args, execution_mode=execution_mode)
        safe_tool_call = {"name": internal_name, "args": decision.safe_args, "id": call_id}

        if decision.status == "allowed":
            allowed.append(safe_tool_call)

        elif decision.status == "approval_required":
            run_id = state.get("run_id") or ""
            thread_id = state.get("thread_id") or state.get("run_id") or ""
            requested_action = {"tool_name": internal_name, "args": decision.safe_args}
            policy_decision = {
                "reason": decision.reason,
                "risk_level": decision.risk_level,
                "requested_action": requested_action,
            }

            if db is not None:
                from engine.agent_core import persistence as ap
                approval_rec = ap.create_approval(
                    db,
                    run_id=run_id,
                    session_id=thread_id,
                    step_name=_step_name(internal_name),
                    tool_name=internal_name,
                    risk_level=decision.risk_level,
                    reason=decision.reason,
                    policy_decision=policy_decision,
                    requested_action=requested_action,
                )
                pending_app = approval_rec.model_dump(mode="json")
                pending_app["tool_call_id"] = call_id
            else:
                pending_app = {
                    "id": f"approval_mock_{uuid4().hex[:8]}",
                    "run_id": run_id,
                    "session_id": thread_id,
                    "step_name": _step_name(internal_name),
                    "tool_name": internal_name,
                    "status": "pending",
                    "risk_level": decision.risk_level,
                    "reason": decision.reason,
                    "policy_decision": policy_decision,
                    "requested_action": requested_action,
                    "tool_call_id": call_id,
                }

            return {
                "status": "waiting_approval",
                "pending_approval": pending_app,
                "allowed_tool_calls": [safe_tool_call],
                "messages": list(deferred_messages),
                "trace_events": [
                    {
                        "type": "agent.approval.required",
                        "tool_name": internal_name,
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
                    name=alias_name,
                )
            )

    MAX_CONSECUTIVE_BLOCKS = 2

    if blocked_messages:
        # Anti-loop: track how many consecutive blocks for the same tool set
        prior_blocked = state.get("blocked_tool_calls") or []
        prior_blocked_names = {c["name"] for c in prior_blocked if isinstance(c, dict)}
        current_blocked_names = {c["name"] for c in tool_calls}
        same_tools_blocked = prior_blocked_names == current_blocked_names
        consecutive_blocks = (state.get("consecutive_blocks") or 0) + 1 if same_tools_blocked else 1

        if consecutive_blocks > MAX_CONSECUTIVE_BLOCKS and same_tools_blocked:
            # Force finalize — model is stuck in a blocked loop
            return {
                "messages": deferred_messages + blocked_messages,
                "status": "failed",
                "error": f"Agent exceeded blocked tool call limit for: {', '.join(sorted(current_blocked_names))}.",
                "allowed_tool_calls": [],
                "blocked_tool_calls": tool_calls,
                "consecutive_blocks": consecutive_blocks,
                "trace_events": [
                    {
                        "type": "agent.policy.blocked_loop_limit",
                        "tool_names": sorted(current_blocked_names),
                        "consecutive_blocks": consecutive_blocks,
                    }
                ],
            }

        return {
            "messages": deferred_messages + blocked_messages,
            "blocked_tool_calls": tool_calls,
            "allowed_tool_calls": [],
            "consecutive_blocks": consecutive_blocks,
            "trace_events": [
                {
                    "type": "agent.policy.blocked",
                    "count": len(blocked_messages),
                }
            ],
        }

    return {
        "allowed_tool_calls": allowed,
        "messages": list(deferred_messages),
        "consecutive_blocks": 0,
        "trace_events": [
            {
                "type": "agent.policy.allowed",
                "tool_names": [c["name"] for c in allowed],
            }
        ],
    }


def _can_batch_tool_calls(tool_calls: list[Any], registry: Any) -> bool:
    groups: set[str] = set()
    for call in tool_calls:
        internal_name = to_internal(call["name"])
        if internal_name not in _BATCHABLE_DISCOVERY_TOOLS:
            return False

        tool = registry.get(internal_name)
        if tool is None:
            return False

        spec = tool.spec
        policy = spec.policy
        if policy.side_effect != "none" or policy.requires_approval or policy.requires_validated_sql:
            return False
        groups.add(spec.group)

    return len(groups) == 1
