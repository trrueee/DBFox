from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from engine.agent import AgentRunRequest, ToolObservation
from engine.agent.events import EventEmitter
from engine.agent.state import AgentState
from engine.agent import persistence as agent_persistence
from engine.agent.runtime import DataBoxAgentRuntime
from engine.agent_kernel.controller import CONTROLLER_SYSTEM_PROMPT, _controller_state_view
from engine.agent_kernel.databinding import apply_tool_result_to_state
from engine.agent_kernel.databox_tools import register_databox_tools
from engine.agent_kernel.graph import build_agent_kernel_graph, langgraph_available
from engine.agent_kernel.policy import PolicyGate
from engine.agent_kernel.response import AgentKernelResponseAssembler
from engine.agent_kernel.schemas import AgentDecision, ToolCallDecision
from engine.agent_kernel.service import AgentKernelService
from engine.agent_kernel.tool_registry import ToolContext
from engine.schema_sync import sync_schema


def _fake_select_sql(*_args, **_kwargs):
    return {
        "sql": "SELECT id, username FROM users LIMIT 3",
        "model": "test",
        "mode": "offline",
        "latencyMs": 1,
        "schemaValidationWarnings": [],
    }


def _kernel_waiting_run(db_session, demo_datasource, monkeypatch, session_id: str = "kernel-approval-session"):
    sync_schema(db_session, demo_datasource.id)
    monkeypatch.setattr("engine.agent.tools._render_sql_from_query_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("engine.agent.tools.generate_sql", _fake_select_sql)
    monkeypatch.setattr("engine.agent_kernel.databox_tools.validate_sql_tool", _fake_approval_validation)

    events = list(AgentKernelService(db_session).run_iter(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="list users",
            execute=True,
            session_id=session_id,
        )
    ))
    final = events[-1]
    assert final.response is not None
    approval = agent_persistence.get_pending_approval_for_run(db_session, final.response.run_id)
    assert approval is not None
    return final.response, approval, events


def _fake_approval_validation(_db, datasource_id: str, sql: str) -> ToolObservation:
    return ToolObservation(
        name="validate_sql",
        status="success",
        input={"datasource_id": datasource_id, "sql_preview": sql},
        output={
            "passed": True,
            "can_execute": True,
            "safe_sql": sql,
            "original_sql": sql,
            "schema_warnings": [],
            "guardrail": {
                "result": "pass",
                "originalSql": sql,
                "safeSql": sql,
                "checks": [],
                "message": "SQL passed.",
            },
            "trust_gate": {
                "riskLevel": "warning",
                "requiresConfirmation": True,
                "canExecute": True,
                "messages": ["Production datasource requires manual confirmation."],
            },
            "execution_safety_decision": {
                "decision_id": "safety-test",
                "datasource_id": datasource_id,
                "policy": "agent_readonly",
                "original_sql": sql,
                "safe_sql": sql,
                "passed": True,
                "can_execute": True,
                "requires_confirmation": True,
                "guardrail": {
                    "result": "pass",
                    "originalSql": sql,
                    "safeSql": sql,
                    "checks": [],
                    "message": "SQL passed.",
                },
                "schema_warnings": [],
                "scope_state": {"env": "prod"},
                "blocked_reasons": ["requires_confirmation"],
                "messages": ["Production datasource requires manual confirmation."],
            },
            "requires_confirmation": True,
            "messages": ["Production datasource requires manual confirmation."],
            "blocked_reasons": ["requires_confirmation"],
            "revise_suggestion": None,
        },
        error=None,
        latency_ms=0,
    )


def test_agent_kernel_registry_exposes_domain_tools() -> None:
    registry = register_databox_tools()
    names = {spec.name for spec in registry.list_specs()}

    assert {
        "schema.build_context",
        "query_plan.build",
        "sql.generate",
        "sql.validate",
        "sql.execute_readonly",
        "sql.revise",
        "answer.synthesize",
    }.issubset(names)

    execute_spec = registry.require("sql.execute_readonly").spec
    assert execute_spec.policy.requires_validated_sql is True
    assert execute_spec.policy.side_effect == "read"


def test_agent_kernel_tool_registry_schema_snapshot() -> None:
    registry = register_databox_tools()
    snapshot = {
        spec.name: {
            "input_props": sorted((spec.input_schema.get("properties") or {}).keys()),
            "input_required": spec.input_schema.get("required", []),
            "output_props": sorted((spec.output_schema.get("properties") or {}).keys()),
            "output_required": spec.output_schema.get("required", []),
        }
        for spec in registry.list_specs()
    }

    assert snapshot == {
        "answer.synthesize": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": [
                "answer",
                "caveats",
                "evidence",
                "follow_up_questions",
                "key_findings",
                "recommendations",
            ],
            "output_required": ["answer"],
        },
        "chart.suggest": {
            "input_props": [],
            "input_required": [],
            "output_props": ["reason", "type", "x", "y"],
            "output_required": ["type", "reason"],
        },
        "followup.load_context": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": [
                "analysis_question",
                "context_summary",
                "referenced_artifact_ids",
                "schema_linking_question",
            ],
            "output_required": ["context_summary", "analysis_question", "schema_linking_question"],
        },
        "followup.suggest": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": ["suggestions"],
            "output_required": ["suggestions"],
        },
        "query_plan.build": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": [
                "analysis_goal",
                "assumptions",
                "candidate_tables",
                "dimensions",
                "filters",
                "metrics",
                "raw_plan",
                "risk_notes",
                "time_range",
            ],
            "output_required": ["analysis_goal"],
        },
        "result.profile": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": [
                "anomalies",
                "column_profiles",
                "detected_patterns",
                "limitations",
                "notable_facts",
                "row_count",
            ],
            "output_required": ["row_count"],
        },
        "schema.build_context": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": [
                "candidate_columns",
                "candidate_tables",
                "mode",
                "original_schema_table_count",
                "schema_context",
                "schema_context_size",
                "schema_linking_reasons",
                "selected_schema_table_count",
                "selected_tables",
            ],
            "output_required": ["schema_context", "selected_tables", "mode"],
        },
        "sql.execute_readonly": {
            "input_props": ["question", "sql"],
            "input_required": [],
            "output_props": [
                "columns",
                "error_type",
                "executionId",
                "historyId",
                "latencyMs",
                "revise_suggestion",
                "rowCount",
                "rows",
                "safetyDecision",
                "success",
                "timing",
                "truncated",
                "warnings",
            ],
            "output_required": ["success"],
        },
        "sql.generate": {
            "input_props": ["question"],
            "input_required": [],
            "output_props": [
                "latency_ms",
                "metadata",
                "mode",
                "model",
                "raw_sql",
                "rewrite_notes",
                "schema_validation_warnings",
                "sql",
            ],
            "output_required": ["sql"],
        },
        "sql.revise": {
            "input_props": ["error", "instruction", "reason", "safe_sql", "sql", "user_instruction"],
            "input_required": [],
            "output_props": [
                "blocked_sql",
                "can_fix",
                "changes",
                "fixed_sql",
                "reason",
                "remaining_risks",
                "revise_suggestion",
            ],
            "output_required": ["can_fix", "reason", "revise_suggestion"],
        },
        "sql.skip_execution": {
            "input_props": [],
            "input_required": [],
            "output_props": ["reason"],
            "output_required": ["reason"],
        },
        "sql.validate": {
            "input_props": ["sql"],
            "input_required": [],
            "output_props": [
                "blocked_reasons",
                "can_execute",
                "execution_safety_decision",
                "guardrail",
                "messages",
                "original_sql",
                "passed",
                "requires_confirmation",
                "revise_suggestion",
                "safe_sql",
                "schema_warnings",
                "trust_gate",
            ],
            "output_required": ["passed", "can_execute", "safe_sql", "requires_confirmation"],
        },
    }

    for spec in registry.list_specs():
        assert spec.input_schema != {"type": "object"}
        assert spec.output_schema != {"type": "object"}


def test_agent_kernel_policy_blocks_execution_without_validated_sql() -> None:
    registry = register_databox_tools()
    decision = PolicyGate(registry).check({}, "sql.execute_readonly", {})

    assert decision.status == "blocked"
    assert "sql.validate" in decision.reason


def test_agent_kernel_policy_uses_state_safe_sql_for_execution() -> None:
    registry = register_databox_tools()
    decision = PolicyGate(registry).check(
        {"safety": {"can_execute": True, "safe_sql": "SELECT id FROM users LIMIT 3"}},
        "sql.execute_readonly",
        {"sql": "SELECT * FROM secrets"},
    )

    assert decision.status == "allowed"
    assert decision.safe_args == {"sql": "SELECT id FROM users LIMIT 3"}


def test_agent_kernel_does_not_execute_when_validation_blocks_sql(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, demo_datasource.id)
    decisions = iter([
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.validate",
                args={"sql": "SELECT id FROM users ORDER BY ARRAY() LIMIT 10"},
                reason="Validate SQL before execution.",
            ),
            confidence="high",
            reasoning_summary="Validate first.",
        ),
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.execute_readonly",
                args={"sql": "SELECT id FROM users ORDER BY ARRAY() LIMIT 10"},
                reason="Try execution after validation.",
            ),
            confidence="high",
            reasoning_summary="PolicyGate should block this.",
        ),
        AgentDecision(
            action="final_answer",
            final_answer="Validation blocked execution.",
            confidence="high",
            reasoning_summary="Stop after PolicyGate blocked execution.",
        ),
    ])

    def fake_validate_sql_tool(_db, datasource_id: str, sql: str) -> ToolObservation:
        return ToolObservation(
            name="validate_sql",
            status="success",
            input={"datasource_id": datasource_id, "sql_preview": sql},
            output={
                "passed": False,
                "can_execute": False,
                "safe_sql": None,
                "original_sql": sql,
                "schema_warnings": [],
                "guardrail": {"result": "reject", "originalSql": sql, "safeSql": None, "checks": [], "message": "Syntax error."},
                "requires_confirmation": False,
                "messages": ["EXPLAIN dry-run failed: syntax error"],
                "blocked_reasons": ["syntax_error"],
                "revise_suggestion": "Fix SQL syntax.",
            },
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.validate_sql_tool", fake_validate_sql_tool)
    monkeypatch.setattr(
        "engine.agent_kernel.databox_tools.execute_sql_tool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("blocked SQL must not execute")),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="run invalid SQL",
            execute=True,
            session_id="kernel-blocked-validation-no-execute",
        )
    )

    assert "validate_sql" in [step.name for step in res.steps]
    assert "execute_sql" not in [step.name for step in res.steps]
    assert res.execution is None


def test_agent_kernel_response_binds_artifact_dependencies_and_answer_evidence() -> None:
    response = AgentKernelResponseAssembler().build_response(
        req=AgentRunRequest(datasource_id="ds-1", question="list users"),
        success=True,
        steps=[],
        query_plan={"analysis_goal": "list users", "candidate_tables": ["users"]},
        sql="SELECT id FROM users LIMIT 3",
        safety={
            "passed": True,
            "can_execute": True,
            "requires_confirmation": False,
            "safe_sql": "SELECT id FROM users LIMIT 3",
            "messages": [],
            "blocked_reasons": [],
        },
        execution={
            "success": True,
            "columns": ["id"],
            "rows": [{"id": 1}],
            "rowCount": 1,
            "latencyMs": 1,
        },
        explanation=None,
        chart_suggestion=None,
        result_profile={
            "row_count": 1,
            "column_profiles": {},
            "detected_patterns": [],
            "notable_facts": ["1 row returned."],
            "anomalies": [],
            "limitations": [],
        },
        answer={
            "answer": "1 row returned.",
            "key_findings": ["1 row returned."],
            "evidence": [
                {"artifact_id": "sql_candidate", "label": "SQL", "value": "validated candidate"},
                {"artifact_id": "safety_report", "label": "Safety", "value": "passed"},
                {"artifact_id": "result_table", "label": "Rows returned", "value": 1},
                {"artifact_id": "result_profile", "label": "Result profile", "value": "1 rows profiled"},
            ],
            "caveats": [],
            "recommendations": [],
            "follow_up_questions": [],
        },
        suggestions=[],
        error=None,
        run_id="run-artifacts",
        session_id="session-artifacts",
    )

    artifact_ids = {artifact.id for artifact in response.artifacts}
    semantic_to_id = {artifact.semantic_id: artifact.id for artifact in response.artifacts}

    assert {evidence.artifact_id for evidence in response.answer.evidence}.issubset(artifact_ids)
    assert response.answer.evidence[0].artifact_id == semantic_to_id["sql_candidate"]
    result_table = next(artifact for artifact in response.artifacts if artifact.semantic_id == "result_table")
    result_profile = next(artifact for artifact in response.artifacts if artifact.semantic_id == "result_profile")
    assert semantic_to_id["sql_candidate"] in result_table.depends_on
    assert semantic_to_id["safety_report"] in result_table.depends_on
    assert result_table.id in result_profile.depends_on
    for artifact in response.artifacts:
        assert artifact.semantic_id
        assert artifact.produced_by_step


def test_agent_kernel_recommendation_artifact_avoids_dangling_dependency_without_profile() -> None:
    response = AgentKernelResponseAssembler().build_response(
        req=AgentRunRequest(datasource_id="ds-1", question="list users"),
        success=True,
        steps=[],
        query_plan={"analysis_goal": "list users", "candidate_tables": ["users"]},
        sql="SELECT id FROM users LIMIT 3",
        safety={
            "passed": True,
            "can_execute": True,
            "requires_confirmation": False,
            "safe_sql": "SELECT id FROM users LIMIT 3",
            "messages": [],
            "blocked_reasons": [],
        },
        execution={
            "success": True,
            "columns": ["id"],
            "rows": [{"id": 1}],
            "rowCount": 1,
            "latencyMs": 1,
        },
        explanation=None,
        chart_suggestion=None,
        result_profile=None,
        answer={
            "answer": "1 row returned.",
            "key_findings": ["1 row returned."],
            "evidence": [
                {"artifact_id": "result_table", "label": "Rows returned", "value": 1},
                {"artifact_id": "sql_candidate", "label": "SQL", "value": "validated candidate"},
            ],
            "caveats": [],
            "recommendations": ["Compare by region."],
            "follow_up_questions": ["Show by region"],
        },
        suggestions=[],
        error=None,
        run_id="run-recommendations",
        session_id="session-recommendations",
    )

    artifact_ids = {artifact.id for artifact in response.artifacts}
    recommendation = next(artifact for artifact in response.artifacts if artifact.type == "recommendation")

    assert recommendation.semantic_id == "recommendations"
    assert recommendation.produced_by_step == "answer_synthesizer"
    assert recommendation.depends_on
    assert set(recommendation.depends_on).issubset(artifact_ids)


def test_agent_kernel_stream_emits_run_step_artifact_and_completion_events(
    db_session,
    demo_datasource,
) -> None:
    sync_schema(db_session, demo_datasource.id)

    events = list(AgentKernelService(db_session).run_iter(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="list users",
            execute=False,
            session_id="kernel-stream-regression",
        )
    ))
    event_types = [event.type for event in events]

    assert event_types[0] == "agent.run.started"
    assert "agent.step.started" in event_types
    assert "agent.step.completed" in event_types
    assert "agent.artifact.created" in event_types
    assert event_types[-1] == "agent.run.completed"
    assert events[-1].response is not None
    assert events[-1].response.status == "completed"


def test_agent_kernel_graph_factory_builds_langgraph_shape() -> None:
    if not langgraph_available():
        return

    graph = build_agent_kernel_graph(
        controller_node=lambda _state: {"pending_decision": {"action": "final_answer"}},
        policy_node=lambda _state: {},
        execute_tool_node=lambda _state: {},
    )

    assert graph is not None


def test_agent_kernel_checkpointer_factory_prefers_sqlite(monkeypatch) -> None:
    from contextlib import ExitStack

    from engine.agent_kernel.checkpointer import build_agent_kernel_checkpointer

    monkeypatch.delenv("DATABOX_TESTING", raising=False)
    monkeypatch.delenv("DATABOX_AGENT_KERNEL_CHECKPOINTER", raising=False)
    checkpoint_path = Path(".databox_runtime") / "test-checkpoints" / f"{uuid.uuid4().hex}.sqlite"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        checkpointer = build_agent_kernel_checkpointer(checkpoint_path, stack=stack)

        assert checkpointer.__class__.__name__ == "SqliteSaver"
    checkpoint_path.unlink(missing_ok=True)


def test_agent_kernel_controller_state_view_includes_actionable_context() -> None:
    view = _controller_state_view(
        {
            "goal": "Explain the current SQL",
            "status": "waiting_approval",
            "execute": True,
            "messages": [
                {"role": "user", "content": "list users"},
                {"role": "assistant", "content": "Generated SQL."},
                {"role": "user", "content": "explain this SQL"},
            ],
            "artifacts": [
                {"id": "artifact_schema", "tool_name": "schema.build_context", "payload": {"tables": ["users"]}},
                {
                    "id": "artifact_sql",
                    "tool_name": "sql.generate",
                    "payload": {"sql": "SELECT id, username FROM users LIMIT 3"},
                },
            ],
            "pending_approval": {
                "id": "approval_1",
                "tool_name": "sql.execute_readonly",
                "status": "pending",
                "reason": "Manual review required.",
            },
            "sql": "SELECT id, username FROM users LIMIT 3",
            "safety": {
                "safe_sql": "SELECT id, username FROM users LIMIT 3",
                "can_execute": True,
                "requires_confirmation": True,
                "blocked_reasons": ["requires_confirmation"],
            },
            "execution": {
                "success": True,
                "columns": ["id", "username"],
                "rows": [{"id": 1, "username": "alice"}, {"id": 2, "username": "bob"}],
                "rowCount": 2,
            },
            "tool_results": [
                {
                    "name": "validate_sql",
                    "status": "success",
                    "output": {"safe_sql": "SELECT id, username FROM users LIMIT 3"},
                }
            ],
            "workspace_context": {
                "selected_sql": "SELECT * FROM users",
                "selected_artifact_id": "artifact_sql",
                "selected_table_names": ["users"],
                "last_query_result_preview": {"columns": ["id"], "rows": [{"id": 1}]},
            },
            "plan_events": [
                {"operation": "create_plan", "step": {"id": "step_1", "title": "Generate SQL", "status": "completed"}}
            ],
            "step_count": 4,
            "max_steps": 20,
        }
    )

    assert view["latest_messages"][-1] == {"role": "user", "content": "explain this SQL"}
    assert view["latest_artifacts"][-1]["id"] == "artifact_sql"
    assert view["pending_approval"]["id"] == "approval_1"
    assert view["sql_preview"] == "SELECT id, username FROM users LIMIT 3"
    assert view["safe_sql_preview"] == "SELECT id, username FROM users LIMIT 3"
    assert view["execution_preview"] == {"success": True, "row_count": 2, "columns": ["id", "username"]}
    assert view["last_tool_result"]["name"] == "validate_sql"
    assert view["workspace_context_summary"]["selected_artifact_id"] == "artifact_sql"
    assert view["workspace_context_summary"]["selected_table_names"] == ["users"]
    assert view["plan_events"][-1]["operation"] == "create_plan"


def test_agent_kernel_controller_prompt_teaches_followup_artifact_and_approval_policy() -> None:
    prompt = CONTROLLER_SYSTEM_PROMPT.lower()

    assert "follow-up" in prompt
    assert "artifact" in prompt
    assert "approval" in prompt
    assert "resume" in prompt
    assert "update_plan" in prompt
    assert "pending_approval" in prompt
    assert "sql.revise" in prompt
    assert "execute=false" in prompt
    assert "never call sql.execute_readonly while pending approval is unresolved" in prompt
    assert "approval api flow" in prompt
    assert "never invent execution results" in prompt


def test_agent_kernel_sql_revise_accepts_instruction_and_pending_approval_sql(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_revise_sql_tool(*, sql, error, safety, db, datasource_id):
        captured.update({
            "sql": sql,
            "error": error,
            "safety": safety,
            "db": db,
            "datasource_id": datasource_id,
        })
        return ToolObservation(
            name="revise_sql",
            status="success",
            input={"sql_preview": sql, "error": error},
            output={
                "can_fix": False,
                "fixed_sql": None,
                "reason": error,
                "changes": [],
                "remaining_risks": [],
                "revise_suggestion": "Apply the user's requested SQL change.",
                "blocked_sql": sql,
            },
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.databox_tools.revise_sql_tool", fake_revise_sql_tool)

    registry = register_databox_tools()
    tool = registry.require("sql.revise")
    ctx = ToolContext(
        db=db_session,
        request=AgentRunRequest(datasource_id=demo_datasource.id, question="Change the limit to 10"),
        state={
            "pending_approval": {
                "id": "approval_1",
                "requested_action": {
                    "tool_name": "sql.execute_readonly",
                    "args": {"safe_sql": "SELECT id, username FROM users LIMIT 100"},
                },
            },
            "safety": {"requires_confirmation": True},
        },
    )

    obs = tool.handler(ctx, {"instruction": "Change the limit to 10 before execution."})

    assert obs.status == "success"
    assert captured["sql"] == "SELECT id, username FROM users LIMIT 100"
    assert captured["error"] == "Change the limit to 10 before execution."
    assert captured["safety"] == {"requires_confirmation": True}
    assert captured["datasource_id"] == demo_datasource.id


def test_agent_kernel_sql_revise_state_clears_stale_execution_approval_and_safety() -> None:
    observation = ToolObservation(
        name="revise_sql",
        status="success",
        input={"sql_preview": "SELECT id FROM users LIMIT 100"},
        output={
            "can_fix": True,
            "fixed_sql": "SELECT id FROM users LIMIT 10",
            "reason": "Change the limit to 10.",
            "changes": ["Changed LIMIT 100 to LIMIT 10."],
            "remaining_risks": [],
            "revise_suggestion": "Validate the revised SQL before execution.",
            "blocked_sql": "SELECT id FROM users LIMIT 100",
        },
        latency_ms=0,
    )

    update = apply_tool_result_to_state(
        state={
            "sql": "SELECT id FROM users LIMIT 100",
            "safety": {
                "safe_sql": "SELECT id FROM users LIMIT 100",
                "can_execute": True,
                "requires_confirmation": False,
            },
            "execution": {"success": True, "rowCount": 3},
            "pending_approval": {"id": "approval_1", "status": "pending"},
        },
        tool_name="sql.revise",
        observation=observation,
    )

    assert update["sql"] == "SELECT id FROM users LIMIT 10"
    assert update["safety"] is None
    assert update["execution"] is None
    assert update["pending_approval"] is None
    assert update["trace_events"][-1]["type"] == "approval.superseded"


def test_agent_kernel_validate_state_carries_generation_metadata() -> None:
    observation = ToolObservation(
        name="validate_sql",
        status="success",
        input={"sql_preview": "SELECT Country FROM singer"},
        output={
            "safe_sql": "SELECT Country FROM singer",
            "can_execute": True,
            "blocked_reasons": [],
        },
        latency_ms=0,
    )

    update = apply_tool_result_to_state(
        state={
            "sql_candidate": {
                "metadata": {
                    "semantic_violations": [{"code": "distinct_missing"}],
                    "semantic_retry_attempted": True,
                }
            }
        },
        tool_name="sql.validate",
        observation=observation,
    )

    assert update["safety"]["generation_metadata"]["semantic_retry_attempted"] is True
    assert update["safety"]["generation_metadata"]["semantic_violations"][0]["code"] == "distinct_missing"


def test_agent_kernel_event_bridge_emits_approval_required_event() -> None:
    from engine.agent_kernel.event_bridge import events_from_graph_update

    created_at = datetime.now(timezone.utc)
    agent_state = AgentState(
        run_id="run_approval",
        session_id="thread_approval",
        question="list users",
        datasource_id="ds_1",
    )

    events = list(events_from_graph_update(
        emit=EventEmitter("run_approval").emit,
        node_name="policy",
        update={
            "pending_approval": {
                "id": "approval_1",
                "run_id": "run_approval",
                "session_id": "thread_approval",
                "step_name": "execute_sql",
                "tool_name": "sql.execute_readonly",
                "status": "pending",
                "risk_level": "warning",
                "reason": "Manual review required.",
                "policy_decision": {"requires_confirmation": True},
                "requested_action": {"tool_name": "sql.execute_readonly", "args": {"sql": "SELECT 1"}},
                "created_at": created_at,
            }
        },
        agent_state=agent_state,
        step_name_for_tool=lambda tool_name: tool_name,
        artifact_events=lambda *_args: iter(()),
    ))

    assert [event.type for event in events] == ["agent.approval.required"]
    assert events[0].approval is not None
    assert events[0].approval.id == "approval_1"
    assert events[0].step == {"name": "execute_sql", "status": "waiting_approval"}


def test_agent_kernel_event_bridge_emits_tool_step_events_and_delegates_artifacts() -> None:
    from engine.agent_kernel.event_bridge import events_from_graph_update

    agent_state = AgentState(
        run_id="run_tool",
        session_id="thread_tool",
        question="list users",
        datasource_id="ds_1",
    )
    observation = ToolObservation(
        name="validate_sql",
        status="success",
        input={"sql_preview": "SELECT 1"},
        output={"safe_sql": "SELECT 1"},
        latency_ms=7,
    )
    artifact_observations: list[str] = []

    def artifact_events(observation_arg, *_args):
        artifact_observations.append(observation_arg.name)
        return iter(())

    events = list(events_from_graph_update(
        emit=EventEmitter("run_tool").emit,
        node_name="execute_tool",
        update={"last_observation": observation.model_dump(mode="json"), "last_tool_name": "sql.validate"},
        agent_state=agent_state,
        step_name_for_tool=lambda tool_name: "validate_sql" if tool_name == "sql.validate" else tool_name,
        artifact_events=artifact_events,
    ))

    assert [event.type for event in events] == ["agent.step.started", "agent.step.completed"]
    assert events[0].step == {"name": "validate_sql", "tool_name": "sql.validate"}
    assert events[1].step == {
        "name": "validate_sql",
        "tool_name": "sql.validate",
        "status": "success",
        "error": None,
        "latency_ms": 7,
    }
    assert [step.name for step in agent_state.steps] == ["validate_sql"]
    assert artifact_observations == ["validate_sql"]


def test_agent_kernel_fallback_execute_false_returns_review_response(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户", execute=False)

    res = AgentKernelService(db_session).run(req)

    assert res.success is True, res.model_dump()
    assert res.status == "completed"
    assert res.sql is not None
    assert res.safety is not None
    assert res.safety["can_execute"] is True
    assert res.execution == {"reason": "Request execute=false; SQL was not executed."}
    assert res.answer is not None
    assert [step.name for step in res.steps] == [
        "build_schema_context",
        "build_query_plan",
        "generate_sql_candidate",
        "validate_sql",
        "execute_sql",
        "profile_result",
        "suggest_chart",
        "suggest_followups",
        "answer_synthesizer",
    ]
    assert res.steps[4].status == "skipped"


def test_agent_kernel_controller_final_answer_uses_workspace_sql_without_schema_restart(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    def fail_schema_context(*_args, **_kwargs):
        raise AssertionError("SQL follow-up final_answer should not restart schema context building.")

    monkeypatch.setattr("engine.agent_kernel.databox_tools.build_schema_context_tool", fail_schema_context)
    monkeypatch.setattr(
        "engine.agent_kernel.service.decide_next_action",
        lambda **_kwargs: AgentDecision(
            action="final_answer",
            final_answer=(
                "This uses the SQL already selected in the workspace.\n\n"
                "SQL:\n```sql\nSELECT id, username FROM users LIMIT 3\n```"
            ),
            confidence="high",
            reasoning_summary="Answer from workspace SQL context.",
        ),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Explain this SQL",
            execute=False,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "selected_sql": "SELECT id, username FROM users LIMIT 3",
                "selected_artifact_id": "artifact_sql",
            },
            session_id="workspace-sql-explain-thread",
        )
    )

    assert res.success is True, res.model_dump()
    assert res.status == "completed"
    assert res.answer is not None
    assert "SELECT id, username FROM users LIMIT 3" in res.answer.answer
    assert res.steps == []


def test_agent_kernel_pending_approval_followup_explains_sql_without_schema_restart(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-pending-explain-followup",
    )

    def fail_schema_context(*_args, **_kwargs):
        raise AssertionError("Pending approval SQL follow-up should not restart schema context building.")

    monkeypatch.setattr("engine.agent_kernel.databox_tools.build_schema_context_tool", fail_schema_context)
    monkeypatch.setattr(
        "engine.agent_kernel.service.decide_next_action",
        lambda **_kwargs: AgentDecision(
            action="final_answer",
            final_answer=(
                "This pending approval would run the current SQL after approval.\n\n"
                "SQL:\n```sql\nSELECT id, username FROM users LIMIT 3\n```"
            ),
            confidence="high",
            reasoning_summary="Answer pending approval SQL question from current state.",
        ),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Can you explain what this SQL will do before I approve?",
            execute=False,
            session_id=response.session_id,
            parent_run_id=response.run_id,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "selected_sql": response.sql,
                "pending_approval_id": approval.id,
            },
        )
    )

    assert res.success is True, res.model_dump()
    assert res.status == "completed"
    assert res.answer is not None
    assert "SELECT id, username FROM users LIMIT 3" in res.answer.answer
    assert "build_schema_context" not in [step.name for step in res.steps]


def test_agent_kernel_pending_approval_followup_hydrates_approval_context(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-pending-hydrate-followup",
    )
    captured_state: dict[str, object] = {}

    def capture_decision(**kwargs):
        state = kwargs["state"]
        captured_state.update({
            "pending_approval": state.get("pending_approval"),
            "sql": state.get("sql"),
            "safety": state.get("safety"),
        })
        return AgentDecision(
            action="final_answer",
            final_answer="Answered from hydrated pending approval context.",
            confidence="high",
            reasoning_summary="Use hydrated pending approval context.",
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", capture_decision)
    monkeypatch.setattr(
        "engine.agent_kernel.databox_tools.build_schema_context_tool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not rebuild schema")),
    )
    monkeypatch.setattr(
        "engine.agent_kernel.databox_tools.execute_sql_tool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not execute SQL")),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Why does this need approval?",
            execute=False,
            session_id=response.session_id,
            parent_run_id=response.run_id,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "pending_approval_id": approval.id,
            },
        )
    )

    hydrated_approval = captured_state["pending_approval"]
    hydrated_safety = captured_state["safety"]
    assert res.status == "completed"
    assert isinstance(hydrated_approval, dict)
    assert hydrated_approval["id"] == approval.id
    assert captured_state["sql"] == response.sql
    assert isinstance(hydrated_safety, dict)
    assert hydrated_safety["safe_sql"] == response.sql
    assert hydrated_safety["requires_confirmation"] is True


def test_agent_kernel_pending_approval_modify_calls_revise_not_execute(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-pending-modify-followup",
    )
    captured_revise: dict[str, object] = {}

    decisions = iter([
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.revise",
                args={
                    "sql": response.sql,
                    "instruction": "Change the limit to 10 before execution.",
                },
                reason="User wants to modify pending SQL before approval.",
            ),
            confidence="high",
            reasoning_summary="Revise pending SQL before approval.",
        ),
        AgentDecision(
            action="final_answer",
            final_answer="I revised the SQL for review. It still needs validation before execution.",
            confidence="high",
            reasoning_summary="Stop after revision; do not execute unvalidated SQL.",
        ),
    ])

    def fake_decide_next_action(**_kwargs):
        return next(decisions)

    def fake_revise_sql_tool(*, sql, error, safety, db, datasource_id):
        captured_revise.update({"sql": sql, "error": error, "safety": safety, "datasource_id": datasource_id})
        return ToolObservation(
            name="revise_sql",
            status="success",
            input={"sql_preview": sql, "error": error},
            output={
                "can_fix": True,
                "fixed_sql": "SELECT id, username FROM users LIMIT 10",
                "reason": error,
                "changes": ["Changed LIMIT 3 to LIMIT 10."],
                "remaining_risks": [],
                "revise_suggestion": "Validate the revised SQL before execution.",
                "blocked_sql": sql,
            },
            latency_ms=0,
        )

    def fail_execute_sql(*_args, **_kwargs):
        raise AssertionError("Pending approval SQL revision must not execute directly.")

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", fake_decide_next_action)
    monkeypatch.setattr("engine.agent_kernel.databox_tools.revise_sql_tool", fake_revise_sql_tool)
    monkeypatch.setattr("engine.agent_kernel.databox_tools.execute_sql_tool", fail_execute_sql)

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Change the limit to 10 before executing",
            execute=False,
            session_id=response.session_id,
            parent_run_id=response.run_id,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "selected_sql": response.sql,
                "pending_approval_id": approval.id,
            },
        )
    )

    assert captured_revise["sql"] == response.sql
    assert captured_revise["error"] == "Change the limit to 10 before execution."
    assert res.sql == "SELECT id, username FROM users LIMIT 10"
    assert "execute_sql" not in [step.name for step in res.steps if step.status == "success"]
    assert res.status == "completed"


def test_agent_kernel_pending_approval_revision_revalidates_and_expires_old_approval(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-pending-revise-validate",
    )
    captured: dict[str, object] = {}
    decisions = iter([
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.revise",
                args={"instruction": "Change the limit to 10 before execution."},
                reason="Revise pending SQL before approval.",
            ),
            confidence="high",
            reasoning_summary="Revise pending approval SQL.",
        ),
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.validate",
                args={"sql": "SELECT id, username FROM users LIMIT 10"},
                reason="Validate revised SQL before execution.",
            ),
            confidence="high",
            reasoning_summary="Validate revised SQL.",
        ),
        AgentDecision(
            action="final_answer",
            final_answer="The revised SQL has been validated for review.",
            confidence="high",
            reasoning_summary="Stop before execution.",
        ),
    ])

    def fake_revise_sql_tool(*, sql, error, safety, db, datasource_id):
        captured["revised_from_sql"] = sql
        captured["revision_instruction"] = error
        return ToolObservation(
            name="revise_sql",
            status="success",
            input={"sql_preview": sql, "error": error},
            output={
                "can_fix": True,
                "fixed_sql": "SELECT id, username FROM users LIMIT 10",
                "reason": error,
                "changes": ["Changed LIMIT 3 to LIMIT 10."],
                "remaining_risks": [],
                "revise_suggestion": "Validate the revised SQL before execution.",
                "blocked_sql": sql,
            },
            latency_ms=0,
        )

    def fake_validate_sql_tool(_db, datasource_id: str, sql: str) -> ToolObservation:
        captured["validated_sql"] = sql
        return ToolObservation(
            name="validate_sql",
            status="success",
            input={"datasource_id": datasource_id, "sql_preview": sql},
            output={
                "passed": True,
                "can_execute": True,
                "safe_sql": sql,
                "original_sql": sql,
                "schema_warnings": [],
                "guardrail": {"result": "pass", "originalSql": sql, "safeSql": sql, "checks": [], "message": "SQL passed."},
                "requires_confirmation": False,
                "messages": ["SQL passed."],
                "blocked_reasons": [],
                "revise_suggestion": None,
            },
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.revise_sql_tool", fake_revise_sql_tool)
    monkeypatch.setattr("engine.agent_kernel.databox_tools.validate_sql_tool", fake_validate_sql_tool)
    monkeypatch.setattr(
        "engine.agent_kernel.databox_tools.execute_sql_tool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not execute revised SQL")),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Change the limit to 10 before executing",
            execute=False,
            session_id=response.session_id,
            parent_run_id=response.run_id,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "pending_approval_id": approval.id,
            },
        )
    )

    expired_approval = agent_persistence.get_approval(db_session, approval.id)

    assert captured["revised_from_sql"] == response.sql
    assert captured["revision_instruction"] == "Change the limit to 10 before execution."
    assert captured["validated_sql"] == "SELECT id, username FROM users LIMIT 10"
    assert [step.name for step in res.steps] == ["revise_sql", "validate_sql"]
    assert "execute_sql" not in [step.name for step in res.steps]
    assert res.sql == "SELECT id, username FROM users LIMIT 10"
    assert expired_approval is not None
    assert expired_approval.status == "expired"
    assert expired_approval.decision_note == "Superseded by user SQL revision before approval."


def test_agent_kernel_pending_approval_revision_without_fixed_sql_keeps_old_approval_valid(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-pending-revise-no-fixed-sql",
    )
    decisions = iter([
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.revise",
                args={"instruction": "Only explain the risk; do not change SQL."},
                reason="Attempt a revision, but no SQL change is available.",
            ),
            confidence="high",
            reasoning_summary="Try revise without producing fixed SQL.",
        ),
        AgentDecision(
            action="final_answer",
            final_answer="I did not modify the SQL, so the existing approval remains valid.",
            confidence="high",
            reasoning_summary="Old pending approval remains valid because no fixed SQL was produced.",
        ),
    ])

    def fake_revise_sql_tool(*, sql, error, safety, db, datasource_id):
        return ToolObservation(
            name="revise_sql",
            status="success",
            input={"sql_preview": sql, "error": error},
            output={
                "can_fix": False,
                "fixed_sql": "",
                "reason": error,
                "changes": [],
                "remaining_risks": ["No SQL modification was produced."],
                "revise_suggestion": "The existing approval can still be reviewed.",
                "blocked_sql": sql,
            },
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.revise_sql_tool", fake_revise_sql_tool)
    monkeypatch.setattr(
        "engine.agent_kernel.databox_tools.execute_sql_tool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not execute while approval is pending")),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Only explain the risk; do not change SQL",
            execute=False,
            session_id=response.session_id,
            parent_run_id=response.run_id,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "pending_approval_id": approval.id,
            },
        )
    )

    persisted_approval = agent_persistence.get_approval(db_session, approval.id)

    assert res.status == "completed"
    assert res.sql == response.sql
    assert res.approval is not None
    assert res.approval.id == approval.id
    assert res.approval.status == "pending"
    assert res.answer is not None
    assert "existing approval remains valid" in res.answer.answer
    assert persisted_approval is not None
    assert persisted_approval.status == "pending"


def test_agent_kernel_pending_approval_revised_sql_needing_confirmation_creates_new_approval(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-pending-revise-new-approval",
    )
    revised_sql = "SELECT id, username FROM users LIMIT 10"
    decisions = iter([
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.revise",
                args={"instruction": "Change the limit to 10 before execution."},
                reason="Revise pending SQL before approval.",
            ),
            confidence="high",
            reasoning_summary="Revise pending approval SQL.",
        ),
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.validate",
                args={"sql": revised_sql},
                reason="Validate revised SQL before execution.",
            ),
            confidence="high",
            reasoning_summary="Validate revised SQL.",
        ),
        AgentDecision(
            action="call_tool",
            tool_call=ToolCallDecision(
                tool_name="sql.execute_readonly",
                args={"sql": revised_sql},
                reason="Execution still requires approval.",
            ),
            confidence="high",
            reasoning_summary="Policy should create a new approval before execution.",
        ),
    ])

    def fake_revise_sql_tool(*, sql, error, safety, db, datasource_id):
        return ToolObservation(
            name="revise_sql",
            status="success",
            input={"sql_preview": sql, "error": error},
            output={
                "can_fix": True,
                "fixed_sql": revised_sql,
                "reason": error,
                "changes": ["Changed LIMIT 3 to LIMIT 10."],
                "remaining_risks": [],
                "revise_suggestion": "Validate the revised SQL before execution.",
                "blocked_sql": sql,
            },
            latency_ms=0,
        )

    def fake_validate_sql_tool(_db, datasource_id: str, sql: str) -> ToolObservation:
        return ToolObservation(
            name="validate_sql",
            status="success",
            input={"datasource_id": datasource_id, "sql_preview": sql},
            output={
                "passed": True,
                "can_execute": True,
                "safe_sql": sql,
                "original_sql": sql,
                "schema_warnings": [],
                "guardrail": {
                    "result": "pass",
                    "originalSql": sql,
                    "safeSql": sql,
                    "checks": [],
                    "message": "SQL passed.",
                },
                "trust_gate": {
                    "riskLevel": "warning",
                    "requiresConfirmation": True,
                    "canExecute": True,
                    "messages": ["Production datasource requires manual confirmation."],
                },
                "requires_confirmation": True,
                "messages": ["Production datasource requires manual confirmation."],
                "blocked_reasons": ["requires_confirmation"],
                "revise_suggestion": None,
            },
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.revise_sql_tool", fake_revise_sql_tool)
    monkeypatch.setattr("engine.agent_kernel.databox_tools.validate_sql_tool", fake_validate_sql_tool)
    monkeypatch.setattr(
        "engine.agent_kernel.databox_tools.execute_sql_tool",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should wait for approval before execution")),
    )

    res = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Change the limit to 10 before executing",
            execute=True,
            session_id=response.session_id,
            parent_run_id=response.run_id,
            workspace_context={
                "datasource_id": demo_datasource.id,
                "pending_approval_id": approval.id,
            },
        )
    )

    expired_approval = agent_persistence.get_approval(db_session, approval.id)
    new_approval = agent_persistence.get_pending_approval_for_run(db_session, res.run_id)

    assert res.status == "waiting_approval"
    assert res.sql == revised_sql
    assert res.execution is None
    assert expired_approval is not None
    assert expired_approval.status == "expired"
    assert new_approval is not None
    assert new_approval.id != approval.id
    assert new_approval.requested_action is not None
    assert new_approval.requested_action["args"]["sql"] == revised_sql
    assert res.approval is not None
    assert res.approval.id == new_approval.id
    assert res.approval.status == "pending"


def test_agent_kernel_service_uses_graph_factory(db_session, demo_datasource, monkeypatch) -> None:
    from engine.agent_kernel import service as service_module

    sync_schema(db_session, demo_datasource.id)
    called = False
    real_factory = service_module.build_agent_kernel_graph

    def wrapped_factory(*args, **kwargs):
        nonlocal called
        called = True
        return real_factory(*args, **kwargs)

    monkeypatch.setattr(service_module, "build_agent_kernel_graph", wrapped_factory)

    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户", execute=False)
    res = AgentKernelService(db_session).run(req)

    assert called is True
    assert res.success is True


def test_agent_kernel_response_assembler_does_not_call_legacy_runtime(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    sync_schema(db_session, demo_datasource.id)

    def fail_legacy_response(*_args, **_kwargs):
        raise AssertionError("AgentKernelService must not call DataBoxAgentRuntime._response")

    monkeypatch.setattr(DataBoxAgentRuntime, "_response", fail_legacy_response)

    req = AgentRunRequest(datasource_id=demo_datasource.id, question="查询所有用户", execute=False)
    res = AgentKernelService(db_session).run(req)

    assert res.success is True


def test_agent_kernel_interrupts_and_persists_waiting_approval(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-waiting-approval",
    )

    assert response.success is False
    assert response.status == "waiting_approval"
    assert response.approval is not None
    assert response.approval.id == approval.id
    assert "execute_sql" not in [step.name for step in response.steps]
    assert [event.type for event in events][-3:] == [
        "agent.approval.required",
        "agent.checkpoint.saved",
        "agent.run.waiting_approval",
    ]

    checkpoints = agent_persistence.list_checkpoints(db_session, response.run_id)
    assert checkpoints
    assert checkpoints[-1].status == "waiting_approval"
    state = AgentKernelService(db_session).get_thread_state(response.session_id)
    assert state["next"] == ["approval_interrupt"]
    assert state["interrupts"]


def test_agent_kernel_resume_after_approval_continues_from_interrupt(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-approve-resume",
    )

    resumed = AgentKernelService(db_session).resume_approval(
        run_id=response.run_id,
        approval_id=approval.id,
        approved=True,
        note="OK",
    )

    assert resumed.success is True, resumed.model_dump()
    assert resumed.status == "completed"
    assert resumed.approval is not None
    assert resumed.approval.status == "approved"
    assert resumed.safety is not None
    assert resumed.safety["requires_confirmation"] is False
    assert resumed.safety["approval"]["status"] == "approved"
    assert "execute_sql" in [step.name for step in resumed.steps]
    assert resumed.execution is not None
    assert resumed.execution["success"] is True


def test_agent_kernel_resume_after_service_restart_uses_saved_checkpoint(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-approve-after-restart",
    )

    original_checkpointer = AgentKernelService._checkpointer
    AgentKernelService._checkpointer = InMemorySaver()
    try:
        resumed = AgentKernelService(db_session).resume_approval(
            run_id=response.run_id,
            approval_id=approval.id,
            approved=True,
            note="OK after restart",
        )
    finally:
        AgentKernelService._checkpointer = original_checkpointer

    assert resumed.success is True, resumed.model_dump()
    assert resumed.status == "completed"
    assert resumed.approval is not None
    assert resumed.approval.status == "approved"
    assert resumed.execution is not None
    assert resumed.execution["success"] is True


def test_agent_kernel_reject_after_interrupt_fails_run(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    response, approval, _events = _kernel_waiting_run(
        db_session,
        demo_datasource,
        monkeypatch,
        session_id="kernel-reject-resume",
    )

    rejected = AgentKernelService(db_session).resume_approval(
        run_id=response.run_id,
        approval_id=approval.id,
        approved=False,
        note="No",
    )

    assert rejected.success is False
    assert rejected.status == "failed"
    assert rejected.error == "User rejected approval."
    assert rejected.approval is not None
    assert rejected.approval.status == "rejected"
