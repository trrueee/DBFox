"""Atomic Run terminalization and evidence composition."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from engine.agent.artifact import ArtifactSelectionSuggestion, ArtifactType
from engine.agent.evidence import (
    CITATION_PATTERN,
    Evidence,
    EvidenceLocator,
    citation_references,
    has_invalid_citation_syntax,
)
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.plan import PlanRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.response import (
    AnswerCandidate,
    ComposedResponse,
    CompletionDisposition,
    CompletionLimitationCode,
    ResponseComposer,
)
from engine.agent.session import SessionLease
from engine.agent.plan import PlanStatus
from engine.agent.turn import ModelTurnResult
from engine.app.safe_errors import fixed_error_detail


class Terminalizer:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        responses: ResponseComposer | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.responses = responses or ResponseComposer()

    def complete(
        self,
        lease: SessionLease,
        run_id: str,
        result: ModelTurnResult,
        *,
        disposition: CompletionDisposition,
        limitation_codes: list[CompletionLimitationCode],
        evidence_artifact_ids: list[str],
    ) -> bool:
        with self.session_factory() as db:
            partial = disposition is CompletionDisposition.BOUNDED_PARTIAL
            artifacts = ArtifactRepository(db).list_for_run(run_id)
            result_artifacts = [
                item for item in artifacts if item.type is ArtifactType.RESULT_VIEW
            ]
            final_text = (
                result.answer_text if result.has_completed_answer_candidate else ""
            )
            text = final_text or (
                "分析已完成，但仅得到部分结果。" if partial else "分析已完成。"
            )
            if has_invalid_citation_syntax(text):
                raise ValueError(
                    "Terminal answer contains malformed DBFox citation markup"
                )
            result_by_id = {item.id: item for item in result_artifacts}
            references = citation_references(text)
            bound_artifact_ids = [
                artifact_id
                for artifact_id in evidence_artifact_ids
                if artifact_id in result_by_id
            ]
            if partial and not bound_artifact_ids and result_artifacts:
                bound_artifact_ids = [result_artifacts[-1].id]
            cited_ids = {item_id for item_id, _, _ in references}
            missing_citations = [
                artifact_id
                for artifact_id in bound_artifact_ids
                if artifact_id not in cited_ids
            ]
            if missing_citations:
                citations = " ".join(
                    f"{{{{cite:{artifact_id}}}}}" for artifact_id in missing_citations
                )
                text = f"{text}\n\n来源：{citations}"
            text = CITATION_PATTERN.sub(
                lambda match: match.group(0) if match.group(1) in result_by_id else "",
                text,
            )
            references = citation_references(text)
            evidence = []
            for citation_index, (artifact_id, start, end) in enumerate(
                references, start=1
            ):
                item = result_by_id[artifact_id]
                claim = str(
                    _claim_text_for_citation(text, start, end)
                    or item.summary
                    or item.title
                ).strip()
                locator_value = {
                    "artifact_id": item.id,
                    "claim": claim,
                    "citation_index": citation_index,
                    "answer_start": start,
                    "answer_end": end,
                }
                evidence.append(
                    Evidence(
                        id=f"evidence_{uuid4().hex}",
                        session_id=lease.session_id,
                        run_id=run_id,
                        claim_id=f"claim:{run_id}:{citation_index}:{item.id}",
                        artifact_id=item.id,
                        label=claim,
                        query_fingerprint=str(
                            item.payload.get("queryFingerprint") or ""
                        ),
                        observed_at=_observed_at(item.payload.get("executedAt")),
                        locator=EvidenceLocator(
                            kind="artifact",
                            value=locator_value,
                        ),
                        value=None,
                    )
                )
            answer = AnswerCandidate(
                text=text,
                evidence=evidence,
                caveats=(
                    [_limitation_caveat(code) for code in limitation_codes]
                    if partial
                    else []
                ),
            )
            suggestion = (
                ArtifactSelectionSuggestion(
                    artifact_id=result_artifacts[-1].id,
                    reason="本次分析的主要查询结果",
                )
                if result_artifacts
                else None
            )
            response = self.responses.compose(
                session_id=lease.session_id,
                run_id=run_id,
                completion_disposition=disposition,
                limitation_codes=limitation_codes,
                answer=answer,
                artifacts=artifacts,
                selection_suggestion=suggestion,
            )
            completed = self.complete_in_session(
                db,
                lease,
                response,
                terminal_turn_id=(
                    result.turn_id if result.completed_answer_messages else None
                ),
                terminal_output_index=(
                    result.completed_answer_messages[-1].output_index
                    if result.completed_answer_messages
                    else None
                ),
                plan_status=PlanStatus.PARTIAL if partial else PlanStatus.COMPLETED,
                memory_delta={
                    "evidence_references": [
                        {
                            "evidence_id": item.id,
                            "artifact_id": item.artifact_id,
                            "query_fingerprint": item.query_fingerprint,
                            "observed_at": item.observed_at.isoformat(),
                            "run_id": run_id,
                        }
                        for item in evidence
                    ]
                },
            )
            db.commit()
            return completed

    @staticmethod
    def complete_in_session(
        db: Session,
        lease: SessionLease,
        response: ComposedResponse,
        *,
        terminal_turn_id: str | None = None,
        terminal_output_index: int | None = None,
        plan_status: PlanStatus = PlanStatus.COMPLETED,
        memory_delta: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically settle the Plan and persist the canonical terminal response."""

        if plan_status not in {PlanStatus.COMPLETED, PlanStatus.PARTIAL}:
            raise ValueError(
                "Successful Run terminalization requires a completed or partial Plan"
            )
        runs = RunRepository(db)
        if runs.has_pending_steering_inputs(lease=lease, run_id=response.run_id):
            return False
        PlanRepository(db).terminalize(
            lease=lease,
            run_id=response.run_id,
            status=plan_status,
        )
        runs.complete(
            lease=lease,
            response=response,
            terminal_turn_id=terminal_turn_id,
            terminal_output_index=terminal_output_index,
            memory_delta=memory_delta or {},
        )
        return True

    @staticmethod
    def cancel_in_session(db: Session, lease: SessionLease, run_id: str) -> None:
        """Atomically settle every durable child before cancelling a Run."""

        ApprovalRepository(db).cancel_pending_for_run(
            lease=lease,
            run_id=run_id,
        )
        QuestionRepository(db).cancel_pending_for_run(
            lease=lease,
            run_id=run_id,
        )
        ToolInvocationRepository(db).cancel_active_for_run(
            lease=lease,
            run_id=run_id,
        )
        runs = RunRepository(db)
        runs.cancel_active_turns(lease=lease, run_id=run_id)
        PlanRepository(db).terminalize(
            lease=lease,
            run_id=run_id,
            status=PlanStatus.CANCELLED,
        )
        runs.cancel(lease=lease, run_id=run_id)

    def cancelled(self, lease: SessionLease, run_id: str) -> bool:
        with self.session_factory() as db:
            repository = RunRepository(db)
            requested = repository.cancellation_requested(lease=lease, run_id=run_id)
            if requested:
                self.cancel_in_session(db, lease, run_id)
                db.commit()
            return requested

    @staticmethod
    def fail_in_session(
        db: Session,
        lease: SessionLease,
        run_id: str,
        code: str,
        message: str,
    ) -> None:
        """Atomically settle every durable child before failing a Run."""

        runs = RunRepository(db)
        if runs.cancellation_requested(lease=lease, run_id=run_id):
            Terminalizer.cancel_in_session(db, lease, run_id)
            return
        public_error = fixed_error_detail(code)
        ApprovalRepository(db).cancel_pending_for_run(
            lease=lease,
            run_id=run_id,
        )
        QuestionRepository(db).cancel_pending_for_run(
            lease=lease,
            run_id=run_id,
        )
        ToolInvocationRepository(db).cancel_active_for_run(
            lease=lease,
            run_id=run_id,
        )
        runs.fail_active_turns(
            lease=lease,
            run_id=run_id,
            error_code=public_error["code"],
            error_message=public_error["message"],
        )
        PlanRepository(db).terminalize(
            lease=lease,
            run_id=run_id,
            status=PlanStatus.FAILED,
            summary=public_error["message"],
        )
        runs.fail(
            lease=lease,
            run_id=run_id,
            error_code=public_error["code"],
            message=public_error["message"],
        )

    def fail(self, lease: SessionLease, run_id: str, code: str, message: str) -> None:
        with self.session_factory() as db:
            self.fail_in_session(db, lease, run_id, code, message)
            db.commit()


def _claim_text_for_citation(text: str, start: int, end: int) -> str:
    left = (
        max(
            text.rfind(marker, 0, start)
            for marker in ("\n", "。", "！", "？", ".", "!", "?")
        )
        + 1
    )
    right_candidates = [
        position
        for marker in ("\n", "。", "！", "？", ".", "!", "?")
        if (position := text.find(marker, end)) >= 0
    ]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return CITATION_PATTERN.sub("", text[left:right]).strip()[:1_000]


def _limitation_caveat(code: CompletionLimitationCode) -> str:
    return {
        CompletionLimitationCode.TURN_BUDGET_REACHED: "已达到分析轮次上限，以下为当前可验证结果。",
        CompletionLimitationCode.TOOL_BUDGET_REACHED: "已达到工具调用上限，以下为当前可验证结果。",
        CompletionLimitationCode.TOKEN_BUDGET_REACHED: "已达到 Token 预算，以下为当前可验证结果。",
        CompletionLimitationCode.COST_BUDGET_REACHED: "已达到费用预算，以下为当前可验证结果。",
        CompletionLimitationCode.DEADLINE_REACHED: "已达到运行时限，以下为当前可验证结果。",
        CompletionLimitationCode.INSUFFICIENT_EVIDENCE: "证据仍不完整，以下仅包含当前可验证结果。",
        CompletionLimitationCode.TOOL_REJECTED: "部分操作未获授权，以下为当前可验证结果。",
        CompletionLimitationCode.PROVIDER_LIMIT: "模型服务未能继续，以下为当前可验证结果。",
        CompletionLimitationCode.NO_PROGRESS: "已停止重复尝试，以下为当前可验证结果。",
    }[code]


def _observed_at(value: Any) -> datetime:
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)
