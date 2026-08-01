"""Exactly-once persistence and resumption for business clarification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.events import RuntimeEventType
from engine.agent.observation import ObservationStatus
from engine.agent.question import (
    QuestionAnswer,
    QuestionConflict,
    QuestionOption,
    QuestionRequest,
    QuestionStatus,
)
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.agent.run import RunStatus
from engine.agent.run_item import dump_run_item, project_run, question_item
from engine.agent.session import SessionLease
from engine.json_codec import canonical_dumps as _json, load_array, load_object
from engine.models import AgentQuestionRequest, AgentRun, AgentToolInvocation


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class QuestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = SessionRepository(session)

    def request(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        tool_invocation_id: str,
        question: str,
        reason: str,
        options: list[dict[str, Any]] | None = None,
        allow_free_text: bool = True,
        expires_in_seconds: int = 86_400,
    ) -> QuestionRequest:
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise QuestionConflict("Question request is fenced by another Session owner")
        if run.status != RunStatus.RUNNING.value:
            raise QuestionConflict(f"Run cannot ask a question from {run.status}")
        invocation = self.session.get(AgentToolInvocation, tool_invocation_id)
        if (
            invocation is None
            or str(invocation.session_id) != lease.session_id
            or str(invocation.run_id) != run_id
            or str(invocation.turn_id) != turn_id
            or str(invocation.status) != "waiting_input"
        ):
            raise QuestionConflict(
                "Question must be bound to the active waiting ToolInvocation"
            )
        existing = self.session.execute(
            select(AgentQuestionRequest).where(
                AgentQuestionRequest.run_id == run_id,
                AgentQuestionRequest.turn_id == turn_id,
                AgentQuestionRequest.status == QuestionStatus.PENDING.value,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self._domain(existing)

        parsed_options = [QuestionOption.model_validate(value) for value in (options or [])]
        if not parsed_options and not allow_free_text:
            raise ValueError("A question without options must allow free-text responses")
        now = _utcnow()
        row = AgentQuestionRequest(
            id=f"question_{uuid4().hex}",
            session_id=str(run.session_id),
            run_id=str(run.id),
            turn_id=turn_id,
            tool_invocation_id=tool_invocation_id,
            status=QuestionStatus.PENDING.value,
            version=0,
            question=question.strip(),
            reason=reason.strip(),
            options_json=_json([item.model_dump(mode="json") for item in parsed_options]),
            allow_free_text=allow_free_text,
            expires_at=now + timedelta(seconds=expires_in_seconds),
            created_at=now,
        )
        value = self._domain(row)
        self.session.add(row)
        run.status = RunStatus.WAITING_INPUT.value
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.session.flush()
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_UPDATED,
            run_id=run_id,
            turn_id=turn_id,
            payload={"run": project_run(run)},
        )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_STARTED,
            run_id=run_id,
            turn_id=turn_id,
            payload={"item": dump_run_item(question_item(row))},
        )
        return value

    def expire_pending(
        self,
        *,
        lease: SessionLease,
        now: datetime | None = None,
    ) -> list[QuestionRequest]:
        """Terminalize expired clarification requests in a claimed Session."""
        begin_agent_write(self.session)
        current_time = now or _utcnow()
        rows = self.session.execute(
            select(AgentQuestionRequest).where(
                AgentQuestionRequest.session_id == lease.session_id,
                AgentQuestionRequest.status == QuestionStatus.PENDING.value,
                AgentQuestionRequest.expires_at.is_not(None),
                AgentQuestionRequest.expires_at <= current_time,
            ).with_for_update()
        ).scalars().all()
        expired: list[QuestionRequest] = []
        for row in rows:
            run = self.session.execute(
                select(AgentRun).where(AgentRun.id == row.run_id).with_for_update()
            ).scalar_one()
            if run.status != RunStatus.WAITING_INPUT.value:
                continue
            run.lease_token = lease.token
            expired.append(self._expire(row=row, run=run, lease=lease, now=current_time))
        return expired

    def cancel_pending_for_run(
        self,
        *,
        lease: SessionLease,
        run_id: str,
    ) -> list[QuestionRequest]:
        """Terminalize unresolved clarification requests for a cancelled Run."""
        begin_agent_write(self.session)
        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        ).scalar_one()
        if str(run.session_id) != lease.session_id or int(run.lease_token or 0) != lease.token:
            raise QuestionConflict("Question cancellation is fenced by another Session owner")
        rows = self.session.execute(
            select(AgentQuestionRequest).where(
                AgentQuestionRequest.run_id == run_id,
                AgentQuestionRequest.status == QuestionStatus.PENDING.value,
            ).with_for_update()
        ).scalars().all()
        now = _utcnow()
        cancelled: list[QuestionRequest] = []
        for row in rows:
            row.status = QuestionStatus.CANCELLED.value
            row.version = int(row.version or 0) + 1
            row.response_json = _json({
                "content": "The Run was cancelled before the user responded.",
                "actor": "system:run_cancel",
            })
            row.answered_at = now
            self.session.flush()
            value = self._domain(row)
            self.sessions.events.append(
                lease=lease,
                event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
                run_id=run_id,
                turn_id=str(row.turn_id),
                payload={"item": dump_run_item(question_item(row))},
            )
            cancelled.append(value)
        return cancelled

    def resolve(
        self,
        *,
        question_id: str,
        expected_version: int,
        answer: QuestionAnswer,
        actor: str,
    ) -> QuestionRequest:
        begin_agent_write(self.session)
        row = self.session.execute(
            select(AgentQuestionRequest)
            .where(AgentQuestionRequest.id == question_id)
            .with_for_update()
        ).scalar_one()
        if row.status != QuestionStatus.PENDING.value or int(row.version or 0) != expected_version:
            raise QuestionConflict("Question has already changed")
        now = _utcnow()
        expires_at = _aware(row.expires_at)
        if expires_at is not None and expires_at <= now:
            run = self.session.execute(
                select(AgentRun).where(AgentRun.id == row.run_id).with_for_update()
            ).scalar_one()
            lease = self.sessions.claim(
                session_id=str(run.session_id),
                owner=f"question:{question_id}",
            )
            if lease is None:
                raise QuestionConflict("Session is currently owned; retry the response")
            run.lease_token = lease.token
            value = self._expire(row=row, run=run, lease=lease, now=now)
            self.sessions.release(lease=lease)
            return value

        options = [QuestionOption.model_validate(item) for item in load_array(str(row.options_json or "[]"))]
        if answer.selected_value and answer.selected_value not in {item.value for item in options}:
            raise QuestionConflict("Selected option is not available")
        if answer.text and not bool(row.allow_free_text):
            raise QuestionConflict("This question does not accept free text")
        content = answer.text or next(
            item.label for item in options if item.value == answer.selected_value
        )

        run = self.session.execute(
            select(AgentRun).where(AgentRun.id == row.run_id).with_for_update()
        ).scalar_one()
        if run.status != RunStatus.WAITING_INPUT.value:
            raise QuestionConflict(f"Question cannot be resolved while Run is {run.status}")
        lease = self.sessions.claim(session_id=str(run.session_id), owner=f"question:{question_id}")
        if lease is None:
            raise QuestionConflict("Session is currently owned; retry the response")
        run.lease_token = lease.token
        message = self.sessions.add_response_input(
            lease=lease,
            run_id=str(run.id),
            content=content,
            idempotency_key=f"question:{question_id}:{expected_version}",
            reply_to_request_id=question_id,
            now=now,
        )
        response = {
            "selected_value": answer.selected_value,
            "text": answer.text,
            "content": content,
            "actor": actor,
        }
        row.status = QuestionStatus.ANSWERED.value
        row.version = int(row.version or 0) + 1
        row.response_message_id = str(message.id)
        row.response_json = _json(response)
        row.answered_at = now
        ToolInvocationRepository(self.session).settle(
            lease=lease,
            invocation_id=str(row.tool_invocation_id),
            status=ObservationStatus.SUCCEEDED,
            model_visible_summary=f"User answered the clarification: {content}",
            facts={
                "answer": content,
                "selected_value": answer.selected_value,
            },
            contributes_progress=True,
        )
        run.status = RunStatus.RUNNING.value
        run.version = int(run.version or 0) + 1
        run.updated_at = now
        self.session.flush()
        value = self._domain(row)
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_COMPLETED,
            run_id=str(run.id),
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(question_item(row))},
        )
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_UPDATED,
            run_id=str(run.id),
            turn_id=str(row.turn_id),
            payload={"run": project_run(run)},
        )
        self.sessions.release(lease=lease)
        return value

    def _expire(
        self,
        *,
        row: AgentQuestionRequest,
        run: AgentRun,
        lease: SessionLease,
        now: datetime,
    ) -> QuestionRequest:
        row.status = QuestionStatus.EXPIRED.value
        row.version = int(row.version or 0) + 1
        row.response_json = _json({
            "content": "The clarification request expired before the user responded.",
            "actor": "system:expiry",
        })
        row.answered_at = now
        ToolInvocationRepository(self.session).settle(
            lease=lease,
            invocation_id=str(row.tool_invocation_id),
            status=ObservationStatus.FAILED,
            model_visible_summary="The clarification request expired before the user responded.",
            error_code="QUESTION_EXPIRED",
            error_message="The user did not answer the clarification before its deadline.",
            contributes_progress=False,
            retryable=False,
        )
        self.session.flush()
        value = self._domain(row)
        self.sessions.events.append(
            lease=lease,
            event_type=RuntimeEventType.RUN_ITEM_CANCELLED,
            run_id=str(run.id),
            turn_id=str(row.turn_id),
            payload={"item": dump_run_item(question_item(row))},
        )
        from engine.agent.terminalizer import Terminalizer

        Terminalizer.fail_in_session(
            self.session,
            lease,
            str(run.id),
            "AGENT_QUESTION_EXPIRED",
            "等待补充信息已超时，请重新发起分析。",
        )
        return value

    @staticmethod
    def _domain(row: AgentQuestionRequest) -> QuestionRequest:
        return QuestionRequest(
            id=str(row.id),
            session_id=str(row.session_id),
            run_id=str(row.run_id),
            turn_id=str(row.turn_id),
            status=QuestionStatus(str(row.status)),
            version=int(row.version or 0),
            question=str(row.question),
            reason=str(row.reason),
            options=[QuestionOption.model_validate(value) for value in load_array(str(row.options_json or "[]"))],
            allow_free_text=bool(row.allow_free_text),
            response=load_object(str(row.response_json)) if row.response_json else None,
            expires_at=row.expires_at,
        )
