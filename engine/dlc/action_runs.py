"""Durable action Runs for explicit Workbench operations contributed by DLCs.

The Kernel owns lifecycle, authority, policy, Tool settlement, and Artifact
persistence.  A DLC owns the business sequence and may invoke only Tools from
its own immutable package contribution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from engine.agent.artifact import ArtifactSelectionSuggestion
from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.response import AnswerCandidate, CompletionDisposition, ResponseComposer
from engine.agent.terminalizer import Terminalizer
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.turn import ModelToolCall
from engine.dlc.api import (
    DlcActionRunResult,
    DlcActionToolResult,
    DlcOperationError,
)
from engine.dlc.snapshot import RuntimeContributionSnapshot
from engine.models import AgentRun, AgentSession
from engine.tools.materialization import ToolMaterialization, materialize_tools
from engine.tools.runtime import ToolExecutor, ToolRegistry
from engine.tools.runtime.attempt import CompositeResourceResolver


SessionFactory = Callable[[], Session]
ProjectResourceAuthorizer = Callable[[Session, str, tuple[Any, ...]], tuple[Any, ...]]


class DlcActionRunsHostImpl:
    """Project- and owner-scoped factory installed in one operation context."""

    def __init__(
        self,
        *,
        dlc_id: str,
        project_id: str | None,
        snapshot: RuntimeContributionSnapshot,
        session_factory: SessionFactory,
        registry: ToolRegistry,
        resource_resolver: CompositeResourceResolver,
        resource_authorizer: ProjectResourceAuthorizer,
    ) -> None:
        self._dlc_id = dlc_id
        self._project_id = project_id
        self._snapshot = snapshot
        self._session_factory = session_factory
        self._registry = registry
        self._resource_resolver = resource_resolver
        self._resource_authorizer = resource_authorizer

    def start(
        self,
        *,
        title: str,
        question: str,
        requested_resources: tuple[Any, ...],
        session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> "_DlcActionRunImpl":
        project_id = str(self._project_id or "").strip()
        if not project_id:
            raise DlcOperationError(
                code="PROJECT_REQUIRED",
                message="This Workbench action requires a Project.",
            )

        registry = self._registry
        owner_tools = {
            registry.key_of(registry.require(name)).local_name: name
            for name in registry.tool_names()
            if registry.owner_of(name) == self._dlc_id
        }
        if not owner_tools:
            raise DlcOperationError(
                code="ACTION_TOOL_UNAVAILABLE",
                message="This capability has no active Workbench action Tools.",
                status_code=503,
            )
        owner_groups = tuple(
            sorted({registry.require(name).group for name in owner_tools.values()})
        )
        definition = AgentDefinition(
            name=f"{self._dlc_id}.workbench_action",
            version="1",
            behavior="explicit_user_workbench_action",
            allowed_tool_groups=owner_groups,
            execution_mode="user_requested_read",
        )
        materialization = materialize_tools(
            registry,
            allowed_names=set(owner_tools.values()),
            execution_mode=definition.execution_mode,
            available_resource_kinds={item.kind for item in requested_resources},
        )
        if not materialization.tools:
            raise DlcOperationError(
                code="ACTION_TOOL_UNAVAILABLE",
                message="No action Tool matches the selected resources.",
                status_code=503,
            )

        with self._session_factory() as db:
            resource_refs = self._resource_authorizer(
                db,
                project_id,
                requested_resources,
            )
            sessions = SessionRepository(db)
            normalized_session_id = str(session_id or "").strip()
            if normalized_session_id:
                aggregate = db.get(AgentSession, normalized_session_id)
                if aggregate is None or str(aggregate.project_id) != project_id:
                    raise DlcOperationError(
                        code="ACTION_SESSION_NOT_FOUND",
                        message="The Workbench action Session is unavailable in this Project.",
                        status_code=404,
                    )
            else:
                aggregate = sessions.create(project_id=project_id, title=title.strip())
                normalized_session_id = str(aggregate.id)

            admission = sessions.admit(
                session_id=normalized_session_id,
                resource_refs=resource_refs,
                content=question.strip(),
                idempotency_key=(
                    str(idempotency_key).strip()
                    if idempotency_key and str(idempotency_key).strip()
                    else f"dlc-action:{self._dlc_id}:{uuid4().hex}"
                ),
                llm_credential_id="dlc-workbench-action",
                api_base=None,
                model_name=None,
                request_payload={
                    "source": "dlc_workbench_action",
                    "owner_id": self._dlc_id,
                },
            )
            run = db.get(AgentRun, admission.run_id)
            if run is None or str(run.status) != "queued":
                raise DlcOperationError(
                    code="ACTION_REPLAY_CONFLICT",
                    message="This Workbench action was already admitted.",
                    status_code=409,
                )
            lease = sessions.claim(
                session_id=normalized_session_id,
                owner=f"dlc-action:{self._dlc_id}:{uuid4().hex}",
            )
            if lease is None:
                raise DlcOperationError(
                    code="ACTION_SESSION_BUSY",
                    message="Another action is already running in this Workbench Session.",
                    status_code=409,
                )
            promoted_run_id = sessions.promote_next_input(lease=lease)
            if promoted_run_id != admission.run_id:
                raise DlcOperationError(
                    code="ACTION_SESSION_BUSY",
                    message="Another queued action must finish first.",
                    status_code=409,
                )
            turn = sessions.start_turn(
                lease=lease,
                run_id=admission.run_id,
                agent_definition_version=definition.version,
                prompt_version="dlc-workbench-action@1",
                prompt_hash="dlc-workbench-action",
                context_snapshot={"source": "dlc_workbench_action"},
                context_hash="dlc-workbench-action",
                tool_materialization=materialization.model_dump(mode="json"),
                tool_materialization_hash=materialization.hash,
                provider="none",
                model_name="none",
            )
            turn_id = str(turn.id)
            db.commit()

        executor = ToolExecutor(max_workers=1)

        def representation_provider(artifact_type: str, representation_type: str):
            contribution = self._snapshot.get_artifact_representation(
                artifact_type,
                representation_type,
            )
            return contribution.provider if contribution is not None else None

        def artifact_payload_contract(artifact_type: str, schema_version: int):
            contribution = self._snapshot.get_artifact_contract(
                artifact_type,
                schema_version,
            )
            return contribution.validator if contribution is not None else None

        dispatcher = ToolDispatcher(
            session_factory=self._session_factory,
            registry=registry,
            definition=definition,
            executor=executor,
            resource_resolver=self._resource_resolver,
            resource_providers=self._snapshot.resource_providers,
            artifact_representation_provider_resolver=representation_provider,
            artifact_payload_contract_resolver=artifact_payload_contract,
            runtime_snapshot_id=self._snapshot.snapshot_id,
        )
        return _DlcActionRunImpl(
            dlc_id=self._dlc_id,
            owner_tools=owner_tools,
            session_factory=self._session_factory,
            dispatcher=dispatcher,
            executor=executor,
            materialization=materialization,
            lease=lease,
            run_id=admission.run_id,
            session_id=normalized_session_id,
            turn_id=turn_id,
            definition=definition,
        )


class _DlcActionRunImpl:
    def __init__(
        self,
        *,
        dlc_id: str,
        owner_tools: dict[str, str],
        session_factory: SessionFactory,
        dispatcher: ToolDispatcher,
        executor: ToolExecutor,
        materialization: ToolMaterialization,
        lease: Any,
        run_id: str,
        session_id: str,
        turn_id: str,
        definition: AgentDefinition,
    ) -> None:
        self._dlc_id = dlc_id
        self._owner_tools = owner_tools
        self._session_factory = session_factory
        self._dispatcher = dispatcher
        self._executor = executor
        self._materialization = materialization
        self._lease = lease
        self._run_id = run_id
        self._session_id = session_id
        self._turn_id = turn_id
        self._definition = definition
        self._completed = False
        self._call_sequence = 0

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def session_id(self) -> str:
        return self._session_id

    def invoke(self, tool_name: str, raw_input: dict[str, Any]) -> DlcActionToolResult:
        if self._completed:
            raise RuntimeError("The action Run is already terminal")
        provider_name = self._owner_tools.get(tool_name)
        if provider_name is None:
            raise DlcOperationError(
                code="ACTION_TOOL_FORBIDDEN",
                message="A capability may invoke only its own action Tools.",
            )
        self._call_sequence += 1
        call = ModelToolCall(
            id=f"action_call_{self._call_sequence}_{uuid4().hex}",
            name=provider_name,
            arguments=dict(raw_input),
        )
        control = self._control()
        dispatch = self._dispatcher.request(
            lease=self._lease,
            run_id=self._run_id,
            turn_id=self._turn_id,
            call=call,
            materialization=self._materialization,
            control=control,
            release_on_stopper=False,
        )
        if dispatch.outcome is not ToolDispatchOutcome.REQUESTED or dispatch.invocation is None:
            return DlcActionToolResult(
                status="failed",
                output={},
                error_code=(
                    "ACTION_APPROVAL_REQUIRED"
                    if dispatch.outcome is ToolDispatchOutcome.WAITING_APPROVAL
                    else "ACTION_TOOL_REJECTED"
                ),
            )
        completed = self._dispatcher.execute_requested_unsettled(
            self._lease,
            dispatch.invocation,
            control=control,
        )
        if completed is None:
            return DlcActionToolResult(
                status="failed",
                output={},
                error_code="ACTION_TOOL_REJECTED",
            )
        tool_result = completed.result
        self._dispatcher.settle_executed(
            self._lease,
            dispatch.invocation,
            completed,
            control=control,
        )
        with self._session_factory() as db:
            artifacts = tuple(
                artifact
                for artifact in ArtifactRepository(db).list_for_run(self._run_id)
                if artifact.provenance.get("tool_invocation_id") == dispatch.invocation.id
            )
        return DlcActionToolResult(
            status="success" if tool_result.status == "success" else "failed",
            output=dict(tool_result.output or {}),
            artifacts=artifacts,
            error_code=tool_result.error_code,
        )

    def complete(
        self,
        *,
        summary: str,
        selected_artifact_id: str | None = None,
    ) -> DlcActionRunResult:
        if self._completed:
            raise RuntimeError("The action Run is already terminal")
        with self._session_factory() as db:
            repository = ArtifactRepository(db)
            artifacts = repository.list_for_run(self._run_id)
            selected = (
                next((item for item in artifacts if item.id == selected_artifact_id), None)
                if selected_artifact_id
                else None
            )
            response = ResponseComposer().compose(
                session_id=self._session_id,
                run_id=self._run_id,
                completion_disposition=CompletionDisposition.COMPLETE,
                limitation_codes=[],
                answer=AnswerCandidate(text=summary.strip() or "Workbench action completed."),
                artifacts=artifacts,
                selection_suggestion=(
                    ArtifactSelectionSuggestion(
                        artifact_id=selected.id,
                        reason="Workbench action result",
                    )
                    if selected is not None
                    else None
                ),
            )
            Terminalizer.complete_in_session(
                db,
                self._lease,
                response,
                terminal_turn_id=self._turn_id,
            )
            SessionRepository(db).release(lease=self._lease)
            db.commit()
        self._completed = True
        self._executor.close(wait=False)
        return DlcActionRunResult(
            run_id=self._run_id,
            session_id=self._session_id,
            artifacts=tuple(artifacts),
        )

    def __enter__(self) -> "_DlcActionRunImpl":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Literal[False]:
        if not self._completed:
            with self._session_factory() as db:
                Terminalizer.fail_in_session(
                    db,
                    self._lease,
                    self._run_id,
                    "AGENT_REQUEST_ERROR",
                    "The Workbench action failed.",
                )
                SessionRepository(db).release(lease=self._lease)
                db.commit()
            self._completed = True
            self._executor.close(wait=False)
        return False

    def _control(self) -> LeaseAwareRunControl:
        with self._session_factory() as db:
            run = db.get(AgentRun, self._run_id)
            if run is None:
                raise RuntimeError("The action Run no longer exists")

        def cancellation_requested() -> bool:
            with self._session_factory() as db:
                current = db.get(AgentRun, self._run_id)
                return current is None or bool(current.cancel_requested)

        return LeaseAwareRunControl(
            run=run,
            limits=self._definition.limits,
            cancellation_probe=cancellation_requested,
            lease_lost_probe=None,
        )
