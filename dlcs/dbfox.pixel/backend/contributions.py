"""Public Host tools, resources, bounded context and project operations."""
from __future__ import annotations

from dbfox_dlc_api import (ArtifactDraft, BaseTool, CapabilityGuidanceSpec, ContextFragment,
    DlcOperationError, DlcOperationSpec, RequestedResourceRef, SemanticArtifactCompletionSupport,
    ToolExecutionSpec, ToolInputError, ToolKey, ToolObservationProjection, ToolOutcome,
    ToolPolicy, ToolPresentation, ToolReconciliation, ToolResourceRequirement, ToolSemanticSpec)
from pydantic import create_model

from . import contracts as c
from .domain import PixelError, require
from .representation import PixelRepresentation
from .store import PixelStore


def revision_artifact(result, scope):
    summary = c.DocumentSummary.model_validate(result.model_dump(exclude={"changed", "changed_pixel_count", "changed_frame_ids", "changed_frame_ids_truncated", "changed_layer_ids"}))
    return ArtifactDraft(key="pixel_revision", type=c.ARTIFACT_TYPE, schema_version=1,
        title=f"{summary.title} · r{summary.revision}", payload=summary.model_dump(mode="json"),
        summary=f"{summary.width}x{summary.height}; {summary.frame_count} frames, {summary.layer_count} layers; revision {summary.revision}.",
        semantic_key=f"pixel:{summary.document_id}:{summary.revision}", resource_refs=(scope,))


def _authorized(context, input, library):
    kind = c.LIBRARY_KIND if library else c.DOCUMENT_KIND
    expected_id = input.library_id if library else input.document_id
    refs = context.scopes(kind)
    require(len(refs) == 1 and refs[0].id == expected_id, "One exact frozen Pixel resource is required.", "AUTHORITY")
    scope = refs[0]
    value = context.resource(scope)
    if library:
        require(isinstance(value, c.Library) and value.project_id == scope.id and str(scope.version) == "1",
                "Pixel Library handle does not match the invocation.", "AUTHORITY")
        return value.project_id, scope
    require(isinstance(value, c.Revision) and value.summary.document_id == scope.id and str(value.summary.revision) == str(scope.version),
            "Pixel document handle does not match the invocation.", "AUTHORITY")
    return value.summary.project_id, scope


def _execution(library=False, write=False):
    return ToolExecutionSpec(recovery="reconcile" if write else "retry_safe", retryable=not write,
        max_retries=0 if write else 1, concurrency="sequential" if write else "parallel_safe", max_output_bytes=c.MAX_OUTPUT_BYTES,
        required_resources=(ToolResourceRequirement(kind=c.LIBRARY_KIND if library else c.DOCUMENT_KIND,
            selector_field="library_id" if library else "document_id"),))


class PixelWriteTool(BaseTool):
    name = "pixel_apply"
    group = "pixel"
    description = "Atomically apply up to 128 typed incremental Pixel operations. Inspect first and use expected_version; stale edits fail without changing the document."
    input_model = c.ApplyInput
    output_model = c.MutationResult
    version = "1"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = _execution(write=True)
    presentation = ToolPresentation(title="编辑像素作品", category="manage")
    semantics = ToolSemanticSpec(produces=(c.ARTIFACT_TYPE,))
    action = "apply"
    library = False

    def __init__(self, store):
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        if status != "success":
            return ToolObservationProjection(summary="Pixel operation did not complete.")
        result = c.MutationResult.model_validate(output)
        facts = result.model_dump(mode="json")
        require(len(c.canonical(facts).encode("utf-8")) <= c.MAX_OUTPUT_BYTES, "Pixel observation exceeds its budget.", "LIMIT")
        return ToolObservationProjection(summary=f"Pixel {result.document_id} revision {result.revision}; changed={result.changed}.",
                                         facts=facts, provider_payload=facts)

    def run(self, input, context):
        try:
            project_id, scope = _authorized(context, input, self.library)
            if self.action == "create":
                result = self.store.create(project_id, input, context.invocation_id, "agent", scope, context.is_cancelled)
            else:
                result = self.store.mutate(project_id, input, context.invocation_id, self.action, "agent", scope, context.is_cancelled)
            return ToolOutcome(output=result, artifacts=(revision_artifact(result, scope),))
        except PixelError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc

    def reconcile(self, input, context):
        try:
            project_id, scope = _authorized(context, input, self.library)
            result = self.store.reconcile(project_id, "agent", context.invocation_id, self.action, input, scope)
            if result is None:
                return ToolReconciliation(status="not_applied")
            return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json"), artifacts=(revision_artifact(result, scope),))
        except PixelError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc


class PixelReadTool(BaseTool):
    name = "pixel_inspect"
    group = "pixel"
    description = "Inspect bounded Pixel frame/layer/tag/palette metadata and an optional 16x16 cel window. Preserve returned document_id and revision; use smaller pages if a rich diff exceeds its budget."
    input_model = c.InspectInput
    output_model = c.PageResult
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = _execution()
    presentation = ToolPresentation(title="查看像素作品", category="explore")
    action = "inspect"
    library = False

    def __init__(self, store):
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        del artifacts
        if status != "success":
            return ToolObservationProjection(summary="Pixel inspection did not complete.")
        result = self.output_model.model_validate(output)
        provider = result.model_dump(mode="json")
        facts = {key: value for key, value in provider.items() if key != "pixels"}
        require(len(c.canonical(provider).encode("utf-8")) <= c.MAX_OUTPUT_BYTES, "Pixel observation exceeds its budget.", "LIMIT")
        return ToolObservationProjection(summary="Pixel inspection returned a bounded page; inspect the next page when has_more is true.",
                                         facts=facts, provider_payload=provider)

    def run(self, input, context):
        try:
            project_id, scope = _authorized(context, input, self.library)
            if self.action == "inspect":
                # An explicit historical read cannot jump beyond frozen authority.
                revision = input.revision if input.revision is not None else int(scope.version)
                require(revision <= int(scope.version), "Pixel read exceeds the frozen revision.", "AUTHORITY")
                request = c.InspectInput.model_validate({**input.model_dump(mode="json"), "revision": revision})
                result = self.store.inspect(project_id, request)
            elif self.action == "diff":
                require(max(input.from_revision, input.to_revision) <= int(scope.version), "Pixel diff exceeds the frozen revision.", "AUTHORITY")
                result = self.store.diff(project_id, input)
            else:
                result = self.store.list_documents(project_id, input)
            require(len(c.canonical(result).encode("utf-8")) <= c.MAX_OUTPUT_BYTES, "Pixel page exceeds output budget; request a smaller page.", "LIMIT")
            return ToolOutcome(output=result)
        except PixelError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc


def build_tools(store):
    tools = [PixelWriteTool(store), PixelReadTool(store)]
    for name, action, model, library in (
        ("pixel_create", "create", c.CreateToolInput, True), ("pixel_restore", "restore", c.RestoreInput, True),
        ("pixel_undo", "undo", c.UndoInput, False), ("pixel_delete", "delete", c.VersionInput, False),
        ("pixel_export", "export", c.VersionInput, False)):
        tool_type = type(name + "Tool", (PixelWriteTool,), {"name": name, "action": action, "input_model": model,
            "library": library, "execution": _execution(library, True), "reconcile": PixelWriteTool.reconcile,
            "description": f"{action.capitalize()} a durable Pixel document. Use exact resource identity and expected_version; creation requires zero. Preserve unrelated content and never automatically replay a write."})
        tools.append(tool_type(store))
    for name, operation in (("pixel_fill", c.Fill), ("pixel_line", c.Line), ("pixel_rect", c.Rectangle),
        ("pixel_stamp", c.Stamp), ("palette_set", c.PaletteSet), ("frame_create", c.FrameCreate),
        ("frame_duplicate", c.FrameDuplicate), ("layer_create", c.LayerCreate), ("region_transform", c.RegionTransform)):
        model = create_model(name + "Input", __base__=c.SingleInput, operation=(operation, ...))
        tool_type = type(name + "Tool", (PixelWriteTool,), {"name": name, "input_model": model, "reconcile": PixelWriteTool.reconcile,
            "description": f"Apply the typed {name} incremental Pixel operation at expected_version. Inspect exact frame/layer IDs first; coordinates are integer pixels and rectangles are half-open. Operation kind is required."})
        tools.append(tool_type(store))
    for name, action, model, output, library in (
        ("pixel_diff", "diff", c.DiffInput, c.DiffResult, False), ("pixel_documents", "list", c.DocumentsInput, c.ListResult, True)):
        tool_type = type(name + "Tool", (PixelReadTool,), {"name": name, "action": action, "input_model": model,
            "output_model": output, "library": library, "execution": _execution(library)})
        tools.append(tool_type(store))
    return tuple(tools)


class PixelContext:
    id = c.OWNER + ".context"
    def __init__(self, store):
        self.store = store

    def build(self, input):
        lines = []
        for ref in input.resource_refs:
            if ref.kind == c.DOCUMENT_KIND:
                try:
                    value = self.store.resolve_document(ref)
                except PixelError:
                    continue
                summary = value.summary
                lines.append(f"Pixel document {summary.document_id} revision {summary.revision}; {summary.width}x{summary.height}; "
                             f"{summary.frame_count} frames, {summary.layer_count} layers, {summary.tag_count} animation tags. "
                             "Use pixel_inspect for exact object IDs; expected_version is required for edits.")
            elif ref.kind == c.LIBRARY_KIND:
                lines.append(f"Pixel Library {ref.id} permits creation with expected_version=0. Use the returned document ID for later tools in the same Run.")
        fragments, current = [], ""
        for line in lines:
            if len(current) + len(line) + 1 > 2000:
                fragments.append(current)
                current = ""
            current += line + "\n"
            if len(fragments) == 4:
                break
        if current and len(fragments) < 4:
            fragments.append(current)
        return tuple(ContextFragment(source_id=self.id, source_version="1", lane="resource", content=value,
            provenance={"owner": c.OWNER}) for value in fragments)


def register_operations(host, store):
    def project(context):
        require(context.dlc_id == c.OWNER and context.project_id, "A project-scoped Pixel operation is required.", "AUTHORITY")
        return context.project_id

    def export(input, context):
        project_id = project(context)
        previous = store.reserve_export(project_id, input)
        if previous is not None:
            return previous
        with context.require_action_runs().start(title="Pixel export", question="Export this immutable Pixel revision.",
            requested_resources=(RequestedResourceRef(kind=c.DOCUMENT_KIND, id=input.document_id),), idempotency_key=input.mutation_id) as action:
            output = action.invoke("pixel_export", {"document_id": input.document_id, "expected_version": input.expected_version})
            require(output.status == "success" and output.artifacts, "Pixel Artifact action did not complete.", "EXPORT_FAILED")
            completed = action.complete(summary="Pixel PNG and sprite sheet are ready.", selected_artifact_id=output.artifacts[0].id)
            result = c.ExportResult(run_id=completed.run_id, session_id=completed.session_id, artifact_ids=[item.id for item in output.artifacts])
        store.finish_export(project_id, input, result)
        return result

    specs = [
        ("documents.list", c.ListInput, c.ListResult, lambda i, x: store.list_documents(project(x), i), 65536),
        ("documents.get", c.ReadInput, c.MetadataResult, lambda i, x: store.get(project(x), i), 524288),
        ("documents.head", c.HeadInput, c.HeadResult, lambda i, x: store.head(project(x), i), 1024),
        ("frames.read", c.FrameReadInput, c.FrameResult, lambda i, x: store.read_frame(project(x), i), c.MAX_DOCUMENT_BYTES),
        ("documents.create", c.CreateRequest, c.MutationResult, lambda i, x: store.create(project(x), i, i.mutation_id), c.MAX_OUTPUT_BYTES),
        ("documents.revisions", c.RevisionsInput, c.RevisionsResult, lambda i, x: store.revisions(project(x), i), 65536),
        ("documents.diff", c.DiffInput, c.DiffResult, lambda i, x: store.diff(project(x), i), c.MAX_OUTPUT_BYTES),
        ("documents.export", c.VersionRequest, c.ExportResult, export, c.MAX_OUTPUT_BYTES),
    ]
    def mutation(action):
        return lambda i, x: store.mutate(project(x), i, i.mutation_id, action)
    for action, model in (("apply", c.ApplyRequest), ("undo", c.UndoRequest), ("delete", c.VersionRequest), ("restore", c.VersionRequest)):
        specs.append(("documents." + action, model, c.MutationResult, mutation(action), c.MAX_OUTPUT_BYTES))
    def guarded(handler):
        def execute(input, context):
            try:
                return handler(input, context)
            except PixelError as exc:
                status = 404 if exc.code == "PIXEL_NOT_FOUND" else 503 if exc.code == "PIXEL_BUSY" else 409
                raise DlcOperationError(code=exc.code, message=str(exc), status_code=status) from exc
        return execute
    for name, input_model, output_model, handler, budget in specs:
        host.operations.register(DlcOperationSpec(name=name, input_model=input_model, output_model=output_model,
            handler=guarded(handler), scope="project", max_output_bytes=budget))


def register(host):
    store = PixelStore(host.runtime_info.data_path)
    tools = build_tools(store)
    for tool in tools:
        host.tools.register(tool)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(c.LIBRARY_KIND, store.resolve_library)
    host.resources.register_resolver(c.DOCUMENT_KIND, store.resolve_document)
    host.context.register(PixelContext(store))
    host.artifacts.register(c.ARTIFACT_TYPE, 1, c.DocumentSummary)
    host.artifacts.register_representation(c.ARTIFACT_TYPE, c.REPRESENTATION_TYPE, PixelRepresentation(store))
    host.completion.register_support(SemanticArtifactCompletionSupport(id=c.ARTIFACT_TYPE, semantic_capability=c.ARTIFACT_TYPE))
    host.agent_guidance.register(CapabilityGuidanceSpec(id="pixel_authoring", version="1",
        instructions="Create and incrementally edit pixel art and sprite animations. Use Pixel Library to create; continue with returned document_id in the same Run. "
        "Inspect exact frame/layer/tag IDs and revision before editing. Creation requires expected_version=0; every edit requires the inspected revision. "
        "Pixel canvas uses integer x/y coordinates, half-open rectangles, row-major palette indices; slot 0 is transparent. "
        "Use high-level fill, line, rect, stamp and transform, or an atomic apply batch of at most 128 operations. "
        "Do not regenerate the full document. A locked layer cannot be painted or deleted; frame deletion requires unlocked cels. "
        "Selection and labels never confer authority. Ask for clarification on ambiguous targets or incompatible instructions, without changing content. "
        "Stale edits fail; re-inspect and reconsider rather than automatically replaying. Historical identity cannot be reused; undo creates a new revision. "
        "Inspect pages are bounded (16 entries, 16x16 pixels); for rich diff output use smaller pages if a budget is exceeded. "
        "Artifacts expose immutable metadata, bounded RGBA, PNG and horizontal sprite sheets through dbfox.pixel.sprite.v1. "
        "Only claim successful mutations supported by formal tool results.",
        applies_to_resource_kinds=(c.LIBRARY_KIND, c.DOCUMENT_KIND), applies_to_artifact_types=(c.ARTIFACT_TYPE,),
        tool_refs=tuple(ToolKey(owner_id=c.OWNER, local_name=tool.name) for tool in tools)))
    register_operations(host, store)
