from __future__ import annotations

from typing import Any
from langchain_core.runnables import RunnableConfig

from engine.agent.graph.state import DataBoxAgentState


def finalize_answer(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    """Finalize the agent run: extract answer from last AIMessage and set terminal status.

    This node is reached when the model produces a response without tool_calls,
    meaning it considers the task complete.
    """
    messages = state.get("messages", [])
    error = state.get("error")
    pending_approval = state.get("pending_approval")

    # Determine final answer text
    answer_text = ""
    if messages:
        last = messages[-1]
        content = getattr(last, "content", "")
        if isinstance(content, str):
            answer_text = content
        elif isinstance(content, list):
            # Anthropic-style content blocks
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            answer_text = " ".join(parts).strip()

    if pending_approval:
        status = "waiting_approval"
    elif error:
        status = "failed"
    elif answer_text:
        status = "completed"
    else:
        status = "failed"
        if not error:
            error = "Agent completed without producing an answer."

    # Build answer payload for AgentRunResponse compatibility
    answer_payload: dict[str, Any] = {
        "answer": answer_text,
        "key_findings": [],
        "evidence": [],
        "caveats": [],
        "recommendations": [],
        "follow_up_questions": [],
    }

    trace_event: dict[str, Any] = {
        "type": "agent.finalized",
        "status": status,
        "has_answer": bool(answer_text),
        "has_error": bool(error),
    }
    if pending_approval:
        trace_event["pending_approval"] = True

    return {
        "status": status,
        "answer": answer_payload,
        "final_answer": answer_payload,
        "error": error,
        "trace_events": [trace_event],
        "agent_graph_route": "end",
    }
