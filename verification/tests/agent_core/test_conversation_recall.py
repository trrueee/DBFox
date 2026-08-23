from __future__ import annotations

from types import SimpleNamespace

from engine.agent.conversation_recall import ConversationRecallService
from engine.models import AgentMessage, AgentSession
from engine.tools.builtin.contracts import (
    ConversationReadInput,
    ConversationSearchInput,
)
from engine.tools.builtin.conversation import (
    ConversationReadTool,
    ConversationSearchTool,
)
from engine.tools.runtime import ToolRunContext


def _session(db_session, resource_id: str, session_id: str) -> AgentSession:
    value = AgentSession(id=session_id, title=session_id)
    db_session.add(value)
    db_session.flush()
    return value


def _message(
    db_session,
    *,
    session_id: str,
    message_id: str,
    sequence: int,
    role: str,
    content: str,
    status: str = "completed",
) -> AgentMessage:
    value = AgentMessage(
        id=message_id,
        session_id=session_id,
        sequence=sequence,
        role=role,
        content=content,
        status=status,
    )
    db_session.add(value)
    db_session.flush()
    return value


def _context(db_session, resource_id: str, session_id: str) -> ToolRunContext:
    request = SimpleNamespace(
        resource_id=resource_id,
        question="回忆本轮对话",
        session_id=session_id,
        run_id="run_recall",
        execution_id="execution_recall",
    )
    return ToolRunContext.for_invocation(
        request=request,
        idempotency_key="recall-test",
        resources={("verification.resource", resource_id): db_session},
        metadata_session=db_session,
    )


def test_fts_search_tracks_completed_canonical_messages_and_updates(
    db_session,
    test_resource,
) -> None:
    session_id = "recall_fts"
    _session(db_session, str(test_resource.id), session_id)
    assistant = _message(
        db_session,
        session_id=session_id,
        message_id="recall_assistant",
        sequence=1,
        role="assistant",
        content="最初决定采用紫狐发布方案",
        status="created",
    )
    db_session.commit()
    service = ConversationRecallService(db_session)

    matches, mode = service.search(
        session_id=session_id,
        query="紫狐发布",
        roles=["assistant"],
        limit=10,
    )
    assert mode == "fts5_trigram"
    assert matches == []

    assistant.status = "completed"
    db_session.commit()
    matches, _ = service.search(
        session_id=session_id,
        query="紫狐发布",
        roles=["assistant"],
        limit=10,
    )
    assert [item.message_id for item in matches] == ["recall_assistant"]

    assistant.content = "后来决定采用蓝鲸发布方案"
    db_session.commit()
    old_matches, _ = service.search(
        session_id=session_id,
        query="紫狐发布",
        roles=["assistant"],
        limit=10,
    )
    new_matches, _ = service.search(
        session_id=session_id,
        query="蓝鲸发布",
        roles=["assistant"],
        limit=10,
    )
    assert old_matches == []
    assert [item.message_id for item in new_matches] == ["recall_assistant"]

    db_session.delete(assistant)
    db_session.commit()
    deleted_matches, _ = service.search(
        session_id=session_id,
        query="蓝鲸发布",
        roles=["assistant"],
        limit=10,
    )
    assert deleted_matches == []


def test_search_is_current_session_only_and_short_queries_are_bound(
    db_session,
    test_resource,
) -> None:
    resource_id = str(test_resource.id)
    _session(db_session, resource_id, "recall_local")
    _session(db_session, resource_id, "recall_foreign")
    _message(
        db_session,
        session_id="recall_local",
        message_id="local_message",
        sequence=1,
        role="user",
        content="我选择了 A 方案，标记为「旧约」。",
    )
    _message(
        db_session,
        session_id="recall_foreign",
        message_id="foreign_message",
        sequence=1,
        role="user",
        content='另一个会话也提到了「旧约」以及 " OR 1=1 --。',
    )
    _message(
        db_session,
        session_id="recall_local",
        message_id="hidden_system",
        sequence=2,
        role="system",
        content="旧约不能展示",
    )
    db_session.commit()

    matches, mode = ConversationRecallService(db_session).search(
        session_id="recall_local",
        query="旧约",
        roles=["user", "assistant"],
        limit=20,
    )
    assert mode == "literal_scan"
    assert [item.message_id for item in matches] == ["local_message"]

    injected, _ = ConversationRecallService(db_session).search(
        session_id="recall_local",
        query='" OR 1=1 --',
        roles=["user", "assistant"],
        limit=20,
    )
    assert injected == []


def test_read_uses_stable_sequence_paging_and_excludes_unfinished_assistant(
    db_session,
    test_resource,
) -> None:
    session_id = "recall_page"
    _session(db_session, str(test_resource.id), session_id)
    for sequence, role, status in [
        (1, "user", "completed"),
        (2, "assistant", "completed"),
        (3, "assistant", "failed"),
        (4, "user", "completed"),
    ]:
        _message(
            db_session,
            session_id=session_id,
            message_id=f"page_{sequence}",
            sequence=sequence,
            role=role,
            status=status,
            content=f"message {sequence}",
        )
    db_session.commit()
    service = ConversationRecallService(db_session)

    first, first_more = service.read(session_id=session_id, after_sequence=0, limit=2)
    second, second_more = service.read(
        session_id=session_id,
        after_sequence=first[-1].sequence,
        limit=2,
    )
    assert [item.sequence for item in first] == [1, 2]
    assert first_more is True
    assert [item.sequence for item in second] == [4]
    assert second_more is False


def test_tools_redact_provider_text_and_persist_only_structural_facts(
    db_session,
    test_resource,
) -> None:
    session_id = "recall_redaction"
    resource_id = str(test_resource.id)
    secret = "sk" + "-abcdefgh123456"
    dsn_password = "dsn-password-recall"
    _session(db_session, resource_id, session_id)
    _message(
        db_session,
        session_id=session_id,
        message_id="secret_message",
        sequence=1,
        role="user",
        content=(
            f"密钥是 {secret}，dsn=postgresql://dbuser:{dsn_password}@db.invalid/app，"
            "请记住部署决定。"
        ),
    )
    db_session.commit()
    context = _context(db_session, resource_id, session_id)

    search_tool = ConversationSearchTool()
    search_output = search_tool.run(
        ConversationSearchInput(query="部署决定"),
        context,
    )
    search_payload = search_output.model_dump(mode="json")
    search_projection = search_tool.project_observation(
        status="success",
        output=search_payload,
        artifacts=[],
    )
    assert secret not in str(search_projection.provider_payload)
    assert dsn_password not in str(search_projection.provider_payload)
    assert "[REDACTED_API_KEY]" in str(search_projection.provider_payload)
    assert "snippet" not in str(search_projection.facts)

    read_tool = ConversationReadTool()
    read_output = read_tool.run(ConversationReadInput(after_sequence=0), context)
    read_payload = read_output.model_dump(mode="json")
    read_projection = read_tool.project_observation(
        status="success",
        output=read_payload,
        artifacts=[],
    )
    assert secret not in str(read_projection.provider_payload)
    assert dsn_password not in str(read_projection.provider_payload)
    assert "content" not in str(read_projection.facts)
