from __future__ import annotations

from engine.agent import AgentRunRequest, ToolObservation
from engine.agent.artifacts import build_agent_plan_artifact
from engine.agent_kernel.schemas import AgentDecision, PlanPatch, PlanStep
from engine.agent_kernel.service import AgentKernelService


def test_agent_kernel_plan_events_reduce_to_plan_state() -> None:
    from engine.agent_kernel.plan_state import apply_plan_patches

    plan = apply_plan_patches(
        None,
        [
            PlanPatch(
                operation="add_step",
                step=PlanStep(
                    id="schema",
                    title="Inspect schema",
                    tool_name="schema.build_context",
                    depends_on=[],
                ),
            ),
            PlanPatch(operation="mark_running", step_id="schema"),
            PlanPatch(operation="mark_completed", step_id="schema"),
            PlanPatch(
                operation="add_step",
                step=PlanStep(
                    id="answer",
                    title="Answer from evidence",
                    tool_name="answer.synthesize",
                    depends_on=["schema"],
                ),
            ),
            PlanPatch(operation="skip_step", step_id="answer", reason="No execution evidence is needed."),
        ],
    )

    assert plan["version"] == "agent-plan/v1"
    assert plan["steps"][0]["id"] == "schema"
    assert plan["steps"][0]["status"] == "completed"
    assert plan["steps"][0]["tool_name"] == "schema.build_context"
    assert plan["steps"][1]["id"] == "answer"
    assert plan["steps"][1]["status"] == "skipped"
    assert plan["steps"][1]["depends_on"] == ["schema"]


def test_agent_kernel_plan_reducer_supports_create_update_and_clear() -> None:
    from engine.agent_kernel.plan_state import apply_plan_patches

    plan = apply_plan_patches(
        None,
        [
            PlanPatch(
                operation="create_plan",
                step=PlanStep(id="schema", title="Inspect schema", tool_name="schema.build_context"),
            ),
            PlanPatch(
                operation="update_step",
                step=PlanStep(
                    id="schema",
                    title="Inspect synced schema",
                    tool_name="schema.build_context",
                    depends_on=["context"],
                ),
            ),
        ],
    )

    assert plan["steps"] == [
        {
            "id": "schema",
            "title": "Inspect synced schema",
            "status": "pending",
            "tool_name": "schema.build_context",
            "artifact_ids": [],
            "depends_on": ["context"],
        }
    ]

    cleared = apply_plan_patches(plan, [PlanPatch(operation="clear_plan")])
    assert cleared["steps"] == []


def test_agent_plan_artifact_has_stable_contract_copy() -> None:
    artifact = build_agent_plan_artifact({"version": "agent-plan/v1", "steps": []})

    assert artifact.type == "agent_plan"
    assert artifact.semantic_id == "agent_plan_draft"
    assert artifact.title == "Agent plan"
    assert artifact.produced_by_step == "plan_agent"
    assert artifact.depends_on == []


def test_agent_kernel_update_plan_continues_and_returns_agent_plan_artifact(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    decisions = iter(
        [
            AgentDecision(
                action="update_plan",
                plan_patches=[
                    PlanPatch(
                        operation="add_step",
                        step=PlanStep(
                            id="draft_sql",
                            title="Draft SQL candidate",
                            tool_name="sql.generate",
                            depends_on=[],
                        ),
                    )
                ],
                confidence="high",
                reasoning_summary="Expose the visible plan before choosing the next action.",
            ),
            AgentDecision(
                action="final_answer",
                final_answer="Plan is ready for review.",
                confidence="high",
                reasoning_summary="Stop after proving update_plan can continue.",
            ),
        ]
    )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))

    response = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Plan a query",
            execute=False,
            session_id="kernel-plan-update",
        )
    )

    plan_artifacts = [artifact for artifact in response.artifacts if artifact.type == "agent_plan"]

    assert response.status == "completed"
    assert response.answer is not None
    assert response.answer.answer == "Plan is ready for review."
    assert plan_artifacts
    assert plan_artifacts[0].semantic_id == "agent_plan_draft"
    assert plan_artifacts[0].payload["steps"][0]["id"] == "draft_sql"
    assert plan_artifacts[0].payload["steps"][0]["status"] == "pending"


def test_agent_kernel_plan_auto_syncs_tool_completion_to_plan_artifact(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    decisions = iter(
        [
            AgentDecision(
                action="update_plan",
                plan_patches=[
                    PlanPatch(
                        operation="add_step",
                        step=PlanStep(
                            id="schema",
                            title="Inspect schema",
                            tool_name="schema.build_context",
                        ),
                    )
                ],
                confidence="high",
                reasoning_summary="Show plan before executing schema context.",
            ),
            AgentDecision(
                action="call_tool",
                tool_call={"tool_name": "schema.build_context", "args": {}, "reason": "Inspect schema."},
                confidence="high",
                reasoning_summary="Run schema context tool.",
            ),
            AgentDecision(
                action="final_answer",
                final_answer="Schema plan step completed.",
                confidence="high",
                reasoning_summary="Stop after tool completion.",
            ),
        ]
    )

    def fake_schema_context(*_args, **_kwargs):
        return ToolObservation(
            name="build_schema_context",
            status="success",
            input={},
            output={"schema_context": "users(id)", "selected_tables": ["users"], "mode": "test"},
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.build_schema_context_tool", fake_schema_context)

    response = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Plan then inspect schema",
            execute=False,
            session_id="kernel-plan-auto-sync-success",
        )
    )

    plan_artifact = next(artifact for artifact in response.artifacts if artifact.type == "agent_plan")
    assert plan_artifact.payload["steps"][0]["id"] == "schema"
    assert plan_artifact.payload["steps"][0]["status"] == "completed"
    assert any(step.name == "build_schema_context" for step in response.steps)


def test_agent_kernel_plan_auto_syncs_failed_tool_to_failed_step(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    decisions = iter(
        [
            AgentDecision(
                action="update_plan",
                plan_patches=[
                    PlanPatch(
                        operation="add_step",
                        step=PlanStep(id="schema", title="Inspect schema", tool_name="schema.build_context"),
                    )
                ],
                confidence="high",
                reasoning_summary="Show plan before executing schema context.",
            ),
            AgentDecision(
                action="call_tool",
                tool_call={"tool_name": "schema.build_context", "args": {}, "reason": "Inspect schema."},
                confidence="high",
                reasoning_summary="Run schema context tool.",
            ),
            AgentDecision(
                action="final_answer",
                final_answer="Schema step failed.",
                confidence="high",
                reasoning_summary="Stop after failed tool.",
            ),
        ]
    )

    def fake_failed_schema_context(*_args, **_kwargs):
        return ToolObservation(
            name="build_schema_context",
            status="failed",
            input={},
            output={},
            error="schema unavailable",
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.build_schema_context_tool", fake_failed_schema_context)

    response = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Plan then fail schema",
            execute=False,
            session_id="kernel-plan-auto-sync-failed",
        )
    )

    plan_artifact = next(artifact for artifact in response.artifacts if artifact.type == "agent_plan")

    assert plan_artifact.payload["steps"][0]["status"] == "failed"


def test_agent_kernel_plan_auto_syncs_skipped_tool_to_skipped_step(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    decisions = iter(
        [
            AgentDecision(
                action="update_plan",
                plan_patches=[
                    PlanPatch(
                        operation="add_step",
                        step=PlanStep(id="execute", title="Skip execution", tool_name="sql.skip_execution"),
                    )
                ],
                confidence="high",
                reasoning_summary="Show plan before skipping execution.",
            ),
            AgentDecision(
                action="call_tool",
                tool_call={"tool_name": "sql.skip_execution", "args": {}, "reason": "Review only."},
                confidence="high",
                reasoning_summary="Skip execution.",
            ),
            AgentDecision(
                action="final_answer",
                final_answer="Execution skipped.",
                confidence="high",
                reasoning_summary="Stop after skipped tool.",
            ),
        ]
    )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))

    response = AgentKernelService(db_session).run(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Plan then skip execution",
            execute=False,
            session_id="kernel-plan-auto-sync-skipped",
        )
    )

    plan_artifact = next(artifact for artifact in response.artifacts if artifact.type == "agent_plan")

    assert plan_artifact.payload["steps"][0]["status"] == "skipped"


def test_agent_kernel_streams_agent_plan_artifact_before_planned_tool_runs(
    db_session,
    demo_datasource,
    monkeypatch,
) -> None:
    decisions = iter(
        [
            AgentDecision(
                action="update_plan",
                plan_patches=[
                    PlanPatch(
                        operation="add_step",
                        step=PlanStep(id="schema", title="Inspect schema", tool_name="schema.build_context"),
                    )
                ],
                confidence="high",
                reasoning_summary="Show plan before executing schema context.",
            ),
            AgentDecision(
                action="call_tool",
                tool_call={"tool_name": "schema.build_context", "args": {}, "reason": "Inspect schema."},
                confidence="high",
                reasoning_summary="Run schema context tool.",
            ),
            AgentDecision(
                action="final_answer",
                final_answer="Plan streamed before work.",
                confidence="high",
                reasoning_summary="Stop after planned tool.",
            ),
        ]
    )

    def fake_schema_context(*_args, **_kwargs):
        return ToolObservation(
            name="build_schema_context",
            status="success",
            input={},
            output={"schema_context": "users(id)", "selected_tables": ["users"], "mode": "test"},
            latency_ms=0,
        )

    monkeypatch.setattr("engine.agent_kernel.service.decide_next_action", lambda **_kwargs: next(decisions))
    monkeypatch.setattr("engine.agent_kernel.databox_tools.build_schema_context_tool", fake_schema_context)

    events = list(AgentKernelService(db_session).run_iter(
        AgentRunRequest(
            datasource_id=demo_datasource.id,
            question="Stream plan before tool",
            execute=False,
            session_id="kernel-plan-stream-early",
        )
    ))

    plan_event_index = next(
        index
        for index, event in enumerate(events)
        if event.type == "agent.artifact.created" and event.artifact and event.artifact.type == "agent_plan"
    )
    schema_started_index = next(
        index
        for index, event in enumerate(events)
        if event.type == "agent.step.started" and event.step and event.step.get("tool_name") == "schema.build_context"
    )

    assert plan_event_index < schema_started_index
