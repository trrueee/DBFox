"""Public API v2 registrations; no private Core imports or alternate execution chain."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from dbfox_dlc_api import (
    BackendExtensionHost, BaseModel, CapabilityGuidanceSpec, ContextContributionInput,
    ContextFragment, DlcOperationContext, DlcOperationError, DlcOperationSpec,
    RequestedResourceRef, SemanticArtifactCompletionSupport, ToolKey,
)
from pydantic import JsonValue

from . import contracts as c
from .compute import ComputeBridge
from .inspection import diff, get_page, inspect, metadata, revisions
from .representation import Representation
from .store import ShaderError, Store
from .tools import TOOL_TYPES

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


def project(context: DlcOperationContext) -> str:
    if context.dlc_id != c.OWNER or context.project_id is None:
        raise ShaderError("SHADER_SCOPE", "A Shader-owned Project context is required.")
    return context.project_id


def boundary(handler: Callable[[I, DlcOperationContext], O]) -> Callable[[I, DlcOperationContext], O]:
    def invoke(data: I, context: DlcOperationContext) -> O:
        if context.dlc_id != c.OWNER:
            raise DlcOperationError(code="SHADER_SCOPE", message="Shader owner context is required.", status_code=403)
        try:
            return handler(data, context)
        except ShaderError as exc:
            status = 409 if exc.code in {"STALE_VERSION", "SHADER_REQUEST_CONFLICT", "SHADER_COMPUTE_BUSY", "SHADER_EPOCH_STALE", "SHADER_DELETED"} else 404 if exc.code == "SHADER_NOT_FOUND" else 400
            raise DlcOperationError(code=exc.code, message=str(exc)[:512], status_code=status) from exc
        except ValueError as exc:
            raise DlcOperationError(code="SHADER_INVALID", message="Shader request violates the domain contract.") from exc
    return invoke


class ShaderContext:
    id = c.OWNER

    def __init__(self, store: Store) -> None:
        self.store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        scopes = [ref for ref in input.resource_refs if ref.kind == c.STUDIO_KIND]
        if len(scopes) != 1:
            return ()
        ref = scopes[0]
        studio = self.store.resolve(ref)
        with self.store.transaction() as db:
            catalog, total = self.store.catalog(db, studio.project_id, studio.generation, limit=8)
            known = {value.document.id: value for value in catalog}
            # Recent Artifact locators are historical evidence only, never new Tool authority.
            for artifact in input.recent_artifacts:
                if artifact.artifact_type not in {c.DOCUMENT_ARTIFACT, c.REPORT_ARTIFACT, c.PREVIEW_ARTIFACT} or not any(value.kind == c.STUDIO_KIND and value.id == studio.project_id for value in artifact.resource_refs):
                    continue
                locator = c.ArtifactLocator.model_validate(artifact.payload)
                if locator.project_id == studio.project_id and (locator.document_id in known or len(known) < 8):
                    revision = self.store.read_revision(db, studio.project_id, locator.document_id, locator.version)
                    if revision.content_hash != locator.content_hash:
                        raise ShaderError("SHADER_CORRUPT", "Context Artifact fingerprint mismatch.")
                    previous = known.get(locator.document_id)
                    if previous is None or previous.version < revision.version:
                        known[locator.document_id] = revision
            documents: list[dict[str, JsonValue]] = []
            for value in known.values():
                item = value.summary().model_dump(mode="json")
                item.update({key: count for key, count in metadata(value).items() if key.endswith("_count")})
                row = db.execute("SELECT id FROM reports WHERE project=? AND document_id=? AND version=? ORDER BY rowid DESC LIMIT 1", (studio.project_id, value.document.id, value.version)).fetchone()
                if row is None:
                    item["compile_status"] = "not_compiled"
                else:
                    report, _ = self.store.read_report(db, studio.project_id, row[0])
                    item.update(compile_status="compiled" if report.compiled else "compile_errors", report_id=report.id)
                documents.append(item)
        content: dict[str, JsonValue] = {"studio_id": studio.project_id, "studio_generation": studio.generation, "documents": documents, "truncated": total>len(documents)}
        while len(c.encoded(content).decode("utf-8")) > 4000 and documents:
            documents.pop()
            content["truncated"] = True
        return (ContextFragment(source_id=self.id, source_version=str(studio.generation), lane="resource", content=c.encoded(content).decode("utf-8"), provenance={"resource_kind": c.STUDIO_KIND, "studio_id": studio.project_id, "generation": studio.generation}),)


def operation_specs(store: Store, bridge: ComputeBridge) -> tuple[DlcOperationSpec, ...]:
    def list_documents(data: c.PageInput, context: DlcOperationContext) -> c.PageResult:
        return inspect(store, project(context), c.InspectInput(section="documents", **data.model_dump()))

    def get(data: c.GetInput, context: DlcOperationContext) -> c.PageResult:
        return get_page(store, project(context), data)

    def head(data: c.HeadInput, context: DlcOperationContext) -> c.HeadResult:
        return store.head(project(context), data.document_id)

    def create(data: c.CreateRequest, context: DlcOperationContext) -> c.MutationResult:
        return store.mutate(project(context), "human", data.request_id, "create", data)

    def apply(data: c.ApplyRequest, context: DlcOperationContext) -> c.MutationResult:
        return store.mutate(project(context), "human", data.request_id, "apply", data)

    def undo(data: c.UndoRequest, context: DlcOperationContext) -> c.MutationResult:
        return store.mutate(project(context), "human", data.request_id, "undo", data)

    def delete(data: c.VersionRequest, context: DlcOperationContext) -> c.MutationResult:
        return store.mutate(project(context), "human", data.request_id, "delete", data)

    def revision_list(data: c.RevisionsInput, context: DlcOperationContext) -> c.PageResult:
        return revisions(store, project(context), data)

    def differences(data: c.DiffInput, context: DlcOperationContext) -> c.PageResult:
        return diff(store, project(context), data)

    def action(data: c.VersionRequest, context: DlcOperationContext) -> c.ActionResult:
        project_id = project(context)
        names = {"documents.compile": "compile", "documents.preview": "render_preview", "documents.export": "shader_export"}
        tool_name = names[context.operation_name]
        with context.require_action_runs().start(title="Shader " + tool_name, question=f"Explicit Shader action {tool_name} for document {data.document_id} version {data.expected_version}.", requested_resources=(RequestedResourceRef(kind=c.STUDIO_KIND, id=project_id),), idempotency_key=data.request_id) as run:
            result = run.invoke(tool_name, data.model_dump(mode="json", exclude={"request_id"}))
            if result.status != "success":
                raise ShaderError("SHADER_ACTION_FAILED", "Shader action did not complete; inspect its Run before requesting new work.")
            completed = run.complete(summary="Shader action completed with its exact observed outcome.", selected_artifact_id=result.artifacts[-1].id if result.artifacts else None)
            return c.ActionResult(session_id=completed.session_id, run_id=completed.run_id, artifact_ids=[value.id for value in completed.artifacts], outcome=result.output)

    def attach(data: c.AttachInput, context: DlcOperationContext) -> c.AttachResult:
        return bridge.attach(data)

    def next_request(data: c.LeaseInput, context: DlcOperationContext) -> c.NextResult:
        return bridge.next(data)

    def complete(data: c.CompleteInput, context: DlcOperationContext) -> c.Accepted:
        return bridge.complete(data)

    def detach(data: c.DetachInput, context: DlcOperationContext) -> c.Accepted:
        return bridge.detach(data)

    return (
        DlcOperationSpec(name="documents.list", input_model=c.PageInput, output_model=c.PageResult, handler=boundary(list_documents), scope="project", max_output_bytes=32768),
        DlcOperationSpec(name="documents.get", input_model=c.GetInput, output_model=c.PageResult, handler=boundary(get), scope="project", max_output_bytes=32768),
        DlcOperationSpec(name="documents.head", input_model=c.HeadInput, output_model=c.HeadResult, handler=boundary(head), scope="project"),
        DlcOperationSpec(name="documents.create", input_model=c.CreateRequest, output_model=c.MutationResult, handler=boundary(create), scope="project"),
        DlcOperationSpec(name="documents.apply", input_model=c.ApplyRequest, output_model=c.MutationResult, handler=boundary(apply), scope="project"),
        DlcOperationSpec(name="documents.undo", input_model=c.UndoRequest, output_model=c.MutationResult, handler=boundary(undo), scope="project"),
        DlcOperationSpec(name="documents.delete", input_model=c.VersionRequest, output_model=c.MutationResult, handler=boundary(delete), scope="project"),
        DlcOperationSpec(name="documents.revisions", input_model=c.RevisionsInput, output_model=c.PageResult, handler=boundary(revision_list), scope="project", max_output_bytes=32768),
        DlcOperationSpec(name="documents.diff", input_model=c.DiffInput, output_model=c.PageResult, handler=boundary(differences), scope="project", max_output_bytes=32768),
        DlcOperationSpec(name="documents.compile", input_model=c.VersionRequest, output_model=c.ActionResult, handler=boundary(action), scope="project"),
        DlcOperationSpec(name="documents.preview", input_model=c.VersionRequest, output_model=c.ActionResult, handler=boundary(action), scope="project"),
        DlcOperationSpec(name="documents.export", input_model=c.VersionRequest, output_model=c.ActionResult, handler=boundary(action), scope="project"),
        DlcOperationSpec(name="compute.attach", input_model=c.AttachInput, output_model=c.AttachResult, handler=boundary(attach), scope="machine"),
        DlcOperationSpec(name="compute.next", input_model=c.LeaseInput, output_model=c.NextResult, handler=boundary(next_request), scope="machine", max_output_bytes=8_388_608),
        DlcOperationSpec(name="compute.complete", input_model=c.CompleteInput, output_model=c.Accepted, handler=boundary(complete), scope="machine"),
        DlcOperationSpec(name="compute.detach", input_model=c.DetachInput, output_model=c.Accepted, handler=boundary(detach), scope="machine"),
    )


def register(host: BackendExtensionHost) -> None:
    store = Store(host.runtime_info.data_path)
    bridge = ComputeBridge(host.runtime_info.package_digest)
    tools = [tool_type(store, bridge) for tool_type in TOOL_TYPES]
    for tool in tools:
        host.tools.register(tool)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(c.STUDIO_KIND, store.resolve)
    host.context.register(ShaderContext(store))
    for kind in (c.DOCUMENT_ARTIFACT, c.REPORT_ARTIFACT, c.PREVIEW_ARTIFACT):
        host.artifacts.register(kind, 1, c.ArtifactLocator)
    for kind, representation in ((c.DOCUMENT_ARTIFACT, "dbfox.shader.document.v1"), (c.REPORT_ARTIFACT, "dbfox.shader.compile-report.v1"), (c.PREVIEW_ARTIFACT, "dbfox.shader.preview.v1"), (c.PREVIEW_ARTIFACT, "dbfox.shader.preview-png.v1")):
        host.artifacts.register_representation(kind, representation, Representation(store, kind, representation))
    for spec in operation_specs(store, bridge):
        host.operations.register(spec)
    host.completion.register_support(SemanticArtifactCompletionSupport(id="dbfox.shader.document", semantic_capability=c.DOCUMENT_ARTIFACT))
    host.completion.register_support(SemanticArtifactCompletionSupport(id="dbfox.shader.report", semantic_capability=c.REPORT_ARTIFACT))
    host.completion.register_support(SemanticArtifactCompletionSupport(id="dbfox.shader.preview", semantic_capability=c.PREVIEW_ARTIFACT))
    host.agent_guidance.register(CapabilityGuidanceSpec(id="shader_authoring", version="1", applies_to_resource_kinds=(c.STUDIO_KIND,), applies_to_artifact_types=(c.DOCUMENT_ARTIFACT, c.REPORT_ARTIFACT, c.PREVIEW_ARTIFACT), tool_refs=tuple(ToolKey(owner_id=c.OWNER, local_name=tool.name) for tool in tools), instructions=(
        "Use Shader Studio Tools for ESSL 3.00 documents. Inspect existing work and use returned document/object ids and exact version for bounded incremental edits. "
        "Create returns default vertex/fragment/pass ids. A mutation advances only its document version and the studio generation; no-op preserves both. "
        "On stale state inspect again; do not replay unknown outcomes. A missing reconcile receipt is unknown. Local refs only name earlier creates in the same atomic batch. "
        "Passes execute in listed order with earlier-only texture inputs, fixed fullscreen triangle and explicit uniforms. Only u_resolution vec2 and u_time float are builtins. "
        "Compile and render_preview require a visible active Chromium WebGL2 executor. A saved source or old report is not proof of current compilation. "
        "compiled=false is an observed compiler/binding failure: read its exact report, repair only the diagnosed source/config, then explicitly compile again. "
        "Unavailability, cancellation and timeout never imply successful GPU work. Durable previews use frozen time and exact source version; local playback is not durable evidence. "
        "Use immutable Artifact representations for composition. Never request raw pixels in normal observations, use paths/URLs for textures, replace the whole document, "
        "invent object ids, or add an alternate execution chain. Clarify an ambiguous destructive edit before applying it.")))
