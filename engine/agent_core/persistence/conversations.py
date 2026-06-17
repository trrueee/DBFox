"""ChatConversation sync — builds the conversation timeline from agent runs."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from engine.models import AgentArtifactRecord
from engine.models import AgentSession, AgentRun, ChatConversation
from engine.agent_core.persistence._common import (
    _parse_json,
    _to_timestamp_ms,
    _format_cell,
)

logger = logging.getLogger("dbfox.agent.persistence")


def sync_chat_conversation_from_session(db: Session, session_id: str) -> None:
    """Reconstructs the full conversational timeline and updates/inserts ChatConversation."""
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if session is None:
        logger.warning("Session %s not found for ChatConversation sync", session_id)
        return

    from engine.agent_core.persistence.runs import get_run_sequence_by_session
    runs = get_run_sequence_by_session(db, session_id)
    if not runs:
        return

    title = _build_conversation_title(session, runs)
    messages = _build_conversation_messages(runs)
    view_artifacts = _build_view_artifacts(db, session_id)
    _persist_conversation_record(db, session, session_id, title, messages, view_artifacts)


def _build_conversation_title(session: AgentSession, runs: list[AgentRun]) -> str:
    title = session.title or runs[0].question
    if title and len(title) > 100:
        title = title[:97] + "..."
    return title or ""


def _build_conversation_messages(runs: list[AgentRun]) -> list[dict[str, Any]]:
    """Build the full message timeline from agent runs."""
    messages: list[dict[str, Any]] = []

    for run in runs:
        messages.append({
            "id": f"message-user-{run.id}",
            "role": "user",
            "content": run.question,
            "createdAt": _to_timestamp_ms(run.created_at),
        })

        completed_ts = run.completed_at or run.updated_at or datetime.now(UTC)
        completed_ms = _to_timestamp_ms(completed_ts)

        if run.status in ("success", "completed"):
            ans_text = ""
            suggestions = []
            if run.response_json:
                try:
                    resp_data = json.loads(run.response_json)
                    answer = resp_data.get("answer")
                    explanation = resp_data.get("explanation")
                    suggestions = resp_data.get("suggestions") or []

                    if answer and answer.get("answer"):
                        parts = [answer["answer"].strip()]
                        if answer.get("key_findings"):
                            parts.append("\n".join(f"• {item}" for item in answer["key_findings"]))
                        if answer.get("caveats"):
                            parts.append("\n".join(f"注意：{item}" for item in answer["caveats"]))
                        ans_text = "\n\n".join(parts)
                    else:
                        ans_text = (explanation or "").strip() or "已为您生成分析结果。"
                except Exception:
                    ans_text = "已为您生成分析结果。"
            else:
                ans_text = "已为您生成分析结果。"

            messages.append({
                "id": f"message-assistant-{run.id}",
                "role": "assistant",
                "content": ans_text,
                "createdAt": completed_ms,
            })

            if suggestions:
                lines = [
                    f"• {item.get('question') or item.get('label')}"
                    for item in suggestions[:4]
                    if item.get("question") or item.get("label")
                ]
                if lines:
                    messages.append({
                        "id": f"message-suggestions-{run.id}",
                        "role": "assistant",
                        "content": "你可以继续问：\n" + "\n".join(lines),
                        "createdAt": completed_ms,
                    })

        elif run.status == "waiting_approval":
            messages.append({
                "id": f"message-assistant-{run.id}",
                "role": "assistant",
                "content": "该操作存在风险，需要你确认后才会继续执行。请在下方审批卡片中选择。",
                "createdAt": completed_ms,
            })
        elif run.status == "failed":
            messages.append({
                "id": f"message-assistant-{run.id}",
                "role": "assistant",
                "content": f"执行未完成：{run.error or 'Agent 已停止。'}",
                "createdAt": completed_ms,
            })
        elif run.status == "cancelled":
            messages.append({
                "id": f"message-assistant-{run.id}",
                "role": "assistant",
                "content": "已取消。",
                "createdAt": completed_ms,
            })
        else:
            messages.append({
                "id": f"message-assistant-{run.id}",
                "role": "assistant",
                "content": "思考中…",
                "createdAt": completed_ms,
            })

    return messages


_HIDDEN_ARTIFACT_TYPES: frozenset[str] = frozenset({"agent_plan", "query_plan", "safety"})

_TYPE_ORDER: dict[str, int] = {
    "table": 0, "chart": 1, "sql": 2, "sql_suggestion": 3,
    "insight": 4, "recommendation": 5, "error": 6,
}


def _build_view_artifacts(db: Session, session_id: str) -> list[dict[str, Any]]:
    """Deduplicate, filter, and convert DB artifacts into frontend-visible cards."""
    records = (
        db.query(AgentArtifactRecord)
        .filter(AgentArtifactRecord.session_id == session_id)
        .order_by(AgentArtifactRecord.sequence)
        .all()
    )

    raw: list[dict[str, Any]] = []
    for r in records:
        payload = _parse_json(r.payload_json) or {}
        presentation = _parse_json(r.presentation_json) or {}
        refs = _parse_json(r.refs_json) or {}
        depends_on = (_parse_json(r.depends_on_json) or {}).get("depends_on", [])
        raw.append({
            "id": r.id, "type": r.type, "title": r.title,
            "payload": payload, "presentation": presentation,
            "refs": refs, "depends_on": depends_on, "semantic_id": r.semantic_id,
        })

    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for art in raw:
        key = art["semantic_id"] or art["id"]
        if key in seen_keys:
            deduped = [a for a in deduped if (a["semantic_id"] or a["id"]) != key]
        deduped.append(art)
        seen_keys.add(key)

    visible = [
        art for art in deduped
        if art["type"] not in _HIDDEN_ARTIFACT_TYPES
        and art.get("presentation", {}).get("mode") != "hidden"
    ]

    cards: list[dict[str, Any]] = []
    for art in visible:
        card = _artifact_to_card(art, visible)
        if card:
            cards.append(card)

    cards.sort(key=lambda a: _TYPE_ORDER.get(a["type"], 9))
    return cards


def _artifact_to_card(art: dict[str, Any], all_visible: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Convert a single deserialized artifact to a frontend card."""
    atype = art["type"]
    payload = art["payload"]

    if atype in ("sql", "sql_suggestion"):
        sql = payload.get("sql") or payload.get("proposed_sql") or payload.get("safe_sql")
        if sql:
            card = {
                "id": art["id"], "type": "sql",
                "title": "SQL 修改建议" if atype == "sql_suggestion" else "执行的 SQL",
                "sql": sql,
            }
            if isinstance(payload.get("reason"), str):
                card["description"] = payload["reason"]
            return card

    if atype == "table":
        columns = payload.get("columns") or []
        raw_rows = payload.get("rows") or []
        if columns:
            rows = []
            for row in raw_rows:
                if isinstance(row, dict):
                    rows.append([_format_cell(row.get(col)) for col in columns])
            row_count = payload.get("rowCount")
            if not isinstance(row_count, int):
                row_count = len(rows)
            return {
                "id": art["id"], "type": "table", "title": "查询结果",
                "description": f"{row_count} 行 · {len(columns)} 列",
                "columns": [str(c) for c in columns],
                "rows": rows,
            }
        return None

    if atype == "chart":
        chart_type = payload.get("type")
        x = payload.get("x")
        y = payload.get("y")
        if chart_type in ("line", "bar") and x and y:
            table_art = next((a for a in all_visible if a["type"] == "table"), None)
            series = []
            if table_art:
                table_rows = table_art["payload"].get("rows") or []
                for row in table_rows:
                    if isinstance(row, dict):
                        val = row.get(y)
                        try:
                            val_num = float(val)
                            import math
                            if not math.isfinite(val_num):
                                continue
                            series.append({
                                "label": str(row.get(x) if row.get(x) is not None else "NULL"),
                                "value": val_num,
                            })
                        except (ValueError, TypeError):
                            continue
                        if len(series) >= 60:
                            break
            if series:
                card = {
                    "id": art["id"], "type": "chart",
                    "title": f"{y} 按 {x} 分布",
                    "chartType": chart_type,
                    "series": series,
                }
                if isinstance(payload.get("reason"), str):
                    card["description"] = payload["reason"]
                return card
        return None

    if atype == "insight":
        if art["semantic_id"] != "semantic_resolution":
            lines = []
            if isinstance(payload.get("row_count"), int):
                lines.append(f"共 {payload['row_count']} 行结果。")
            for key in ("notable_facts", "detected_patterns", "anomalies", "limitations"):
                vals = payload.get(key)
                if isinstance(vals, list):
                    for val in vals:
                        if isinstance(val, str) and val.strip():
                            lines.append(f"- {val.strip()}")
            if lines:
                return {"id": art["id"], "type": "markdown", "title": "数据洞察", "content": "\n".join(lines)}
        return None

    if atype == "recommendation":
        lines = []
        if isinstance(payload.get("recommendations"), list):
            for item in payload["recommendations"]:
                if isinstance(item, str) and item.strip():
                    lines.append(f"- {item.strip()}")
        if isinstance(payload.get("followUpQuestions"), list):
            for item in payload["followUpQuestions"]:
                if isinstance(item, str) and item.strip():
                    lines.append(f"- {item.strip()}")
        if lines:
            return {"id": art["id"], "type": "markdown", "title": "建议的下一步", "content": "\n".join(lines)}
        return None

    if atype == "error":
        message = payload.get("message") or payload.get("error") or payload.get("detail") or payload.get("reason")
        if not message:
            message = json.dumps(payload, ensure_ascii=False)
        return {
            "id": art["id"], "type": "markdown",
            "title": art.get("title") or "执行中遇到的问题",
            "content": str(message),
        }

    return None


def _persist_conversation_record(
    db: Session,
    session: AgentSession,
    session_id: str,
    title: str,
    messages: list[dict[str, Any]],
    view_artifacts: list[dict[str, Any]],
) -> None:
    """Write or update the ChatConversation row."""
    row = db.query(ChatConversation).filter(ChatConversation.id == session_id).first()

    context_tables: list[str] = []
    if row is not None and row.context_tables_json:
        try:
            context_tables = json.loads(row.context_tables_json)
        except Exception:
            pass

    if row is None:
        row = ChatConversation(id=session_id)
        db.add(row)

    row.title = title
    row.created_at = _to_timestamp_ms(session.created_at)
    row.updated_at = _to_timestamp_ms(session.updated_at)
    row.context_tables_json = json.dumps(context_tables)
    row.messages_json = json.dumps(messages, ensure_ascii=False)
    row.artifacts_json = json.dumps(view_artifacts, ensure_ascii=False)
    db.flush()
