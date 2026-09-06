"""API v2 registration. Game state and domain semantics stay owner-local."""
from __future__ import annotations

from collections.abc import Callable

from dbfox_dlc_api import (
    BackendExtensionHost, CapabilityGuidanceSpec, ContextContributionInput, ContextFragment,
    DlcOperationContext, DlcOperationError, DlcOperationSpec, RequestedResourceRef,
    SemanticArtifactCompletionSupport, ToolKey,
)
from pydantic import ValidationError

from . import contracts as c
from . import views
from .compute import Bridge
from .representation import DOCUMENT, REPORT, DocumentRepresentation, ReportRepresentation
from .store import GameError, Store
from .tools import TOOL_TYPES


class GameContext:
    id = c.OWNER

    def __init__(self, store: Store) -> None:
        self.store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        facts: list[c.JsonValue] = []
        for ref in input.resource_refs:
            if ref.kind not in (c.LIBRARY, c.RESOURCE):
                continue
            resource = self.store.resolve(ref)
            if isinstance(resource, c.LibraryScope):
                fact = {"kind": c.LIBRARY, "project_id": resource.project_id, "expected_library_version": resource.version}
            else:
                fact = resource.summary().data()
            candidate = c.encoded({"resources": [*facts, fact], "instruction": "Inspect stable object IDs and the current version before editing. Selection is view state. Playtest uses fixed ticks in Phaser; preview is derived."}).decode("utf-8")
            if len(candidate) > 3700:
                break
            facts.append(fact)
        if not facts:
            return ()
        content = c.encoded({"resources": facts, "instruction": "Inspect stable object IDs and the current version before editing. Selection is view state. Playtest uses fixed ticks in Phaser; preview is derived.", "truncated": len(facts) < sum(ref.kind in (c.LIBRARY, c.RESOURCE) for ref in input.resource_refs)}).decode("utf-8")
        return (ContextFragment(source_id=c.OWNER, source_version="1", lane="resource", content=content, provenance={"owner": c.OWNER, "resource_count": len(facts)}),)


def project(context: DlcOperationContext) -> str:
    if context.dlc_id != c.OWNER or not context.project_id:
        raise GameError("INVALID_PROJECT", "Game operation requires its authorized Host Project")
    return context.project_id


def register(host: BackendExtensionHost) -> None:
    if host.runtime_info.dlc_id != c.OWNER:
        raise ValueError("Game package owner does not match runtime identity")
    store = Store(host.runtime_info.data_path)
    bridge = Bridge(host.runtime_info.package_digest)
    for tool_type in TOOL_TYPES:
        host.tools.register(tool_type(store, bridge))
    host.resources.register_provider(store.resources)
    host.resources.register_resolver(c.LIBRARY, store.resolve)
    host.resources.register_resolver(c.RESOURCE, store.resolve)
    host.context.register(lambda: GameContext(store))
    host.artifacts.register(c.DOCUMENT_ARTIFACT, 1, c.ArtifactLocator)
    host.artifacts.register_representation(c.DOCUMENT_ARTIFACT, DOCUMENT, DocumentRepresentation(store))
    host.artifacts.register(c.REPORT_ARTIFACT, 1, c.ArtifactLocator)
    host.artifacts.register_representation(c.REPORT_ARTIFACT, REPORT, ReportRepresentation(store))
    host.completion.register_support(SemanticArtifactCompletionSupport(id=c.OWNER + ".document", semantic_capability=c.DOCUMENT_ARTIFACT))
    host.completion.register_support(SemanticArtifactCompletionSupport(id=c.OWNER + ".playtest", semantic_capability=c.REPORT_ARTIFACT))
    host.agent_guidance.register(CapabilityGuidanceSpec(id=c.OWNER + ".authoring", version="1", instructions="Create a durable Game, inspect IDs, then use structured incremental edits. Human edits share the same expected_version CAS. Playtest feedback is derived from the same Phaser engine; no scripts or arbitrary URLs are accepted.", applies_to_resource_kinds=(c.LIBRARY, c.RESOURCE), tool_refs=tuple(ToolKey(c.OWNER, tool_type.name) for tool_type in TOOL_TYPES)))

    def operation(name: str, input_model: type[c.Input], output_model: type[c.Contract], handler: Callable[[c.Input, str, DlcOperationContext], c.Contract], maximum: int = 32768) -> None:
        def invoke(data: c.Input, context: DlcOperationContext) -> c.Contract:
            try:
                if context.operation_name != name:
                    raise GameError("INVALID_OPERATION", "Game operation identity does not match")
                return handler(data, project(context), context)
            except GameError as exc:
                raise DlcOperationError(code=exc.code, message=str(exc)[:400], status_code=503 if exc.status == 500 else exc.status) from exc
            except ValidationError as exc:
                raise DlcOperationError(code="INVALID_GAME", message="Game model or references are invalid") from exc
            except ValueError as exc:
                raise DlcOperationError(code="INVALID_GAME", message=str(exc)[:400]) from exc
        host.operations.register(DlcOperationSpec(name=name, input_model=input_model, output_model=output_model, handler=invoke, scope="project", description="Typed Game " + name, max_output_bytes=maximum))

    def listing(data: c.Input, project_id: str, context: DlcOperationContext) -> c.Page:
        if not isinstance(data, c.ListInput):
            raise GameError("INVALID_OPERATION", "List input contract mismatch")
        if data.offset and data.version is None:
            raise GameError("INVALID_PAGE", "Subsequent Game library pages require the first page's fixed version")
        library, games = store.list_games(project_id, data.version)
        return views.page("games", None, library.version, [item.data() for item in games], data.offset, data.limit)

    def head(data: c.Input, project_id: str, context: DlcOperationContext) -> c.HeadOutput:
        if not isinstance(data, c.HeadInput):
            raise GameError("INVALID_OPERATION", "Head input contract mismatch")
        return c.HeadOutput(game=store.get(project_id, data.game_id).summary(), library_version=store.library(project_id).version)

    def get(data: c.Input, project_id: str, context: DlcOperationContext) -> c.Page:
        if not isinstance(data, c.GetInput) or data.version is None:
            raise GameError("INVALID_PAGE", "Game pages require a fixed version; read games.head first")
        return views.read(store, store.get(project_id, data.game_id, data.version), data)

    def create(data: c.Input, project_id: str, context: DlcOperationContext) -> c.Mutation:
        if not isinstance(data, c.CreateRequest):
            raise GameError("INVALID_OPERATION", "Create input contract mismatch")
        return store.create(project_id, "human", data.request_id, c.CreateInput.model_validate(data.model_dump(exclude={"request_id"})))

    def mutation(data: c.Input, project_id: str, context: DlcOperationContext) -> c.Mutation:
        if isinstance(data, c.ApplyRequest):
            return store.mutate(project_id, "human", data.request_id, "apply", c.ApplyInput.model_validate(data.model_dump(exclude={"request_id"}, exclude_none=True)))
        if isinstance(data, c.UndoRequest):
            return store.mutate(project_id, "human", data.request_id, "undo", c.UndoInput.model_validate(data.model_dump(exclude={"request_id"})))
        if isinstance(data, c.UploadRequest):
            return store.mutate(project_id, "human", data.request_id, "upload", c.UploadInput.model_validate(data.model_dump(exclude={"request_id"})))
        if isinstance(data, c.VersionRequest):
            return store.mutate(project_id, "human", data.request_id, "delete", c.VersionInput.model_validate(data.model_dump(exclude={"request_id"})))
        raise GameError("INVALID_OPERATION", "Mutation input contract mismatch")

    def history(data: c.Input, project_id: str, context: DlcOperationContext) -> c.Page:
        if not isinstance(data, c.HistoryInput):
            raise GameError("INVALID_OPERATION", "History input contract mismatch")
        revision = store.get(project_id, data.game_id, data.version)
        total, items = store.history(project_id, data.game_id, data.version, data.offset, data.limit)
        return views.page("revisions", revision, revision.library_version, items, data.offset, data.limit, total=total)

    def diff(data: c.Input, project_id: str, context: DlcOperationContext) -> c.Page:
        if not isinstance(data, c.DiffInput):
            raise GameError("INVALID_OPERATION", "Diff input contract mismatch")
        before = store.get(project_id, data.game_id, data.from_version)
        after = store.get(project_id, data.game_id, data.to_version)
        return views.page("diff", after, after.library_version, views.differences(before, after), data.offset, data.limit)

    def export(data: c.Input, project_id: str, context: DlcOperationContext) -> c.ActionResult:
        if not isinstance(data, c.VersionRequest):
            raise GameError("INVALID_OPERATION", "Export input contract mismatch")
        return action_run(data, project_id, context, "game_export")

    def playtest(data: c.Input, project_id: str, context: DlcOperationContext) -> c.ActionResult:
        if not isinstance(data, c.PlaytestRequest):
            raise GameError("INVALID_OPERATION", "Playtest input contract mismatch")
        return action_run(data, project_id, context, "playtest")

    def action_run(data: c.VersionRequest | c.PlaytestRequest, project_id: str, context: DlcOperationContext, tool_name: str) -> c.ActionResult:
        host_actions = context.require_action_runs()
        request = c.PlaytestInput.model_validate(data.model_dump(exclude={"request_id"})) if isinstance(data, c.PlaytestRequest) else c.VersionInput.model_validate(data.model_dump(exclude={"request_id"}))
        previous = store.reserve_action(project_id, data.request_id, tool_name, request)
        if previous is not None:
            return previous
        with host_actions.start(title="Game " + tool_name, question="Run the explicit Game workbench action against its fixed revision.", requested_resources=(RequestedResourceRef(kind=c.RESOURCE, id=data.game_id),), idempotency_key=data.request_id) as run:
            result = run.invoke(tool_name, request.data())
            if result.status != "success":
                raise GameError("ACTION_FAILED", "Game action failed; inspect its durable Run. This request will not be replayed.", 409)
            completed = run.complete(summary="Game action completed", selected_artifact_id=result.artifacts[-1].id if result.artifacts else None)
            output = c.ActionResult(session_id=completed.session_id, run_id=completed.run_id, artifact_ids=[item.id for item in completed.artifacts], outcome=result.output)
            store.finish_action(project_id, data.request_id, tool_name, request, output)
            return output

    operation("games.list", c.ListInput, c.Page, listing)
    operation("games.head", c.HeadInput, c.HeadOutput, head)
    operation("games.get", c.GetInput, c.Page, get)
    operation("games.create", c.CreateRequest, c.Mutation, create)
    operation("games.apply", c.ApplyRequest, c.Mutation, mutation)
    operation("games.undo", c.UndoRequest, c.Mutation, mutation)
    operation("games.delete", c.VersionRequest, c.Mutation, mutation)
    operation("assets.upload", c.UploadRequest, c.Mutation, mutation)
    operation("games.revisions", c.HistoryInput, c.Page, history)
    operation("games.diff", c.DiffInput, c.Page, diff)
    operation("games.export", c.VersionRequest, c.ActionResult, export)
    operation("games.playtest", c.PlaytestRequest, c.ActionResult, playtest)

    def machine(name: str, input_model: type[c.Input], output_model: type[c.Contract], handler: Callable[[c.Input], c.Contract], maximum: int) -> None:
        def invoke(data: c.Input, context: DlcOperationContext) -> c.Contract:
            try:
                if context.dlc_id != c.OWNER or context.operation_name != name or context.project_id is not None:
                    raise GameError("INVALID_EXECUTOR", "Game executor requires its owner machine operation")
                return handler(data)
            except GameError as exc:
                raise DlcOperationError(code=exc.code, message=str(exc), status_code=exc.status) from exc
        host.operations.register(DlcOperationSpec(name=name, input_model=input_model, output_model=output_model, handler=invoke, scope="machine", description="Transient Phaser activation " + name, max_output_bytes=maximum))

    def attach(data: c.Input) -> c.Attachment:
        if not isinstance(data, c.AttachInput):
            raise GameError("INVALID_EXECUTOR", "Attach contract mismatch")
        return bridge.attach(data)

    def poll(data: c.Input) -> c.PollOutput:
        if not isinstance(data, c.Lease):
            raise GameError("INVALID_EXECUTOR", "Lease contract mismatch")
        return bridge.next(data)

    def complete(data: c.Input) -> c.Acknowledged:
        if not isinstance(data, c.CompleteInput):
            raise GameError("INVALID_EXECUTOR", "Complete contract mismatch")
        return bridge.complete(data)

    def detach(data: c.Input) -> c.Acknowledged:
        if not isinstance(data, c.Lease):
            raise GameError("INVALID_EXECUTOR", "Detach contract mismatch")
        return bridge.detach(data)

    machine("playtest.attach", c.AttachInput, c.Attachment, attach, 2048)
    machine("playtest.next", c.Lease, c.PollOutput, poll, 8388608)
    machine("playtest.complete", c.CompleteInput, c.Acknowledged, complete, 2048)
    machine("playtest.detach", c.Lease, c.Acknowledged, detach, 2048)
