from __future__ import annotations

from engine.agent import AgentRunRequest, ToolObservation
from engine.agent import persistence as agent_persistence
from engine.agent.runtime import DataBoxAgentRuntime
from engine.agent_kernel.databox_tools import register_databox_tools
from engine.agent_kernel.graph import build_agent_kernel_graph, langgraph_available
from engine.agent_kernel.policy import PolicyGate
from engine.agent_kernel.service import AgentKernelService
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


def test_agent_kernel_policy_blocks_execution_without_validated_sql() -> None:
    registry = register_databox_tools()
    decision = PolicyGate(registry).check({}, "sql.execute_readonly", {})

    assert decision.status == "blocked"
    assert "sql.validate" in decision.reason


def test_agent_kernel_graph_factory_builds_langgraph_shape() -> None:
    if not langgraph_available():
        return

    graph = build_agent_kernel_graph(
        controller_node=lambda _state: {"pending_decision": {"action": "final_answer"}},
        policy_node=lambda _state: {},
        execute_tool_node=lambda _state: {},
    )

    assert graph is not None


def test_agent_kernel_execute_false_returns_review_response(db_session, demo_datasource) -> None:
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
