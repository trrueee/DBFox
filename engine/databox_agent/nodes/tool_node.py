from __future__ import annotations

import json
import logging
import time
from typing import Any
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from engine.agent.sandbox.base import ExecutionContext
from engine.agent.types import ToolObservation
from engine.agent.tool_runtime_gateway import ToolRuntimeGateway
from engine.agent_kernel.tool_registry import ToolContext
from engine.databox_agent.graph.state import DataBoxAgentState

logger = logging.getLogger("databox.databox_agent.nodes.tool_node")


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


def DataBoxToolNode(state: DataBoxAgentState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable") or {}
    registry = configurable.get("registry")
    db = configurable.get("db")
    req = configurable.get("request")

    allowed_tool_calls = state.get("allowed_tool_calls") or []

    messages = []
    tool_results = []
    trace_events = []

    for call in allowed_tool_calls:
        tool_name = call["name"]
        args = call["args"] or {}
        call_id = call["id"]

        logger.info("Executing tool %s with args %s", tool_name, args)

        trace_events.append({
            "type": "agent.tool.started",
            "tool_name": tool_name,
        })

        observation = _execute_tool(registry, db, req, state, tool_name, args)

        tool_results.append(observation.model_dump(mode="json"))

        content = observation.error if observation.status == "failed" else (
            observation.output.get("answer") if (observation.output and "answer" in observation.output) else (
                observation.output if observation.output else "Success"
            )
        )
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)

        messages.append(
            ToolMessage(
                content=str(content),
                tool_call_id=call_id,
                name=tool_name,
            )
        )

        trace_events.append({
            "type": "agent.tool.completed",
            "tool_name": tool_name,
            "status": observation.status,
            "latency_ms": observation.latency_ms,
        })

    return {
        "messages": messages,
        "last_tool_results": tool_results,
        "allowed_tool_calls": [],
        "trace_events": trace_events,
    }


def _execute_tool(
    registry: Any,
    db: Any,
    req: Any,
    state: dict[str, Any],
    tool_name: str,
    args: dict[str, Any],
) -> ToolObservation:
    tool = registry.require(tool_name)
    if hasattr(tool, "base_tool") and tool.base_tool is not None:
        merged_args = dict(args)
        if "question" not in merged_args and req is not None:
            merged_args["question"] = req.question
        if "schema_context" not in merged_args:
            merged_args["schema_context"] = state.get("schema_context")
        if "query_plan" not in merged_args:
            merged_args["query_plan"] = state.get("query_plan")
        if "follow_up_context" not in merged_args:
            merged_args["follow_up_context"] = state.get("follow_up_context")
        if "safety" not in merged_args:
            merged_args["safety"] = state.get("safety")
        if "execution" not in merged_args:
            merged_args["execution"] = state.get("execution")
        if "result_profile" not in merged_args:
            merged_args["result_profile"] = state.get("result_profile")
        if "chart_suggestion" not in merged_args:
            merged_args["chart_suggestion"] = state.get("chart_suggestion")
        if "suggestions" not in merged_args:
            merged_args["suggestions"] = state.get("suggestions")
        if "error" not in merged_args:
            merged_args["error"] = state.get("error")
        if "sql" not in merged_args:
            merged_args["sql"] = state.get("sql")

        exec_ctx = ExecutionContext(
            thread_id=str(state.get("thread_id") or state.get("session_id") or ""),
            datasource_id=req.datasource_id if req else "",
            db_dialect="mysql",
            read_only=tool.spec.policy.side_effect != "write",
            db_session=db,
            api_key=req.api_key if req else None,
            api_base=req.api_base if req else None,
            model_name=req.model_name if req else None,
        )
        start_time = time.perf_counter()
        try:
            base_tool = tool.base_tool
            validated_input = base_tool.input_schema.model_validate(merged_args)
            output_model = base_tool.execute(validated_input, exec_ctx)
            output_dict = output_model.model_dump(mode="json")
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            status = "skipped" if tool_name == "sql.skip_execution" else "success"
            obs_name = _step_name(tool_name)
            return ToolObservation(
                name=obs_name,
                status=status,
                input=args,
                output=output_dict,
                error=None,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            obs_name = _step_name(tool_name)
            return ToolObservation(
                name=obs_name,
                status="failed",
                input=args,
                output=None,
                error=str(exc),
                latency_ms=latency_ms,
            )

    ctx = ToolContext(db=db, request=req, state=dict(state))
    validated_args = ToolRuntimeGateway.validate_input(tool.spec.name, tool.spec.input_model, args)
    observation = tool.handler(ctx, validated_args)
    return ToolRuntimeGateway.validate_observation_output(tool.spec.name, tool.spec.output_model, observation)
