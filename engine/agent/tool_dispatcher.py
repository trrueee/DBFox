"""Durable tool-call admission, execution, and settlement."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.execution_authority import (
    ApprovalAuthorityError,
    ApprovalAuthorityVerifier,
)
from engine.agent.observation import (
    Observation,
    ObservationStatus,
    serialize_model_observation,
)
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.artifact import (
    ArtifactDraftContractError,
    ArtifactRepository,
)
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.session import SessionLease
from engine.agent.tool import ToolInvocation
from engine.agent.turn import ModelToolCall
from engine.agent.working_state import RunWorkingStateAssembler
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.errors import ToolInputError
from engine.models import AgentApproval, AgentRun, AgentToolInvocation, AgentTurn
from engine.policy.authority import ExecutionAuthority
from engine.policy.gate import PolicyGate
from engine.query_registry import QUERY_REGISTRY
from engine.tools.materialization import (
    ToolMaterialization,
    ToolVersionMismatch,
    require_current_tool,
    require_reconciliation_tool,
)
from engine.tools.runtime import ToolExecutor, ToolRegistry, ToolRuntime
from engine.tools.runtime.resource_context import build_tool_scope_context
from engine.tools.runtime.base import (
    BaseTool,
    ControlCommand,
    ControlCommandContext,
    ControlDisposition,
    ToolRecoveryPolicy,
)
from engine.tools.runtime.executor import ToolExecutionControl
from engine.tools.runtime.observation import ToolObservationProjection
from engine.tools.runtime.result import ToolResult


logger = logging.getLogger("dbfox.agent.tool_dispatcher")
_OUTPUT_CONTRACT_ERROR = "Tool output did not match its declared contract."
_OUTPUT_CONTRACT_SUMMARY = "工具输出未通过合同校验。"


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    datasource_id: str
    datasource_generation: int
    question: str
    session_id: str
    run_id: str
    execution_id: str
    execution_mode: str


class ToolDispatchOutcome(StrEnum):
    SETTLED = "settled"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"


@dataclass(frozen=True)
class TransientToolOutput:
    """Provider input retained only in RunLoop memory for the current Run."""

    call_id: str
    output: str


@dataclass(frozen=True)
class ToolDispatchResult:
    outcome: ToolDispatchOutcome
    provider_output: TransientToolOutput | None = None


@dataclass(frozen=True)
class _PreparedToolExecution:
    tool: BaseTool
    state: dict[str, Any]
    request: ToolRequest
    execution_authority: ExecutionAuthority | None
    needs_reconciliation: bool


class ToolDispatcher:
    """Own the durable boundary around model-authored tool calls."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        registry: ToolRegistry,
        definition: AgentDefinition,
        executor: ToolExecutor,
    ) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.definition = definition
        self.executor = executor
        self.approval_authority = ApprovalAuthorityVerifier()

    def request_and_execute(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        call: ModelToolCall,
        materialization: ToolMaterialization,
        control: LeaseAwareRunControl,
    ) -> ToolDispatchResult:
        try:
            materialization.require(call.name)
        except KeyError:
            return self._reject_unavailable_call(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                call=call,
                materialization=materialization,
                error_code="UNKNOWN_TOOL",
                summary=(
                    "The requested tool is not available in this Turn. Use only a "
                    "tool from the supplied function definitions."
                ),
            )
        registered_function = self.registry.get(call.name)
        if registered_function is None:
            return self._reject_unavailable_call(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                call=call,
                materialization=materialization,
                error_code="TOOL_VERSION_CHANGED",
                summary=(
                    "The frozen tool implementation is no longer installed. Plan a "
                    "new call using the currently supplied function definitions."
                ),
            )
        with self.session_factory() as db:
            run = RunRepository(db).get(run_id)
            state = RunWorkingStateAssembler(
                db,
                self.definition,
            ).build(run)
            policy_decision = PolicyGate(self.registry, db).check(
                state,
                call.name,
                call.arguments,
                self.definition.execution_mode,
            )
            decision = policy_decision.model_dump(mode="json")
            invocations = ToolInvocationRepository(db)
            invocation = invocations.request(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                provider_call_id=call.id,
                tool_name=call.name,
                raw_input=call.arguments,
                materialization=materialization,
                policy_decision=decision,
            )
            if invocation.status.value == "waiting_approval":
                approvals = ApprovalRepository(db)
                if approvals.was_rejected_without_new_input(
                    run_id=run_id,
                    tool_name=invocation.tool_name,
                    input_hash=invocation.authorized_input_hash,
                ):
                    observation = invocations.settle(
                        lease=lease,
                        invocation_id=invocation.id,
                        status=ObservationStatus.REJECTED,
                        model_visible_summary=(
                            "The user already rejected this exact action. Do not request it again "
                            "unless the user provides new direction; choose a safe alternative or "
                            "explain the limitation."
                        ),
                        error_code="APPROVAL_PREVIOUSLY_REJECTED",
                        error_message="The exact action was already rejected by the user.",
                    )
                    db.commit()
                    return self._settled_result(call.id, observation)
                approvals.request(
                    lease=lease,
                    invocation_id=invocation.id,
                    policy_decision=decision,
                )
                SessionRepository(db).release(lease=lease)
                db.commit()
                return ToolDispatchResult(ToolDispatchOutcome.WAITING_APPROVAL)
            if invocation.status.value == "rejected":
                observation = invocations.settle(
                    lease=lease,
                    invocation_id=invocation.id,
                    status=ObservationStatus.REJECTED,
                    model_visible_summary=str(
                        decision.get("reason") or "Tool request rejected."
                    ),
                    error_code=(policy_decision.error_code or "TOOL_POLICY_REJECTED"),
                    error_message="Tool request rejected.",
                )
                db.commit()
                return self._settled_result(call.id, observation)
            if isinstance(registered_function, ControlCommand):
                parsed = registered_function.input_model.model_validate(
                    invocation.authorized_input
                )
                try:
                    command_result = registered_function.handle(
                        parsed,
                        ControlCommandContext(
                            db=db,
                            lease=lease,
                            run_id=run_id,
                            turn_id=turn_id,
                            invocation_id=invocation.id,
                        ),
                    )
                except ToolInputError as exc:
                    safe_message = exc.message.strip() or "The tool input is invalid."
                    observation = invocations.settle(
                        lease=lease,
                        invocation_id=invocation.id,
                        status=ObservationStatus.REJECTED,
                        model_visible_summary=safe_message,
                        contributes_progress=False,
                        error_code="TOOL_INPUT_INVALID",
                        error_message="The tool input is invalid.",
                    )
                    db.commit()
                    return self._settled_result(call.id, observation)
                if command_result.disposition is ControlDisposition.WAITING_INPUT:
                    SessionRepository(db).release(lease=lease)
                    db.commit()
                    return ToolDispatchResult(ToolDispatchOutcome.WAITING_INPUT)
                if command_result.output is None:
                    raise RuntimeError(
                        f"Control command {call.name} settled without output"
                    )
                output = registered_function.output_model.model_validate(
                    command_result.output
                ).model_dump(mode="json")
                observation = invocations.settle(
                    lease=lease,
                    invocation_id=invocation.id,
                    status=ObservationStatus.SUCCEEDED,
                    model_visible_summary=command_result.summary,
                    facts={
                        **command_result.facts,
                        "output": output,
                    },
                    contributes_progress=False,
                )
                db.commit()
                return self._settled_result(call.id, observation)
            db.commit()

        provider_output = self.execute_requested(
            lease,
            invocation,
            control=control,
        )
        return ToolDispatchResult(
            ToolDispatchOutcome.SETTLED,
            provider_output=provider_output,
        )

    def _reject_unavailable_call(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        call: ModelToolCall,
        materialization: ToolMaterialization,
        error_code: str,
        summary: str,
    ) -> ToolDispatchResult:
        with self.session_factory() as db:
            observation = ToolInvocationRepository(db).reject_unmaterialized(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                provider_call_id=call.id,
                tool_name=call.name,
                materialization=materialization,
                error_code=error_code,
                model_visible_summary=summary,
            )
            db.commit()
        return self._settled_result(call.id, observation)

    def execute_requested(
        self,
        lease: SessionLease,
        invocation: ToolInvocation,
        *,
        control: LeaseAwareRunControl,
    ) -> TransientToolOutput | None:
        prepared = self._prepare_execution(lease, invocation)
        if prepared is None:
            return None
        result = self._run_prepared_execution(
            lease,
            invocation,
            prepared=prepared,
            control=control,
        )
        if result is None:
            return None
        try:
            provider_output = self._settle_execution_result(
                lease,
                invocation,
                tool=prepared.tool,
                result=result,
                needs_reconciliation=prepared.needs_reconciliation,
            )
        except ArtifactDraftContractError as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.TOOL_RUNTIME_OUTPUT_CONTRACT_FAILED,
                exc=exc,
                fingerprint_subject={
                    "tool": invocation.tool_name,
                    "version": invocation.tool_version,
                    "error_type": type(exc).__name__,
                },
            )
            provider_output = self._settle_execution_result(
                lease,
                invocation,
                tool=prepared.tool,
                result=result.model_copy(
                    update={
                        "status": "failed",
                        "output": {
                            "status": "failed",
                            "error_code": "TOOL_OUTPUT_CONTRACT_FAILED",
                        },
                        "artifact_drafts": [],
                        "error": _OUTPUT_CONTRACT_ERROR,
                        "error_code": "TOOL_OUTPUT_CONTRACT_FAILED",
                    }
                ),
                needs_reconciliation=prepared.needs_reconciliation,
            )
        control.checkpoint()
        return provider_output

    def _prepare_execution(
        self,
        lease: SessionLease,
        invocation: ToolInvocation,
    ) -> _PreparedToolExecution | None:
        execution_authority: ExecutionAuthority | None = None
        with self.session_factory() as db:
            run = RunRepository(db).get(invocation.run_id)
            state = RunWorkingStateAssembler(
                db,
                self.definition,
            ).build(run)
            request = self._tool_request(run)
            materialization = self._turn_materialization(db, invocation.turn_id)
            needs_reconciliation = (
                invocation.recovery_policy is ToolRecoveryPolicy.RECONCILE
                and invocation.attempt_count > 0
            )
            try:
                resolve_tool = (
                    require_reconciliation_tool
                    if needs_reconciliation
                    else require_current_tool
                )
                tool = resolve_tool(
                    self.registry,
                    materialization,
                    name=invocation.tool_name,
                    version=invocation.tool_version,
                )
                if not isinstance(tool, BaseTool):
                    raise ToolVersionMismatch(
                        f"{invocation.tool_name} is no longer an executable data tool"
                    )
            except ToolVersionMismatch:
                interrupted = invocation.attempt_count > 0
                ToolInvocationRepository(db).settle(
                    lease=lease,
                    invocation_id=invocation.id,
                    status=(
                        ObservationStatus.UNKNOWN
                        if interrupted
                        else ObservationStatus.FAILED
                    ),
                    model_visible_summary=(
                        "The interrupted tool implementation is no longer available, "
                        "so its outcome cannot be proven."
                        if interrupted
                        else (
                            "The tool implementation changed while this call was pending. "
                            "Plan a new call using the currently available tool contract."
                        )
                    ),
                    error_code=(
                        "TOOL_OUTCOME_UNKNOWN"
                        if interrupted
                        else "TOOL_VERSION_CHANGED"
                    ),
                    error_message=(
                        "The current tool version does not match the Turn's frozen version."
                    ),
                    retryable=False,
                )
                db.commit()
                return None

            if not needs_reconciliation:
                authorized, execution_authority = self._authorize_and_mark_running(
                    db,
                    lease=lease,
                    invocation=invocation,
                    run=run,
                    state=state,
                    interrupted_outcome_unresolved=invocation.attempt_count > 0,
                )
                if not authorized:
                    db.commit()
                    return None
            db.commit()

        return _PreparedToolExecution(
            tool=tool,
            state=state,
            request=request,
            execution_authority=execution_authority,
            needs_reconciliation=needs_reconciliation,
        )

    def _run_prepared_execution(
        self,
        lease: SessionLease,
        invocation: ToolInvocation,
        *,
        prepared: _PreparedToolExecution,
        control: LeaseAwareRunControl,
    ) -> ToolResult | None:
        tool = prepared.tool
        state = prepared.state
        request = prepared.request
        execution_authority = prepared.execution_authority

        def execute_leaf(tool_control: ToolExecutionControl) -> ToolResult:
            with self.session_factory() as leaf_db:
                scope_refs, resources = build_tool_scope_context(
                    leaf_db,
                    request,
                    tool,
                )
                result = ToolRuntime(self.registry).invoke(
                    tool_name=invocation.tool_name,
                    raw_input=invocation.authorized_input,
                    request=request,
                    db=leaf_db,
                    cancellation_probe=tool_control.is_cancelled,
                    deadline=tool_control.deadline,
                    execution_authority=execution_authority,
                    scope_refs=scope_refs,
                    resources=resources,
                    idempotency_key=invocation.idempotency_key,
                )
                if result.status == "success" and not tool_control.is_cancelled():
                    leaf_db.commit()
                    return result
                leaf_db.rollback()
                if tool_control.is_cancelled() and result.error_code is None:
                    return result.model_copy(
                        update={
                            "status": "failed",
                            "output": None,
                            "error": "Tool execution was cancelled.",
                            "error_code": "TOOL_CANCELLED",
                        }
                    )
                return result

        def record_attempt(attempt: int) -> None:
            if attempt <= 1:
                return
            with self.session_factory() as retry_db:
                ToolInvocationRepository(retry_db).record_retry(
                    lease=lease,
                    invocation_id=invocation.id,
                )
                retry_db.commit()

        result: ToolResult | None = None
        if prepared.needs_reconciliation:

            def reconcile_leaf(tool_control: ToolExecutionControl) -> ToolResult:
                with self.session_factory() as leaf_db:
                    scope_refs, resources = build_tool_scope_context(
                        leaf_db,
                        request,
                        tool,
                    )
                    reconciled = ToolRuntime(self.registry).reconcile(
                        tool_name=invocation.tool_name,
                        raw_input=invocation.authorized_input,
                        request=request,
                        db=leaf_db,
                        idempotency_key=invocation.idempotency_key,
                        cancellation_probe=tool_control.is_cancelled,
                        deadline=tool_control.deadline,
                        execution_authority=execution_authority,
                        scope_refs=scope_refs,
                        resources=resources,
                    )
                    leaf_db.rollback()
                    return reconciled

            result = self.executor.execute(
                tool=tool,
                scope_key=invocation.run_id,
                operation=reconcile_leaf,
                should_cancel=control.is_cancel_requested,
                cancel_action=None,
                on_attempt=None,
                deadline=control.deadline,
            )
            if result.error_code == "TOOL_RECONCILIATION_NOT_APPLIED":
                with self.session_factory() as db:
                    try:
                        require_current_tool(
                            self.registry,
                            self._turn_materialization(db, invocation.turn_id),
                            name=invocation.tool_name,
                            version=invocation.tool_version,
                        )
                    except ToolVersionMismatch:
                        return ToolResult(
                            name=invocation.tool_name,
                            status="failed",
                            error=(
                                "The tool contract changed after the interrupted action "
                                "was proven not to have run. Submit a new tool call."
                            ),
                            error_code="TOOL_VERSION_CHANGED",
                            latency_ms=result.latency_ms,
                        )
                    run = RunRepository(db).get(invocation.run_id)
                    state = RunWorkingStateAssembler(
                        db,
                        self.definition,
                    ).build(run)
                    authorized, execution_authority = self._authorize_and_mark_running(
                        db,
                        lease=lease,
                        invocation=invocation,
                        run=run,
                        state=state,
                        interrupted_outcome_unresolved=False,
                    )
                    if not authorized:
                        db.commit()
                        return None
                    db.commit()
                result = None

        execution_id = str(state.get("execution_id") or "")

        if execution_id:
            QUERY_REGISTRY.reserve(execution_id, request.datasource_id)

        def cancel_query() -> None:
            if execution_id:
                QUERY_REGISTRY.cancel(execution_id)

        try:
            if result is None:
                result = self.executor.execute(
                    tool=tool,
                    scope_key=invocation.run_id,
                    operation=execute_leaf,
                    should_cancel=control.is_cancel_requested,
                    cancel_action=cancel_query if execution_id else None,
                    on_attempt=record_attempt,
                    deadline=control.deadline,
                )
        finally:
            if execution_id:
                QUERY_REGISTRY.unregister(execution_id)

        return result

    def _settle_execution_result(
        self,
        lease: SessionLease,
        invocation: ToolInvocation,
        *,
        tool: BaseTool,
        result: ToolResult,
        needs_reconciliation: bool,
    ) -> TransientToolOutput:
        with self.session_factory() as db:
            artifacts = []
            output = result.output or {}
            if result.status == "success":
                try:
                    artifacts = ArtifactRepository(db).persist_drafts(
                        lease=lease,
                        run_id=invocation.run_id,
                        turn_id=invocation.turn_id,
                        invocation_id=invocation.id,
                        tool_name=invocation.tool_name,
                        drafts=result.artifact_drafts,
                    )
                except ArtifactDraftContractError:
                    db.rollback()
                    raise
            artifact_ids = [item.id for item in artifacts]
            if (
                tool.spec.semantics.publishes_artifact_references
                and result.status == "success"
            ):
                for referenced_id in output.get("referenced_artifact_ids") or []:
                    value = str(referenced_id).strip()
                    if value and value not in artifact_ids:
                        artifact_ids.append(value)
            observation = (
                ToolObservationProjection(summary=_OUTPUT_CONTRACT_SUMMARY)
                if result.error_code == "TOOL_OUTPUT_CONTRACT_FAILED"
                else tool.project_observation(
                    status=result.status,
                    output=output,
                    artifacts=artifacts,
                )
            )
            status = self._observation_status(
                result,
                needs_reconciliation=needs_reconciliation,
            )
            succeeded = status is ObservationStatus.SUCCEEDED
            retryable = (
                result.status != "success"
                and tool.execution.recovery is ToolRecoveryPolicy.RETRY_SAFE
                and tool.execution.retryable
                and result.error_code
                not in {
                    "TOOL_CANCELLED",
                    "TOOL_TIMEOUT",
                    "TOOL_OUTPUT_CONTRACT_FAILED",
                }
            )
            error_code = (
                None
                if result.status == "success"
                else (result.error_code or "TOOL_EXECUTION_FAILED")
            )
            ToolInvocationRepository(db).settle(
                lease=lease,
                invocation_id=invocation.id,
                status=status,
                model_visible_summary=observation.summary,
                artifact_ids=artifact_ids,
                facts=observation.facts,
                capabilities=(
                    tuple(
                        str(capability) for capability in tool.spec.semantics.produces
                    )
                    if succeeded
                    else ()
                ),
                contributes_progress=(
                    succeeded and tool.spec.semantics.contributes_progress
                ),
                error_code=error_code,
                error_message=result.error,
                retryable=retryable,
            )
            db.commit()
            provider_facts = (
                observation.provider_payload
                if succeeded and observation.provider_payload
                else observation.facts
            )
            return TransientToolOutput(
                call_id=str(invocation.provider_call_id),
                output=serialize_model_observation(
                    status=status.value,
                    summary=observation.summary,
                    facts=provider_facts,
                    artifact_ids=artifact_ids,
                    retryable=retryable,
                    error_code=error_code,
                    error_message=result.error,
                ),
            )

    @staticmethod
    def _settled_result(
        call_id: str,
        observation: Observation,
    ) -> ToolDispatchResult:
        return ToolDispatchResult(
            ToolDispatchOutcome.SETTLED,
            provider_output=TransientToolOutput(
                call_id=call_id,
                output=observation.model_output,
            ),
        )

    @staticmethod
    def _observation_status(
        result: ToolResult,
        *,
        needs_reconciliation: bool,
    ) -> ObservationStatus:
        if result.status == "success":
            return ObservationStatus.SUCCEEDED
        if result.error_code == "TOOL_CANCELLED":
            return ObservationStatus.CANCELLED
        outcome_unknown = result.error_code in {
            "TOOL_OUTCOME_UNKNOWN",
            "TOOL_TIMEOUT",
        }
        if outcome_unknown and needs_reconciliation:
            return ObservationStatus.UNKNOWN
        return ObservationStatus.FAILED

    def _authorize_and_mark_running(
        self,
        db: Session,
        *,
        lease: SessionLease,
        invocation: ToolInvocation,
        run: AgentRun,
        state: dict[str, Any],
        interrupted_outcome_unresolved: bool,
    ) -> tuple[bool, ExecutionAuthority | None]:
        """Revalidate authority immediately before a side-effecting attempt."""

        decision = PolicyGate(self.registry, db).check(
            state,
            invocation.tool_name,
            invocation.authorized_input,
            self.definition.execution_mode,
        )
        invocation_row = db.get(AgentToolInvocation, invocation.id)
        approval = (
            db.get(AgentApproval, invocation_row.approval_id)
            if invocation_row is not None and invocation_row.approval_id
            else None
        )
        execution_authority = None
        approved_request = (
            decision.status == "approval_required"
            and approval is not None
            and approval.status == "approved"
        )
        if approved_request:
            try:
                execution_authority = self.approval_authority.verify(
                    invocation=invocation,
                    approval=approval,
                    decision=decision,
                    datasource_generation=int(run.datasource_generation),
                )
            except ApprovalAuthorityError as exc:
                ToolInvocationRepository(db).settle(
                    lease=lease,
                    invocation_id=invocation.id,
                    status=(
                        ObservationStatus.UNKNOWN
                        if interrupted_outcome_unresolved
                        else ObservationStatus.REJECTED
                    ),
                    model_visible_summary=(
                        "The interrupted action cannot be retried under the current "
                        "approval, so its outcome remains unknown."
                        if interrupted_outcome_unresolved
                        else (
                            "The approval no longer matches the canonical action. "
                            "Revalidate the action before requesting approval again."
                        )
                    ),
                    error_code=(
                        "TOOL_OUTCOME_UNKNOWN"
                        if interrupted_outcome_unresolved
                        else "TOOL_APPROVAL_STALE"
                    ),
                    error_message=str(exc),
                )
                return False, None
        if decision.status != "allowed" and execution_authority is None:
            ToolInvocationRepository(db).settle(
                lease=lease,
                invocation_id=invocation.id,
                status=(
                    ObservationStatus.UNKNOWN
                    if interrupted_outcome_unresolved
                    else ObservationStatus.REJECTED
                ),
                model_visible_summary=(
                    "The interrupted action cannot be retried under the current "
                    "policy, so its outcome remains unknown."
                    if interrupted_outcome_unresolved
                    else decision.reason
                ),
                error_code=(
                    "TOOL_OUTCOME_UNKNOWN"
                    if interrupted_outcome_unresolved
                    else "TOOL_POLICY_CHANGED"
                ),
                error_message="Tool permission changed before execution.",
            )
            return False, None
        ToolInvocationRepository(db).mark_running(
            lease=lease,
            invocation_id=invocation.id,
        )
        return True, execution_authority

    def pending_invocations(self, run_id: str) -> list[ToolInvocation]:
        with self.session_factory() as db:
            return ToolInvocationRepository(db).requested_for_run(run_id)

    @staticmethod
    def tool_budget_usage(db: Session, run_id: str) -> int:
        """Count calls using the same frozen interaction semantics as dispatch."""
        rows = db.execute(
            select(
                AgentToolInvocation.tool_name,
                AgentTurn.tool_materialization_json,
            )
            .join(AgentTurn, AgentTurn.id == AgentToolInvocation.turn_id)
            .where(AgentToolInvocation.run_id == run_id)
        ).all()
        count = 0
        for tool_name, materialization_json in rows:
            materialization = ToolMaterialization.model_validate_json(
                str(materialization_json)
            )
            if materialization.require(str(tool_name)).kind != "control":
                count += 1
        return count

    @staticmethod
    def _turn_materialization(
        db: Session,
        turn_id: str,
    ) -> ToolMaterialization:
        turn = db.get(AgentTurn, turn_id)
        if turn is None:
            raise ValueError("ToolInvocation references a missing Turn")
        return ToolMaterialization.model_validate_json(
            str(turn.tool_materialization_json)
        )

    def _tool_request(self, run: AgentRun) -> ToolRequest:
        return ToolRequest(
            datasource_id=str(run.datasource_id),
            datasource_generation=int(run.datasource_generation),
            question=str(run.question),
            session_id=str(run.session_id),
            run_id=str(run.id),
            execution_id=str(run.execution_id or ""),
            execution_mode=self.definition.execution_mode,
        )
