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
    existing_answer = state.get("answer")
    if isinstance(existing_answer, dict):
        answer_payload = {
            "answer": answer_text or existing_answer.get("answer") or "",
            "key_findings": existing_answer.get("key_findings") or [],
            "evidence": existing_answer.get("evidence") or [],
            "caveats": existing_answer.get("caveats") or [],
            "recommendations": existing_answer.get("recommendations") or [],
            "follow_up_questions": existing_answer.get("follow_up_questions") or [],
        }
    else:
        answer_payload = {
            "answer": answer_text,
            "key_findings": [],
            "evidence": [],
            "caveats": [],
            "recommendations": [],
            "follow_up_questions": [],
        }

    # Clean up any raw tool node prefix from answer if present
    if isinstance(answer_payload.get("answer"), str):
        ans_str = answer_payload["answer"]
        if ans_str.startswith("[") and "]" in ans_str:
            parts = ans_str.split("]", 1)
            if len(parts) > 1:
                answer_payload["answer"] = parts[1].strip()

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

