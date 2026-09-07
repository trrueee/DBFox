"""Comic uses only the public Host resource, tool, operation and Artifact seams."""
from __future__ import annotations

import sqlite3
from dbfox_dlc_api import (ArtifactDraft, BackendExtensionHost, BaseTool, CapabilityGuidanceSpec,
    ContextFragment, DlcOperationError, DlcOperationSpec, RequestedResourceRef,
    SemanticArtifactCompletionSupport, ToolExecutionSpec, ToolInputError, ToolKey,
    ToolObservationProjection, ToolOutcome, ToolPolicy, ToolPresentation, ToolReconciliation,
    ToolResourceRequirement, ToolSemanticSpec)
from pydantic import create_model
from .contracts import (ARTIFACT_TYPE, OWNER, REPRESENTATION_TYPE, DOCUMENT_KIND, LIBRARY_KIND,
    ApplyInput, ApplyRequest, ArtifactResult, CreateInput, CreateRequest, DiffInput, DiffResult,
    InspectInput, InspectResult, Library, ListResult, MutationResult, OPERATIONS, PageInput,
    Revision, RevisionArtifact, ToolInspectInput, UndoInput, UndoRequest, VersionInput, VersionRequest)
from .store import ComicError, ComicStore, encoded
from .representation import ComicRepresentation


def artifact(summary, scope):
    return ArtifactDraft(key="comic_revision", type=ARTIFACT_TYPE, schema_version=1,
        title=f"{summary.title} · v{summary.version}", payload=summary.model_dump(mode="json"),
        summary=f"Comic revision {summary.version}: {summary.page_count} pages, {summary.panel_count} panels.",
        semantic_key=f"comic:{summary.id}:{summary.version}", resource_refs=(scope,))


def resource(context, kind, identity=None):
    refs = context.scopes(kind)
    if len(refs) != 1 or (identity is not None and refs[0].id != identity):
        raise ToolInputError("An exact frozen Comic resource is required.")
    scope = refs[0]
    resolved = context.resource(scope)
    if kind == LIBRARY_KIND:
        if not isinstance(resolved, Library) or resolved.project_id != scope.id or scope.version != 1:
            raise ToolInputError("Invalid resolved Comic Library.")
    elif not isinstance(resolved, Revision) or resolved.comic.id != scope.id or resolved.comic.version != scope.version:
        raise ToolInputError("Resolved Comic revision does not match frozen authority.")
    return resolved, scope


READ = ToolExecutionSpec(recovery="retry_safe", retryable=True, max_retries=1, concurrency="parallel_safe",
    max_output_bytes=256 * 1024, required_resources=(ToolResourceRequirement(kind=DOCUMENT_KIND, selector_field="comic_id"),))
WRITE = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential", max_output_bytes=64 * 1024,
    required_resources=(ToolResourceRequirement(kind=DOCUMENT_KIND, selector_field="comic_id"),))


class ComicWriteTool(BaseTool[ApplyInput, MutationResult]):
    name = "comic_apply"
    group = "comic"
    version = "1"
    description = "Incrementally edit a comic at expected_version; preserve unrelated visual narration."
    input_model = ApplyInput
    output_model = MutationResult
    execution = WRITE
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    presentation = ToolPresentation(title="编辑分镜", category="manage")
    semantics = ToolSemanticSpec(produces=(ARTIFACT_TYPE,))
    action = "apply"

    def __init__(self, store):
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="Comic operation did not complete.")
        result = MutationResult.model_validate(output)
        values = result.model_dump(mode="json")
        return ToolObservationProjection(summary=f"Comic {result.comic.id} v{result.comic.version}; changed={result.changed}.",
                                         facts=values, provider_payload=values)

    def _source(self, input, context):
        if self.action == "create":
            source, scope = resource(context, LIBRARY_KIND)
            return source.project_id, scope
        source, scope = resource(context, DOCUMENT_KIND, input.comic_id)
        return source.comic.project_id, scope

    def run(self, input, context):
        project, scope = self._source(input, context)
        try:
            result = self.store.write(project, self.action, input, context.invocation_id,
                frozen=scope.version if self.action != "create" else None, cancelled=context.is_cancelled)
        except ComicError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc
        return ToolOutcome(output=result, artifacts=(artifact(result.comic, scope),))

    def reconcile(self, input, context):
        project, scope = self._source(input, context)
        result = self.store.reconcile(project, self.action, input, context.invocation_id)
        if result is None:
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json"), artifacts=(artifact(result.comic, scope),))


class ComicReadTool(BaseTool[ToolInspectInput, InspectResult]):
    name = "comic_inspect"
    group = "comic"
    version = "1"
    description = "Inspect bounded pages, panels, or elements; carry the returned version into subsequent pages and edits."
    input_model = ToolInspectInput
    output_model = InspectResult
    execution = READ
    policy = ToolPolicy(risk_level="safe")
    presentation = ToolPresentation(title="检查分镜", category="explore")

    def __init__(self, store):
        self.store = store

    def run(self, input, context):
        source, scope = resource(context, DOCUMENT_KIND, input.comic_id)
        if context.is_cancelled():
            raise ToolInputError("Comic read was cancelled.")
        try:
            if self.name == "comic_diff":
                if max(input.from_version, input.to_version) > scope.version:
                    raise ComicError("STALE", "Cannot read versions newer than frozen authority.")
                result = self.store.diff(source.comic.project_id, input)
            else:
                version = input.version if input.version is not None else scope.version
                if version > scope.version:
                    raise ComicError("STALE", "Cannot read a version newer than frozen authority.")
                result = self.store.inspect(source.comic.project_id, input.model_copy(update={"version": version}))
        except ComicError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc
        return ToolOutcome(output=result)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="Comic inspection did not complete.")
        values = self.output_model.model_validate(output).model_dump(mode="json")
        field = "differences" if self.name == "comic_diff" else "items"
        while values[field] and len(encoded(values).encode("utf-8")) > 24_000:
            values[field].pop()
        values["next_offset"] = values["offset"] + len(values[field])
        if field == "items":
            values["has_more"] = values["next_offset"] < values["total"]
        return ToolObservationProjection(summary=f"Comic inspection returned {len(values[field])} entries.", facts=values, provider_payload=values)


def build_tools(store):
    result = [ComicReadTool(store)]
    for name, action, model in (("comic_create", "create", CreateInput), ("comic_undo", "undo", UndoInput),
                                ("comic_delete", "delete", VersionInput), ("comic_export", "export", VersionInput)):
        cls = type(name, (ComicWriteTool,), {"name": name, "action": action, "input_model": model,
            "description": f"{name}: durable Comic operation; edits require the exact inspected version.",
            "execution": ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential",
                max_output_bytes=64 * 1024, required_resources=(ToolResourceRequirement(kind=LIBRARY_KIND),)) if action == "create" else WRITE,
            "reconcile": ComicWriteTool.reconcile})
        result.append(cls(store))
    for model in OPERATIONS:
        name = model.model_fields["kind"].default
        input_model = create_model(model.__name__ + "Input", __base__=ApplyInput, operation=(model, ...))
        cls = type(model.__name__ + "Tool", (ComicWriteTool,), {"name": name, "input_model": input_model,
            "description": f"{name}: edit exact page/panel/element IDs at expected_version. Coordinates are normalized within the parent.",
            "reconcile": ComicWriteTool.reconcile})
        result.append(cls(store))
    diff = type("ComicDiffTool", (ComicReadTool,), {"name": "comic_diff", "input_model": DiffInput,
                "output_model": DiffResult, "description": "Compare fixed Comic versions with bounded changed object IDs, fields and hashes."})
    result.append(diff(store))
    return tuple(result)


class ComicContext:
    id = "dbfox.comic.context"

    def __init__(self, store):
        self.store = store

    def build(self, input):
        lines = []
        for ref in input.resource_refs:
            if ref.kind == LIBRARY_KIND:
                lines.append("Comic Library: create a new visual narrative.")
            elif ref.kind == DOCUMENT_KIND:
                try:
                    summary = self.store.resolve(ref).comic
                    lines.append(f"Comic {summary.id} v{summary.version}: {summary.page_count} pages, {summary.panel_count} panels. Inspect exact IDs before editing.")
                except ComicError:
                    continue
        if not lines:
            return ()
        return (ContextFragment(source_id=self.id, source_version="1", lane="resource", content="\n".join(lines)[:4000], provenance={"owner": OWNER}),)


def register(host: BackendExtensionHost):
    store = ComicStore(host.runtime_info.data_path)
    tools = build_tools(store)
    for tool in tools:
        host.tools.register(tool)
    host.resources.register_provider(store.resources)
    host.resources.register_resolver(LIBRARY_KIND, store.resolve_library)
    host.resources.register_resolver(DOCUMENT_KIND, store.resolve)
    host.context.register(ComicContext(store))
    host.artifacts.register(ARTIFACT_TYPE, 1, RevisionArtifact)
    host.artifacts.register_representation(ARTIFACT_TYPE, REPRESENTATION_TYPE, ComicRepresentation(store))
    host.completion.register_support(SemanticArtifactCompletionSupport(id=ARTIFACT_TYPE, semantic_capability=ARTIFACT_TYPE))
    host.agent_guidance.register(CapabilityGuidanceSpec(id="comic_authoring", version="1",
        instructions="Comic owns visual narrative, not Story world facts. Use Comic Library to create, then the returned comic ID. "
        "Inspect pages, panels and elements in fixed-version pages. Supply expected_version and exact stable IDs for incremental changes. "
        "Coordinates are normalized to the containing page or panel. Character labels describe visual placements, not a second character database. "
        "Never regenerate an entire comic. For ambiguous instructions clarify before mutation. Stale edits require reinspection, never blind replay. "
        "Reorder must list all siblings exactly once. Unassign speech bubbles before deleting their speaker. Undo restores an old document as a new version. "
        "Export produces immutable HTML/JSON representations; only claim changes with successful tool evidence.",
        applies_to_resource_kinds=(LIBRARY_KIND, DOCUMENT_KIND), applies_to_artifact_types=(ARTIFACT_TYPE,),
        tool_refs=tuple(ToolKey(owner_id=OWNER, local_name=t.name) for t in tools)))

    def project(context):
        if context.dlc_id != OWNER or not context.project_id:
            raise DlcOperationError(code="COMIC_PROJECT_REQUIRED", message="An active Project is required.")
        return context.project_id

    def guard(handler):
        def call(input, context):
            try:
                return handler(input, context)
            except ComicError as exc:
                raise DlcOperationError(code=exc.code, message=str(exc), status_code=404 if exc.code == "COMIC_NOT_FOUND" else 409) from exc
            except sqlite3.OperationalError as exc:
                raise DlcOperationError(code="COMIC_BUSY", message="Comic storage is busy; inspect before trying again.", status_code=503) from exc
        return call

    specs = [("comics.list", PageInput, ListResult, lambda i, c: store.list(project(c), i)),
             ("comics.get", InspectInput, InspectResult, lambda i, c: store.inspect(project(c), i)),
             ("comics.diff", DiffInput, DiffResult, lambda i, c: store.diff(project(c), i))]
    for name, action, request_model, input_model in (("create", "create", CreateRequest, CreateInput),
            ("apply", "apply", ApplyRequest, ApplyInput), ("undo", "undo", UndoRequest, UndoInput),
            ("delete", "delete", VersionRequest, VersionInput)):
        def write(input, context, action=action, model=input_model):
            p = project(context)
            payload = model.model_validate(input.model_dump(exclude={"request_id"}))
            return store.write(p, action, payload, f"ui:{p}:{input.request_id}")
        specs.append(("comics." + name, request_model, MutationResult, write))

    def export(input, context):
        p = project(context)
        store.fence(store.get(p, input.comic_id), input.expected_version)
        with context.require_action_runs().start(title="Comic export", question="Export this Comic revision.",
                requested_resources=(RequestedResourceRef(kind=DOCUMENT_KIND, id=input.comic_id),), idempotency_key=input.request_id) as action:
            result = action.invoke("comic_export", {"comic_id": input.comic_id, "expected_version": input.expected_version})
            if result.status != "success" or not result.artifacts:
                raise ComicError("ARTIFACT", "Comic export action did not complete.")
            selected = result.artifacts[0].id
            completed = action.complete(summary="Immutable Comic export is ready.", selected_artifact_id=selected)
            return ArtifactResult(artifact_id=selected, run_id=completed.run_id, session_id=completed.session_id)
    specs.append(("comics.artifact", VersionRequest, ArtifactResult, export))
    for name, input_model, output_model, handler in specs:
        host.operations.register(DlcOperationSpec(name=name, input_model=input_model, output_model=output_model,
            handler=guard(handler), scope="project", max_output_bytes=256 * 1024))
