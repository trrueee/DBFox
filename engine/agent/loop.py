"""The single explicit ReAct-style DBFox Agent execution loop."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
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
from engine.agent.context import ContextAssembler, ContextSnapshot
from engine.agent.context_fragment import ContextContributor
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
from engine.agent.run_item import RunItemDelta, RunItemStatus, RunItemType
from engine.agent.turn import (
    ModelTurnResult,
    TurnStreamAssembler,
    TurnStreamCancelled,
    TurnStreamError,
    TurnStreamItem,
    TurnStreamKind,
)
from engine.app.safe_errors import fixed_error_detail
from engine.llm.config import (
    LlmConfigurationError,
    resolve_product_llm_config_from_credential,
)
from engine.llm.endpoint_policy import LlmEndpointPolicyError
from engine.json_codec import load_object
from engine.models import (
    AgentSessionInput,
    AgentTurn,
)
from engine.agent.resource_refs import load_resource_refs
from engine.tools.materialization import ToolMaterialization, materialize_tools
from engine.tools.runtime import ToolExecutionTask, ToolExecutor, ToolRegistry
from engine.tools.runtime.attempt import CompositeResourceResolver
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
    context: ContextSnapshot
    messages: list[dict[str, Any]]
    tools: ToolMaterialization
    provider_settings: ProviderSettings


@dataclass
class _StreamingMessageState:
    output_index: int
    phase: Literal["commentary", "final_answer"] | None
    text: str = ""
    live_revision: int = 0
    persisted_revision: int = 0
    flushed_bytes: int = 0
    last_flush: float = field(default_factory=time.monotonic)
    ended: bool = False


@dataclass
class _ExecutionState:
    control: LeaseAwareRunControl
    provider_settings: ProviderSettings
    pricing: ModelPricing | None
    tool_count: int
    completed_turn_count: int
    finalizing: bool = False
    last_result: ModelTurnResult = field(default_factory=ModelTurnResult)
    best_answer_result: ModelTurnResult = field(default_factory=ModelTurnResult)
    transient_tool_outputs: dict[str, str] = field(default_factory=dict)

    @property
    def answer_result(self) -> ModelTurnResult:
        if self.best_answer_result.answer_text:
            return self.best_answer_result
        return self.last_result

    def record_result(self, result: ModelTurnResult) -> None:
        self.last_result = result
        if result.has_completed_answer_candidate:
            self.best_answer_result = result


@dataclass(frozen=True)
class _PlannedToolCall:
    call: Any
    invocation: Any
    frozen_tool: Any | None
    counts_toward_budget: bool
    provider_call_index: int


def _relevant_tool_groups(
    configured_groups: set[str],
    context: ContextSnapshot,
) -> set[str]:
    """Return configured groups without interpreting capability artifacts."""

    del context
    return set(configured_groups)


LIVE_STREAM_HUB = LiveStreamHub()
_FINALIZATION_TOOL_NAMES = frozenset({"update_plan"})


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
        model_factory: Callable[
            [ProviderSettings], ModelAdapter
        ] = _default_model_factory,
        registry: ToolRegistry | None = None,
        context_contributors: tuple[Callable[[Session], ContextContributor], ...] | None = None,
        completion: CompletionGate | None = None,
        definition: AgentDefinition = DEFAULT_AGENT_DEFINITION,
        live_stream: LiveStreamHub = LIVE_STREAM_HUB,
        tool_executor: ToolExecutor | None = None,
        resource_resolver: CompositeResourceResolver | None = None,
        pricing_resolver: (
            Callable[[ProviderSettings], ModelPricing | None] | None
        ) = None,
    ) -> None:
        self.session_factory = session_factory
        self.model_factory = model_factory
        if registry is None or context_contributors is None or completion is None:
            # This fallback keeps direct test construction ergonomic. Production
            # startup injects all three values from runtime_composition.
            from engine.runtime_composition import (
                build_default_completion_policy,
                build_product_tool_registry,
                default_context_contributors,
            )

            if registry is None:
                registry = build_product_tool_registry()
            if context_contributors is None:
                context_contributors = default_context_contributors()
            if completion is None:
                completion = CompletionGate(build_default_completion_policy())
        self.registry = registry
        if not self.registry.frozen:
            self.registry.freeze()
        self.definition = definition
        self.live_stream = live_stream
        self._owns_tool_executor = tool_executor is None
        self.tool_executor = tool_executor or ToolExecutor()
        self.pricing_resolver = pricing_resolver or (lambda _settings: None)
        self.prompts = PromptAssembler()
        self.context_contributors = context_contributors
        self.completion = completion
        self.tool_dispatcher = ToolDispatcher(
            session_factory=self.session_factory,
            registry=self.registry,
            definition=self.definition,
            executor=self.tool_executor,
            resource_resolver=resource_resolver,
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
            self._execute_pending_invocations(lease, run_id, state)

            for turn_count in range(
                state.completed_turn_count + 1,
                self.definition.limits.max_turns + 1,
            ):
                state.control.checkpoint()
                if self._should_enter_finalization(state, turn_count=turn_count):
                    self._activate_finalization(
                        lease,
                        run_id,
                        state,
                        turns_remaining=(
                            self.definition.limits.max_turns - turn_count + 1
                        ),
                        reason=(
                            "The Run reached its finalization reserve. Synthesize the "
                            "best supported answer without starting new analysis."
                        ),
                    )
                prepared = self._prepare_turn(
                    lease,
                    run_id,
                    finalizing=state.finalizing,
                    tool_output_overrides=state.transient_tool_outputs,
                )
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
                        state=state,
                        turn_count=turn_count,
                    ):
                        return
                    continue

                decision = self.completion.evaluate(
                    context=prepared.context,
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
                        state=state,
                        turn_count=turn_count,
                        context=prepared.context,
                    ):
                        return
                    if decision.kind is CompletionKind.REPAIR:
                        state.control.record_repair()
                    continue
                if decision.kind is CompletionKind.FAIL:
                    self._fail(lease, run_id, "AGENT_INCOMPLETE", decision.reason)
                    return
                partial = decision.kind is CompletionKind.PARTIAL
                if self._complete(
                    lease,
                    run_id,
                    result,
                    disposition=(
                        CompletionDisposition.BOUNDED_PARTIAL
                        if partial
                        else CompletionDisposition.COMPLETE
                    ),
                    limitation_codes=(
                        [CompletionLimitationCode.TURN_BUDGET_REACHED]
                        if partial
                        else []
                    ),
                    evidence_artifact_ids=decision.evidence_artifact_ids,
                ):
                    return
                continue
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
            completed_turn_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(AgentTurn)
                    .where(AgentTurn.run_id == run_id)
                )
                or 0
            )
            best_answer_result = RunRepository(db).latest_completed_answer(run_id)
            run_result = load_object(str(run.result_json or "{}"))
            focus = run_result.get("focus")
            finalizing = isinstance(focus, dict) and focus.get("kind") == "synthesize"
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
            finalizing=finalizing,
            best_answer_result=best_answer_result,
        )

    def _execute_pending_invocations(
        self,
        lease: SessionLease,
        run_id: str,
        state: _ExecutionState,
    ) -> None:
        for invocation in self.tool_dispatcher.pending_invocations(run_id):
            state.control.checkpoint()
            provider_output = self.tool_dispatcher.execute_requested(
                lease,
                invocation,
                control=state.control,
            )
            if provider_output is not None:
                state.transient_tool_outputs[provider_output.call_id] = (
                    provider_output.output
                )

    def _run_model_turn(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        prepared: _PreparedTurn,
        state: _ExecutionState,
    ) -> ModelTurnResult | None:
        try:
            adapter = self.model_factory(prepared.provider_settings)
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
            result = result.model_copy(update={"turn_id": prepared.turn_id})
        except (LlmConfigurationError, LlmEndpointPolicyError) as exc:
            detail = fixed_error_detail(exc.code)
            with self.session_factory() as db:
                RunRepository(db).settle_turn(
                    lease=lease,
                    turn_id=prepared.turn_id,
                    result=ModelTurnResult(),
                    error_code=detail["code"],
                    error_message=detail["message"],
                )
                db.commit()
            raise RunControlError(detail["code"], detail["message"]) from exc
        except TurnStreamCancelled as exc:
            state.control.checkpoint()
            raise RunCancellationRequested() from exc
        except TurnStreamError as exc:
            with self.session_factory() as db:
                RunRepository(db).settle_turn(
                    lease=lease,
                    turn_id=prepared.turn_id,
                    result=ModelTurnResult(),
                    error_code=exc.code,
                    error_message=str(exc),
                )
                db.commit()
            if exc.retryable is False:
                raise RunControlError(exc.code, str(exc)) from exc
            state.control.record_provider_failure()
            state.control.wait_for_provider_retry(exc.retry_after_seconds)
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
                )
                or 0
            ),
        )
        output_tokens = max(
            0,
            int(
                result.usage.get(
                    "completion_tokens",
                    result.usage.get("output_tokens", 0),
                )
                or 0
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
        planned_calls: list[_PlannedToolCall] = []
        next_tool_count = state.tool_count
        next_stopper: ToolDispatchOutcome | None = None
        budget_reached = False

        def _counts_toward_budget(frozen_tool: Any | None) -> bool:
            return frozen_tool is not None and frozen_tool.kind != "control"

        for call_index, call in enumerate(result.tool_calls):
            state.control.checkpoint()
            try:
                frozen_tool = prepared.tools.require(call.name)
            except KeyError:
                # Admission owns unavailable-tool rejection and returns a durable,
                # model-visible observation.  Do not let budget classification turn
                # a provider-authored call outside this Turn's frozen contract into
                # a Run-level infrastructure failure.
                frozen_tool = None

            counts_toward_budget = _counts_toward_budget(frozen_tool)
            if (
                counts_toward_budget
                and next_tool_count >= self.definition.limits.max_tool_invocations
            ):
                budget_reached = True
                break
            if counts_toward_budget:
                next_tool_count += 1

            dispatch = self.tool_dispatcher.request(
                lease=lease,
                run_id=run_id,
                turn_id=prepared.turn_id,
                call=call,
                materialization=prepared.tools,
                control=state.control,
                release_on_stopper=False,
            )
            if dispatch.provider_output is not None:
                state.transient_tool_outputs[
                    dispatch.provider_output.call_id
                ] = dispatch.provider_output.output
            if dispatch.outcome is not ToolDispatchOutcome.REQUESTED:
                if dispatch.outcome in {
                    ToolDispatchOutcome.WAITING_APPROVAL,
                    ToolDispatchOutcome.WAITING_INPUT,
                }:
                    next_stopper = dispatch.outcome
                continue
            if dispatch.invocation is None:
                raise RuntimeError("Requested invocation is missing its identity")
            planned_calls.append(
                _PlannedToolCall(
                    call=call,
                    invocation=dispatch.invocation,
                    frozen_tool=frozen_tool,
                    counts_toward_budget=counts_toward_budget,
                    provider_call_index=call_index,
                )
            )

        if next_stopper is not None:
            # A Turn's calls are all durably admitted before it waits. Nothing
            # executes while any approval/input stopper is unresolved, so resume
            # uses the canonical invocation set rather than a partial transcript.
            with self.session_factory() as db:
                SessionRepository(db).release(lease=lease)
                db.commit()
            state.tool_count = next_tool_count
            return True

        if not planned_calls:
            if budget_reached:
                if not self._complete_for_limit(
                    lease,
                    run_id,
                    state.answer_result,
                    code=CompletionLimitationCode.TOOL_BUDGET_REACHED,
                    context=prepared.context,
                ):
                    self._fail(
                        lease,
                        run_id,
                        "AGENT_TOOL_BUDGET",
                        "工具调用已达到本次分析上限。",
                    )
                return True
            return next_stopper is not None

        batches: list[list[_PlannedToolCall]] = []
        current_batch: list[_PlannedToolCall] = []
        for entry in planned_calls:
            if (
                entry.frozen_tool is None
                or str(entry.frozen_tool.execution.get("concurrency") or "sequential")
                != "parallel_safe"
            ):
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                batches.append([entry])
            else:
                current_batch.append(entry)
        if current_batch:
            batches.append(current_batch)

        for batch in batches:
            if len(batch) > 1:
                def run_parallel_entry(invocation: Any) -> Any:
                    return self.tool_dispatcher.execute_requested_unsettled(
                        lease,
                        invocation,
                        control=state.control,
                    )

                completed_attempts = self.tool_executor.execute_batch(
                    tasks=[
                        ToolExecutionTask(
                            operation=partial(run_parallel_entry, entry.invocation)
                        )
                        for entry in batch
                    ],
                    max_parallel=len(batch),
                )
            else:
                completed_attempts = [
                    self.tool_dispatcher.execute_requested_unsettled(
                        lease,
                        batch[0].invocation,
                        control=state.control,
                    )
                ]
            # Tool execution may finish in any order. Settlement is intentionally
            # serial and follows provider call order, so Observation.sequence has
            # one deterministic owner and never races on SQLite's unique key.
            for entry, completed in zip(batch, completed_attempts):
                if completed is not None:
                    output = self.tool_dispatcher.settle_executed(
                        lease,
                        entry.invocation,
                        completed,
                        control=state.control,
                    )
                    state.transient_tool_outputs[output.call_id] = output.output
        state.tool_count = max(state.tool_count, next_tool_count)

        if budget_reached:
            if not self._complete_for_limit(
                lease,
                run_id,
                state.answer_result,
                code=CompletionLimitationCode.TOOL_BUDGET_REACHED,
                context=prepared.context,
            ):
                self._fail(
                    lease,
                    run_id,
                    "AGENT_TOOL_BUDGET",
                    "工具调用已达到本次分析上限。",
                )
            return True

        return next_stopper is not None

    def _record_continuation(
        self,
        lease: SessionLease,
        run_id: str,
        decision: CompletionDecision,
    ) -> None:
        with self.session_factory() as db:
            repository = RunRepository(db)
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

    def _prepare_turn(
        self,
        lease: SessionLease,
        run_id: str,
        *,
        finalizing: bool = False,
        tool_output_overrides: dict[str, str] | None = None,
    ) -> _PreparedTurn:
        with self.session_factory() as db:
            # Steer inputs become durable Run-scoped messages at this boundary.
            # ContextAssembler reads the consumed inputs from the same transaction,
            # so queued inputs belonging to later Runs cannot leak into this Turn.
            SessionRepository(db).consume_steering_inputs(lease=lease, run_id=run_id)
            run = RunRepository(db).get(run_id)
            context = ContextAssembler(
                db,
                contributors=self.context_contributors,
            ).build(run_id)
            state = RunWorkingStateAssembler(
                db,
                self.definition,
            ).build(run)
            groups = set(
                state.get("allowed_tool_groups") or self.definition.allowed_tool_groups
            )
            groups = _relevant_tool_groups(groups, context)

            available_resource_kinds: frozenset[str] = frozenset()
            if run.input_id:
                input_row = db.get(AgentSessionInput, str(run.input_id))
                if input_row is not None and input_row.resource_refs_json is not None:
                    frozen_refs = load_resource_refs(str(input_row.resource_refs_json))
                    available_resource_kinds = frozenset(r.kind for r in frozen_refs)

            tools = materialize_tools(
                self.registry,
                allowed_groups=(groups or None),
                allowed_names=(set(_FINALIZATION_TOOL_NAMES) if finalizing else None),
                execution_mode=self.definition.execution_mode,
                available_resource_kinds=available_resource_kinds,
            )
            tool_schemas = tools.provider_schemas()
            prompt = self.prompts.assemble(
                definition=self.definition,
                context=context,
                tool_schemas=tool_schemas,
                tool_output_overrides=tool_output_overrides,
            )
            turn = SessionRepository(db).start_turn(
                lease=lease,
                run_id=run_id,
                agent_definition_version=self.definition.version,
                prompt_version=prompt.version,
                prompt_hash=prompt.hash,
                context_snapshot={
                    **context.model_dump(mode="json"),
                    "prompt_budget": prompt.budget,
                },
                context_hash=context.hash,
                tool_materialization=tools.model_dump(mode="json"),
                tool_materialization_hash=tools.hash,
                provider="openai-responses",
                model_name=str(run.model_name or ""),
            )
            settings = ProviderSettings(
                credential_id=str(run.llm_credential_id),
                api_base=str(run.api_base) if run.api_base else None,
                model_name=str(run.model_name) if run.model_name else None,
            )
            db.commit()
            return _PreparedTurn(
                turn_id=str(turn.id),
                context=context,
                messages=list(prompt.messages),
                tools=tools,
                provider_settings=settings,
            )

    def _publish_stream(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        items: Iterable[TurnStreamItem],
        control: LeaseAwareRunControl,
    ) -> Iterable[TurnStreamItem]:
        messages: dict[str, _StreamingMessageState] = {}
        stream_completed = False
        try:
            for item in items:
                control.checkpoint()
                if item.kind is TurnStreamKind.ANSWER_START:
                    if item.output_index is None:
                        raise TurnStreamError(
                            "Answer stream item is missing its output index"
                        )
                    state = _StreamingMessageState(
                        output_index=item.output_index,
                        phase=item.phase,
                    )
                    messages[item.item_id] = state
                    state.persisted_revision = 1
                    self._persist_turn_message(
                        lease=lease,
                        run_id=run_id,
                        turn_id=turn_id,
                        state=state,
                        status=RunItemStatus.IN_PROGRESS,
                    )
                elif item.kind is TurnStreamKind.ANSWER_DELTA:
                    delta_state = messages.get(item.item_id)
                    if delta_state is None or delta_state.ended:
                        raise TurnStreamError(
                            "Answer delta is outside its persisted message lifecycle"
                        )
                    content = item.content or ""
                    offset = len(delta_state.text)
                    delta_state.text += content
                    delta_state.live_revision += 1
                    durable_item_id = (
                        f"message:{run_id}:{turn_id}:{delta_state.output_index}"
                    )
                    self.live_stream.publish(
                        RunItemDelta(
                            session_id=lease.session_id,
                            run_id=run_id,
                            turn_id=turn_id,
                            item_id=durable_item_id,
                            item_type=RunItemType.MESSAGE,
                            field="content",
                            revision=delta_state.live_revision,
                            offset=offset,
                            content=content,
                        )
                    )
                    current_bytes = len(delta_state.text.encode("utf-8"))
                    if delta_state.text and (
                        current_bytes - delta_state.flushed_bytes >= 1024
                        or time.monotonic() - delta_state.last_flush >= 0.25
                    ):
                        delta_state.persisted_revision += 1
                        self._persist_turn_message(
                            lease=lease,
                            run_id=run_id,
                            turn_id=turn_id,
                            state=delta_state,
                            status=RunItemStatus.IN_PROGRESS,
                        )
                        delta_state.flushed_bytes = current_bytes
                        delta_state.last_flush = time.monotonic()
                elif item.kind is TurnStreamKind.ANSWER_END:
                    ended_state = messages.get(item.item_id)
                    if ended_state is None or ended_state.ended:
                        raise TurnStreamError(
                            "Answer end is outside its persisted message lifecycle"
                        )
                    if item.message_status not in {"completed", "incomplete"}:
                        raise TurnStreamError(
                            "Answer end is missing its completed status"
                        )
                    ended_state.phase = item.phase
                    ended_state.ended = True
                    ended_state.persisted_revision += 1
                    self._persist_turn_message(
                        lease=lease,
                        run_id=run_id,
                        turn_id=turn_id,
                        state=ended_state,
                        status=(
                            RunItemStatus.COMPLETED
                            if item.message_status == "completed"
                            else RunItemStatus.FAILED
                        ),
                    )
                yield item
            stream_completed = True
        finally:
            if not stream_completed:
                for state in messages.values():
                    if state.ended:
                        continue
                    state.ended = True
                    state.persisted_revision += 1
                    self._persist_turn_message(
                        lease=lease,
                        run_id=run_id,
                        turn_id=turn_id,
                        state=state,
                        status=RunItemStatus.CANCELLED,
                    )

    def _persist_turn_message(
        self,
        *,
        lease: SessionLease,
        run_id: str,
        turn_id: str,
        state: _StreamingMessageState,
        status: RunItemStatus,
    ) -> None:
        with self.session_factory() as db:
            RunRepository(db).persist_turn_message(
                lease=lease,
                run_id=run_id,
                turn_id=turn_id,
                output_index=state.output_index,
                revision=state.persisted_revision,
                phase=state.phase,
                content=state.text,
                status=status,
            )
            db.commit()

    def _complete(
        self,
        lease: SessionLease,
        run_id: str,
        result: ModelTurnResult,
        *,
        disposition: CompletionDisposition,
        limitation_codes: list[CompletionLimitationCode],
        evidence_artifact_ids: list[str],
    ) -> bool:
        return self.terminalizer.complete(
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
            return bool(run.cancel_requested) or str(run.status) in {
                "cancelling",
                "cancelled",
            }

    def _should_enter_finalization(
        self,
        state: _ExecutionState,
        *,
        turn_count: int,
    ) -> bool:
        if state.finalizing:
            return False
        limits = self.definition.limits
        turn_reserve = limits.effective_finalization_turn_reserve
        tool_reserve = limits.effective_finalization_tool_reserve
        turn_boundary = (
            turn_reserve > 0 and turn_count >= limits.max_turns - turn_reserve + 1
        )
        tool_boundary = (
            tool_reserve > 0
            and state.tool_count >= limits.max_tool_invocations - tool_reserve
        )
        return turn_boundary or tool_boundary

    def _activate_finalization(
        self,
        lease: SessionLease,
        run_id: str,
        state: _ExecutionState,
        *,
        turns_remaining: int,
        reason: str,
    ) -> None:
        if state.finalizing:
            return
        tools_remaining = max(
            0,
            self.definition.limits.max_tool_invocations - state.tool_count,
        )
        with self.session_factory() as db:
            RunRepository(db).record_focus(
                lease=lease,
                run_id=run_id,
                kind="synthesize",
                reason=(
                    f"{reason} Remaining Turn budget: {max(0, turns_remaining)}; "
                    f"remaining data-tool budget: {tools_remaining}."
                ),
                missing=["settled_plan", "inline_evidence", "final_answer"],
            )
            db.commit()
        state.finalizing = True

    def _stop_if_stalled(
        self,
        lease: SessionLease,
        run_id: str,
        result: ModelTurnResult,
        *,
        state: _ExecutionState,
        turn_count: int,
        context: ContextSnapshot | None = None,
    ) -> bool:
        with self.session_factory() as db:
            guard = ProgressGuard(db)
            fingerprint = guard.fingerprint(run_id)
            snapshot = context or ContextAssembler(
                db,
                contributors=self.context_contributors,
            ).build(run_id)
            decision = self.completion.evaluate_bounded_partial(
                context=snapshot,
                model_result=result,
                reason="The run reached its no-progress limit with usable durable work.",
            )
            repository = RunRepository(db)
            stalled_turns = repository.record_progress(
                lease=lease,
                run_id=run_id,
                fingerprint=fingerprint,
            )
            reached_limit = stalled_turns >= self.definition.limits.max_stalled_turns
            db.commit()
        if not reached_limit:
            return False
        if decision.kind is CompletionKind.PARTIAL:
            if not state.finalizing and turn_count < self.definition.limits.max_turns:
                self._activate_finalization(
                    lease,
                    run_id,
                    state,
                    turns_remaining=(self.definition.limits.max_turns - turn_count),
                    reason=(
                        "The Run stopped making progress. Use the remaining budget "
                        "once to synthesize the durable work already completed."
                    ),
                )
                return False
            return self._complete(
                lease,
                run_id,
                result,
                disposition=CompletionDisposition.BOUNDED_PARTIAL,
                limitation_codes=[CompletionLimitationCode.NO_PROGRESS],
                evidence_artifact_ids=decision.evidence_artifact_ids,
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
        context: ContextSnapshot | None = None,
    ) -> bool:
        with self.session_factory() as db:
            snapshot = context or ContextAssembler(
                db,
                contributors=self.context_contributors,
            ).build(run_id)
            decision = self.completion.evaluate_bounded_partial(
                context=snapshot,
                model_result=result,
                reason=f"The run stopped at the {code.value} boundary with usable durable work.",
            )
        if decision.kind is not CompletionKind.PARTIAL:
            return False
        return self._complete(
            lease,
            run_id,
            result,
            disposition=CompletionDisposition.BOUNDED_PARTIAL,
            limitation_codes=[code],
            evidence_artifact_ids=decision.evidence_artifact_ids,
        )

    def _fail(self, lease: SessionLease, run_id: str, code: str, message: str) -> None:
        self.terminalizer.fail(lease, run_id, code, message)
