# Conversation Interaction Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DBFox's tab-local chat implementation with a structured Conversation / Message / Run / Artifact path and a ChatGPT-style conversation workspace.

**Architecture:** Reuse `AgentSession` as the conversation table, add `AgentMessage`, extend `AgentRun` and `AgentArtifactRecord`, and make conversation APIs return structured messages, runs, artifacts, approvals, and trace data. The frontend opens conversation tabs, consumes structured APIs and SSE events by stable ids, and renders a focused message stream with collapsed trace and expandable evidence.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, React 19, Zustand, TypeScript, Vitest, ECharts, lucide-react.

---

## Scope Check

The spec spans backend persistence, API contracts, frontend state, and UI. Keep it as one cohesive plan because each layer depends on the same id contract: `conversation_id`, `user_message_id`, `assistant_message_id`, `run_id`, and `artifact_id`. Each task below produces a working checkpoint with focused tests and a commit.

Before starting implementation, create or switch to a feature branch such as `codex/conversation-interaction-redesign`. The current working tree has unrelated local changes; do not revert them.

## File Structure

Backend model and migrations:

- Modify: `engine/models.py`
  - Add `AgentMessage`.
  - Extend `AgentSession`, `AgentRun`, and `AgentArtifactRecord`.
  - Remove `ChatConversation`.
- Create: `engine/migrations/versions/f6a7b8c9d0e1_conversation_interaction_redesign.py`
  - Add `agent_messages`.
  - Add conversation and message linkage columns.
  - Drop `chat_conversations`.
- Modify: `engine/agent_core/types.py`
  - Add conversation/message ids to `AgentRunRequest`, `AgentRunResponse`, and `AgentRuntimeEvent`.
- Modify: `engine/agent_core/persistence_sink.py`
  - Persist messages and artifact message linkage.
- Modify: `engine/agent_core/persistence/__init__.py`
  - Export new helpers.
- Create: `engine/agent_core/persistence/conversation_records.py`
  - Structured conversation query and serialization helpers.
- Delete or stop importing: `engine/agent_core/persistence/conversations.py`
  - Old JSON snapshot sync path.
- Modify: `engine/api/conversations.py`
  - Replace old JSON record API with structured endpoints.
- Modify: `engine/api/agent.py`
  - Preserve legacy `/agent/run/stream` during transition, add conversation id fields to stream events where available.

Backend tests:

- Replace: `engine/tests/test_conversations.py`
- Replace: `engine/tests/test_conversation_rehydration.py`
- Add: `engine/tests/test_conversation_runtime_contract.py`
- Update: `engine/tests/test_persistence_sink.py`

Frontend API and state:

- Replace: `desktop/src/types/conversation.ts`
- Replace: `desktop/src/features/conversation/conversationRepository.ts`
- Create: `desktop/src/stores/conversationStore.ts`
- Create: `desktop/src/stores/__tests__/conversationStore.test.ts`
- Modify: `desktop/src/lib/api/types.ts`
- Modify: `desktop/src/lib/api/agent.ts`
- Modify: `desktop/src/lib/api/index.ts`
- Modify: `desktop/src/stores/workspaceStore.ts`
- Modify: `desktop/src/stores/agentStore.ts`
- Modify: `desktop/src/types/workspace.ts`

Frontend UI:

- Create: `desktop/src/features/conversation/workspace/ConversationWorkspace.tsx`
- Create: `desktop/src/features/conversation/workspace/ConversationHeader.tsx`
- Create: `desktop/src/features/conversation/workspace/MessageList.tsx`
- Create: `desktop/src/features/conversation/workspace/MessageBubble.tsx`
- Create: `desktop/src/features/conversation/workspace/RunTracePanel.tsx`
- Create: `desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx`
- Create: `desktop/src/features/conversation/workspace/Composer.tsx`
- Create: `desktop/src/features/conversation/workspace/conversationWorkspace.css`
- Modify: `desktop/src/features/conversation/ConversationHistoryPanel.tsx`
- Modify: `desktop/src/features/appShell/WorkspaceRouter.tsx`
- Modify: `desktop/src/features/workspace/QueryResultWorkspace.tsx`
- Remove after replacement: `desktop/src/features/agentTask/AgentTaskView.tsx`, `AgentTurnItem.tsx`, `FinalAnswerCard.tsx`, and `AgentTaskView.css` if no callers remain.

Frontend tests:

- Create: `desktop/src/features/conversation/workspace/__tests__/conversationViewModel.test.ts`
- Create: `desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx`
- Update: `desktop/src/features/conversation/__tests__/conversationRepository.test.ts`
- Update or delete old tests that assert JSON snapshot behavior.

## Task 1: Backend Schema Contract

**Files:**

- Modify: `engine/models.py`
- Create: `engine/migrations/versions/f6a7b8c9d0e1_conversation_interaction_redesign.py`
- Test: `engine/tests/test_conversation_runtime_contract.py`

- [ ] **Step 1: Write the failing model test**

Create `engine/tests/test_conversation_runtime_contract.py` with this first test:

```python
from __future__ import annotations

from datetime import UTC, datetime

from engine.models import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
)


def test_conversation_message_run_artifact_links(db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-contract",
        datasource_id="ds-1",
        title="Revenue chat",
        context_tables_json='["orders"]',
        created_at=now,
        updated_at=now,
    )
    user = AgentMessage(
        id="msg-user-1",
        session_id=session.id,
        role="user",
        content="Show revenue",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    assistant = AgentMessage(
        id="msg-assistant-1",
        session_id=session.id,
        role="assistant",
        content="",
        status="streaming",
        sequence=2,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-1",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=user.id,
        assistant_message_id=assistant.id,
        question="Show revenue",
        status="running",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id="artifact-sql-1",
        run_id=run.id,
        session_id=session.id,
        message_id=assistant.id,
        semantic_id="sql-1",
        type="sql",
        title="SQL 1",
        payload_json='{"sql": "select 1"}',
        presentation_json='{"mode": "visible"}',
        depends_on_json="[]",
        status="completed",
        sequence=1,
        created_at=now,
    )

    db_session.add_all([session, user, assistant, run, artifact])
    db_session.commit()

    saved = db_session.get(AgentSession, session.id)
    assert saved is not None
    assert [message.id for message in saved.messages] == ["msg-user-1", "msg-assistant-1"]
    assert saved.runs[0].user_message_id == "msg-user-1"
    assert saved.runs[0].assistant_message_id == "msg-assistant-1"
    assert saved.runs[0].artifacts[0].message_id == "msg-assistant-1"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest engine/tests/test_conversation_runtime_contract.py::test_conversation_message_run_artifact_links -q
```

Expected: FAIL because `AgentMessage` and the new columns do not exist.

- [ ] **Step 3: Update `engine/models.py`**

Add imports if missing:

```python
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
```

Update `AgentSession`:

```python
class AgentSession(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_datasource", "datasource_id"),
        Index("ix_agent_sessions_created", "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    datasource_id = Column(String, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=True)
    context_tables_json = Column(Text, nullable=False, default="[]")
    archived_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    messages = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.sequence",
    )
    runs = relationship("AgentRun", back_populates="session", cascade="all, delete-orphan")
```

Add `AgentMessage` before `AgentRun`:

```python
class AgentMessage(Base):  # type: ignore[misc,valid-type]
    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_session", "session_id"),
        Index("ix_agent_messages_role", "role"),
        UniqueConstraint("session_id", "sequence", name="uq_agent_messages_session_sequence"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="created")
    sequence = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    session = relationship("AgentSession", back_populates="messages")
```

Extend `AgentRun`:

```python
    user_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    assistant_message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
```

Extend `AgentArtifactRecord`:

```python
    message_id = Column(String, ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, nullable=False, default="completed")
```

Remove the `ChatConversation` class from `engine/models.py`.

- [ ] **Step 4: Create the Alembic migration**

Create `engine/migrations/versions/f6a7b8c9d0e1_conversation_interaction_redesign.py`:

```python
"""conversation interaction redesign

Revision ID: f6a7b8c9d0e1
Revises: f1a2b3c4d5e6
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_sessions", sa.Column("context_tables_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("agent_sessions", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("agent_sessions", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="created"),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_messages_session_sequence"),
    )
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id"])
    op.create_index("ix_agent_messages_role", "agent_messages", ["role"])

    op.add_column("agent_runs", sa.Column("user_message_id", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("assistant_message_id", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("error_code", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_agent_runs_user_message", "agent_runs", "agent_messages", ["user_message_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_agent_runs_assistant_message", "agent_runs", "agent_messages", ["assistant_message_id"], ["id"], ondelete="SET NULL")

    op.add_column("agent_artifacts", sa.Column("message_id", sa.String(), nullable=True))
    op.add_column("agent_artifacts", sa.Column("status", sa.String(), nullable=False, server_default="completed"))
    op.create_foreign_key("fk_agent_artifacts_message", "agent_artifacts", "agent_messages", ["message_id"], ["id"], ondelete="SET NULL")

    op.drop_table("chat_conversations")


def downgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("context_tables_json", sa.Text(), nullable=False),
        sa.Column("messages_json", sa.Text(), nullable=False),
        sa.Column("artifacts_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_conversations_updated_at", "chat_conversations", ["updated_at"])

    op.drop_constraint("fk_agent_artifacts_message", "agent_artifacts", type_="foreignkey")
    op.drop_column("agent_artifacts", "status")
    op.drop_column("agent_artifacts", "message_id")

    op.drop_constraint("fk_agent_runs_assistant_message", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_user_message", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "started_at")
    op.drop_column("agent_runs", "error_message")
    op.drop_column("agent_runs", "error_code")
    op.drop_column("agent_runs", "assistant_message_id")
    op.drop_column("agent_runs", "user_message_id")

    op.drop_index("ix_agent_messages_role", table_name="agent_messages")
    op.drop_index("ix_agent_messages_session", table_name="agent_messages")
    op.drop_table("agent_messages")

    op.drop_column("agent_sessions", "deleted_at")
    op.drop_column("agent_sessions", "archived_at")
    op.drop_column("agent_sessions", "context_tables_json")
```

- [ ] **Step 5: Run the model test again**

Run:

```bash
pytest engine/tests/test_conversation_runtime_contract.py::test_conversation_message_run_artifact_links -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/models.py engine/migrations/versions/f6a7b8c9d0e1_conversation_interaction_redesign.py engine/tests/test_conversation_runtime_contract.py
git commit -m "feat: add structured conversation schema"
```

## Task 2: Structured Conversation Query Helpers

**Files:**

- Create: `engine/agent_core/persistence/conversation_records.py`
- Modify: `engine/agent_core/persistence/__init__.py`
- Replace tests in: `engine/tests/test_conversations.py`

- [ ] **Step 1: Replace the old conversations API tests with structured expectations**

In `engine/tests/test_conversations.py`, replace imports of `ChatConversation` with:

```python
from datetime import UTC, datetime

from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentSession
```

Add this test:

```python
def test_list_conversations_uses_agent_sessions(client, db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-list-1",
        datasource_id="ds-1",
        title="Orders analysis",
        context_tables_json='["orders"]',
        created_at=now,
        updated_at=now,
    )
    msg = AgentMessage(
        id="msg-list-user",
        session_id=session.id,
        role="user",
        content="List orders",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-list-1",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=msg.id,
        question="List orders",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([session, msg, run])
    db_session.commit()

    resp = client.get("/api/v1/conversations", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data == [
        {
            "id": "conv-list-1",
            "title": "Orders analysis",
            "datasource_id": "ds-1",
            "updated_at": data[0]["updated_at"],
            "last_message": "List orders",
            "message_count": 1,
            "run_status": "completed",
            "artifact_count": 0,
        }
    ]
```

Add this detail test:

```python
def test_get_conversation_detail_returns_messages_runs_and_artifacts(client, db_session):
    now = datetime.now(UTC)
    session = AgentSession(
        id="conv-detail-1",
        datasource_id="ds-1",
        title="Revenue",
        context_tables_json='["orders"]',
        created_at=now,
        updated_at=now,
    )
    user = AgentMessage(
        id="msg-detail-user",
        session_id=session.id,
        role="user",
        content="Revenue?",
        status="completed",
        sequence=1,
        created_at=now,
        updated_at=now,
    )
    assistant = AgentMessage(
        id="msg-detail-assistant",
        session_id=session.id,
        role="assistant",
        content="Revenue is 100.",
        status="completed",
        sequence=2,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id="run-detail-1",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=user.id,
        assistant_message_id=assistant.id,
        question="Revenue?",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    artifact = AgentArtifactRecord(
        id="artifact-detail-sql",
        run_id=run.id,
        session_id=session.id,
        message_id=assistant.id,
        semantic_id="sql-1",
        type="sql",
        title="SQL 1",
        payload_json='{"sql": "select 100 as revenue"}',
        presentation_json='{"mode": "visible"}',
        depends_on_json="[]",
        status="completed",
        sequence=1,
        created_at=now,
    )
    db_session.add_all([session, user, assistant, run, artifact])
    db_session.commit()

    resp = client.get("/api/v1/conversations/conv-detail-1", headers=_hdrs())
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "conv-detail-1"
    assert [m["id"] for m in data["messages"]] == ["msg-detail-user", "msg-detail-assistant"]
    assert data["runs"][0]["id"] == "run-detail-1"
    assert data["artifacts"][0]["message_id"] == "msg-detail-assistant"
    assert data["artifacts"][0]["payload"]["sql"] == "select 100 as revenue"
```

- [ ] **Step 2: Run the failing API tests**

Run:

```bash
pytest engine/tests/test_conversations.py -q
```

Expected: FAIL because `engine/api/conversations.py` still returns old JSON records.

- [ ] **Step 3: Add structured query helpers**

Create `engine/agent_core/persistence/conversation_records.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentSession


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _json(text: str | None, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        return fallback


def serialize_message(row: AgentMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.session_id,
        "role": row.role,
        "content": row.content,
        "status": row.status,
        "sequence": row.sequence,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def serialize_run(row: AgentRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.session_id,
        "parent_run_id": row.parent_run_id,
        "user_message_id": row.user_message_id,
        "assistant_message_id": row.assistant_message_id,
        "datasource_id": row.datasource_id,
        "question": row.question,
        "status": row.status,
        "error_code": row.error_code,
        "error_message": row.error_message or row.error,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
        "started_at": _dt(row.started_at),
        "completed_at": _dt(row.completed_at),
    }


def serialize_artifact(row: AgentArtifactRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.session_id,
        "run_id": row.run_id,
        "message_id": row.message_id,
        "semantic_id": row.semantic_id,
        "type": row.type,
        "title": row.title,
        "status": row.status,
        "sequence": row.sequence,
        "payload": _json(row.payload_json, {}),
        "presentation": _json(row.presentation_json, {}),
        "depends_on": _json(row.depends_on_json, []),
        "refs": _json(row.refs_json, {}),
        "created_at": _dt(row.created_at),
    }


def list_conversation_summaries(db: Session) -> list[dict[str, Any]]:
    sessions = (
        db.query(AgentSession)
        .options(selectinload(AgentSession.messages), selectinload(AgentSession.runs))
        .filter(AgentSession.deleted_at == None)
        .order_by(AgentSession.updated_at.desc())
        .all()
    )
    summaries: list[dict[str, Any]] = []
    for session in sessions:
        messages = sorted(session.messages, key=lambda item: item.sequence)
        runs = sorted(session.runs, key=lambda item: item.created_at)
        last_message = messages[-1].content if messages else ""
        summaries.append({
            "id": session.id,
            "title": session.title or (messages[0].content[:80] if messages else "New conversation"),
            "datasource_id": session.datasource_id,
            "updated_at": _dt(session.updated_at),
            "last_message": last_message,
            "message_count": len(messages),
            "run_status": runs[-1].status if runs else None,
            "artifact_count": sum(len(run.artifacts) for run in runs),
        })
    return summaries


def get_conversation_detail(db: Session, conversation_id: str) -> dict[str, Any] | None:
    session = (
        db.query(AgentSession)
        .options(
            selectinload(AgentSession.messages),
            selectinload(AgentSession.runs).selectinload(AgentRun.artifacts),
            selectinload(AgentSession.runs).selectinload(AgentRun.approvals),
            selectinload(AgentSession.runs).selectinload(AgentRun.trace_events),
        )
        .filter(AgentSession.id == conversation_id, AgentSession.deleted_at == None)
        .first()
    )
    if session is None:
        return None
    runs = sorted(session.runs, key=lambda item: item.created_at)
    artifacts = sorted(
        [artifact for run in runs for artifact in run.artifacts],
        key=lambda item: (item.sequence or 0, item.created_at),
    )
    return {
        "id": session.id,
        "title": session.title or "",
        "datasource_id": session.datasource_id,
        "context_tables": _json(session.context_tables_json, []),
        "created_at": _dt(session.created_at),
        "updated_at": _dt(session.updated_at),
        "messages": [serialize_message(message) for message in sorted(session.messages, key=lambda item: item.sequence)],
        "runs": [serialize_run(run) for run in runs],
        "artifacts": [serialize_artifact(artifact) for artifact in artifacts],
        "approvals": [],
    }
```

- [ ] **Step 4: Export helpers**

In `engine/agent_core/persistence/__init__.py`, export:

```python
from .conversation_records import (
    get_conversation_detail,
    list_conversation_summaries,
    serialize_artifact,
    serialize_message,
    serialize_run,
)
```

- [ ] **Step 5: Commit**

Do not commit until Task 3 replaces the API and the tests pass, because the helpers are not externally used yet.

## Task 3: Structured Conversation API

**Files:**

- Modify: `engine/api/conversations.py`
- Modify: `engine/api/__init__.py` only if router imports change.
- Test: `engine/tests/test_conversations.py`

- [ ] **Step 1: Replace the old API module**

Replace `engine/api/conversations.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.agent_core.persistence import get_conversation_detail, list_conversation_summaries
from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import AgentSession


router = APIRouter()


class ConversationCreateRequest(BaseModel):
    datasource_id: str
    title: str | None = None
    context_tables: list[str] = []


class ConversationPatchRequest(BaseModel):
    title: str | None = None
    context_tables: list[str] | None = None
    archived: bool | None = None


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return list_conversation_summaries(db)


@router.post("/conversations")
def create_conversation(payload: ConversationCreateRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    import json

    now = datetime.now(UTC)
    row = AgentSession(
        datasource_id=payload.datasource_id,
        title=payload.title or "New conversation",
        context_tables_json=json.dumps(payload.context_tables, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    detail = get_conversation_detail(db, row.id)
    assert detail is not None
    return detail


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    detail = get_conversation_detail(db, conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."})
    return detail


@router.patch("/conversations/{conversation_id}")
def patch_conversation(
    conversation_id: str,
    payload: ConversationPatchRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    import json

    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is None:
        raise DBFoxError("Conversation not found.", code="CONVERSATION_NOT_FOUND")
    if payload.title is not None:
        row.title = payload.title
    if payload.context_tables is not None:
        row.context_tables_json = json.dumps(payload.context_tables, ensure_ascii=False)
    if payload.archived is not None:
        row.archived_at = datetime.now(UTC) if payload.archived else None
    row.updated_at = datetime.now(UTC)
    db.commit()
    detail = get_conversation_detail(db, conversation_id)
    assert detail is not None
    return detail


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return {"status": "ok"}
```

Remove `heal_missing_conversations` because old JSON self-healing is out of scope and old history is intentionally discarded.

- [ ] **Step 2: Run API tests**

Run:

```bash
pytest engine/tests/test_conversations.py -q
```

Expected: PASS.

- [ ] **Step 3: Remove old rehydration test assertions**

Replace `engine/tests/test_conversation_rehydration.py` with a compact file that imports no `ChatConversation`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from engine.agent_core.persistence import get_conversation_detail
from engine.models import AgentMessage, AgentRun, AgentSession


def test_conversation_detail_rehydrates_from_structured_tables(db_session):
    now = datetime.now(UTC)
    session = AgentSession(id="conv-rehydrate", datasource_id="ds-1", title="Structured", created_at=now, updated_at=now)
    user = AgentMessage(id="msg-rehydrate-user", session_id=session.id, role="user", content="Hello", status="completed", sequence=1, created_at=now, updated_at=now)
    assistant = AgentMessage(id="msg-rehydrate-assistant", session_id=session.id, role="assistant", content="Hi", status="completed", sequence=2, created_at=now, updated_at=now)
    run = AgentRun(
        id="run-rehydrate",
        session_id=session.id,
        datasource_id="ds-1",
        user_message_id=user.id,
        assistant_message_id=assistant.id,
        question="Hello",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([session, user, assistant, run])
    db_session.commit()

    detail = get_conversation_detail(db_session, session.id)
    assert detail is not None
    assert [message["content"] for message in detail["messages"]] == ["Hello", "Hi"]
    assert detail["runs"][0]["assistant_message_id"] == "msg-rehydrate-assistant"
```

- [ ] **Step 4: Run all conversation backend tests**

Run:

```bash
pytest engine/tests/test_conversations.py engine/tests/test_conversation_rehydration.py engine/tests/test_conversation_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/api/conversations.py engine/agent_core/persistence/__init__.py engine/agent_core/persistence/conversation_records.py engine/tests/test_conversations.py engine/tests/test_conversation_rehydration.py
git commit -m "feat: expose structured conversation api"
```

## Task 4: Runtime Message and Artifact Linkage

**Files:**

- Modify: `engine/agent_core/types.py`
- Modify: `engine/agent/app/service.py`
- Modify: `engine/agent_core/persistence_sink.py`
- Modify: `engine/agent_core/persistence/runs.py` if start/complete/fail helpers live there.
- Test: `engine/tests/test_persistence_sink.py`
- Test: `engine/tests/test_conversation_runtime_contract.py`

- [ ] **Step 1: Write failing persistence tests**

Append to `engine/tests/test_conversation_runtime_contract.py`:

```python
from engine.agent_core.types import AgentRunRequest, AgentRunResponse
from engine.agent_core.persistence import get_conversation_detail
from engine.agent_core.persistence_sink import create_persistence_sink


def test_persistence_sink_creates_user_and_assistant_messages(db_session):
    sink = create_persistence_sink(db_session)
    req = AgentRunRequest(datasource_id="ds-1", question="Count users", session_id="conv-sink")

    sink.start_run(req, run_id="run-sink", session_id="conv-sink")
    db_session.commit()

    detail = get_conversation_detail(db_session, "conv-sink")
    assert detail is not None
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "Count users"
    assert detail["messages"][1]["status"] == "streaming"
    assert detail["runs"][0]["user_message_id"] == detail["messages"][0]["id"]
    assert detail["runs"][0]["assistant_message_id"] == detail["messages"][1]["id"]


def test_persistence_sink_completes_assistant_message(db_session):
    sink = create_persistence_sink(db_session)
    req = AgentRunRequest(datasource_id="ds-1", question="Count users", session_id="conv-sink-complete")
    sink.start_run(req, run_id="run-sink-complete", session_id="conv-sink-complete")
    response = AgentRunResponse(
        run_id="run-sink-complete",
        session_id="conv-sink-complete",
        success=True,
        status="completed",
        question="Count users",
        explanation="There are 10 users.",
        artifacts=[],
    )

    sink.complete_run(response)
    db_session.commit()

    detail = get_conversation_detail(db_session, "conv-sink-complete")
    assert detail is not None
    assistant = detail["messages"][1]
    assert assistant["role"] == "assistant"
    assert assistant["status"] == "completed"
    assert "There are 10 users." in assistant["content"]
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
pytest engine/tests/test_conversation_runtime_contract.py::test_persistence_sink_creates_user_and_assistant_messages engine/tests/test_conversation_runtime_contract.py::test_persistence_sink_completes_assistant_message -q
```

Expected: FAIL because persistence still syncs old `ChatConversation` records or lacks message linking.

- [ ] **Step 3: Extend Pydantic contracts**

In `engine/agent_core/types.py`, extend `AgentRunRequest`:

```python
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
```

Extend `AgentRunResponse`:

```python
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
```

Extend `AgentRuntimeEvent`:

```python
    conversation_id: str | None = None
    message_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
```

- [ ] **Step 4: Implement message creation in the persistence sink**

In `engine/agent_core/persistence_sink.py`, add helper logic equivalent to:

```python
from datetime import UTC, datetime
import uuid

from engine.models import AgentMessage, AgentRun, AgentSession


def _next_message_sequence(db: Session, session_id: str) -> int:
    value = (
        db.query(AgentMessage.sequence)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.sequence.desc())
        .first()
    )
    return int(value[0]) + 1 if value else 1


def _answer_text(response: AgentRunResponse) -> str:
    if response.answer and response.answer.answer.strip():
        return response.answer.answer.strip()
    if response.explanation and response.explanation.strip():
        return response.explanation.strip()
    if response.error:
        return f"执行未完成：{response.error}"
    return "已完成。"
```

In the sink start method, create or update `AgentSession`, append `AgentMessage` rows, and set run links:

```python
now = datetime.now(UTC)
session = db.get(AgentSession, session_id)
if session is None:
    session = AgentSession(
        id=session_id,
        datasource_id=req.datasource_id,
        title=(req.question[:80] if req.question else "New conversation"),
        context_tables_json="[]",
        created_at=now,
        updated_at=now,
    )
    db.add(session)

user_message_id = req.user_message_id or f"msg-user-{uuid.uuid4()}"
assistant_message_id = req.assistant_message_id or f"msg-assistant-{uuid.uuid4()}"
sequence = _next_message_sequence(db, session_id)
db.add(AgentMessage(id=user_message_id, session_id=session_id, role="user", content=req.question, status="completed", sequence=sequence, created_at=now, updated_at=now))
db.add(AgentMessage(id=assistant_message_id, session_id=session_id, role="assistant", content="", status="streaming", sequence=sequence + 1, created_at=now, updated_at=now))

run = AgentRun(
    id=run_id,
    session_id=session_id,
    datasource_id=req.datasource_id,
    user_message_id=user_message_id,
    assistant_message_id=assistant_message_id,
    question=req.question,
    status="running",
    started_at=now,
    created_at=now,
    updated_at=now,
)
db.add(run)
```

Update complete/fail/cancel methods to update the linked assistant message by id:

```python
assistant = db.get(AgentMessage, run.assistant_message_id) if run.assistant_message_id else None
if assistant is not None:
    assistant.content = _answer_text(response)
    assistant.status = "completed" if response.success else "failed"
    assistant.updated_at = datetime.now(UTC)
```

When recording an artifact, set `message_id` from the run:

```python
run = db.get(AgentRun, run_id)
record = AgentArtifactRecord(
    id=artifact.id,
    run_id=run_id,
    session_id=session_id,
    message_id=run.assistant_message_id if run else None,
    semantic_id=artifact.semantic_id,
    type=artifact.type,
    title=artifact.title,
    payload_json=json.dumps(artifact.payload, ensure_ascii=False),
    presentation_json=artifact.presentation.model_dump_json(),
    refs_json=json.dumps(artifact.refs, ensure_ascii=False),
    depends_on_json=json.dumps(artifact.depends_on, ensure_ascii=False),
    status="completed",
    sequence=index,
)
```

- [ ] **Step 5: Remove old JSON sync calls**

Delete imports and calls to `sync_chat_conversation_from_session`. The new persistence path writes structured rows directly.

- [ ] **Step 6: Run persistence tests**

Run:

```bash
pytest engine/tests/test_conversation_runtime_contract.py engine/tests/test_persistence_sink.py -q
```

Expected: PASS after updating any `test_persistence_sink.py` assertions to look at `AgentMessage` instead of `ChatConversation`.

- [ ] **Step 7: Commit**

```bash
git add engine/agent_core/types.py engine/agent/app/service.py engine/agent_core/persistence_sink.py engine/agent_core/persistence/runs.py engine/tests/test_conversation_runtime_contract.py engine/tests/test_persistence_sink.py
git commit -m "feat: persist conversation messages from agent runs"
```

## Task 5: Conversation Message Streaming Endpoint

**Files:**

- Modify: `engine/api/conversations.py`
- Modify: `engine/api/agent.py`
- Test: `engine/tests/test_conversations.py`
- Test: `engine/tests/test_agent_api.py`

- [ ] **Step 1: Add API tests for message submission contract**

Append to `engine/tests/test_conversations.py`:

```python
def test_create_conversation_endpoint(client):
    resp = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "New analysis", "context_tables": ["orders"]},
        headers=_hdrs(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New analysis"
    assert data["datasource_id"] == "ds-1"
    assert data["context_tables"] == ["orders"]
    assert data["messages"] == []
```

Add a non-streaming preflight endpoint test:

```python
def test_prepare_conversation_message_creates_message_ids(client, db_session):
    create = client.post(
        "/api/v1/conversations",
        json={"datasource_id": "ds-1", "title": "Message test", "context_tables": []},
        headers=_hdrs(),
    )
    conv_id = create.json()["id"]

    resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Count users", "api_key": "test-key", "model_name": "test-model"},
        headers=_hdrs(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv_id
    assert data["user_message_id"].startswith("msg-user-")
    assert data["assistant_message_id"].startswith("msg-assistant-")
    assert data["run_id"] is None
```

- [ ] **Step 2: Implement request and response models**

In `engine/api/conversations.py`, add:

```python
class ConversationMessageRequest(BaseModel):
    content: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    execute: bool = True


class ConversationMessageStartResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    run_id: str | None = None
```

- [ ] **Step 3: Add preflight message endpoint**

Add:

```python
@router.post("/conversations/{conversation_id}/messages", response_model=ConversationMessageStartResponse)
def prepare_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    db: Session = Depends(get_db),
) -> ConversationMessageStartResponse:
    import uuid

    row = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."})
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail={"code": "EMPTY_MESSAGE", "message": "Message content is required."})
    return ConversationMessageStartResponse(
        conversation_id=conversation_id,
        user_message_id=f"msg-user-{uuid.uuid4()}",
        assistant_message_id=f"msg-assistant-{uuid.uuid4()}",
        run_id=None,
    )
```

This endpoint only allocates ids. The streaming endpoint will pass them into the runtime so persistence creates rows exactly once.

- [ ] **Step 4: Add streaming endpoint**

Add:

```python
@router.post("/conversations/{conversation_id}/messages/stream")
def stream_conversation_message(
    conversation_id: str,
    payload: ConversationMessageRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    import uuid

    session = db.query(AgentSession).filter(AgentSession.id == conversation_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found."})
    user_message_id = f"msg-user-{uuid.uuid4()}"
    assistant_message_id = f"msg-assistant-{uuid.uuid4()}"
    req = AgentRunRequest(
        datasource_id=session.datasource_id,
        question=payload.content,
        session_id=conversation_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        api_key=payload.api_key,
        api_base=payload.api_base,
        model_name=payload.model_name,
        execute=payload.execute,
    )

    def stream_events() -> object:
        try:
            for event in DBFoxAgentRuntime(db).run_iter(req):
                event.conversation_id = conversation_id
                event.user_message_id = user_message_id
                event.assistant_message_id = assistant_message_id
                event.message_id = assistant_message_id
                yield _format_sse_event(event)
        except Exception as exc:
            db.rollback()
            yield sse_failed_event("conversation_stream_error", "", f"Agent runtime failed: {exc}", "AGENT_RUNTIME_ERROR")

    return StreamingResponse(stream_events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

Import `StreamingResponse`, `AgentRunRequest`, `DBFoxAgentRuntime`, `_format_sse_event`, and `sse_failed_event` as needed without creating circular imports. If importing helpers from `engine/api/agent.py` creates a cycle, move `_format_sse_event` and `sse_failed_event` into `engine/api/sse.py`.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest engine/tests/test_conversations.py engine/tests/test_agent_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/api/conversations.py engine/api/agent.py engine/api/sse.py engine/tests/test_conversations.py engine/tests/test_agent_api.py
git commit -m "feat: stream agent runs from conversation messages"
```

## Task 6: Frontend Conversation Types and API Client

**Files:**

- Replace: `desktop/src/types/conversation.ts`
- Replace: `desktop/src/features/conversation/conversationRepository.ts`
- Modify: `desktop/src/lib/api/types.ts`
- Modify: `desktop/src/lib/api/agent.ts`
- Test: `desktop/src/features/conversation/__tests__/conversationRepository.test.ts`

- [ ] **Step 1: Write frontend API tests**

Replace `desktop/src/features/conversation/__tests__/conversationRepository.test.ts` with tests for structured API mapping:

```typescript
import { describe, expect, it, vi, beforeEach } from "vitest";
import { createConversation, listConversations, startConversationMessageStream } from "../conversationRepository";

vi.mock("../../../lib/api/client", () => ({
  request: vi.fn(),
  BASE_URL: "http://127.0.0.1:8000/api/v1",
  ENGINE_TOKEN: "test-token",
}));

const { request } = await import("../../../lib/api/client");

describe("conversationRepository", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("lists structured conversation summaries", async () => {
    vi.mocked(request).mockResolvedValueOnce([
      {
        id: "conv-1",
        title: "Orders",
        datasource_id: "ds-1",
        updated_at: "2026-06-21T00:00:00+00:00",
        last_message: "Done",
        message_count: 2,
        run_status: "completed",
        artifact_count: 3,
      },
    ]);

    const result = await listConversations();

    expect(result[0].id).toBe("conv-1");
    expect(result[0].message_count).toBe(2);
    expect(request).toHaveBeenCalledWith("/conversations");
  });

  it("creates a conversation through the structured endpoint", async () => {
    vi.mocked(request).mockResolvedValueOnce({ id: "conv-2", messages: [], runs: [], artifacts: [] });

    const result = await createConversation({ datasource_id: "ds-1", title: "New", context_tables: ["orders"] });

    expect(result.id).toBe("conv-2");
    expect(request).toHaveBeenCalledWith("/conversations", {
      method: "POST",
      body: JSON.stringify({ datasource_id: "ds-1", title: "New", context_tables: ["orders"] }),
    });
  });
});
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd desktop
npm run test -- src/features/conversation/__tests__/conversationRepository.test.ts
```

Expected: FAIL because repository still maps old `ConversationRecord`.

- [ ] **Step 3: Replace conversation types**

Replace `desktop/src/types/conversation.ts` with:

```typescript
import type { AgentAnswer, AgentRuntimeEvent } from "../lib/api/types";

export type ConversationRole = "user" | "assistant" | "system";
export type ConversationMessageStatus = "created" | "streaming" | "completed" | "failed";
export type AgentRunStatus = "queued" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled";
export type ConversationArtifactType = "sql" | "table" | "chart" | "markdown";

export interface ConversationSummary {
  id: string;
  title: string;
  datasource_id: string;
  updated_at: string | null;
  last_message: string;
  message_count: number;
  run_status: AgentRunStatus | null;
  artifact_count: number;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: ConversationRole;
  content: string;
  status: ConversationMessageStatus;
  sequence: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConversationRun {
  id: string;
  conversation_id: string;
  parent_run_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  datasource_id: string;
  question: string;
  status: AgentRunStatus;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  answer?: AgentAnswer | null;
}

export interface ConversationArtifact {
  id: string;
  conversation_id: string;
  run_id: string;
  message_id?: string | null;
  semantic_id?: string | null;
  type: ConversationArtifactType;
  title: string;
  status: "created" | "running" | "completed" | "failed";
  sequence?: number | null;
  payload: Record<string, unknown>;
  presentation?: Record<string, unknown>;
  depends_on: string[];
  refs?: Record<string, unknown>;
  created_at?: string | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  datasource_id: string;
  context_tables: string[];
  created_at: string | null;
  updated_at: string | null;
  messages: ConversationMessage[];
  runs: ConversationRun[];
  artifacts: ConversationArtifact[];
  approvals: unknown[];
}

export interface ConversationCreateInput {
  datasource_id: string;
  title?: string;
  context_tables: string[];
}

export interface ConversationMessageInput {
  content: string;
  api_key?: string;
  api_base?: string;
  model_name?: string;
  execute?: boolean;
}

export interface ConversationMessageStart {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  run_id: string | null;
}

export type ConversationStreamEvent = AgentRuntimeEvent & {
  conversation_id?: string | null;
  message_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
};
```

- [ ] **Step 4: Replace repository**

Replace `desktop/src/features/conversation/conversationRepository.ts` with:

```typescript
import { BASE_URL, ENGINE_TOKEN, request } from "../../lib/api/client";
import type {
  ConversationCreateInput,
  ConversationDetail,
  ConversationMessageInput,
  ConversationMessageStart,
  ConversationStreamEvent,
  ConversationSummary,
} from "../../types/conversation";

export const listConversations = () => request<ConversationSummary[]>("/conversations");

export const createConversation = (input: ConversationCreateInput) =>
  request<ConversationDetail>("/conversations", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const getConversation = (conversationId: string) =>
  request<ConversationDetail>(`/conversations/${encodeURIComponent(conversationId)}`);

export const patchConversation = (conversationId: string, patch: { title?: string; context_tables?: string[]; archived?: boolean }) =>
  request<ConversationDetail>(`/conversations/${encodeURIComponent(conversationId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const deleteConversation = (conversationId: string) =>
  request<{ status: "ok" }>(`/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });

export const prepareConversationMessage = (conversationId: string, input: ConversationMessageInput) =>
  request<ConversationMessageStart>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    body: JSON.stringify(input),
  });

function parseSseEvent(rawEvent: string): ConversationStreamEvent | null {
  const dataLines = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as ConversationStreamEvent;
  } catch {
    return null;
  }
}

export async function startConversationMessageStream(
  conversationId: string,
  input: ConversationMessageInput,
  options?: { signal?: AbortSignal; onEvent?: (event: ConversationStreamEvent) => void },
): Promise<void> {
  const response = await fetch(`${BASE_URL}/conversations/${encodeURIComponent(conversationId)}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Local-Token": ENGINE_TOKEN },
    body: JSON.stringify(input),
    signal: options?.signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Conversation stream failed.");
  }
  if (!response.body) throw new Error("Conversation stream is not supported.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);
        if (rawEvent) {
          const event = parseSseEvent(rawEvent);
          if (event) options?.onEvent?.(event);
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

- [ ] **Step 5: Extend frontend runtime event types**

In `desktop/src/lib/api/types.ts`, add optional fields to `AgentRuntimeEvent`:

```typescript
  conversation_id?: string | null;
  message_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
```

- [ ] **Step 6: Run repository tests**

Run:

```bash
cd desktop
npm run test -- src/features/conversation/__tests__/conversationRepository.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add desktop/src/types/conversation.ts desktop/src/features/conversation/conversationRepository.ts desktop/src/lib/api/types.ts desktop/src/features/conversation/__tests__/conversationRepository.test.ts
git commit -m "feat: add structured conversation frontend api"
```

## Task 7: Frontend Conversation Store

**Files:**

- Create: `desktop/src/stores/conversationStore.ts`
- Create: `desktop/src/stores/__tests__/conversationStore.test.ts`
- Modify: `desktop/src/stores/workspaceStore.ts`
- Modify: `desktop/src/stores/agentStore.ts`

- [ ] **Step 1: Write reducer tests**

Create `desktop/src/stores/__tests__/conversationStore.test.ts`:

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import { useConversationStore } from "../conversationStore";

describe("conversationStore", () => {
  beforeEach(() => {
    useConversationStore.setState(useConversationStore.getInitialState());
  });

  it("applies assistant delta to the addressed assistant message only", () => {
    const store = useConversationStore.getState();
    store.loadConversation({
      id: "conv-1",
      title: "Test",
      datasource_id: "ds-1",
      context_tables: [],
      created_at: null,
      updated_at: null,
      messages: [
        { id: "user-1", conversation_id: "conv-1", role: "user", content: "hello", status: "completed", sequence: 1, created_at: null, updated_at: null },
        { id: "assistant-1", conversation_id: "conv-1", role: "assistant", content: "", status: "streaming", sequence: 2, created_at: null, updated_at: null },
      ],
      runs: [],
      artifacts: [],
      approvals: [],
    });

    store.applyStreamEvent({
      event_id: "event-1",
      run_id: "run-1",
      sequence: 1,
      created_at_ms: 1,
      type: "agent.answer.completed",
      conversation_id: "conv-1",
      message_id: "assistant-1",
      assistant_message_id: "assistant-1",
      answer: { answer: "world", key_findings: [], evidence: [], caveats: [], recommendations: [], follow_up_questions: [] },
    });

    const state = useConversationStore.getState();
    expect(state.messagesById["user-1"].content).toBe("hello");
    expect(state.messagesById["assistant-1"].content).toBe("world");
    expect(state.messagesById["assistant-1"].status).toBe("completed");
  });
});
```

- [ ] **Step 2: Run failing store test**

Run:

```bash
cd desktop
npm run test -- src/stores/__tests__/conversationStore.test.ts
```

Expected: FAIL because `conversationStore.ts` does not exist.

- [ ] **Step 3: Implement `conversationStore.ts`**

Create `desktop/src/stores/conversationStore.ts`:

```typescript
import { create } from "zustand";
import { getStoredApiConfig } from "../components/SettingsDialog";
import { useDatasourceStore } from "./datasourceStore";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  startConversationMessageStream,
} from "../features/conversation/conversationRepository";
import type {
  ConversationArtifact,
  ConversationDetail,
  ConversationMessage,
  ConversationRun,
  ConversationStreamEvent,
  ConversationSummary,
} from "../types/conversation";

interface ConversationState {
  summaries: ConversationSummary[];
  activeConversationId: string | null;
  detailById: Record<string, ConversationDetail>;
  messagesById: Record<string, ConversationMessage>;
  runsById: Record<string, ConversationRun>;
  artifactsById: Record<string, ConversationArtifact>;
  abortControllers: Map<string, AbortController>;
}

interface ConversationActions {
  initConversations: () => Promise<void>;
  openConversation: (conversationId: string) => Promise<ConversationDetail>;
  createAndOpenConversation: (question: string, contextTables: string[]) => Promise<ConversationDetail>;
  deleteConversationById: (conversationId: string) => Promise<void>;
  loadConversation: (detail: ConversationDetail) => void;
  sendMessage: (conversationId: string, content: string) => Promise<void>;
  cancelRun: (runId: string) => void;
  applyStreamEvent: (event: ConversationStreamEvent) => void;
}

export type ConversationStore = ConversationState & ConversationActions;

function answerText(event: ConversationStreamEvent): string | null {
  if (event.answer?.answer) return event.answer.answer;
  if (event.response?.answer?.answer) return event.response.answer.answer;
  if (event.response?.explanation) return event.response.explanation;
  if (event.error) return `执行未完成：${event.error}`;
  return null;
}

function upsertMessage(state: ConversationState, messageId: string, patch: Partial<ConversationMessage>) {
  const current = state.messagesById[messageId];
  if (!current) return;
  state.messagesById = { ...state.messagesById, [messageId]: { ...current, ...patch } };
}

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  summaries: [],
  activeConversationId: null,
  detailById: {},
  messagesById: {},
  runsById: {},
  artifactsById: {},
  abortControllers: new Map(),

  initConversations: async () => {
    const summaries = await listConversations();
    set({ summaries });
  },

  openConversation: async (conversationId) => {
    const detail = await getConversation(conversationId);
    get().loadConversation(detail);
    return detail;
  },

  createAndOpenConversation: async (question, contextTables) => {
    const datasourceId = useDatasourceStore.getState().activeDatasourceId;
    if (!datasourceId) throw new Error("请先选择数据源。");
    const detail = await createConversation({ datasource_id: datasourceId, title: question.slice(0, 80), context_tables: contextTables });
    get().loadConversation(detail);
    return detail;
  },

  deleteConversationById: async (conversationId) => {
    await deleteConversation(conversationId);
    set((state) => ({
      summaries: state.summaries.filter((item) => item.id !== conversationId),
      activeConversationId: state.activeConversationId === conversationId ? null : state.activeConversationId,
    }));
  },

  loadConversation: (detail) => {
    const messagesById = { ...get().messagesById };
    const runsById = { ...get().runsById };
    const artifactsById = { ...get().artifactsById };
    for (const message of detail.messages) messagesById[message.id] = message;
    for (const run of detail.runs) runsById[run.id] = run;
    for (const artifact of detail.artifacts) artifactsById[artifact.id] = artifact;
    set((state) => ({
      activeConversationId: detail.id,
      detailById: { ...state.detailById, [detail.id]: detail },
      messagesById,
      runsById,
      artifactsById,
    }));
  },

  sendMessage: async (conversationId, content) => {
    const llm = getStoredApiConfig();
    const abortController = new AbortController();
    get().abortControllers.set(conversationId, abortController);
    await startConversationMessageStream(
      conversationId,
      { content, api_key: llm.apiKey || undefined, api_base: llm.apiBase || undefined, model_name: llm.modelName || undefined, execute: true },
      { signal: abortController.signal, onEvent: (event) => get().applyStreamEvent(event) },
    );
    get().abortControllers.delete(conversationId);
    await get().openConversation(conversationId);
    await get().initConversations();
  },

  cancelRun: (runId) => {
    for (const controller of get().abortControllers.values()) controller.abort();
    set((state) => ({
      runsById: state.runsById[runId]
        ? { ...state.runsById, [runId]: { ...state.runsById[runId], status: "cancelled" } }
        : state.runsById,
    }));
  },

  applyStreamEvent: (event) => {
    set((state) => {
      const messageId = event.message_id || event.assistant_message_id || event.response?.assistant_message_id || null;
      const text = answerText(event);
      const next: ConversationState = { ...state };
      if (event.run_id && !next.runsById[event.run_id]) {
        next.runsById = {
          ...next.runsById,
          [event.run_id]: {
            id: event.run_id,
            conversation_id: event.conversation_id || "",
            datasource_id: "",
            question: "",
            status: "running",
            user_message_id: event.user_message_id,
            assistant_message_id: event.assistant_message_id,
          },
        };
      }
      if (event.type === "agent.run.completed" || event.type === "agent.run.failed" || event.type === "agent.run.cancelled") {
        const status = event.type === "agent.run.completed" ? "completed" : event.type === "agent.run.cancelled" ? "cancelled" : "failed";
        if (next.runsById[event.run_id]) next.runsById = { ...next.runsById, [event.run_id]: { ...next.runsById[event.run_id], status } };
      }
      if (messageId && text) upsertMessage(next, messageId, { content: text, status: event.type === "agent.run.failed" ? "failed" : "completed" });
      if (event.artifact) {
        next.artifactsById = {
          ...next.artifactsById,
          [event.artifact.id]: {
            id: event.artifact.id,
            conversation_id: event.conversation_id || "",
            run_id: event.run_id,
            message_id: messageId,
            semantic_id: event.artifact.semantic_id || null,
            type: event.artifact.type as ConversationArtifact["type"],
            title: event.artifact.title,
            status: "completed",
            sequence: event.sequence,
            payload: event.artifact.payload || {},
            presentation: event.artifact.presentation as unknown as Record<string, unknown>,
            depends_on: event.artifact.depends_on || [],
            refs: event.artifact.refs || {},
            created_at: null,
          },
        };
      }
      return next;
    });
  },
}));
```

- [ ] **Step 4: Remove old persistence actions from `workspaceStore`**

Remove `conversations`, `persistConversation`, `deleteConversationById`, and `initConversations` from `WorkspaceState` and `WorkspaceActions`. Keep tab management only.

Change `openConversationResult` to open a conversation tab by id:

```typescript
openConversationResult: (conv) => {
  const tabId = `conversation-${conv.id}`;
  set((s) => ({
    tabs: s.tabs.some((t) => t.id === tabId)
      ? s.tabs
      : [...s.tabs, { id: tabId, title: conv.title, type: "query-result", conversationId: conv.id }],
    activeTabId: tabId,
  }));
},
```

- [ ] **Step 5: Stop `agentStore` from mutating tab messages**

Replace calls from `SmartQueryHome` integration later, then remove `runAgentForTab`, `sendFollowUp`, and persistence calls after `ConversationWorkspace` uses `conversationStore.sendMessage`. Keep approval/cancel wrappers only if still needed by old tabs during transition.

- [ ] **Step 6: Run store tests**

Run:

```bash
cd desktop
npm run test -- src/stores/__tests__/conversationStore.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add desktop/src/stores/conversationStore.ts desktop/src/stores/__tests__/conversationStore.test.ts desktop/src/stores/workspaceStore.ts desktop/src/stores/agentStore.ts
git commit -m "feat: add conversation-first frontend store"
```

## Task 8: Conversation Workspace UI

**Files:**

- Create: `desktop/src/features/conversation/workspace/ConversationWorkspace.tsx`
- Create: `desktop/src/features/conversation/workspace/ConversationHeader.tsx`
- Create: `desktop/src/features/conversation/workspace/MessageList.tsx`
- Create: `desktop/src/features/conversation/workspace/MessageBubble.tsx`
- Create: `desktop/src/features/conversation/workspace/RunTracePanel.tsx`
- Create: `desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx`
- Create: `desktop/src/features/conversation/workspace/Composer.tsx`
- Create: `desktop/src/features/conversation/workspace/conversationWorkspace.css`
- Create: `desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx`

- [ ] **Step 1: Write evidence grouping test**

Create `desktop/src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ArtifactEvidencePanel } from "../ArtifactEvidencePanel";
import type { ConversationArtifact } from "../../../../types/conversation";

describe("ArtifactEvidencePanel", () => {
  it("groups SQL, table, and chart by depends_on", () => {
    const artifacts: ConversationArtifact[] = [
      { id: "sql-1", conversation_id: "conv", run_id: "run", message_id: "assistant", type: "sql", title: "SQL 1", status: "completed", sequence: 1, payload: { sql: "select 1" }, depends_on: [] },
      { id: "table-1", conversation_id: "conv", run_id: "run", message_id: "assistant", type: "table", title: "Rows", status: "completed", sequence: 2, payload: { columns: ["value"], rows: [{ value: 1 }] }, depends_on: ["sql-1"] },
      { id: "chart-1", conversation_id: "conv", run_id: "run", message_id: "assistant", type: "chart", title: "Chart", status: "completed", sequence: 3, payload: { type: "bar", series: [{ label: "A", value: 1 }] }, depends_on: ["table-1"] },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("SQL 1")).toBeInTheDocument();
    expect(screen.getByText("Rows")).toBeInTheDocument();
    expect(screen.getByText("Chart")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run failing UI test**

Run:

```bash
cd desktop
npm run test -- src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
```

Expected: FAIL because component does not exist.

- [ ] **Step 3: Implement `ArtifactEvidencePanel`**

Create `desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx`:

```tsx
import { Copy, Database, Play, Terminal, BarChart2 } from "lucide-react";
import type { ConversationArtifact } from "../../../types/conversation";

interface ArtifactEvidencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

function sqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.proposed_sql || artifact.payload.safe_sql;
  return typeof value === "string" ? value : "";
}

function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = artifacts.filter((item) => item.type === "sql").sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  return sql.map((sqlArtifact) => {
    const tables = artifacts.filter((item) => item.type === "table" && item.depends_on.includes(sqlArtifact.id));
    const tableIds = new Set(tables.map((item) => item.id));
    const charts = artifacts.filter((item) => item.type === "chart" && (item.depends_on.includes(sqlArtifact.id) || item.depends_on.some((id) => tableIds.has(id))));
    return { sql: sqlArtifact, tables, charts };
  });
}

export function ArtifactEvidencePanel({ artifacts, onOpenSqlConsole }: ArtifactEvidencePanelProps) {
  const groups = groupedArtifacts(artifacts);
  if (artifacts.length === 0) return null;
  return (
    <details className="conv-evidence" open>
      <summary>
        <Database size={14} />
        <span>{artifacts.length} evidence items</span>
      </summary>
      <div className="conv-evidence-body">
        {groups.map((group, index) => {
          const sql = sqlText(group.sql);
          return (
            <section className="conv-sql-group" key={group.sql.id}>
              <header>
                <span><Terminal size={13} /> SQL {index + 1}</span>
                <button type="button" onClick={() => navigator.clipboard.writeText(sql)}><Copy size={13} /> Copy</button>
                <button type="button" onClick={() => onOpenSqlConsole(sql)}><Play size={13} /> Open</button>
              </header>
              <pre>{sql}</pre>
              {group.tables.map((table) => (
                <div className="conv-table-artifact" key={table.id}>
                  <strong>{table.title}</strong>
                </div>
              ))}
              {group.charts.map((chart) => (
                <div className="conv-chart-artifact" key={chart.id}>
                  <BarChart2 size={13} />
                  <strong>{chart.title}</strong>
                </div>
              ))}
            </section>
          );
        })}
      </div>
    </details>
  );
}
```

- [ ] **Step 4: Implement message components**

Create `MessageBubble.tsx`:

```tsx
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../types/conversation";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { ArtifactEvidencePanel } from "./ArtifactEvidencePanel";
import { RunTracePanel } from "./RunTracePanel";

interface MessageBubbleProps {
  message: ConversationMessage;
  run?: ConversationRun;
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

export function MessageBubble({ message, run, artifacts, onOpenSqlConsole }: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <article className={`conv-message conv-message-${message.role}`}>
      <div className="conv-message-body">
        {isUser ? <p>{message.content}</p> : <MarkdownContent content={message.content || (message.status === "streaming" ? "思考中..." : "")} />}
        {!isUser && run?.status === "failed" && <div className="conv-error-card">{run.error_message || "Agent stopped."}</div>}
        {!isUser && run && <RunTracePanel run={run} />}
        {!isUser && <ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={onOpenSqlConsole} />}
      </div>
    </article>
  );
}
```

Create `RunTracePanel.tsx`:

```tsx
import type { ConversationRun } from "../../../types/conversation";

export function RunTracePanel({ run }: { run: ConversationRun }) {
  return (
    <details className="conv-run-trace">
      <summary>
        {run.status === "running" ? "Analyzing..." : `Run ${run.status}`}
      </summary>
      <div className="conv-run-trace-body">
        <div>Run ID: {run.id}</div>
        {run.error_message && <div>{run.error_message}</div>}
      </div>
    </details>
  );
}
```

Create `MessageList.tsx`:

```tsx
import { useEffect, useRef } from "react";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../types/conversation";
import { MessageBubble } from "./MessageBubble";

interface MessageListProps {
  messages: ConversationMessage[];
  runs: ConversationRun[];
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

export function MessageList({ messages, runs, artifacts, onOpenSqlConsole }: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, artifacts.length]);
  return (
    <div className="conv-message-scroll" ref={ref}>
      <div className="conv-message-column">
        {messages.map((message) => {
          const run = runs.find((item) => item.assistant_message_id === message.id);
          const messageArtifacts = artifacts.filter((artifact) => artifact.message_id === message.id);
          return <MessageBubble key={message.id} message={message} run={run} artifacts={messageArtifacts} onOpenSqlConsole={onOpenSqlConsole} />;
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement header, composer, and workspace**

Create `ConversationHeader.tsx`:

```tsx
import { History, Trash2 } from "lucide-react";
import type { ConversationDetail } from "../../../types/conversation";

export function ConversationHeader({ detail, onOpenHistory, onDelete }: { detail: ConversationDetail; onOpenHistory: () => void; onDelete: () => void }) {
  return (
    <header className="conv-header">
      <div>
        <h2>{detail.title || "Conversation"}</h2>
        <span>{detail.datasource_id}</span>
      </div>
      <div className="conv-header-actions">
        <button type="button" onClick={onOpenHistory} title="Open history"><History size={16} /></button>
        <button type="button" onClick={onDelete} title="Delete conversation"><Trash2 size={16} /></button>
      </div>
    </header>
  );
}
```

Create `Composer.tsx`:

```tsx
import { Send, Square } from "lucide-react";
import { useState } from "react";

export function Composer({ disabled, running, onSend, onCancel }: { disabled?: string | null; running: boolean; onSend: (text: string) => void; onCancel: () => void }) {
  const [value, setValue] = useState("");
  const submit = () => {
    const text = value.trim();
    if (!text || disabled || running) return;
    setValue("");
    onSend(text);
  };
  return (
    <footer className="conv-composer">
      <div className="conv-composer-box">
        <textarea value={value} onChange={(event) => setValue(event.target.value)} placeholder={disabled || "Continue asking..."} disabled={Boolean(disabled)} />
        {running ? (
          <button type="button" onClick={onCancel} title="Cancel"><Square size={16} /></button>
        ) : (
          <button type="button" onClick={submit} title="Send"><Send size={16} /></button>
        )}
      </div>
    </footer>
  );
}
```

Create `ConversationWorkspace.tsx`:

```tsx
import { useEffect, useMemo } from "react";
import { useConversationStore } from "../../../stores/conversationStore";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../types/conversation";
import { ConversationHeader } from "./ConversationHeader";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import "./conversationWorkspace.css";

export function ConversationWorkspace({ conversationId, onOpenHistory, onOpenSqlConsole, onDelete }: { conversationId: string; onOpenHistory: () => void; onOpenSqlConsole: (sql?: string) => void; onDelete: () => void }) {
  const store = useConversationStore();
  const detail = store.detailById[conversationId];
  useEffect(() => {
    if (!detail) void store.openConversation(conversationId);
  }, [conversationId, detail, store]);
  const messages = useMemo<ConversationMessage[]>(() => detail?.messages.map((item) => store.messagesById[item.id] || item) || [], [detail, store.messagesById]);
  const runs = useMemo<ConversationRun[]>(() => detail?.runs.map((item) => store.runsById[item.id] || item) || [], [detail, store.runsById]);
  const artifacts = useMemo<ConversationArtifact[]>(() => detail?.artifacts.map((item) => store.artifactsById[item.id] || item) || Object.values(store.artifactsById).filter((item) => item.conversation_id === conversationId), [conversationId, detail, store.artifactsById]);
  const runningRun = runs.find((run) => run.status === "running" || run.status === "waiting_approval");
  if (!detail) return <div className="conv-workspace">Loading...</div>;
  return (
    <div className="conv-workspace">
      <ConversationHeader detail={detail} onOpenHistory={onOpenHistory} onDelete={onDelete} />
      <MessageList messages={messages} runs={runs} artifacts={artifacts} onOpenSqlConsole={onOpenSqlConsole} />
      <Composer running={Boolean(runningRun)} onSend={(text) => void store.sendMessage(conversationId, text)} onCancel={() => runningRun && store.cancelRun(runningRun.id)} />
    </div>
  );
}
```

- [ ] **Step 6: Add CSS**

Create `conversationWorkspace.css`:

```css
.conv-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #f8fafc;
  color: #111827;
}

.conv-header {
  height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  border-bottom: 1px solid #e5e7eb;
  background: #ffffff;
}

.conv-header h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
  letter-spacing: 0;
}

.conv-header span {
  font-size: 11px;
  color: #6b7280;
}

.conv-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.conv-header-actions button,
.conv-composer button,
.conv-sql-group button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid #d1d5db;
  background: #ffffff;
  color: #374151;
  border-radius: 6px;
  min-width: 32px;
  min-height: 32px;
  cursor: pointer;
}

.conv-message-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 24px 36px;
}

.conv-message-column {
  width: min(880px, 100%);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.conv-message {
  display: flex;
}

.conv-message-user {
  justify-content: flex-end;
}

.conv-message-assistant {
  justify-content: flex-start;
}

.conv-message-body {
  max-width: min(760px, 100%);
  font-size: 14px;
  line-height: 1.65;
}

.conv-message-user .conv-message-body {
  max-width: min(560px, 85%);
  padding: 10px 14px;
  background: #eef2ff;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
}

.conv-error-card {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #991b1b;
  border-radius: 6px;
}

.conv-run-trace,
.conv-evidence {
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
  border-radius: 8px;
}

.conv-run-trace summary,
.conv-evidence summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  font-size: 12px;
  color: #4b5563;
}

.conv-evidence-body {
  border-top: 1px solid #e5e7eb;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conv-sql-group {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.conv-sql-group header {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
  padding: 8px 10px;
  background: #f9fafb;
}

.conv-sql-group pre {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  background: #ffffff;
  font-size: 12px;
  line-height: 1.55;
}

.conv-table-artifact,
.conv-chart-artifact {
  padding: 10px 12px;
  border-top: 1px solid #e5e7eb;
}

.conv-composer {
  flex-shrink: 0;
  padding: 12px 24px;
  border-top: 1px solid #e5e7eb;
  background: #ffffff;
}

.conv-composer-box {
  width: min(880px, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 38px;
  gap: 8px;
  align-items: end;
}

.conv-composer textarea {
  min-height: 42px;
  max-height: 140px;
  resize: vertical;
  border: 1px solid #d1d5db;
  border-radius: 7px;
  padding: 10px 12px;
  font: inherit;
}
```

- [ ] **Step 7: Run UI test**

Run:

```bash
cd desktop
npm run test -- src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add desktop/src/features/conversation/workspace
git commit -m "feat: add conversation workspace components"
```

## Task 9: Workspace Integration

**Files:**

- Modify: `desktop/src/features/appShell/WorkspaceRouter.tsx`
- Modify: `desktop/src/features/conversation/ConversationHistoryPanel.tsx`
- Modify: `desktop/src/stores/workspaceStore.ts`
- Modify: `desktop/src/types/workspace.ts`
- Modify: `desktop/src/features/workspace/QueryResultWorkspace.tsx`
- Modify: `desktop/src/features/appShell/useAppCommands.tsx`

- [ ] **Step 1: Update workspace tab type**

In `desktop/src/types/workspace.ts`, keep `query-result` for the tab kind but remove chat-specific fields from new code paths. Add a comment:

```typescript
  conversationId?: string;
  // Conversation content is stored in conversationStore. These legacy fields stay only
  // until old AgentTaskView callers are deleted.
```

- [ ] **Step 2: Update `SmartQueryHomeTab` submission flow**

In `WorkspaceRouter.tsx`, replace `handleSubmitAsk` with:

```tsx
const handleSubmitAsk = async () => {
  const text = askInputValue.trim();
  if (!text) return;
  setAskInputValue("");
  const detail = await useConversationStore.getState().createAndOpenConversation(text, contextTables);
  useWorkspaceStore.getState().openConversationResult({ id: detail.id, title: detail.title });
  void useConversationStore.getState().sendMessage(detail.id, text);
};
```

Import `useConversationStore`.

- [ ] **Step 3: Replace QueryResult tab rendering**

In `QueryResultTab`, render `ConversationWorkspace`:

```tsx
return (
  <ConversationWorkspace
    conversationId={activeTab.conversationId || ""}
    onOpenHistory={() => useWorkspaceStore.getState().openConversationHistoryTab()}
    onOpenSqlConsole={openSqlConsole}
    onDelete={() => {
      if (activeTab.conversationId) void useConversationStore.getState().deleteConversationById(activeTab.conversationId);
      useWorkspaceStore.getState().closeTab(activeTab.id);
    }}
  />
);
```

Remove `sendFollowUp`, `handleApprovalDecision`, `cancelAgentRun`, and `regenerateAgentRun` props from this path.

- [ ] **Step 4: Update history panel to summaries**

Change `ConversationHistoryPanelProps`:

```tsx
import type { ConversationSummary } from "../../types/conversation";

interface ConversationHistoryPanelProps {
  conversations: ConversationSummary[];
  activeConversationId?: string;
  onOpenConversation: (conversation: ConversationSummary) => void;
  onDeleteConversation: (conversationId: string) => void;
}
```

Replace preview logic with `conversation.last_message`, `conversation.message_count`, and `conversation.artifact_count`.

- [ ] **Step 5: Update history tab data source**

In `ConversationHistoryTab`, use `useConversationStore`:

```tsx
const conversations = useConversationStore((s) => s.summaries);
const openConversation = async (summary: ConversationSummary) => {
  await useConversationStore.getState().openConversation(summary.id);
  useWorkspaceStore.getState().openConversationResult({ id: summary.id, title: summary.title });
};
```

- [ ] **Step 6: Run TypeScript build**

Run:

```bash
cd desktop
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add desktop/src/features/appShell/WorkspaceRouter.tsx desktop/src/features/conversation/ConversationHistoryPanel.tsx desktop/src/stores/workspaceStore.ts desktop/src/types/workspace.ts desktop/src/features/workspace/QueryResultWorkspace.tsx desktop/src/features/appShell/useAppCommands.tsx
git commit -m "feat: route workspace tabs through conversation store"
```

## Task 10: Remove Old JSON Conversation Path and Old Agent UI

**Files:**

- Delete: `engine/agent_core/persistence/conversations.py`
- Delete or update: old tests that import `ChatConversation`
- Delete: `desktop/src/features/agentTask/AgentTaskView.tsx`
- Delete: `desktop/src/features/agentTask/AgentTurnItem.tsx`
- Delete: `desktop/src/features/agentTask/FinalAnswerCard.tsx`
- Delete: `desktop/src/features/agentTask/AgentTaskView.css`
- Modify: imports that referenced old agentTask components.

- [ ] **Step 1: Search for old symbols**

Run:

```bash
rg "ChatConversation|messages_json|artifacts_json|sync_chat_conversation_from_session|AgentTaskView|AgentTurnItem|FinalAnswerCard|appendTabMessages|updateTabMessage" engine desktop/src
```

Expected: output only from files intentionally being removed or updated in this task.

- [ ] **Step 2: Delete old backend JSON sync module**

Remove `engine/agent_core/persistence/conversations.py`. Remove imports from `engine/agent_core/persistence/__init__.py` and `engine/api/conversations.py`.

- [ ] **Step 3: Delete old agent task UI once no imports remain**

Remove old files only after `rg "AgentTaskView|AgentTurnItem|FinalAnswerCard" desktop/src` shows no active imports outside those files.

- [ ] **Step 4: Run old symbol search again**

Run:

```bash
rg "ChatConversation|messages_json|artifacts_json|sync_chat_conversation_from_session|AgentTaskView|AgentTurnItem|FinalAnswerCard" engine desktop/src
```

Expected: no output.

- [ ] **Step 5: Run full targeted test suite**

Run:

```bash
pytest engine/tests/test_conversations.py engine/tests/test_conversation_rehydration.py engine/tests/test_conversation_runtime_contract.py engine/tests/test_persistence_sink.py engine/tests/test_agent_api.py -q
cd desktop
npm run test -- src/features/conversation/__tests__/conversationRepository.test.ts src/stores/__tests__/conversationStore.test.ts src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add engine desktop/src
git commit -m "refactor: remove legacy conversation and agent task ui"
```

## Task 11: Manual Verification

**Files:**

- No source files unless verification reveals a bug.

- [ ] **Step 1: Start backend and frontend**

Use the repo's normal development commands. If a process is already running, reuse it.

Frontend:

```bash
cd desktop
npm run dev
```

Backend:

```bash
python -m engine.main --reload
```

Expected: FastAPI engine is reachable at `http://127.0.0.1:18625/api/v1/health`.

- [ ] **Step 2: Verify empty history after direct cleanup**

Open DBFox and the conversation history tab.

Expected:

- Old JSON history is not displayed.
- New conversations created during this verification appear in history.

- [ ] **Step 3: Verify normal conversation**

Send a simple question.

Expected:

- A user message appears on the right.
- An assistant message appears on the left.
- The assistant answer updates by stable id, not by replacing the user message.
- The composer remains fixed at the bottom of the conversation workspace.

- [ ] **Step 4: Verify multi-SQL evidence**

Ask for two SQL checks in one answer, or use a mocked backend response with two SQL artifacts.

Expected:

- Evidence summary shows multiple evidence items.
- SQL 1 and SQL 2 appear in sequence.
- Each table/chart appears under the SQL it depends on.

- [ ] **Step 5: Verify failure state**

Run with an invalid API key or force an LLM timeout.

Expected:

- Failure appears inside the assistant message.
- The user message remains visible.
- Composer allows another follow-up after the run reaches `failed`.

- [ ] **Step 6: Verify refresh recovery**

Refresh the page and reopen the conversation from history.

Expected:

- Messages, runs, and artifacts are restored from `GET /conversations/{id}`.
- No tab-local `chatMessages` state is required for display.

- [ ] **Step 7: Final verification commands**

Run:

```bash
pytest engine/tests/test_conversations.py engine/tests/test_conversation_rehydration.py engine/tests/test_conversation_runtime_contract.py engine/tests/test_persistence_sink.py engine/tests/test_agent_api.py -q
cd desktop
npm run test -- src/features/conversation/__tests__/conversationRepository.test.ts src/stores/__tests__/conversationStore.test.ts src/features/conversation/workspace/__tests__/ArtifactEvidencePanel.test.tsx
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 8: Commit any verification fixes**

If verification required fixes:

```bash
git add engine desktop/src
git commit -m "fix: stabilize conversation redesign verification"
```

If no fixes were needed, do not create an empty commit.

## Spec Coverage Checklist

- [ ] ChatGPT-style message stream: Task 8 creates `ConversationWorkspace`, `MessageList`, `MessageBubble`, and fixed `Composer`.
- [ ] Append-only user messages and targeted assistant updates: Task 4 persists linked messages; Task 7 reducer updates by `message_id` / `assistant_message_id`.
- [ ] AgentRun as the unit for trace, approval, error, and artifacts: Task 1 extends `AgentRun`; Task 4 links runtime persistence; Task 8 renders run status per assistant message.
- [ ] Multi-SQL and Chart binding: Task 1 adds artifact message linkage; Task 8 groups artifacts by `depends_on`; Task 11 verifies multi-SQL manually.
- [ ] Refresh and history recovery: Task 2 serializes detail from structured tables; Task 6 adds frontend API; Task 9 wires history and conversation tabs.
- [ ] Old JSON conversation path removed: Task 1 drops `chat_conversations`; Task 10 removes old sync module and old UI callers.
- [ ] Failure states inside assistant messages: Task 4 updates assistant message status; Task 8 renders `conv-error-card`; Task 11 verifies invalid API key or timeout.
- [ ] Tests: backend tests are in Tasks 1 through 5; frontend tests are in Tasks 6 through 8; final targeted test pass is in Task 10 and Task 11.
