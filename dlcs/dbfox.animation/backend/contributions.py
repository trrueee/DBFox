"""Tools and Workbench share the same incremental owner transaction boundary."""
import sqlite3
import json
from hashlib import sha256
from pydantic import create_model
from dbfox_dlc_api import (BaseTool, ToolPolicy, ToolExecutionSpec, ToolResourceRequirement, ToolPresentation,
    ToolSemanticSpec, ToolObservationProjection, ToolOutcome, ToolInputError, ToolReconciliation, ArtifactDraft,
    DlcOperationSpec, DlcOperationError, RequestedResourceRef, ArtifactRepresentationRequest,
    CapabilityGuidanceSpec, ToolKey, ContextFragment, SemanticArtifactCompletionSupport)
from . import contracts as c
from .store import AnimationStore
from .model import AnimationError
from .representation import AnimationRepresentation


def artifact(summary, scope):
    payload = c.RevisionArtifact(animation_id=summary.id, project_id=summary.project_id,
        version=summary.version, content_hash=summary.content_hash, title=summary.title)
    return ArtifactDraft(key="animation_revision", type=c.ARTIFACT_TYPE, schema_version=1,
        title=f"{summary.title} · v{summary.version}", payload=payload.model_dump(mode="json"),
        summary=f"Animation revision {summary.version}; {summary.counts['tracks']} tracks, {summary.counts['keyframes']} keys.",
        semantic_key=f"animation:{summary.id}:{summary.version}", resource_refs=(scope,))


def resource(context, kind, identity=None):
    refs = context.scopes(kind)
    if len(refs) != 1 or (identity is not None and refs[0].id != identity):
        raise ToolInputError("An exact frozen Animation resource is required.")
    value = context.resource(refs[0])
    if kind == c.LIBRARY_KIND:
        if not isinstance(value, c.Library) or value.project_id != refs[0].id:
            raise ToolInputError("Invalid resolved Animation Library.")
    elif not isinstance(value, c.Revision) or value.animation.id != identity or value.animation.version != refs[0].version:
        raise ToolInputError("Invalid resolved Animation revision.")
    return value, refs[0]


WRITE = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential", max_output_bytes=65536,
    required_resources=(ToolResourceRequirement(kind=c.DOCUMENT_KIND, selector_field="animation_id"),))
READ = ToolExecutionSpec(recovery="retry_safe", retryable=True, max_retries=1, concurrency="parallel_safe", max_output_bytes=262144,
    required_resources=(ToolResourceRequirement(kind=c.DOCUMENT_KIND, selector_field="animation_id"),))


class AnimationTool(BaseTool):
    name = "animation_apply"
    group = "animation"
    description = "Apply a bounded incremental Animation edit at expected_version. Time is integer milliseconds. Inspect before editing."
    input_model = c.MutationInput
    output_model = c.MutationResult
    version = "1"
    action = "apply"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = WRITE
    presentation = ToolPresentation(title="编辑动画", category="manage")
    semantics = ToolSemanticSpec(produces=(c.ARTIFACT_TYPE,))

    def __init__(self, store):
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="Animation operation did not complete.")
        facts = dict(output)
        field = "items" if "items" in facts else "differences" if "differences" in facts else None
        if field:
            entries = list(facts[field])
            original_count = len(entries)
            offset = facts.get("offset", facts["next_offset"] - original_count)
            while entries and len(json.dumps({**facts, field: entries}, ensure_ascii=False).encode("utf-8")) > 24000:
                entries.pop()
            facts.update({field: entries, "next_offset": offset + len(entries), "has_more": offset + len(entries) < facts["total"],
                          "observation_truncated": len(entries) < original_count})
        return ToolObservationProjection(summary=f"Animation {self.name} completed.", facts=facts, provider_payload=facts)

    def run(self, input, context):
        try:
            if self.action == "create":
                library, scope = resource(context, c.LIBRARY_KIND)
                result = self.store.create(library.project_id, input, context.invocation_id, context.is_cancelled)
            else:
                source, scope = resource(context, c.DOCUMENT_KIND, input.animation_id)
                bound_targets = bind_scene(input, context) if self.action == "bind" else None
                result = self.store.mutate(source.animation.project_id, self.action, input, context.invocation_id,
                    scope.version, context.is_cancelled, bound_targets)
            return ToolOutcome(output=result, artifacts=(artifact(result.animation, scope),))
        except (AnimationError, ValueError) as exc:
            raise ToolInputError(f"{getattr(exc, 'code', 'ANIMATION_INVALID')}: {exc}") from exc

    def reconcile(self, input, context):
        source, scope = resource(context, c.LIBRARY_KIND) if self.action == "create" else resource(context, c.DOCUMENT_KIND, input.animation_id)
        project = source.project_id if self.action == "create" else source.animation.project_id
        result = self.store.reconcile(project, self.action, input, context.invocation_id)
        if result is None:
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json"), artifacts=(artifact(result.animation, scope),))


def bind_scene(input, context):
    """Consume only Host-authorized public fixed Scene representations, never owner internals."""
    if len(set(input.object_ids)) != len(input.object_ids):
        raise AnimationError("REFERENCE", "Scene object IDs must be unique.")
    source = context.artifact(input.artifact_id)
    if source.type != "dbfox.scene.revision":
        raise AnimationError("REFERENCE", "A Scene revision Artifact is required.")
    summary = context.read_artifact_representation(input.artifact_id, "dbfox.scene.document.v1",
        ArtifactRepresentationRequest(operation="summary", parameters={}))
    scene = summary.payload.get("scene", {})
    version, fingerprint = str(scene.get("version")), scene.get("content_hash")
    if summary.consistency != "durable_snapshot" or summary.source_version != version or summary.source_fingerprint != fingerprint:
        raise AnimationError("REFERENCE", "Scene must expose a fixed version and content hash.")
    requested, found = set(input.object_ids), {}
    # Public pages remain bounded; explicit upper bound matches Scene's public 10,000-object limit.
    for offset in range(0, 10000, 100):
        if context.is_cancelled():
            raise AnimationError("CANCELLED", "Scene binding cancelled.")
        page = context.read_artifact_representation(input.artifact_id, "dbfox.scene.document.v1",
            ArtifactRepresentationRequest(operation="objects_page", parameters={"offset": offset, "limit": 100}))
        if page.consistency != "durable_snapshot" or page.source_version != version or page.source_fingerprint != fingerprint:
            raise AnimationError("STALE", "Scene representation identity changed while binding.")
        for item in page.payload.get("objects", []):
            if item.get("id") in requested:
                found[item["id"]] = item
        if requested <= found.keys() or offset + 100 >= page.payload.get("total", 0):
            break
    if requested != found.keys():
        raise AnimationError("REFERENCE", "Some requested stable Scene objects do not exist in this revision.")
    result = []
    for identity in input.object_ids:
        item = found[identity]
        binding = c.SceneBinding(artifact_id=input.artifact_id, scene_id=scene["id"], version=int(version), content_hash=fingerprint, object_id=identity)
        target_id = "scene." + sha256(f"{scene['id']}:{version}:{fingerprint}:{identity}".encode()).hexdigest()[:40]
        result.append(c.Target(id=target_id, name=item["name"], position=item["position"], rotation=item["rotation"], scale=item["scale"], source=binding))
    return result


class InspectTool(AnimationTool):
    name = "animation_inspect"
    description = "Inspect immutable Animation entities in pages <=100. Reuse version for subsequent pages. Optional track_id filters keys."
    input_model = c.InspectInput
    output_model = c.PageResult
    policy = ToolPolicy(risk_level="safe")
    execution = READ
    semantics = ToolSemanticSpec()

    def run(self, input, context):
        source, scope = resource(context, c.DOCUMENT_KIND, input.animation_id)
        try:
            self.store.check_cancel(context.is_cancelled)
            if input.version is None:
                self.store.require_live(source.animation.project_id, input.animation_id, source.animation.version, scope.version)
            elif input.version > source.animation.version:
                raise AnimationError("REFERENCE", "Requested revision exceeds frozen authority.")
            request = input.model_copy(update={"version": input.version or source.animation.version})
            return ToolOutcome(output=self.store.page(source.animation.project_id, request))
        except AnimationError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc


class DiffTool(InspectTool):
    name = "animation_diff"
    description = "Compare two fixed Animation versions by stable entity IDs and changed fields, at most 100 differences per page."
    input_model = c.DiffInput
    output_model = c.DiffResult

    def run(self, input, context):
        source, _ = resource(context, c.DOCUMENT_KIND, input.animation_id)
        if max(input.from_version, input.to_version) > source.animation.version:
            raise ToolInputError("Requested diff exceeds frozen Animation authority.")
        self.store.check_cancel(context.is_cancelled)
        return ToolOutcome(output=self.store.diff(source.animation.project_id, input))


class ExportTool(AnimationTool):
    name = "animation_export"
    description = "Produce a fixed Animation revision Artifact with JSON export preserving curves, clips, markers and source identities."
    input_model = c.VersionInput
    policy = ToolPolicy(risk_level="safe")
    execution = READ

    def run(self, input, context):
        source, scope = resource(context, c.DOCUMENT_KIND, input.animation_id)
        try:
            self.store.check_cancel(context.is_cancelled)
            self.store.require_live(source.animation.project_id, input.animation_id, input.expected_version, scope.version)
        except AnimationError as exc:
            raise ToolInputError(f"{exc.code}: {exc}") from exc
        return ToolOutcome(output=c.MutationResult(animation=source.animation, changed=False), artifacts=(artifact(source.animation, scope),))


def build_tools(store):
    definitions = [("animation_create", c.CreateInput, "create"), ("animation_undo", c.UndoInput, "undo"),
                   ("animation_delete", c.VersionInput, "delete"), ("scene_bind", c.BindInput, "bind")]
    for operation in c.OPERATIONS:
        model = create_model(operation.__name__ + "Input", __base__=c.MutationInput, operation=(operation, ...))
        definitions.append((operation.model_fields["kind"].default, model, "apply"))
    tools = [InspectTool(store), DiffTool(store), ExportTool(store)]
    for name, model, action in definitions:
        attributes = {"name": name, "input_model": model, "action": action, "reconcile": AnimationTool.reconcile,
            "description": f"{name}: incrementally edit Animation; expected_version is mandatory for existing documents. "
                "Times are integer milliseconds; clips are non-destructive windows; key IDs are exact, never names. "
                "A shared curve edit affects all keys referencing that curve. Scene binding reads an authorized fixed Scene Artifact."}
        if action == "create":
            attributes["execution"] = ToolExecutionSpec(recovery="reconcile", retryable=False,
                required_resources=(ToolResourceRequirement(kind=c.LIBRARY_KIND),), max_output_bytes=65536)
        tools.append(type(name + "Tool", (AnimationTool,), attributes)(store))
    return tuple(tools)


class AnimationContext:
    id = "dbfox.animation.context"

    def __init__(self, store):
        self.store = store

    def build(self, input):
        lines = []
        for ref in input.resource_refs:
            if ref.kind == c.LIBRARY_KIND:
                lines.append("Animation Library permits creating a durable timeline.")
            elif ref.kind == c.DOCUMENT_KIND:
                try:
                    summary = self.store.resolve_document(ref).animation
                    lines.append(f"Animation {summary.id} v{summary.version}: {summary.title}; {summary.counts['tracks']} tracks, {summary.counts['keyframes']} keys.")
                except AnimationError:
                    continue
        if not lines:
            return ()
        return (ContextFragment(source_id=self.id, source_version="1", lane="resource", content=("\n".join(lines) +
            "\nInspect <=100 entities per page. Use exact stable IDs, frozen version and integer millisecond ticks. Selection grants no authority.")[:4000], provenance={"owner": c.OWNER}),)


def register_operations(host, store):
    def project(context):
        if context.dlc_id != c.OWNER or not context.project_id:
            raise DlcOperationError(code="ANIMATION_PROJECT_REQUIRED", message="Animation requires a Project.")
        return context.project_id

    def mutation(action, model):
        def execute(input, context):
            project_id = project(context)
            payload = model.model_validate(input.model_dump(exclude={"request_id"}))
            invocation = f"ui:{project_id}:{input.request_id}"
            if action == "create":
                return store.create(project_id, payload, invocation)
            return store.mutate(project_id, action, payload, invocation)
        return execute

    def export(input, context):
        project_id = project(context)
        store.require_live(project_id, input.animation_id, input.expected_version)
        with context.require_action_runs().start(title="Animation export", question="Export this Animation revision.",
            requested_resources=(RequestedResourceRef(kind=c.DOCUMENT_KIND, id=input.animation_id),), idempotency_key=input.request_id) as action:
            result = action.invoke("animation_export", {"animation_id": input.animation_id, "expected_version": input.expected_version})
            if result.status != "success" or not result.artifacts:
                raise AnimationError("ARTIFACT_FAILED", "Animation Artifact action did not complete.")
            selected = result.artifacts[0].id
            completed = action.complete(summary="Animation revision export is ready.", selected_artifact_id=selected)
            return c.ArtifactResult(artifact_id=selected, run_id=completed.run_id, session_id=completed.session_id)

    def guard(handler):
        def execute(input, context):
            try:
                return handler(input, context)
            except AnimationError as exc:
                raise DlcOperationError(code=exc.code, message=str(exc), status_code=409 if exc.code in (
                    "ANIMATION_STALE", "ANIMATION_DELETED", "ANIMATION_RECEIPT_MISMATCH", "ANIMATION_ID_REUSED") else 400) from exc
            except sqlite3.OperationalError as exc:
                raise DlcOperationError(code="ANIMATION_BUSY", message="Animation storage is busy. Refresh before trying again.", status_code=503) from exc
        return execute
    for name, input_model, output_model, handler in (
        ("animations.list", c.PageInput, c.ListResult, lambda input, context: store.list(project(context), input)),
        ("animations.get", c.InspectInput, c.PageResult, lambda input, context: store.page(project(context), input)),
        ("animations.diff", c.DiffInput, c.DiffResult, lambda input, context: store.diff(project(context), input)),
        ("animations.create", c.CreateRequest, c.MutationResult, mutation("create", c.CreateInput)),
        ("animations.apply", c.MutationRequest, c.MutationResult, mutation("apply", c.MutationInput)),
        ("animations.undo", c.UndoRequest, c.MutationResult, mutation("undo", c.UndoInput)),
        ("animations.delete", c.VersionRequest, c.MutationResult, mutation("delete", c.VersionInput)),
        ("animations.artifact", c.VersionRequest, c.ArtifactResult, export),
    ):
        host.operations.register(DlcOperationSpec(name=name, input_model=input_model, output_model=output_model,
            handler=guard(handler), scope="project", max_output_bytes=262144))


def register(host):
    store = AnimationStore(host.runtime_info.data_path)
    tools = build_tools(store)
    for tool in tools:
        host.tools.register(tool)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(c.LIBRARY_KIND, store.resolve_library)
    host.resources.register_resolver(c.DOCUMENT_KIND, store.resolve_document)
    host.context.register(AnimationContext(store))
    host.artifacts.register(c.ARTIFACT_TYPE, 1, c.RevisionArtifact)
    host.artifacts.register_representation(c.ARTIFACT_TYPE, c.REPRESENTATION_TYPE, AnimationRepresentation(store))
    host.completion.register_support(SemanticArtifactCompletionSupport(id=c.ARTIFACT_TYPE, semantic_capability=c.ARTIFACT_TYPE))
    host.agent_guidance.register(CapabilityGuidanceSpec(id="animation_authoring", version="1",
        instructions="Create Animation in its Library, then use its exact document resource. Inspect before every edit and supply expected_version. "
            "Track properties are local scalar position/rotation/scale XYZ; radians for rotation. Time is integer milliseconds up to one hour. "
            "Keyframe edits are bounded to 256; inspection pages to 100. Duplicate track times and dangling references are rejected. "
            "Shared curves affect all referenced outgoing key intervals. Clip trim never deletes keys. Reducing duration rejects out-of-range content. "
            "Scene binding consumes public fixed Artifact representations with stable IDs and version/hash. Never infer Scene identities from names. "
            "On stale or ambiguity inspect/clarify; never replay writes automatically. Undo restores a fixed revision as a new head. "
            "Only claim successful tool output. Export fixed Artifacts for complete canonical JSON including curves, clips, markers and source bindings.",
        applies_to_resource_kinds=(c.LIBRARY_KIND, c.DOCUMENT_KIND), applies_to_artifact_types=(c.ARTIFACT_TYPE,),
        tool_refs=tuple(ToolKey(owner_id=c.OWNER, local_name=tool.name) for tool in tools)))
    register_operations(host, store)
