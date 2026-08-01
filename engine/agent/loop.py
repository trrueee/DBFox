"""The single explicit ReAct-style DBFox Agent execution loop."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.agent.completion import CompletionDecision, CompletionGate, CompletionKind
from engine.agent.control import (
    LeaseAwareRunControl,
    ModelPricing,
    RunCancellationRequested,
    RunControlError,
    RunLeaseLost,
    UsageCharge,
)
from engine.agent.context import ContextAssembler
from engine.agent.definition import AgentDefinition, DEFAULT_AGENT_DEFINITION
from engine.agent.events import LiveStreamHub
from engine.agent.progress_guard import ProgressGuard
from engine.agent.prompt import PromptAssembler
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.response import CompletionDisposition, CompletionLimitationCode
from engine.agent.session import SessionLease
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.run_item import RunItemDelta, RunItemType
from engine.agent.turn import (
    ModelTurnResult,
    TurnStreamAssembler,
    TurnStreamCancelled,
    TurnStreamError,
    TurnStreamItem,
    TurnStreamKind,
)
from engine.llm.config import resolve_product_llm_config_from_credential
from engine.models import (
    AgentTurn,
)
from engine.tools.builtin import register_dbfox_tools
from engine.tools.materialization import ToolMaterialization, materialize_tools
from engine.tools.runtime import ToolExecutor, ToolRegistry
from engine.agent.terminalizer import Terminalizer
from engine.agent.working_state import RunWorkingStateAssembler


class ModelAdapter(Protocol):
    def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout_seconds: float | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> Iterable[TurnStreamItem]: ...


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credential_id: str
    api_base: str | None = None
    model_name: str | None = None


@dataclass(frozen=True)
class _PreparedTurn:
    turn_id: str
    messages: list[dict[str, Any]]
    tools: ToolMaterialization
    provider_settings: ProviderSettings


@dataclass
class _ExecutionState:
    control: LeaseAwareRunControl
    provider_settings: ProviderSettings
    pricing: ModelPricing | None
    tool_count: int
    completed_turn_count: int
    last_result: ModelTurnResult = field(default_factory=ModelTurnResult)
    best_answer_result: ModelTurnResult = field(default_factory=ModelTurnResult)

    @property
    def answer_result(self) -> ModelTurnResult:
        if self.best_answer_result.text.strip():
            return self.best_answer_result
        return self.last_result

    def record_result(self, result: ModelTurnResult) -> None:
        self.last_result = result
        if result.message_phase == "final_answer" and result.text.strip():
            self.best_answer_result = result


LIVE_STREAM_HUB = LiveStreamHub()


def _default_model_factory(settings: ProviderSettings) -> ModelAdapter:
    config = resolve_product_llm_config_from_credential(
        llm_credential_id=settings.credential_id,
        api_base=settings.api_base,
        model_name=settings.model_name,
    )
    return OpenAIModelAdapter.from_config(config)


class RunLoop:
    """Dynamic model/tool loop with short transactions around external calls."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        model_factory: Callable[[ProviderSettings], ModelAdapter] = _default_model_factory,
        registry: ToolRegistry | None = None,
        definition: AgentDefinition = DEFAULT_AGENT_DEFINITION,
        live_stream: LiveStreamHub = LIVE_STREAM_HUB,
        tool_executor: ToolExecutor | None = None,
        pricing_resolver: Callable[[ProviderSettings], ModelPricing | None] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.model_factory = model_factory
        self.registry = registry or register_dbfox_tools()
        self.definition = definition
        self.live_stream = live_stream
        self._owns_tool_executor = tool_executor is None
        self.tool_executor = tool_executor or ToolExecutor()
        self.pricing_resolver = pricing_resolver or (lambda _settings: None)
        self.prompts = PromptAssembler()
        self.completion = CompletionGate()
        self.tool_dispatcher = ToolDispatcher(
            session_factory=self.session_factory,
            registry=self.registry,
            definition=self.definition,
            executor=self.tool_executor,
        )
        self.terminalizer = Terminalizer(session_factory=self.session_factory)

    def execute(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        lease_lost: Event | None = None,
    ) -> None:
        state: _ExecutionState | None = None
        try:
            state = self._initialize_execution(
                lease=lease,
                run_id=run_id,
                lease_lost=lease_lost,
            )
            if (
                self.definition.limits.cost_budget_usd is not None
                and state.pricing is None
            ):
                raise RunControlError(
                    "AGENT_COST_PRICING_UNAVAILABLE",
                    "当前模型未配置可核算价格，无法执行带费用上限的分析。",
                )
            state.control.checkpoint()
            self._execute_pending_invocations(lease, run_id, state.control)

            for turn_count in range(
                state.completed_turn_count + 1,
                self.definition.limits.max_turns + 1,
            ):
                state.control.checkpoint()
                prepared = self._prepare_turn(lease, run_id)
                result = self._run_model_turn(
                    lease=lease,
                    run_id=run_id,
                    prepared=prepared,
                    state=state,
                )
                if result is None:
                    continue

                if result.tool_calls:
                    if self._dispatch_tool_calls(
                        lease=lease,
                        run_id=run_id,
                        prepared=prepared,
                        result=result,
                        state=state,
                    ):
                        return
                    if self._stop_if_stalled(
                        lease,
                        run_id,
                        state.answer_result,
                    ):
                        return
                    continue

                with self.session_factory() as db:
                    context = ContextAssembler(db).build(run_id)
                decision = self.completion.evaluate(
                    context=context,
                    model_result=result,
                    turn_count=turn_count,
                    max_turns=self.definition.limits.max_turns,
                )
                if decision.kind in {CompletionKind.CONTINUE, CompletionKind.REPAIR}:
                    self._record_continuation(lease, run_id, decision)
                    if self._stop_if_stalled(
                        lease,
                        run_id,
                        state.answer_result,
                    ):
                        return
                    if decision.kind is CompletionKind.REPAIR:
                        state.control.record_repair()
                    continue
                if decision.kind is CompletionKind.FAIL:
                    self._fail(lease, run_id, "AGENT_INCOMPLETE", decision.reason)
                    return
                partial = decision.kind is CompletionKind.PARTIAL
                self._complete(
                    lease,
                    run_id,
                    result,
                    disposition=(
                        CompletionDisposition.BOUNDED_PARTIAL
                        if partial else CompletionDisposition.COMPLETE
                    ),
                    limitation_codes=(
                        [CompletionLimitationCode.TURN_BUDGET_REACHED]
                        if partial else []
                    ),
                    evidence_artifact_ids=decision.evidence_artifact_ids,
                )
                return
            if not self._complete_for_limit(
                lease,
                run_id,
                state.answer_result,
                code=CompletionLimitationCode.TURN_BUDGET_REACHED,
            ):
                self._fail(lease, run_id, "AGENT_TURN_BUDGET", "分析已达到轮次上限。")
        except RunCancellationRequested:
            self._cancelled(lease, run_id)
        except RunLeaseLost:
            # The replacement worker owns all further durable transitions. The
            # old worker only closes its transient stream and exits.
            return
        except RunControlError as exc:
            limitation = {
                "AGENT_TOKEN_BUDGET": CompletionLimitationCode.TOKEN_BUDGET_REACHED,
                "AGENT_COST_BUDGET": CompletionLimitationCode.COST_BUDGET_REACHED,
                "AGENT_DEADLINE_EXCEEDED": CompletionLimitationCode.DEADLINE_REACHED,
                "AGENT_PROVIDER_RETRY_BUDGET": CompletionLimitationCode.PROVIDER_LIMIT,
                "AGENT_REPAIR_BUDGET": CompletionLimitationCode.INSUFFICIENT_EVIDENCE,
            }.get(exc.code)
            if limitation is None or not self._complete_for_limit(
                lease,
                run_id,
                state.answer_result if state is not None else ModelTurnResult(),
                code=limitation,
            ):
                self._fail(lease, run_id, exc.code, exc.message)
        except Exception:
            self.live_stream.close_run(run_id)
            raise
        finally:
            self.tool_executor.release_scope(run_id)
            self.live_stream.close_run(run_id)

    def _initialize_execution(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        lease_lost: Event | None,
    ) -> _ExecutionState:
        with self.session_factory() as db:
            RunRepository(db).recover_interrupted_turns(lease=lease, run_id=run_id)
            ToolInvocationRepository(db).recover_interrupted(lease=lease, run_id=run_id)
            db.commit()

        with self.session_factory() as db:
            run = RunRepository(db).get(run_id)
            tool_count = self.tool_dispatcher.tool_budget_usage(db, run_id)
            completed_turn_count = int(db.scalar(
                select(func.count()).select_from(AgentTurn).where(
                    AgentTurn.run_id == run_id
                )
            ) or 0)
            latest_answer_turn = db.execute(
                select(AgentTurn)
                .where(
                    AgentTurn.run_id == run_id,
                    AgentTurn.draft_text != "",
                    AgentTurn.message_phase == "final_answer",
                )
                .order_by(AgentTurn.sequence.desc())
                .limit(1)
            ).scalar_one_or_none()
            best_answer_result = (
                ModelTurnResult(
                    text=str(latest_answer_turn.draft_text),
                    message_phase="final_answer",
                    reasoning_summary=str(latest_answer_turn.reasoning_summary or ""),
                )
                if latest_answer_turn is not None
                else ModelTurnResult()
            )
            provider_settings = ProviderSettings(
                credential_id=str(run.llm_credential_id),
                api_base=str(run.api_base) if run.api_base else None,
                model_name=str(run.model_name) if run.model_name else None,
            )
            control = LeaseAwareRunControl(
                run=run,
                limits=self.definition.limits,
                cancellation_probe=lambda: self._cancellation_requested(run_id),
                lease_lost_probe=lease_lost.is_set if lease_lost is not None else None,
            )

        return _ExecutionState(
            control=control,
            provider_settings=provider_settings,
            pricing=self.pricing_resolver(provider_settings),
            tool_count=tool_count,
            completed_turn_count=completed_turn_count,
            best_answer_result=best_answer_result,
        )

    def _execute_pending_invocations(
        self,
        lease: SessionLease,
        run_id: str,
        control: LeaseAwareRunControl,
    ) -> None:
        for invocation in self.tool_dispatcher.pending_invocations(run_id):
            control.checkpoint()
            self.tool_dispatcher.execute_requested(
                lease,
                invocation,
                control=control,
            )

    def _run_model_turn(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        prepared: _PreparedTurn,
        state: _ExecutionState,
    ) -> ModelTurnResult | None:
        adapter = self.model_factory(prepared.provider_settings)
        try:
            state.control.checkpoint()
            result = TurnStreamAssembler().consume(
                self._publish_stream(
                    lease=lease,
                    run_id=run_id,
                    turn_id=prepared.turn_id,
                    control=state.control,
                    items=adapter.stream(
                    messages=prepared.messages,
                    tools=prepared.tools.provider_schemas(),
                    timeout_seconds=state.control.remaining_seconds(),
                    cancellation_probe=state.control.is_cancel_requested,
                ),
                )
            )
        except TurnStreamCancelled as exc:
            state.control.checkpoint()
            raise RunCancellationRequested() from exc
        except TurnStreamError as exc:
            with self.session_factory() as db:
                RunRepository(db).settle_turn(
                    lease=lease,
                    turn_id=prepared.turn_id,
                    result=ModelTurnResult(),
                    error_code="MODEL_PROVIDER_STREAM_FAILED",
                    error_message=str(exc),
                )
                db.commit()
            state.control.record_provider_failure()
            return None

        state.record_result(result)
        budget_error: RunControlError | None = None
        try:
            charge = state.control.charge_usage(result.usage, pricing=state.pricing)
        except RunControlError as exc:
            budget_error = exc
            charge = self._fallback_usage_charge(result, state.pricing)

        with self.session_factory() as db:
            RunRepository(db).settle_turn(
                lease=lease,
                turn_id=prepared.turn_id,
                result=result,
                input_tokens=charge.input_tokens,
                output_tokens=charge.output_tokens,
                total_tokens=charge.total_tokens,
                cost_usd=charge.cost_usd,
            )
            db.commit()
        if budget_error is not None:
            raise budget_error
        return result

    @staticmethod
    def _fallback_usage_charge(
        result: ModelTurnResult,
        pricing: ModelPricing | None,
    ) -> UsageCharge:
        input_tokens = max(
            0,
            int(
                result.usage.get(
                    "prompt_tokens",
                    result.usage.get("input_tokens", 0),
                ) or 0
            ),
        )
        output_tokens = max(
            0,
            int(
                result.usage.get(
                    "completion_tokens",
                    result.usage.get("output_tokens", 0),
                ) or 0
            ),
        )
        total_tokens = max(
            0,
            int(result.usage.get("total_tokens", input_tokens + output_tokens) or 0),
        )
        return UsageCharge(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=(
                pricing.charge(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                if pricing is not None
                else 0.0
            ),
        )

    def _dispatch_tool_calls(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        prepared: _PreparedTurn,
        result: ModelTurnResult,
        state: _ExecutionState,
    ) -> bool:
        for call in result.tool_calls:
            state.control.checkpoint()
            counts_toward_budget = prepared.tools.require(call.name).kind != "control"
            if (
                counts_toward_budget
                and state.tool_count >= self.definition.limits.max_tool_invocations
            ):
                if not self._complete_for_limit(
                    lease,
                    run_id,
                    state.answer_result,
                    code=CompletionLimitationCode.TOOL_BUDGET_REACHED,
                ):
                    self._fail(
                        lease,
                        run_id,
                        "AGENT_TOOL_BUDGET",
                        "工具调用已达到本次分析上限。",
                    )
                return True

            outcome = self.tool_dispatcher.request_and_execute(
                lease=lease,
                run_id=run_id,
                turn_id=prepared.turn_id,
                call=call,
                materialization=prepared.tools,
                control=state.control,
            )
            if counts_toward_budget:
                state.tool_count += 1
            if outcome in {
                ToolDispatchOutcome.WAITING_APPROVAL,
                ToolDispatchOutcome.WAITING_INPUT,
            }:
                return True
        return False

    def _record_continuation(
        self,
        lease: SessionLease,
        run_id: str,
        decision: CompletionDecision,
    ) -> None:
        with self.session_factory() as db:
            repository = RunRepository(db)
            repository.discard_answer_draft(lease=lease, run_id=run_id)
            repository.record_focus(
                lease=lease,
                run_id=run_id,
                kind=decision.kind.value,
                reason=decision.reason,
                missing=decision.missing,
            )
            if decision.kind is CompletionKind.REPAIR:
                repository.record_repair(
                    lease=lease,
                    run_id=run_id,
                    reason=decision.reason,
                    missing=decision.missing,
                )
            db.commit()

    def close(self) -> None:
        if self._owns_tool_executor:
            self.tool_executor.close(wait=False)

    def _prepare_turn(self, lease: SessionLease, run_id: str) -> _PreparedTurn:
        with self.session_factory() as db:
            # Steer inputs become durable Run-scoped messages at this boundary.
            # ContextAssembler reads the consumed inputs from the same transaction,
            # so queued inputs belonging to later Runs cannot leak into this Turn.
            SessionRepository(db).consume_steering_inputs(lease=lease, run_id=run_id)
            run = RunRepository(db).get(run_id)
            context = ContextAssembler(db).build(run_id)
            state = RunWorkingStateAssembler(
                db,
                self.definition,
            ).build(run)
            groups = set(state.get("allowed_tool_groups") or self.definition.allowed_tool_groups)
            tools = materialize_tools(
                self.registry, allowed_groups=groups, execution_mode=self.definition.execution_mode,
            )
            tool_schemas = tools.provider_schemas()
            prompt = self.prompts.assemble(
                definition=self.definition,
                context=context,
                tool_schemas=tool_schemas,
            )
            turn = SessionRepository(db).start_turn(
                lease=lease, run_id=run_id,
                agent_definition_version=self.definition.version,
                prompt_version=prompt.version, prompt_hash=prompt.hash,
                context_snapshot={
                    **context.model_dump(mode="json"),
                    "prompt_budget": prompt.budget,
                }, context_hash=context.hash,
                tool_materialization=tools.model_dump(mode="json"),
                tool_materialization_hash=tools.hash,
                provider="openai-responses", model_name=str(run.model_name or ""),
            )
            settings = ProviderSettings(
                credential_id=str(run.llm_credential_id),
                api_base=str(run.api_base) if run.api_base else None,
                model_name=str(run.model_name) if run.model_name else None,
            )
            db.commit()
            return _PreparedTurn(
                turn_id=str(turn.id),
                messages=list(prompt.messages),
                tools=tools,
                provider_settings=settings,
            )

    def _publish_stream(
        self, *, lease: SessionLease, run_id: str, turn_id: str,
        items: Iterable[TurnStreamItem], control: LeaseAwareRunControl,
    ) -> Iterable[TurnStreamItem]:
        text = ""
        flushed_bytes = 0
        last_flush = time.monotonic()
        answer_revision = 0
        answer_item_id = f"message:{run_id}:{turn_id}"
        message_phase: Literal["commentary", "final_answer"] = "commentary"
        for item in items:
            control.checkpoint()
            if item.kind is TurnStreamKind.ANSWER_START:
                message_phase = item.phase or "commentary"
                self._merge_draft(lease, run_id, "", message_phase)
            elif item.kind is TurnStreamKind.ANSWER_DELTA:
                content = item.content or ""
                offset = len(text)
                text += content
                answer_revision += 1
                self.live_stream.publish(RunItemDelta(
                    session_id=lease.session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    item_id=answer_item_id,
                    item_type=RunItemType.MESSAGE,
                    field="content",
                    revision=answer_revision,
                    offset=offset,
                    content=content,
                ))
            current_bytes = len(text.encode("utf-8"))
            if text and (current_bytes - flushed_bytes >= 1024 or time.monotonic() - last_flush >= 0.25):
                self._merge_draft(lease, run_id, text, message_phase)
                flushed_bytes = current_bytes
                last_flush = time.monotonic()
            yield item
        if text:
            self._merge_draft(lease, run_id, text, message_phase)

    def _complete(
        self,
        lease: SessionLease,
        run_id: str,
        result: ModelTurnResult,
        *,
        disposition: CompletionDisposition,
        limitation_codes: list[CompletionLimitationCode],
        evidence_artifact_ids: list[str],
    ) -> None:
        self.terminalizer.complete(
            lease,
            run_id,
            result,
            disposition=disposition,
            limitation_codes=limitation_codes,
            evidence_artifact_ids=evidence_artifact_ids,
        )

    def _cancelled(self, lease: SessionLease, run_id: str) -> bool:
        return self.terminalizer.cancelled(lease, run_id)

    def _cancellation_requested(self, run_id: str) -> bool:
        with self.session_factory() as db:
            run = RunRepository(db).get(run_id)
            return bool(run.cancel_requested) or str(run.status) in {"cancelling", "cancelled"}

    def _merge_draft(
        self,
        lease: SessionLease,
        run_id: str,
        text: str,
        phase: Literal["commentary", "final_answer"],
    ) -> None:
        with self.session_factory() as db:
            RunRepository(db).merge_answer_draft(
                lease=lease,
                run_id=run_id,
                content=text,
                phase=phase,
            )
            db.commit()

    def _stop_if_stalled(
        self,
        lease: SessionLease,
        run_id: str,
        result: ModelTurnResult,
    ) -> bool:
        with self.session_factory() as db:
            guard = ProgressGuard(db)
            fingerprint = guard.fingerprint(run_id)
            usable = self._has_usable_work(db, run_id, result)
            repository = RunRepository(db)
            stalled_turns = repository.record_progress(
                lease=lease,
                run_id=run_id,
                fingerprint=fingerprint,
            )
            reached_limit = stalled_turns >= self.definition.limits.max_stalled_turns
            if reached_limit:
                repository.record_no_progress(lease=lease, run_id=run_id)
            db.commit()
        if not reached_limit:
            return False
        if usable:
            self._complete(
                lease,
                run_id,
                result,
                disposition=CompletionDisposition.BOUNDED_PARTIAL,
                limitation_codes=[CompletionLimitationCode.NO_PROGRESS],
                evidence_artifact_ids=[],
            )
        else:
            self._fail(
                lease,
                run_id,
                "AGENT_NO_PROGRESS",
                "连续多轮没有产生新的可验证结果，已停止重复尝试。",
            )
        return True

    def _complete_for_limit(
        self,
        lease: SessionLease,
        run_id: str,
        result: ModelTurnResult,
        *,
        code: CompletionLimitationCode,
    ) -> bool:
        with self.session_factory() as db:
            usable = self._has_usable_work(db, run_id, result)
        if not usable:
            return False
        self._complete(
            lease,
            run_id,
            result,
            disposition=CompletionDisposition.BOUNDED_PARTIAL,
            limitation_codes=[code],
            evidence_artifact_ids=[],
        )
        return True

    def _has_usable_work(self, db: Session, run_id: str, result: ModelTurnResult) -> bool:
        context = ContextAssembler(db).build(run_id)
        return self.completion.has_usable_work(
            context=context,
            model_result=result,
        )

    def _fail(self, lease: SessionLease, run_id: str, code: str, message: str) -> None:
        self.terminalizer.fail(lease, run_id, code, message)
