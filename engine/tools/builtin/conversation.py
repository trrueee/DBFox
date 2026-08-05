"""Current-session conversation recall tools."""

from __future__ import annotations

from engine.agent.conversation_recall import ConversationRecallService, RecalledMessage
from engine.diagnostics.logs import redact_sensitive_text
from engine.tools.builtin.contracts import (
    ConversationMessageOutput,
    ConversationReadInput,
    ConversationReadOutput,
    ConversationSearchInput,
    ConversationSearchMatch,
    ConversationSearchOutput,
)
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
    ToolRunContext,
)
from engine.tools.runtime.observation import safe_observation_facts


MAX_SEARCH_SNIPPET_CHARS = 600
MAX_READ_CONTENT_CHARS = 4_000


def _redacted_content(message: RecalledMessage) -> str:
    return redact_sensitive_text(message.content)


def _snippet(content: str, query: str) -> str:
    if len(content) <= MAX_SEARCH_SNIPPET_CHARS:
        return content
    match_at = content.casefold().find(query.casefold())
    center = match_at if match_at >= 0 else 0
    start = max(center - MAX_SEARCH_SNIPPET_CHARS // 3, 0)
    end = min(start + MAX_SEARCH_SNIPPET_CHARS, len(content))
    start = max(end - MAX_SEARCH_SNIPPET_CHARS, 0)
    return (
        ("…" if start else "")
        + content[start:end]
        + ("…" if end < len(content) else "")
    )


class ConversationSearchTool(
    BaseTool[ConversationSearchInput, ConversationSearchOutput]
):
    name = "conversation_search"
    group = "conversation"
    description = (
        "Search only the durable user and completed-assistant messages in the current "
        "conversation. Use this when older wording or decisions may have fallen outside "
        "the active context window. Results are redacted snippets; use conversation_read "
        "with a returned sequence to inspect the surrounding canonical messages."
    )
    input_model = ConversationSearchInput
    output_model = ConversationSearchOutput
    presentation = ToolPresentation(title="查找历史对话", category="explore")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=65_536,
        capabilities=("metadata_read",),
    )

    def run(
        self,
        tool_input: ConversationSearchInput,
        context: ToolRunContext,
    ) -> ConversationSearchOutput:
        db = context.require_database()
        session_id = context.require_request().session_id
        messages, mode = ConversationRecallService(db).search(
            session_id=session_id,
            query=tool_input.query,
            roles=tool_input.roles,
            limit=tool_input.limit,
        )
        matches = [
            ConversationSearchMatch(
                message_id=message.message_id,
                sequence=message.sequence,
                role=message.role,
                created_at=message.created_at,
                snippet=_snippet(_redacted_content(message), tool_input.query),
            )
            for message in messages
        ]
        return ConversationSearchOutput(
            query=redact_sensitive_text(tool_input.query),
            searched_roles=tool_input.roles,
            search_mode=mode,
            matches=matches,
            returned_count=len(matches),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="历史对话搜索失败。")
        facts = safe_observation_facts(
            {
                "returned_count": int(output.get("returned_count") or 0),
                "matched_sequences": [
                    int(item["sequence"])
                    for item in output.get("matches") or []
                    if "sequence" in item
                ],
                "search_mode": output.get("search_mode"),
            }
        )
        return ToolObservationProjection(
            summary=f"找到 {facts['returned_count']} 条当前对话记录。",
            facts=facts,
            provider_payload=output,
        )


class ConversationReadTool(BaseTool[ConversationReadInput, ConversationReadOutput]):
    name = "conversation_read"
    group = "conversation"
    description = (
        "Read an ordered, bounded page of canonical user and completed-assistant "
        "messages from the current conversation. Page by sequence; never use this to "
        "read another conversation or hidden system/reasoning messages."
    )
    input_model = ConversationReadInput
    output_model = ConversationReadOutput
    presentation = ToolPresentation(title="读取历史对话", category="explore")
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        retryable=True,
        max_retries=1,
        concurrency="parallel_safe",
        max_output_bytes=65_536,
        capabilities=("metadata_read",),
    )

    def run(
        self,
        tool_input: ConversationReadInput,
        context: ToolRunContext,
    ) -> ConversationReadOutput:
        db = context.require_database()
        session_id = context.require_request().session_id
        messages, has_more = ConversationRecallService(db).read(
            session_id=session_id,
            after_sequence=tool_input.after_sequence,
            limit=tool_input.limit,
        )
        output_messages: list[ConversationMessageOutput] = []
        for message in messages:
            content = _redacted_content(message)
            truncated = len(content) > MAX_READ_CONTENT_CHARS
            output_messages.append(
                ConversationMessageOutput(
                    message_id=message.message_id,
                    sequence=message.sequence,
                    role=message.role,
                    created_at=message.created_at,
                    content=content[:MAX_READ_CONTENT_CHARS],
                    truncated=truncated,
                )
            )
        next_sequence = output_messages[-1].sequence if output_messages else None
        return ConversationReadOutput(
            messages=output_messages,
            returned_count=len(output_messages),
            has_more=has_more,
            next_after_sequence=next_sequence,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="历史对话读取失败。")
        facts = safe_observation_facts(
            {
                "returned_count": int(output.get("returned_count") or 0),
                "has_more": bool(output.get("has_more")),
                "next_after_sequence": output.get("next_after_sequence"),
                "returned_sequences": [
                    int(item["sequence"])
                    for item in output.get("messages") or []
                    if "sequence" in item
                ],
            }
        )
        return ToolObservationProjection(
            summary=f"读取 {facts['returned_count']} 条当前对话记录。",
            facts=facts,
            provider_payload=output,
        )
