"""Synchronous application service using the same durable Session/Run path as the API."""

from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent.loop import RunLoop
from engine.agent.projection import conversation_snapshot
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.db import SessionLocal
from engine.models import AgentSession, DataSource


class AgentExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    datasource_id: str
    question: str = Field(min_length=1, max_length=20_000)
    llm_credential_id: str
    api_base: str | None = None
    model_name: str | None = None
    context_tables: list[str] = Field(default_factory=list)


class AgentExecutionArtifact(BaseModel):
    id: str
    type: str
    title: str
    payload: dict[str, Any]


class AgentExecutionAnswer(BaseModel):
    answer: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class AgentExecutionResult(BaseModel):
    run_id: str
    session_id: str
    status: str
    success: bool
    question: str
    context_summary: str | None = None
    sql: str | None = None
    safety: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    explanation: str | None = None
    answer: AgentExecutionAnswer | None = None
    artifacts: list[AgentExecutionArtifact] = Field(default_factory=list)
    steps: list[Any] = Field(default_factory=list)
    trace_events: list[Any] = Field(default_factory=list)


def execute_agent_sync(
    request: AgentExecutionRequest,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    run_loop: RunLoop | None = None,
) -> tuple[AgentExecutionResult, list[dict[str, Any]]]:
    session_id = f"session_{uuid4().hex}"
    with session_factory() as db:
        begin_agent_write(db)
        datasource = db.get(DataSource, request.datasource_id)
        if datasource is None:
            raise ValueError("Datasource does not exist")
        db.add(AgentSession(
            id=session_id,
            datasource_id=request.datasource_id,
            title=request.question[:80],
            context_tables_json=json.dumps(request.context_tables, ensure_ascii=False),
        ))
        db.flush()
        sessions = SessionRepository(db)
        admission = sessions.admit(
            session_id=session_id,
            datasource_id=request.datasource_id,
            datasource_generation=int(datasource.connection_generation),
            content=request.question,
            idempotency_key=f"evaluation:{uuid4().hex}",
            llm_credential_id=request.llm_credential_id,
            api_base=request.api_base,
            model_name=request.model_name,
            request_payload={"source": "evaluation"},
            workspace_context={"selected_table_names": request.context_tables},
        )
        lease = sessions.claim(session_id=session_id, owner=f"sync:{uuid4().hex}")
        if lease is None:
            raise RuntimeError("Could not claim the newly created Agent Session")
        sessions.promote_next_input(lease=lease)
        db.commit()

    (run_loop or RunLoop(session_factory=session_factory)).execute(
        lease=lease,
        run_id=admission.run_id,
    )
    with session_factory() as db:
        snapshot = conversation_snapshot(db, session_id)
        if snapshot is None:
            raise RuntimeError("Agent Session disappeared after execution")
        events = [item.model_dump(mode="json") for item in SessionRepository(db).list_events(session_id)]
    return _execution_result(snapshot, admission.run_id), events


def _execution_result(snapshot: dict[str, Any], run_id: str) -> AgentExecutionResult:
    run = next(item for item in snapshot["runs"] if item["id"] == run_id)
    artifacts = [item for item in snapshot["artifacts"] if item["run_id"] == run_id]
    by_type = {str(item["type"]): item for item in artifacts}
    result = run.get("result") or {}
    answer_value = result.get("answer") if isinstance(result, dict) else None
    answer = None
    if isinstance(answer_value, dict) and answer_value.get("text"):
        answer = AgentExecutionAnswer(
            answer=str(answer_value["text"]),
            evidence=list(answer_value.get("evidence") or []),
            caveats=[str(item) for item in answer_value.get("caveats") or []],
        )
    return AgentExecutionResult(
        run_id=run_id,
        session_id=str(snapshot["session"]["id"]),
        status=str(run["status"]),
        success=str(run["status"]) == "completed",
        question=str(run.get("question") or ""),
        sql=_artifact_text(by_type.get("sql"), "safeSql", "sql"),
        safety=_artifact_payload(by_type.get("safety")),
        execution=_artifact_payload(by_type.get("result_view")),
        explanation=answer.answer if answer else None,
        answer=answer,
        artifacts=[AgentExecutionArtifact(
            id=str(item["id"]), type=str(item["type"]), title=str(item["title"]),
            payload=dict(item.get("payload") or {}),
        ) for item in artifacts],
    )


def _artifact_payload(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(value.get("payload") or {}) if value else None


def _artifact_text(value: dict[str, Any] | None, *keys: str) -> str | None:
    payload = _artifact_payload(value) or {}
    for key in keys:
        if payload.get(key):
            return str(payload[key])
    return None
