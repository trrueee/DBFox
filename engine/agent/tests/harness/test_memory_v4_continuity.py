"""Scripted cross-Run Memory v4 continuity proofs through the production loop."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.memory_v4 import SessionMemoryStateV4
from engine.agent.repositories.session import SessionRepository
from engine.agent.turn import TurnStreamError, TurnStreamItem, TurnStreamKind, TurnTermination
from engine.environment.schema_catalog_sync import ensure_catalog
from engine.json_codec import loads
from engine.models import (
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSessionMemory,
    AgentToolInvocation,
    AgentTurn,
)


def _tool_turn(call_id: str, name: str, arguments: dict[str, object]):
    encoded = json.dumps(arguments, ensure_ascii=False)
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id=f"tool:{call_id}",
        revision=1,
        tool_call_index=0,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id=f"tool:{call_id}",
        revision=2,
        tool_call_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id=f"tool:{call_id}",
        revision=3,
        output_index=0,
        model_output_item={
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": encoded,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


def _final_turn(content: str):
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_START,
        item_id="answer",
        revision=1,
        output_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_DELTA,
        item_id="answer",
        revision=2,
        content=content,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_END,
        item_id="answer",
        revision=3,
        output_index=0,
        message_status="completed",
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="answer",
        revision=4,
        output_index=0,
        model_output_item={"type": "message", "role": "assistant", "content": content},
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


def _has_output(messages: list[dict[str, Any]], call_id: str) -> bool:
    return any(
        item.get("type") == "function_call_output" and item.get("call_id") == call_id
        for item in messages
    )


def _tool_names(tools: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("name") or item.get("function", {}).get("name") or "")
        for item in tools
    }


class _CatalogRunProvider:
    """Uses only the actual Provider messages, tool surface, and tool outputs."""

    def __init__(self, *, fail_after_inspect: bool = False, repair_legacy: bool = False) -> None:
        self.fail_after_inspect = fail_after_inspect
        self.repair_legacy = repair_legacy

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        available = _tool_names(tools)
        assert {"schema_search", "schema_inspect"} <= available
        if self.repair_legacy:
            assert "data_preview" in available
            if not _has_output(messages, "legacy-preview"):
                yield from _tool_turn(
                    "legacy-preview",
                    "data_preview",
                    {"table": "main.orders", "columns": ["legacy_status"], "limit": 1},
                )
                return
            if not _has_output(messages, "inspect-orders"):
                yield from _tool_turn(
                    "inspect-orders", "schema_inspect", {"targets": ["main.orders"]}
                )
                return
            yield from _final_turn("已确认 legacy_status 不存在，真实列为 status。")
            return
        if not _has_output(messages, "search-orders"):
            yield from _tool_turn(
                "search-orders", "schema_search", {"queries": ["orders"]}
            )
            return
        if not _has_output(messages, "inspect-orders"):
            yield from _tool_turn(
                "inspect-orders", "schema_inspect", {"targets": ["main.orders"]}
            )
            return
        if self.fail_after_inspect:
            raise TurnStreamError(
                "scripted provider failure after verified Catalog observations"
            )
        yield from _final_turn("orders 的结构已确认，包含 status。")


class _MemoryReuseProvider:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompt_checked = False

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        assert {"schema_search", "schema_inspect"} <= _tool_names(tools)
        rendered = "\n".join(str(item.get("content") or "") for item in messages)
        assert '<dbfox_context source="session_memory">' in rendered
        assert '"table_name":"orders"' in rendered
        self.prompt_checked = True
        yield from _final_turn(self.answer)


class _CorrectionProvider(_MemoryReuseProvider):
    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        rendered = "\n".join(str(item.get("content") or "") for item in messages)
        active_request = rendered.split("<dbfox_current_request", 1)[1].split(
            "</dbfox_current_request>", 1
        )[0]
        assert "pending" in active_request
        assert "completed" not in active_request
        assert '<dbfox_context source="session_memory">' in rendered
        self.prompt_checked = True
        yield from _final_turn("已按当前更正，仅分析 pending 订单。")


class _RediscoverProvider:
    def __init__(self) -> None:
        self.prompt_checked = False

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        rendered = "\n".join(str(item.get("content") or "") for item in messages)
        assert '<dbfox_context source="session_memory">' not in rendered
        assert "schema_search" in _tool_names(tools)
        self.prompt_checked = True
        if not _has_output(messages, "rediscover-orders"):
            yield from _tool_turn(
                "rediscover-orders", "schema_search", {"queries": ["orders"]}
            )
            return
        yield from _final_turn("已重新发现当前数据源的 orders。")


class _RejectedToolProvider:
    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        assert "data_preview" in _tool_names(tools)
        if not _has_output(messages, "rejected-preview"):
            yield from _tool_turn(
                "rejected-preview",
                "data_preview",
                {"table": "main.orders", "columns": ["not_a_column"], "limit": 1},
            )
            return
        yield from _final_turn("该无效预览不构成已验证的结构事实。")


def _execute_run(
    db_session,
    *,
    session_id: str,
    datasource_id: str,
    generation: int,
    content: str,
    idempotency_key: str,
    provider,
):
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=datasource_id,
        datasource_generation=generation,
        content=content,
        idempotency_key=idempotency_key,
        llm_credential_id="deterministic-fixture",
        api_base=None,
        model_name="scripted",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="memory-v4-harness", ttl_seconds=120)
    assert lease is not None
    assert sessions.promote_next_input(lease=lease) == admission.run_id
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: provider,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)
    db_session.expire_all()
    return admission


def _new_session(db_session, datasource_id: str, case_id: str) -> str:
    session_id = f"memory-v4-{case_id}"
    db_session.add(AgentSession(id=session_id, datasource_id=datasource_id, title=case_id))
    db_session.commit()
    return session_id


def _run_tools(db_session, run_id: str) -> list[str]:
    return [
        str(item.tool_name)
        for item in db_session.query(AgentToolInvocation)
        .filter_by(run_id=run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    ]


def _assert_projection_consumed(db_session, session_id: str, run_id: str) -> None:
    row = db_session.query(AgentSessionMemory).filter_by(session_id=session_id).one()
    memory = SessionMemoryStateV4.model_validate(loads(str(row.memory_v4_json)))
    assert any(item.projection_id == "dbfox.catalog.working_state" for item in memory.projections)
    turn = db_session.query(AgentTurn).filter_by(run_id=run_id).one()
    snapshot = loads(str(turn.context_snapshot_json))
    assert snapshot["session_memory"]["version"] == 4
    assert snapshot["session_memory"]["SESSION_WORKING_STATE"]["selected_count"] > 0
    source = next(item for item in snapshot["sources"] if item["kind"] == "session_memory")
    assert source["included"] is True


def _answer(db_session, admission) -> str:
    message = db_session.get(AgentMessage, admission.assistant_message_id)
    assert message is not None
    return str(message.content)


def test_memory_v4_schema_before_query_avoids_duplicate_discovery(
    db_session, test_datasource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = _new_session(db_session, str(test_datasource.id), "schema-before-query")
    first = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="确认 orders 结构。", idempotency_key="b1-1", provider=_CatalogRunProvider(),
    )
    consumer = _MemoryReuseProvider("已复用 orders 的 status 结构完成分析。")
    second = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="继续，根据已经确认的结构完成分析。", idempotency_key="b1-2", provider=consumer,
    )
    assert db_session.get(AgentRun, first.run_id).status == "completed"
    assert consumer.prompt_checked is True
    _assert_projection_consumed(db_session, session_id, second.run_id)
    assert _run_tools(db_session, second.run_id) == []
    assert "status" in _answer(db_session, second)


def test_memory_v4_failed_preview_then_query_continues(
    db_session, test_datasource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = _new_session(db_session, str(test_datasource.id), "failed-preview-then-query")
    first = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="确认 orders 结构。", idempotency_key="b2-1",
        provider=_CatalogRunProvider(fail_after_inspect=True),
    )
    consumer = _MemoryReuseProvider("失败前已验证 orders；现已继续完成查询。")
    second = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="继续前一轮。", idempotency_key="b2-2", provider=consumer,
    )
    assert db_session.get(AgentRun, first.run_id).status == "failed"
    assert consumer.prompt_checked is True
    _assert_projection_consumed(db_session, session_id, second.run_id)
    assert _run_tools(db_session, second.run_id) == []
    assert "继续完成查询" in _answer(db_session, second)


def test_memory_v4_user_correction_wins_over_prior_context(
    db_session, test_datasource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = _new_session(db_session, str(test_datasource.id), "user-correction-wins")
    _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="确认 orders 结构后统计 completed。", idempotency_key="b3-1", provider=_CatalogRunProvider(),
    )
    consumer = _CorrectionProvider("unused")
    second = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="更正：现在只分析 pending 订单。", idempotency_key="b3-2", provider=consumer,
    )
    assert consumer.prompt_checked is True
    _assert_projection_consumed(db_session, session_id, second.run_id)
    assert _run_tools(db_session, second.run_id) == []
    assert _answer(db_session, second) == "已按当前更正，仅分析 pending 订单。"


def test_memory_v4_missing_column_repair_does_not_reuse_rejected_column(
    db_session, test_datasource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = _new_session(db_session, str(test_datasource.id), "missing-column-repair")
    first = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="检查 legacy_status，失败后确认 orders 的真实结构。", idempotency_key="b4-1",
        provider=_CatalogRunProvider(repair_legacy=True),
    )
    consumer = _MemoryReuseProvider("已使用真实的 status 列，而非 legacy_status。")
    second = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="继续按已确认的 orders 结构完成分析。", idempotency_key="b4-2", provider=consumer,
    )
    invocations = db_session.query(AgentToolInvocation).filter_by(run_id=first.run_id).all()
    assert any(item.status == "failed" for item in invocations)
    _assert_projection_consumed(db_session, session_id, second.run_id)
    snapshot = loads(str(db_session.query(AgentTurn).filter_by(run_id=second.run_id).one().context_snapshot_json))
    rendered = json.dumps(snapshot["session_memory"], ensure_ascii=False)
    assert "status" in rendered
    assert "legacy_status" not in rendered
    assert _run_tools(db_session, second.run_id) == []
    assert "status" in _answer(db_session, second)


def test_memory_v4_generation_change_requires_justified_rediscovery(
    db_session, test_datasource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = _new_session(db_session, str(test_datasource.id), "generation-invalidation")
    _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="确认 orders 结构。", idempotency_key="b5-1", provider=_CatalogRunProvider(),
    )
    consumer = _RediscoverProvider()
    second = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=2,
        content="数据源已切换，请继续。", idempotency_key="b5-2", provider=consumer,
    )
    assert consumer.prompt_checked is True
    assert _run_tools(db_session, second.run_id) == ["schema_search"]
    row = db_session.query(AgentSessionMemory).filter_by(session_id=session_id).one()
    memory = SessionMemoryStateV4.model_validate(loads(str(row.memory_v4_json)))
    projection = next(item for item in memory.projections if item.projection_id == "dbfox.catalog.working_state")
    assert projection.scope["datasource_generation"] == 2
    assert "重新发现" in _answer(db_session, second)


def test_memory_v4_failed_tool_does_not_poison_next_run(
    db_session, test_datasource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("engine.agent.context.MEMORY_V4_CONTEXT_ENABLED", True)
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = _new_session(db_session, str(test_datasource.id), "no-progress-does-not-poison")
    first = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="尝试无效预览。", idempotency_key="b6-1", provider=_RejectedToolProvider(),
    )
    consumer = _RediscoverProvider()
    second = _execute_run(
        db_session, session_id=session_id, datasource_id=str(test_datasource.id), generation=1,
        content="请从可靠结构开始继续。", idempotency_key="b6-2", provider=consumer,
    )
    assert "data_preview" in _run_tools(db_session, first.run_id)
    assert any(
        item.status == "failed"
        for item in db_session.query(AgentToolInvocation).filter_by(run_id=first.run_id).all()
    )
    assert consumer.prompt_checked is True
    assert _run_tools(db_session, second.run_id) == ["schema_search"]
    assert "重新发现" in _answer(db_session, second)
