from __future__ import annotations

from pydantic import BaseModel

from engine.agent.executor import AgentStepSpec, StepExecutor
from engine.agent.registry import AgentToolContext, FunctionAgentTool, ToolRegistry, ToolSpec
from engine.agent.state import AgentState
from engine.agent.types import AgentRunRequest, ToolObservation


def _state() -> AgentState:
    return AgentState(
        run_id="run-test",
        session_id="session-test",
        question="list users",
        datasource_id="ds-test",
    )


def _ctx(state: AgentState) -> AgentToolContext:
    return AgentToolContext(
        db=None,  # type: ignore[arg-type]
        request=AgentRunRequest(datasource_id="ds-test", question="list users"),
        state=state,
    )


class DemoToolInput(BaseModel):
    question: str


class DemoToolOutput(BaseModel):
    sql: str


def test_step_executor_runs_registered_tool_and_returns_step() -> None:
    registry = ToolRegistry().register(
        FunctionAgentTool(
            spec=ToolSpec(name="demo.success", description="Demo success tool."),
            handler=lambda tool_input, _ctx: ToolObservation(
                name="demo_step",
                status="success",
                input=tool_input,
                output={"sql": "SELECT 1"},
                latency_ms=2,
            ),
        )
    )
    state = _state()

    step, observation = StepExecutor(registry).execute_step(
        AgentStepSpec(name="demo_step", tool_name="demo.success"),
        state,
        _ctx(state),
        input_override={"question": "list users"},
    )

    assert observation.status == "success"
    assert step.name == "demo_step"
    assert step.output == {"sql": "SELECT 1"}
    assert state.steps == []


def test_step_executor_catches_tool_exceptions() -> None:
    def fail(_input, _ctx):
        raise RuntimeError("tool exploded")

    registry = ToolRegistry().register(
        FunctionAgentTool(
            spec=ToolSpec(name="demo.failure", description="Demo failure tool."),
            handler=fail,
        )
    )
    state = _state()

    step, observation = StepExecutor(registry).execute_step(
        AgentStepSpec(name="demo_step", tool_name="demo.failure"),
        state,
        _ctx(state),
    )

    assert step.status == "failed"
    assert observation.status == "failed"
    assert observation.error == "tool exploded"
    assert observation.input == {}


def test_step_executor_rejects_input_that_violates_tool_contract() -> None:
    registry = ToolRegistry().register(
        FunctionAgentTool(
            spec=ToolSpec(
                name="demo.contract_input",
                description="Demo contract input tool.",
                input_model=DemoToolInput,
                output_model=DemoToolOutput,
            ),
            handler=lambda tool_input, _ctx: ToolObservation(
                name="demo_step",
                status="success",
                input=tool_input,
                output={"sql": "SELECT 1"},
                latency_ms=1,
            ),
        )
    )
    state = _state()

    step, observation = StepExecutor(registry).execute_step(
        AgentStepSpec(name="demo_step", tool_name="demo.contract_input"),
        state,
        _ctx(state),
        input_override={"question": 123},
    )

    assert step.status == "failed"
    assert observation.status == "failed"
    assert "Input contract failed for tool `demo.contract_input`" in str(observation.error)


def test_step_executor_rejects_output_that_violates_tool_contract() -> None:
    registry = ToolRegistry().register(
        FunctionAgentTool(
            spec=ToolSpec(
                name="demo.contract_output",
                description="Demo contract output tool.",
                input_model=DemoToolInput,
                output_model=DemoToolOutput,
            ),
            handler=lambda tool_input, _ctx: ToolObservation(
                name="demo_step",
                status="success",
                input=tool_input,
                output={"not_sql": "SELECT 1"},
                latency_ms=1,
            ),
        )
    )
    state = _state()

    step, observation = StepExecutor(registry).execute_step(
        AgentStepSpec(name="demo_step", tool_name="demo.contract_output"),
        state,
        _ctx(state),
        input_override={"question": "list users"},
    )

    assert step.status == "failed"
    assert observation.status == "failed"
    assert "Output contract failed for tool `demo.contract_output`" in str(observation.error)


def test_agent_state_apply_observation_updates_runtime_fields() -> None:
    state = _state()

    state.apply_observation(
        "generate_sql_candidate",
        ToolObservation(
            name="generate_sql_candidate",
            status="success",
            input={},
            output={"sql": "SELECT id FROM users LIMIT 10"},
            latency_ms=1,
        ),
    )
    state.apply_observation(
        "validate_sql",
        ToolObservation(
            name="validate_sql",
            status="success",
            input={},
            output={"can_execute": True, "safe_sql": "SELECT id FROM users LIMIT 10"},
            latency_ms=1,
        ),
    )
    state.apply_observation(
        "execute_sql",
        ToolObservation(
            name="execute_sql",
            status="success",
            input={},
            output={"success": True, "rows": [{"id": 1}], "rowCount": 1},
            latency_ms=1,
        ),
    )
    state.apply_observation(
        "suggest_followups",
        ToolObservation(
            name="suggest_followups",
            status="success",
            input={},
            output={"suggestions": [{"label": "Next", "question": "Next?", "reason": "demo", "action_type": "ask"}]},
            latency_ms=1,
        ),
    )

    assert state.sql == "SELECT id FROM users LIMIT 10"
    assert state.safety == {"can_execute": True, "safe_sql": "SELECT id FROM users LIMIT 10"}
    assert state.execution is not None
    assert state.execution["rowCount"] == 1
    assert state.suggestions[0]["question"] == "Next?"
    assert [step.name for step in state.steps] == [
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "suggest_followups",
    ]
