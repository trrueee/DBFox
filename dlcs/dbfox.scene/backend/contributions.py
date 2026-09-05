"""Public Host registrations, Agent tools and project-scoped Workbench operations."""
from __future__ import annotations

from collections.abc import Callable
import json
import sqlite3

from dbfox_dlc_api import (
    ArtifactDraft, BackendExtensionHost, BaseModel, BaseTool, CapabilityGuidanceSpec,
    ContextContributionInput, ContextFragment, DlcOperationContext, DlcOperationError,
    DlcOperationSpec, ExtensionToolRunContext, RequestedResourceRef, ResourceScopeRef,
    SemanticArtifactCompletionSupport, ToolExecutionSpec, ToolInputError, ToolKey,
    ToolObservationProjection, ToolOutcome, ToolPolicy, ToolPresentation, ToolReconciliation, ToolResourceRequirement,
    ToolSemanticSpec,
)
from pydantic import create_model

from .contracts import (
    ARTIFACT_TYPE, OWNER, REPRESENTATION_TYPE, SCENE_KIND, LIBRARY_KIND,
    ArtifactResult, AssignMaterial, CreateCamera, CreateInput, CreateLight, CreateMaterial,
    CreateObjects, CreateRequest, DeleteObjects, DiffInput, DiffResult, DuplicateObjects,
    InspectInput, Library, ListResult, MutationInput, MutationRequest, MutationResult,
    PageInput, PageResult, ReparentObjects, Revision, RevisionArtifact, SceneSummary,
    TransformObjects, UndoInput, UndoRequest, UpdateCamera, UpdateLight, UpdateMaterial, UpdateObject, UpdateSettings,
    VersionInput, VersionRequest,
)
from .representation import SceneRepresentation
from .store import SceneError, SceneStore


def revision_artifact(summary: SceneSummary, scope: ResourceScopeRef) -> ArtifactDraft:
    payload = RevisionArtifact(scene_id=summary.id, project_id=summary.project_id, version=summary.version,
        content_hash=summary.content_hash, title=summary.title, object_count=summary.object_count,
        material_count=summary.material_count)
    return ArtifactDraft(key="scene_revision", type=ARTIFACT_TYPE, schema_version=1,
        title=f"{summary.title} · v{summary.version}", payload=payload.model_dump(mode="json"),
        summary=f"Scene revision {summary.version}: {summary.object_count} objects, {summary.material_count} materials.",
        semantic_key=f"scene:{summary.id}:{summary.version}", resource_refs=(scope,))


def _scope(context: ExtensionToolRunContext, kind: str, identity: str | None = None) -> ResourceScopeRef:
    refs = context.scopes(kind)
    if len(refs) != 1 or (identity is not None and refs[0].id != identity):
        raise ToolInputError("An exact frozen Scene resource is required.")
    return refs[0]


def _scene(context: ExtensionToolRunContext, scene_id: str) -> tuple[Revision, ResourceScopeRef]:
    scope = _scope(context, SCENE_KIND, scene_id)
    revision = context.resource(scope)
    if not isinstance(revision, Revision) or revision.scene.id != scene_id:
        raise ToolInputError("The resolved Scene resource does not match this invocation.")
    return revision, scope


def _library(context: ExtensionToolRunContext) -> tuple[Library, ResourceScopeRef]:
    scope = _scope(context, LIBRARY_KIND)
    library = context.resource(scope)
    if not isinstance(library, Library) or library.project_id != scope.id:
        raise ToolInputError("An authorized Scene Library is required.")
    return library, scope


def _tool_error(exc: SceneError) -> ToolInputError:
    return ToolInputError(f"{exc.code}: {exc}")


WRITE_EXECUTION = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential",
    max_output_bytes=64 * 1024, required_resources=(ToolResourceRequirement(kind=SCENE_KIND, selector_field="scene_id"),))
READ_EXECUTION = ToolExecutionSpec(recovery="retry_safe", retryable=True, max_retries=1,
    concurrency="parallel_safe", max_output_bytes=256 * 1024,
    required_resources=(ToolResourceRequirement(kind=SCENE_KIND, selector_field="scene_id"),))


def _revision_observation(status: str, output: dict) -> ToolObservationProjection:
    if status != "success":
        return ToolObservationProjection(summary="Scene operation did not complete.")
    result = MutationResult.model_validate(output)
    facts = result.model_dump(mode="json")
    return ToolObservationProjection(
        summary=f"Scene {result.scene.id} v{result.scene.version}; changed={result.changed}.",
        facts=facts, provider_payload=facts,
    )


def _page_observation(output: PageResult | DiffResult) -> ToolObservationProjection:
    # Keep complete entities and explicit continuation; never let the generic
    # observation budget replace inspectable entities with a structural summary.
    facts = output.model_dump(mode="json")
    page_fields = ("objects", "materials", "geometries") if isinstance(output, PageResult) else ("differences",)
    entries = {key: facts.pop(key) for key in page_fields}
    facts.update({key: [] for key in page_fields})
    facts.update(returned=0, next_offset=output.offset, has_more=output.offset < output.total,
                 observation_truncated=False)
    for key, items in entries.items():
        for item in items:
            facts[key].append(item)
            if len(json.dumps(facts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 24_000:
                facts[key].pop()
                break
    returned = sum(len(facts[key]) for key in page_fields)
    facts.update(returned=returned, next_offset=output.offset + returned,
                 has_more=output.offset + returned < output.total,
                 observation_truncated=returned < sum(len(items) for items in entries.values()))
    return ToolObservationProjection(summary=f"Scene inspection: {returned} entries; next offset {facts['next_offset']}.",
                                     facts=facts, provider_payload=facts)


class SceneCreateTool(BaseTool[CreateInput, MutationResult]):
    name = "scene_create"
    group = "scene"
    description = "Create a durable empty 3D scene in the Project Scene Library. Add content with bounded incremental object and material tools."
    input_model = CreateInput
    output_model = MutationResult
    version = "1"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = ToolExecutionSpec(recovery="reconcile", retryable=False,
        required_resources=(ToolResourceRequirement(kind=LIBRARY_KIND),), max_output_bytes=64 * 1024)
    presentation = ToolPresentation(title="创建场景", category="manage")
    semantics = ToolSemanticSpec(produces=(ARTIFACT_TYPE,))

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        return _revision_observation(status, output)

    def run(self, input: CreateInput, context: ExtensionToolRunContext) -> ToolOutcome[MutationResult]:
        library, scope = _library(context)
        try:
            result = self.store.create(library.project_id, input, input.title,
                                       context.invocation_id, context.is_cancelled)
        except SceneError as exc:
            raise _tool_error(exc) from exc
        return ToolOutcome(output=result, artifacts=(revision_artifact(result.scene, scope),))

    def reconcile(self, input: CreateInput, context: ExtensionToolRunContext) -> ToolReconciliation:
        library, scope = _library(context)
        result = self.store.reconcile(library.project_id, "create", input, context.invocation_id)
        if result is None:
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json"),
                                  artifacts=(revision_artifact(result.scene, scope),))


class SceneMutationTool(BaseTool[MutationInput, MutationResult]):
    name = "scene_apply"
    group = "scene"
    description = "Apply one structured incremental scene operation at expected_version. Reject stale edits and invalid references; never replace the whole scene."
    input_model = MutationInput
    output_model = MutationResult
    version = "1"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = WRITE_EXECUTION
    presentation = ToolPresentation(title="编辑场景", category="manage")
    semantics = ToolSemanticSpec(produces=(ARTIFACT_TYPE,))

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        return _revision_observation(status, output)

    def run(self, input: MutationInput, context: ExtensionToolRunContext) -> ToolOutcome[MutationResult]:
        source, scope = _scene(context, input.scene_id)
        try:
            result = self.store.mutate(source.scene.project_id, input.scene_id, input.expected_version,
                "apply", input, context.invocation_id, operation=input.operation,
                frozen_version=scope.version, cancelled=context.is_cancelled)
        except SceneError as exc:
            raise _tool_error(exc) from exc
        return ToolOutcome(output=result, artifacts=(revision_artifact(result.scene, scope),))

    def reconcile(self, input: MutationInput, context: ExtensionToolRunContext) -> ToolReconciliation:
        source, scope = _scene(context, input.scene_id)
        result = self.store.reconcile(source.scene.project_id, "apply", input, context.invocation_id)
        if result is None:
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json"),
                                  artifacts=(revision_artifact(result.scene, scope),))


class SceneUndoTool(BaseTool[UndoInput, MutationResult]):
    name = "scene_undo"
    group = "scene"
    description = "Restore an earlier immutable scene document as a new revision, guarded by expected_version. Preserves all historical revisions."
    input_model = UndoInput
    output_model = MutationResult
    version = "1"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = WRITE_EXECUTION
    presentation = ToolPresentation(title="撤销场景修改", category="manage")
    semantics = ToolSemanticSpec(produces=(ARTIFACT_TYPE,))

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        return _revision_observation(status, output)

    def run(self, input: UndoInput, context: ExtensionToolRunContext) -> ToolOutcome[MutationResult]:
        source, scope = _scene(context, input.scene_id)
        try:
            result = self.store.mutate(source.scene.project_id, input.scene_id, input.expected_version,
                "undo", input, context.invocation_id, target_version=input.target_version,
                frozen_version=scope.version, cancelled=context.is_cancelled)
        except SceneError as exc:
            raise _tool_error(exc) from exc
        return ToolOutcome(output=result, artifacts=(revision_artifact(result.scene, scope),))

    def reconcile(self, input: UndoInput, context: ExtensionToolRunContext) -> ToolReconciliation:
        source, scope = _scene(context, input.scene_id)
        result = self.store.reconcile(source.scene.project_id, "undo", input, context.invocation_id)
        if result is None:
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="succeeded", output=result.model_dump(mode="json"),
                                  artifacts=(revision_artifact(result.scene, scope),))


class SceneInspectTool(BaseTool[InspectInput, PageResult]):
    name = "scene_inspect"
    group = "scene"
    description = "Inspect the scene hierarchy, mesh/material references or primitive catalog in pages of at most 100. Returned version must be supplied to edits and subsequent pages."
    input_model = InspectInput
    output_model = PageResult
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = READ_EXECUTION
    presentation = ToolPresentation(title="查看场景", category="explore")

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="Scene inspection did not complete.")
        return _page_observation(PageResult.model_validate(output))

    def run(self, input: InspectInput, context: ExtensionToolRunContext) -> ToolOutcome[PageResult]:
        source, scope = _scene(context, input.scene_id)
        version = input.version if input.version is not None else source.scene.version
        if version > source.scene.version:
            raise ToolInputError("Cannot inspect a revision newer than frozen invocation authority.")
        if context.is_cancelled():
            raise ToolInputError("Scene inspection was cancelled.")
        try:
            if input.version is None:
                self.store.require_live(source.scene.project_id, input.scene_id, source.scene.version, scope.version)
            result = self.store.page(source.scene.project_id, input.model_copy(update={"version": version}))
        except SceneError as exc:
            raise _tool_error(exc) from exc
        return ToolOutcome(output=result)


class SceneDiffTool(BaseTool[DiffInput, DiffResult]):
    name = "scene_diff"
    group = "scene"
    description = "Compare two immutable revisions by stable object/material IDs and changed field names. Returns at most 100 differences per page."
    input_model = DiffInput
    output_model = DiffResult
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = READ_EXECUTION
    presentation = ToolPresentation(title="比较场景版本", category="explore")

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="Scene comparison did not complete.")
        return _page_observation(DiffResult.model_validate(output))

    def run(self, input: DiffInput, context: ExtensionToolRunContext) -> ToolOutcome[DiffResult]:
        source, _scope_ref = _scene(context, input.scene_id)
        if max(input.from_version, input.to_version) > source.scene.version:
            raise ToolInputError("Cannot compare a revision newer than invocation authority.")
        if context.is_cancelled():
            raise ToolInputError("Scene comparison was cancelled.")
        try:
            return ToolOutcome(output=self.store.diff(source.scene.project_id, input))
        except SceneError as exc:
            raise _tool_error(exc) from exc


class SceneExportTool(BaseTool[VersionInput, MutationResult]):
    name = "scene_export"
    group = "scene"
    description = "Produce an immutable Scene Artifact with JSON pages and downloadable glTF/GLB representations. Exports use the frozen revision; no filesystem path or external URL is accepted."
    input_model = VersionInput
    output_model = MutationResult
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = READ_EXECUTION
    presentation = ToolPresentation(title="导出场景", category="visualize")
    semantics = ToolSemanticSpec(produces=(ARTIFACT_TYPE,))

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def project_observation(self, *, status, output, artifacts):
        return _revision_observation(status, output)

    def run(self, input: VersionInput, context: ExtensionToolRunContext) -> ToolOutcome[MutationResult]:
        source, scope = _scene(context, input.scene_id)
        if context.is_cancelled():
            raise ToolInputError("Scene export was cancelled.")
        try:
            self.store.require_live(source.scene.project_id, input.scene_id, input.expected_version, scope.version)
        except SceneError as exc:
            raise _tool_error(exc) from exc
        result = MutationResult(scene=source.scene, changed=False)
        return ToolOutcome(output=result, artifacts=(revision_artifact(result.scene, scope),))


class SceneContextContributor:
    id = "dbfox.scene.context"

    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        lines: list[str] = []
        for ref in input.resource_refs:
            if ref.kind == SCENE_KIND:
                try:
                    revision = self.store.resolve_scene(ref)
                except SceneError:
                    continue
                lines.append(f"Scene {revision.scene.id} v{revision.scene.version}: {revision.scene.title[:100]}; "
                             f"{revision.scene.object_count} objects, {revision.scene.material_count} materials.")
            elif ref.kind == LIBRARY_KIND:
                lines.append("Scene Library is available for creating a durable scene.")
        for artifact in input.recent_artifacts:
            if artifact.artifact_type == ARTIFACT_TYPE:
                try:
                    payload = RevisionArtifact.model_validate(artifact.payload)
                except ValueError:
                    continue
                lines.append(f"Artifact {artifact.artifact_id}: scene {payload.scene_id} v{payload.version}, "
                             f"{payload.object_count} objects. Inspect current version before editing.")
        if not lines:
            return ()
        return (ContextFragment(source_id=self.id, source_version="1", lane="resource",
            content=("\n".join(lines) + "\nUse scene_inspect pages (<=100). Never regenerate the full document.")[:4000],
            provenance={"owner": OWNER}),)


def _project(context: DlcOperationContext) -> str:
    if context.dlc_id != OWNER or not context.project_id:
        raise DlcOperationError(code="SCENE_PROJECT_REQUIRED", message="A Scene Project operation is required.")
    return context.project_id


def _guard(handler: Callable[[BaseModel, DlcOperationContext], BaseModel]) -> Callable[[BaseModel, DlcOperationContext], BaseModel]:
    def execute(input: BaseModel, context: DlcOperationContext) -> BaseModel:
        try:
            return handler(input, context)
        except SceneError as exc:
            status = 404 if exc.code == "SCENE_NOT_FOUND" else 409 if exc.code in (
                "SCENE_STALE", "SCENE_DELETED", "SCENE_RECEIPT_MISMATCH", "SCENE_ID_REUSED") else 400
            raise DlcOperationError(code=exc.code, message=str(exc), status_code=status) from exc
        except sqlite3.OperationalError as exc:
            raise DlcOperationError(code="SCENE_BUSY", message="Scene storage is busy. Refresh before trying again.", status_code=503) from exc
    return execute


def register_operations(host: BackendExtensionHost, store: SceneStore) -> None:
    def list_scenes(input: PageInput, context: DlcOperationContext) -> ListResult:
        return store.list_scenes(_project(context), input)

    def page(input: InspectInput, context: DlcOperationContext) -> PageResult:
        return store.page(_project(context), input)

    def create(input: CreateRequest, context: DlcOperationContext) -> MutationResult:
        project_id = _project(context)
        payload = CreateInput(title=input.title)
        return store.create(project_id, payload, input.title, f"ui:{project_id}:{input.request_id}")

    def apply(input: MutationRequest, context: DlcOperationContext) -> MutationResult:
        project_id = _project(context)
        payload = MutationInput(scene_id=input.scene_id, expected_version=input.expected_version, operation=input.operation)
        return store.mutate(project_id, input.scene_id, input.expected_version, "apply", payload,
                            f"ui:{project_id}:{input.request_id}", operation=input.operation)

    def undo(input: UndoRequest, context: DlcOperationContext) -> MutationResult:
        project_id = _project(context)
        payload = UndoInput(scene_id=input.scene_id, expected_version=input.expected_version, target_version=input.target_version)
        return store.mutate(project_id, input.scene_id, input.expected_version, "undo", payload,
                            f"ui:{project_id}:{input.request_id}", target_version=input.target_version)

    def delete(input: VersionRequest, context: DlcOperationContext) -> MutationResult:
        project_id = _project(context)
        payload = VersionInput(scene_id=input.scene_id, expected_version=input.expected_version)
        return store.mutate(project_id, input.scene_id, input.expected_version, "delete", payload,
                            f"ui:{project_id}:{input.request_id}")

    def diff(input: DiffInput, context: DlcOperationContext) -> DiffResult:
        return store.diff(_project(context), input)

    def artifact(input: VersionRequest, context: DlcOperationContext) -> ArtifactResult:
        project_id = _project(context)
        store.require_live(project_id, input.scene_id, input.expected_version)
        with context.require_action_runs().start(title="Scene export", question="Export this scene revision.",
            requested_resources=(RequestedResourceRef(kind=SCENE_KIND, id=input.scene_id),),
            idempotency_key=input.request_id) as action:
            result = action.invoke("scene_export", {"scene_id": input.scene_id, "expected_version": input.expected_version})
            if result.status != "success" or not result.artifacts:
                raise SceneError("SCENE_ARTIFACT_FAILED", "Scene Artifact action did not complete.")
            selected = result.artifacts[0].id
            completed = action.complete(summary="Scene revision is ready for glTF/GLB export.", selected_artifact_id=selected)
            return ArtifactResult(artifact_id=selected, run_id=completed.run_id, session_id=completed.session_id)

    specs = (
        ("scenes.list", PageInput, ListResult, list_scenes),
        ("scenes.get", InspectInput, PageResult, page),
        ("scenes.create", CreateRequest, MutationResult, create),
        ("scenes.apply", MutationRequest, MutationResult, apply),
        ("scenes.undo", UndoRequest, MutationResult, undo),
        ("scenes.delete", VersionRequest, MutationResult, delete),
        ("scenes.diff", DiffInput, DiffResult, diff),
        ("scenes.artifact", VersionRequest, ArtifactResult, artifact),
    )
    for name, input_model, output_model, handler in specs:
        host.operations.register(DlcOperationSpec(name=name, input_model=input_model, output_model=output_model,
            handler=_guard(handler), scope="project", max_output_bytes=256 * 1024))


def build_tools(store: SceneStore) -> tuple[BaseTool, ...]:
    tools: list[BaseTool] = [SceneCreateTool(store), SceneInspectTool(store), SceneUndoTool(store),
                             SceneDiffTool(store), SceneExportTool(store)]
    for operation_model in (CreateObjects, TransformObjects, DuplicateObjects, DeleteObjects,
        ReparentObjects, UpdateObject, CreateMaterial, UpdateMaterial, AssignMaterial, CreateLight,
        CreateCamera, UpdateLight, UpdateCamera, UpdateSettings):
        name = operation_model.model_fields["kind"].default
        input_model = create_model(f"{operation_model.__name__}Input", __base__=MutationInput,
                                   operation=(operation_model, ...))
        tool_class = type(f"{operation_model.__name__}Tool", (SceneMutationTool,), {
            "name": name, "input_model": input_model, "reconcile": SceneMutationTool.reconcile,
            "description": f"Apply the {name} structured operation to an existing scene at expected_version. "
                           "Inspect first; preserve unrelated objects. Coordinates are local, Euler XYZ radians, scale positive.",
        })
        tools.append(tool_class(store))
    return tuple(tools)


def register(host: BackendExtensionHost) -> None:
    store = SceneStore(host.runtime_info.data_path)
    tools = build_tools(store)
    for tool in tools:
        host.tools.register(tool)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(LIBRARY_KIND, store.resolve_library)
    host.resources.register_resolver(SCENE_KIND, store.resolve_scene)
    host.context.register(SceneContextContributor(store))
    host.artifacts.register(ARTIFACT_TYPE, 1, RevisionArtifact)
    host.artifacts.register_representation(ARTIFACT_TYPE, REPRESENTATION_TYPE, SceneRepresentation(store))
    host.completion.register_support(SemanticArtifactCompletionSupport(id=ARTIFACT_TYPE, semantic_capability=ARTIFACT_TYPE))
    host.agent_guidance.register(CapabilityGuidanceSpec(id="scene_authoring", version="1",
        instructions="Create and incrementally edit durable 3D scenes. Use Scene Library to create; use the returned scene ID "
        "for subsequent tools in the same Run. Inspect the latest version before edits and always provide expected_version. "
        "Use exact stable object IDs; selection never grants authority. Never replace or regenerate the whole scene. "
        "Reject ambiguous selections and clarify intent. Group related edits in one bounded operation (<=500 nodes). "
        "Primitive geometry IDs are geometry.box/sphere/cylinder/cone/plane/torus. Local TRS uses meters, "
        "Euler XYZ radians and positive scale. Colors are linear RGB. Material/light/camera IDs remain stable. "
        "If stale, re-inspect and reconsider; do not automatically replay. Undo creates a new revision. "
        "Only claim modifications backed by successful tool output. Export Artifacts expose immutable JSON/glTF/GLB representations.",
        applies_to_resource_kinds=(LIBRARY_KIND, SCENE_KIND), applies_to_artifact_types=(ARTIFACT_TYPE,),
        tool_refs=tuple(ToolKey(owner_id=OWNER, local_name=tool.name) for tool in tools)))
    register_operations(host, store)
