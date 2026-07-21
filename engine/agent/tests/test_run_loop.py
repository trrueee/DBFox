import json
import re

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.definition import AgentDefinition
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.agent.turn import TurnStreamItem, TurnStreamKind
from engine.models import AgentEvidenceRecord, AgentMessage, AgentRun, AgentSession
from engine.tools.runtime import (
    ArtifactSpec, BaseTool, ToolExecutionSpec, ToolPolicy, ToolRegistry, ToolStateSpec,
)


class ValidateInput(BaseModel):
    sql: str


class ExecuteInput(BaseModel):
    pass


class LooseOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


class ValidateTool(BaseTool[ValidateInput, LooseOutput]):
    name = "sql.validate"
    group = "sql"
    description = "validate"
    input_model = ValidateInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(produces=("safety", "sql"))
    artifacts = ArtifactSpec()

    def run(self, tool_input, context):
        return LooseOutput.model_validate({
            "can_execute": True, "requires_confirmation": False,
            "safe_sql": tool_input.sql, "original_sql": tool_input.sql,
            "risk_level": "safe", "blocked_reasons": [], "messages": [],
        })


class ExecuteTool(BaseTool[ExecuteInput, LooseOutput]):
    name = "sql.execute_readonly"
    group = "sql"
    description = "execute"
    input_model = ExecuteInput
    output_model = LooseOutput
    policy = ToolPolicy(side_effect="read", requires_validated_sql=True)
    execution = ToolExecutionSpec(capabilities=("database_read",))
    state = ToolStateSpec(consumes=("safety", "sql"), produces=("execution",))
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))

    def run(self, tool_input, context):
        assert context.state["safety"]["can_execute"] is True
        return LooseOutput.model_validate({
            "status": "success", "success": True, "columns": ["total"],
            "rows": [{"total": 42}], "rowCount": 1,
            "safe_sql": context.state["safety"]["safe_sql"],
        })


class ScriptedModel:
    def __init__(self, call_number):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number == 1:
            yield TurnStreamItem(
                kind=TurnStreamKind.REASONING_SUMMARY_DELTA, channel="reasoning_summary", offset=0,
                content="先验证并执行聚合查询。",
            )
            for index, (call_id, name, arguments) in enumerate([
                ("validate", "sql.validate", {"sql": "select count(*) as total from orders"}),
                ("execute", "sql.execute_readonly", {}),
            ]):
                yield TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_START, channel=f"tool:{index}", offset=0,
                    tool_call_index=index, tool_call_id=call_id, tool_name=name,
                    arguments_delta=json.dumps(arguments),
                )
                yield TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_END, channel=f"tool:{index}", offset=1,
                    tool_call_index=index,
                )
            yield TurnStreamItem(
                kind=TurnStreamKind.FINISH, channel="meta", offset=0, finish_signal="tool_calls"
            )
        else:
            artifact_match = re.search(r'"artifactIds":\["(artifact_[A-Za-z0-9_-]+)"\]', messages[-1]["content"])
            assert artifact_match is not None
            content = f"共有 42 条订单。{{{{cite:{artifact_match.group(1)}}}}}"
            yield TurnStreamItem(
                kind=TurnStreamKind.TEXT_DELTA, channel="text", offset=0,
                content=content,
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.FINISH, channel="meta", offset=0, finish_signal="stop"
            )


class ToolBudgetModel:
    def __init__(self, call_number):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number == 1:
            yield from ScriptedModel(1).stream(
                messages=messages,
                tools=tools,
                timeout_seconds=timeout_seconds,
                cancellation_probe=cancellation_probe,
            )
            return
        yield TurnStreamItem(
            kind=TurnStreamKind.TOOL_CALL_START, channel="tool:0", offset=0,
            tool_call_index=0, tool_call_id="repeat-validate", tool_name="sql.validate",
            arguments_delta=json.dumps({"sql": "select count(*) as total from orders"}),
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.TOOL_CALL_END, channel="tool:0", offset=1, tool_call_index=0,
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH, channel="meta", offset=0, finish_signal="tool_calls",
        )


def test_explicit_run_loop_closes_tool_artifact_evidence_and_answer_cycle(db_session, test_datasource):
    db_session.add(AgentSession(id="session_loop", datasource_id=str(test_datasource.id), title="Loop"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_loop", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="统计订单数量", idempotency_key="loop", llm_credential_id="credential",
        api_base=None, model_name="test", request_payload={},
    )
    lease = sessions.claim(session_id="session_loop", owner="worker", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}
    def model_factory(_settings):
        calls["count"] += 1
        return ScriptedModel(calls["count"])

    registry = ToolRegistry().register(ValidateTool()).register(ExecuteTool())
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    live = LiveStreamHub()
    subscription = live.subscribe(admission.run_id)
    RunLoop(
        session_factory=factory, model_factory=model_factory, registry=registry, live_stream=live,
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    assert run.status == "completed"
    assert answer.content.startswith("共有 42 条订单。{{cite:artifact_")
    assert db_session.query(AgentEvidenceRecord).filter_by(run_id=run.id).count() == 1
    assert calls["count"] == 2
    assert subscription.receive(timeout=0.01).content == "先验证并执行聚合查询。"
    assert subscription.receive(timeout=0.01).content.startswith("共有 42 条订单。{{cite:artifact_")
def test_result_rows_are_transient_and_never_enter_durable_facts() -> None:
    secret = "transient-sensitive-cell"
    output = {
        "rows": [{"token": secret}],
        "series": [{"label": secret, "value": 1}],
        "columns": ["token"],
        "rowCount": 1,
        "safe_sql": "SELECT token FROM secrets",
    }
    durable = RunLoop._durable_facts("sql.execute_readonly", output, [])
    assert secret not in json.dumps(durable)
    assert durable["rowCount"] == 1
    assert durable["columnCount"] == 1
    assert "columns" not in durable
    assert "safe_sql" not in durable


def test_tool_budget_returns_bounded_partial_when_verified_result_exists(db_session, test_datasource):
    db_session.add(AgentSession(id="session_tool_budget", datasource_id=str(test_datasource.id), title="Budget"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_tool_budget", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="统计订单数量", idempotency_key="tool-budget", llm_credential_id="credential",
        api_base=None, model_name="test", request_payload={},
    )
    lease = sessions.claim(session_id="session_tool_budget", owner="worker", ttl_seconds=120)
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}
    def model_factory(_settings):
        calls["count"] += 1
        return ToolBudgetModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(ValidateTool()).register(ExecuteTool()),
        definition=AgentDefinition(limits=RunLimits(max_tool_invocations=2)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    result = json.loads(run.result_json)
    assert run.status == "completed"
    assert result["completion_disposition"] == "bounded_partial"
    assert result["limitation_codes"] == ["TOOL_BUDGET_REACHED"]
    assert "已达到工具调用上限" in result["answer"]["caveats"][0]
