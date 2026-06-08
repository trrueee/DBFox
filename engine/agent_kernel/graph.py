from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any, Hashable, cast

from engine.agent_kernel.lifecycle import (
    answer_node,
    context_node,
    critique_answer,
    reflect_node,
    resolve_reference,
    understand_node,
)
from engine.agent_kernel.state import KernelState, latest_user_message

LangGraphStateGraph: Any
try:
    from langgraph.graph import END, START, StateGraph as _LangGraphStateGraph

    LangGraphStateGraph = _LangGraphStateGraph
except ImportError:  # pragma: no cover - exercised only when optional runtime is absent.
    END = "__end__"
    START = "__start__"
    LangGraphStateGraph = None


GraphNode = Callable[[KernelState], dict[str, Any]]


def langgraph_available() -> bool:
    return importlib.util.find_spec("langgraph") is not None


def build_agent_kernel_graph(
    *,
    controller_node: GraphNode,
    policy_node: GraphNode,
    execute_tool_node: GraphNode,
    ingest_message_node: GraphNode | None = None,
    approval_interrupt_node: GraphNode | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Build the DataBox Agent Kernel as an intent-routed graph.

    The graph is no longer a linear lifecycle chain with a controller loop. It is
    a conditional graph:

    ingest -> understand -> context -> route_intent

    route_intent branches to specialized subflows:
    - new_data_question: schema -> plan -> SQL -> critic -> validate -> execute/skip -> analyze -> answer
    - revise_sql: revise existing SQL -> critic -> validate -> answer
    - explain_sql: answer from resolved SQL context without schema discovery
    - approval_help: explain pending approval without simulating approval
    - followup_on_result: reuse existing result context
    - chart_request: chart from existing SQL/result context
    - clarification: ask for missing context

    The old controller is still available as a fallback node, but the graph
    topology now encodes the main Agent behavior directly through conditional
    edges and branch-specific nodes.
    """

    if LangGraphStateGraph is None:
        raise RuntimeError("LangGraph is not installed; install `langgraph` to build AgentKernelGraph.")

    graph = cast(Any, LangGraphStateGraph)(KernelState)
    graph.add_node("ingest_message", cast(Any, ingest_message_node or _noop_node))
    graph.add_node("understand", cast(Any, understand_node))
    graph.add_node("context", cast(Any, context_node))
    graph.add_node("route_intent", cast(Any, _route_intent_node))

    graph.add_node("new_data_question", cast(Any, _new_data_question_node))
    graph.add_node("revise_sql", cast(Any, _revise_sql_node))
    graph.add_node("explain_sql", cast(Any, _explain_sql_node))
    graph.add_node("approval_help", cast(Any, _approval_help_node))
    graph.add_node("result_followup", cast(Any, _result_followup_node))
    graph.add_node("chart_request", cast(Any, _chart_request_node))
    graph.add_node("clarification", cast(Any, _clarification_node))

    graph.add_node("controller", cast(Any, controller_node))
    graph.add_node("policy", cast(Any, policy_node))
    graph.add_node("execute_tool", cast(Any, execute_tool_node))
    graph.add_node("observe", cast(Any, _observe_node))
    graph.add_node("sql_critic", cast(Any, reflect_node))
    graph.add_node("answer", cast(Any, answer_node))
    if approval_interrupt_node is not None:
        graph.add_node("approval_interrupt", cast(Any, approval_interrupt_node))

    graph.add_edge(START, "ingest_message")
    graph.add_edge("ingest_message", "understand")
    graph.add_edge("understand", "context")
    graph.add_edge("context", "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        _route_intent,
        {
            "new_data_question": "new_data_question",
            "revise_sql": "revise_sql",
            "explain_sql": "explain_sql",
            "approval_help": "approval_help",
            "result_followup": "result_followup",
            "chart_request": "chart_request",
            "clarification": "clarification",
            "controller": "controller",
        },
    )

    for node_name in (
        "new_data_question",
        "revise_sql",
        "explain_sql",
        "approval_help",
        "result_followup",
        "chart_request",
        "clarification",
    ):
        graph.add_conditional_edges(node_name, _after_branch, _branch_routes())

    graph.add_conditional_edges(
        "controller",
        _after_controller,
        {
            "policy": "policy",
            "route_intent": "route_intent",
            "answer": "answer",
            "end": END,
        },
    )

    policy_routes: dict[Hashable, str] = {
        "execute_tool": "execute_tool",
        "route_intent": "route_intent",
        "revise_sql": "revise_sql",
        "answer": "answer",
        "end": END,
    }
    if approval_interrupt_node is not None:
        policy_routes["approval_interrupt"] = "approval_interrupt"
    graph.add_conditional_edges("policy", _after_policy, policy_routes)

    if approval_interrupt_node is not None:
        graph.add_conditional_edges(
            "approval_interrupt",
            _after_approval,
            {
                "execute_tool": "execute_tool",
                "answer": "answer",
                "end": END,
            },
        )

    graph.add_edge("execute_tool", "observe")
    graph.add_conditional_edges(
        "observe",
        _after_observe,
        {
            "new_data_question": "new_data_question",
            "revise_sql": "revise_sql",
            "result_followup": "result_followup",
            "chart_request": "chart_request",
            "sql_critic": "sql_critic",
            "answer": "answer",
            "route_intent": "route_intent",
        },
    )
    graph.add_conditional_edges(
        "sql_critic",
        _after_sql_critic,
        {
            "revise_sql": "revise_sql",
            "new_data_question": "new_data_question",
            "answer": "answer",
        },
    )
    graph.add_edge("answer", END)
    return graph.compile(checkpointer=checkpointer)


def _noop_node(_state: KernelState) -> dict[str, Any]:
    return {"status": "running"}


def _observe_node(state: KernelState) -> dict[str, Any]:
    # Keep the observation phase lightweight. Tool execution already writes
    # last_tool_name, last_observation, artifacts, and tool_results. This node
    # gives the graph a visible observe point before state-based routing.
    observation = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
    payload = {
        "tool_name": state.get("last_tool_name"),
        "status": observation.get("status"),
        "has_error": bool(observation.get("error")),
    }
    return {"agent_observation": payload, "trace_events": [{"type": "agent.observe", "payload": payload}]}


def _route_intent_node(state: KernelState) -> dict[str, Any]:
    intent = _intent(state)
    route = _route_intent(state)
    return {
        "agent_graph_route": route,
        "trace_events": [{"type": "agent.route_intent", "payload": {"intent": intent, "route": route, "reference": resolve_reference(state)}}],
    }


def _route_intent(state: KernelState) -> str:
    intent = _intent(state)
    if intent == "new_data_question":
        return "new_data_question"
    if intent == "revise_sql":
        return "revise_sql"
    if intent == "explain_sql":
        return "explain_sql"
    if intent == "approval_help":
        return "approval_help"
    if intent == "followup_on_result":
        return "result_followup"
    if intent == "chart_request":
        return "chart_request"
    if intent == "clarification":
        return "clarification"
    return "controller"


def _new_data_question_node(state: KernelState) -> dict[str, Any]:
    if state.get("answer"):
        return _go("answer", "Answer already exists.")
    if not state.get("schema_context"):
        return _call("schema.build_context", {"question": latest_user_message(state)}, "New data question: build schema context.")
    if not state.get("query_plan"):
        return _call("query_plan.build", {}, "New data question: build query plan.")
    if not state.get("sql"):
        return _call("sql.generate", {}, "New data question: generate SQL.")
    if not state.get("agent_sql_critique") and not state.get("safety"):
        return _go("sql_critic", "Critique SQL before validation.")

    critique = state.get("agent_sql_critique") if isinstance(state.get("agent_sql_critique"), dict) else {}
    if critique.get("needs_revision") and not state.get("revision_attempted"):
        return _go("revise_sql", "SQL Critic requested revision.")

    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    if not safety:
        return _call("sql.validate", {"sql": state.get("sql")}, "Validate SQL after critic pass.")
    if safety and not safety.get("can_execute"):
        blocked = [str(reason) for reason in safety.get("blocked_reasons", [])]
        hard_blockers = [reason for reason in blocked if reason != "requires_confirmation"]
        if hard_blockers and not state.get("revision_attempted"):
            return _go("revise_sql", "TrustGate blocked SQL; revise before answering.")
        if state.get("execute", True) and safety.get("requires_confirmation") and not hard_blockers:
            return _call("sql.execute_readonly", {}, "Request approval for gated SQL execution.")
        return _call("answer.synthesize", {}, "Explain why SQL cannot be executed safely.")

    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    if not execution:
        if not state.get("execute", True):
            return _call("sql.skip_execution", {}, "Execution disabled; record skipped execution.")
        return _call("sql.execute_readonly", {}, "Execute validated read-only SQL.")
    if execution.get("success") is False and not state.get("revision_attempted"):
        return _go("revise_sql", "Execution failed; revise SQL.")
    if not state.get("result_profile"):
        return _call("result.profile", {}, "Profile execution result.")
    if not state.get("chart_suggestion"):
        return _call("chart.suggest", {}, "Suggest chart from result.")
    if not state.get("suggestions"):
        return _call("followup.suggest", {}, "Suggest follow-up questions.")
    return _call("answer.synthesize", {}, "Synthesize final answer from evidence.")


def _revise_sql_node(state: KernelState) -> dict[str, Any]:
    if not state.get("sql") and not _reference_sql(state):
        return _answer("I need an existing SQL statement before I can revise it.", "No SQL reference was available for revision.")
    if not state.get("revision_attempted"):
        return _call(
            "sql.revise",
            {"sql": state.get("sql") or _reference_sql(state), "user_instruction": latest_user_message(state), "error": _revision_reason(state)},
            "Revise the existing SQL according to the current instruction or critic feedback.",
        )
    if not state.get("agent_sql_critique") and state.get("sql") and not state.get("safety"):
        return _go("sql_critic", "Critique revised SQL before validation.")
    if not state.get("safety"):
        return _call("sql.validate", {"sql": state.get("sql")}, "Validate revised SQL.")
    return _call("answer.synthesize", {}, "Return revised and validated SQL without forcing execution.")


def _explain_sql_node(state: KernelState) -> dict[str, Any]:
    sql = state.get("sql") or _reference_sql(state)
    if not sql:
        return _answer("I could not find a current SQL statement to explain.", "No SQL reference was available.")
    return _answer(
        "This request is about the SQL already in context, so I am not starting a new data-question flow or executing the query.\n\n"
        f"```sql\n{sql}\n```",
        "Explain SQL branch answered directly from resolved SQL context.",
    )


def _approval_help_node(state: KernelState) -> dict[str, Any]:
    approval = state.get("pending_approval") or {}
    reference = resolve_reference(state)
    approval_id = approval.get("id") if isinstance(approval, dict) else reference.get("id")
    return _answer(
        "This run is waiting for approval before the pending action can continue. "
        "I will not simulate approval or execute the pending action in chat. "
        f"Approval reference: {approval_id or 'current approval context' }.",
        "Approval help branch explained pending approval without execution.",
    )


def _result_followup_node(state: KernelState) -> dict[str, Any]:
    if not state.get("followup_context") and state.get("follow_up_context"):
        return _call("followup.load_context", {}, "Load prior result/artifact context for follow-up.")
    if not state.get("execution") and not state.get("result_profile"):
        return _call("answer.synthesize", {}, "Answer from available follow-up context; no execution result is loaded.")
    if not state.get("result_profile"):
        return _call("result.profile", {}, "Profile existing result for follow-up answer.")
    return _call("answer.synthesize", {}, "Synthesize follow-up answer from existing result context.")


def _chart_request_node(state: KernelState) -> dict[str, Any]:
    if not state.get("execution"):
        return _call("answer.synthesize", {}, "Cannot suggest chart without execution/result context.")
    if not state.get("chart_suggestion"):
        return _call("chart.suggest", {}, "Suggest chart from existing result context.")
    return _call("answer.synthesize", {}, "Explain chart suggestion.")


def _clarification_node(state: KernelState) -> dict[str, Any]:
    return {
        "status": "waiting_user",
        "pending_decision": {"action": "ask_user", "user_message": "I need a bit more detail before I can continue."},
        "trace_events": [{"type": "agent.ask_user", "payload": {"reason": "Clarification branch selected."}}],
    }


def _after_branch(state: KernelState) -> str:
    route = str(state.get("agent_graph_route") or "")
    if route in _branch_routes():
        return route
    if state.get("pending_tool_call"):
        return "policy"
    if state.get("status") in {"completed", "failed", "waiting_user", "paused"} or state.get("answer") or state.get("final_answer"):
        return "answer"
    return "route_intent"


def _branch_routes() -> dict[Hashable, str]:
    return {
        "policy": "policy",
        "sql_critic": "sql_critic",
        "new_data_question": "new_data_question",
        "revise_sql": "revise_sql",
        "result_followup": "result_followup",
        "chart_request": "chart_request",
        "answer": "answer",
        "route_intent": "route_intent",
        "controller": "controller",
        "end": END,
    }


def _after_controller(state: KernelState) -> str:
    decision = state.get("pending_decision") or {}
    if decision.get("action") == "call_tool":
        return "policy"
    if decision.get("action") == "update_plan":
        return "route_intent"
    if decision.get("action") in {"final_answer", "ask_user", "pause", "wait_approval"}:
        return "answer"
    return "end"


def _after_policy(state: KernelState) -> str:
    if state.get("status") == "waiting_approval":
        return "approval_interrupt"
    if state.get("pending_tool_call"):
        return "execute_tool"
    if state.get("error") and state.get("sql") and not state.get("revision_attempted"):
        return "revise_sql"
    if state.get("error"):
        return "answer"
    if state.get("status") in {"completed", "failed", "paused", "waiting_user"}:
        return "answer"
    return "route_intent"


def _after_approval(state: KernelState) -> str:
    if state.get("pending_tool_call"):
        return "execute_tool"
    return "answer"


def _after_observe(state: KernelState) -> str:
    if state.get("error") and state.get("sql") and not state.get("revision_attempted"):
        return "revise_sql"
    if state.get("error"):
        return "answer"
    tool_name = str(state.get("last_tool_name") or "")
    intent = _intent(state)
    if tool_name in {"sql.generate", "sql.revise"}:
        return "sql_critic"
    if tool_name == "sql.validate":
        return "revise_sql" if intent == "revise_sql" else "new_data_question"
    if tool_name in {"sql.execute_readonly", "sql.skip_execution"}:
        return "result_followup" if intent == "followup_on_result" else "new_data_question"
    if tool_name == "result.profile":
        return "chart_request" if intent == "chart_request" else "new_data_question"
    if tool_name == "chart.suggest":
        return "chart_request" if intent == "chart_request" else "new_data_question"
    if tool_name == "followup.suggest":
        return "new_data_question"
    if tool_name == "answer.synthesize" or tool_name.startswith("workspace."):
        return "answer"
    return "route_intent"


def _after_sql_critic(state: KernelState) -> str:
    reflection = state.get("agent_reflection") if isinstance(state.get("agent_reflection"), dict) else {}
    critique = reflection.get("sql_critique") if isinstance(reflection.get("sql_critique"), dict) else state.get("agent_sql_critique")
    if isinstance(critique, dict) and critique.get("needs_revision") and not state.get("revision_attempted"):
        return "revise_sql"
    if _intent(state) == "revise_sql":
        return "revise_sql"
    if state.get("answer") or (isinstance(critique_answer(state), dict) and critique_answer(state).get("needs_correction")):
        return "answer"
    return "new_data_question"


def _intent(state: KernelState) -> str:
    payload = state.get("agent_intent") if isinstance(state.get("agent_intent"), dict) else {}
    return str(payload.get("intent") or "new_data_question")


def _call(tool_name: str, args: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "running",
        "agent_graph_route": "policy",
        "pending_tool_call": {"tool_name": tool_name, "args": args, "reason": reason},
        "trace_events": [{"type": "agent.branch.tool", "payload": {"tool_name": tool_name, "reason": reason}}],
    }


def _go(route: str, reason: str) -> dict[str, Any]:
    return {
        "status": "running",
        "agent_graph_route": route,
        "trace_events": [{"type": "agent.branch.route", "payload": {"route": route, "reason": reason}}],
    }


def _answer(answer: str, reason: str) -> dict[str, Any]:
    payload = {"answer": answer, "key_findings": [], "evidence": [], "caveats": [], "recommendations": [], "follow_up_questions": []}
    return {
        "status": "completed",
        "agent_graph_route": "answer",
        "answer": payload,
        "final_answer": payload,
        "trace_events": [{"type": "agent.branch.answer", "payload": {"reason": reason}}],
    }


def _reference_sql(state: KernelState) -> str | None:
    reference = resolve_reference(state)
    sql_preview = reference.get("sql_preview")
    if isinstance(sql_preview, str) and sql_preview.strip():
        return sql_preview.strip()
    return None


def _revision_reason(state: KernelState) -> str:
    reflection = state.get("agent_reflection") if isinstance(state.get("agent_reflection"), dict) else {}
    critique = reflection.get("sql_critique") if isinstance(reflection.get("sql_critique"), dict) else state.get("agent_sql_critique")
    if isinstance(critique, dict) and critique.get("issues"):
        return "; ".join(str(issue) for issue in critique.get("issues", []))
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    return str(execution.get("revise_suggestion") or state.get("error") or latest_user_message(state) or "Revise SQL.")
