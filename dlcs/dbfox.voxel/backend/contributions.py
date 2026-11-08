"""Voxel contributions registered solely through the public Extension API."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from dbfox_dlc_api import (
    BackendExtensionHost, BaseModel, CapabilityGuidanceSpec, ContextContributionInput,
    ContextFragment, DlcOperationContext, DlcOperationError, DlcOperationSpec,
    RequestedResourceRef, SemanticArtifactCompletionSupport, ToolKey,
)

from .contracts import (
    LIBRARY_KIND, REPRESENTATION_TYPE, SNAPSHOT_TYPE, WORLD_KIND, ChunkPageInput,
    ChunkPageOutput, DiffInput, DiffOutput, HumanApplyInput, HumanConfigureInput,
    HumanCreateInput, HumanDeleteInput, HumanUndoInput, ListInput, MutationOutput,
    ReadInput, RevisionsInput, RevisionsOutput, SnapshotActionInput,
    SnapshotActionOutput, SnapshotPayload, WorldListOutput, WorldOutput,
)
from .geometry import VoxelError
from .representation import VoxelRepresentationProvider
from .store import VoxelStore, canonical
from .tools import (
    VoxelBooleanTool, VoxelBoxTool, VoxelConfigureTool, VoxelCopyRegionTool,
    VoxelCreateTool, VoxelDeleteTool, VoxelDiffTool, VoxelExportTool, VoxelExtrudeTool,
    VoxelFillTool, VoxelInspectTool, VoxelMirrorTool, VoxelReplaceTool, VoxelSphereTool,
    VoxelUndoTool,
)

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


def _project(context: DlcOperationContext) -> str:
    if context.project_id is None or context.dlc_id != "dbfox.voxel":
        raise DlcOperationError(code="PROJECT_REQUIRED", message="Voxel operations require their owning Project context.")
    return context.project_id


def _boundary(handler: Callable[[I, DlcOperationContext], O]) -> Callable[[I, DlcOperationContext], O]:
    """Translate owner errors once at the public management-RPC boundary."""
    def invoke(input: I, context: DlcOperationContext) -> O:
        try:
            return handler(input, context)
        except VoxelError as exc:
            raise DlcOperationError(code=exc.code, message=exc.message, status_code=exc.status_code) from exc
        except ValueError as exc:
            raise DlcOperationError(code="INVALID_INPUT", message="The voxel request violates the domain contract.") from exc
    return invoke


class VoxelContextContributor:
    id = "dbfox.voxel"

    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    def build(self, input: ContextContributionInput) -> tuple[ContextFragment, ...]:
        fragments: list[ContextFragment] = []
        world_count = 0
        for ref in input.resource_refs:
            if ref.kind == LIBRARY_KIND:
                self.store.resolve_library(ref)
                fragments.append(ContextFragment(source_id=self.id, source_version="1", lane="resource",
                    content="Voxel Library: create durable worlds, then use high-level region Tools with explicit world_id and expected_version. Coordinate bounds are half-open; palette 0 means air.",
                    provenance={"resource_kind": LIBRARY_KIND, "project_id": ref.id}))
            elif ref.kind == WORLD_KIND and world_count < 2:
                try:
                    snapshot = self.store.resolve_world(ref)
                except VoxelError:
                    continue
                world_count += 1
                doc = snapshot.document
                # Structured selection before serialization; never slice an entire document JSON.
                layers: list[dict[str, object]] = [{"id": layer.id, "name": layer.name, "locked": layer.locked} for layer in doc.layers[:4]]
                palette: list[dict[str, object]] = [{"index": p.index, "name": p.name} for p in doc.palette[:6]]
                regions: list[dict[str, object]] = [{"id": r.id, "name": r.name} for r in doc.regions[:3]]
                summary = {
                    "world_id": snapshot.world_id, "version": snapshot.version, "title": doc.title,
                    "size": doc.size, "nonzero_count": sum(c.nonzero_count for c in snapshot.chunks.values()),
                    "layers": layers, "palette": palette, "regions": regions,
                    "truncated": len(doc.layers) > 4 or len(doc.palette) > 6 or len(doc.regions) > 3,
                }
                guidance = ("\nInspect complete objects with voxel_inspect using this world_id, version and object_offset=0. "
                    "Geometry is bounded to 2,097,152 candidate cells per call. Use fresh expected_version; do not regenerate a whole world.")
                content = canonical(summary) + guidance
                # Escaped control characters can expand an 80-character name to
                # 480 JSON characters. Count the serialized fragment, including
                # guidance, and remove only whole objects until it fits the SDK.
                while len(content) > 4000:
                    max((layers, palette, regions), key=len).pop()
                    summary["truncated"] = True
                    content = canonical(summary) + guidance
                fragments.append(ContextFragment(source_id=self.id, source_version=str(snapshot.version), lane="resource",
                    content=content, provenance={"world_id": snapshot.world_id, "version": snapshot.version, "content_hash": snapshot.content_hash}))
        return tuple(fragments[:3])


def _register_operations(host: BackendExtensionHost, store: VoxelStore) -> None:
    def list_worlds(input: ListInput, context: DlcOperationContext) -> WorldListOutput:
        return store.list_worlds(_project(context), input)

    def create(input: HumanCreateInput, context: DlcOperationContext) -> MutationOutput:
        return store.create(_project(context), input, origin="human", request_id=input.mutation_id)

    def get(input: ReadInput, context: DlcOperationContext) -> WorldOutput:
        return store.get(_project(context), input)

    def apply(input: HumanApplyInput, context: DlcOperationContext) -> MutationOutput:
        return store.mutate(_project(context), input, kind=input.operation.kind, origin="human", request_id=input.mutation_id)

    def configure(input: HumanConfigureInput, context: DlcOperationContext) -> MutationOutput:
        return store.mutate(_project(context), input, kind="configure", origin="human", request_id=input.mutation_id)

    def undo(input: HumanUndoInput, context: DlcOperationContext) -> MutationOutput:
        return store.mutate(_project(context), input, kind="undo", origin="human", request_id=input.mutation_id)

    def delete(input: HumanDeleteInput, context: DlcOperationContext) -> MutationOutput:
        return store.mutate(_project(context), input, kind="delete", origin="human", request_id=input.mutation_id)

    def revisions(input: RevisionsInput, context: DlcOperationContext) -> RevisionsOutput:
        return store.revisions(_project(context), input)

    def diff(input: DiffInput, context: DlcOperationContext) -> DiffOutput:
        return store.diff(_project(context), input)

    def chunks(input: ChunkPageInput, context: DlcOperationContext) -> ChunkPageOutput:
        return store.chunks(_project(context), input)

    def snapshot(input: SnapshotActionInput, context: DlcOperationContext) -> SnapshotActionOutput:
        project_id = _project(context)
        source = store.snapshot(project_id, input.world_id, input.version)
        if source.document.status == "deleted":
            raise VoxelError("WORLD_DELETED", "Restore the world before creating a new snapshot action.", 409)
        # Keep the explicit version in the Tool input even if the current head changes later.
        with context.require_action_runs().start(title="保存体素快照", question="保存所选体素世界的不可变快照。",
            requested_resources=(RequestedResourceRef(kind=WORLD_KIND, id=input.world_id),), idempotency_key=input.mutation_id) as run:
            outcome = run.invoke("voxel_export", {"world_id": input.world_id, "version": source.version})
            if outcome.status != "success":
                raise VoxelError("SNAPSHOT_FAILED", "The voxel snapshot action did not succeed.", 409)
            completed = run.complete(summary=f"Saved voxel snapshot version {source.version}.", selected_artifact_id=outcome.artifacts[0].id if outcome.artifacts else None)
            return SnapshotActionOutput(run_id=completed.run_id, session_id=completed.session_id, artifact_ids=[a.id for a in completed.artifacts])

    host.operations.register(DlcOperationSpec(name="worlds.list", input_model=ListInput, output_model=WorldListOutput, handler=_boundary(list_worlds), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.create", input_model=HumanCreateInput, output_model=MutationOutput, handler=_boundary(create), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.get", input_model=ReadInput, output_model=WorldOutput, handler=_boundary(get), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.apply", input_model=HumanApplyInput, output_model=MutationOutput, handler=_boundary(apply), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.configure", input_model=HumanConfigureInput, output_model=MutationOutput, handler=_boundary(configure), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.undo", input_model=HumanUndoInput, output_model=MutationOutput, handler=_boundary(undo), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.delete", input_model=HumanDeleteInput, output_model=MutationOutput, handler=_boundary(delete), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.revisions", input_model=RevisionsInput, output_model=RevisionsOutput, handler=_boundary(revisions), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.diff", input_model=DiffInput, output_model=DiffOutput, handler=_boundary(diff), scope="project"))
    host.operations.register(DlcOperationSpec(name="worlds.chunks", input_model=ChunkPageInput, output_model=ChunkPageOutput, handler=_boundary(chunks), scope="project", max_output_bytes=512_000))
    host.operations.register(DlcOperationSpec(name="worlds.snapshot", input_model=SnapshotActionInput, output_model=SnapshotActionOutput, handler=_boundary(snapshot), scope="project"))


def register(host: BackendExtensionHost) -> None:
    store = VoxelStore(host.runtime_info.data_path)
    registered_tools = (VoxelCreateTool(store), VoxelInspectTool(store), VoxelFillTool(store), VoxelBoxTool(store),
        VoxelSphereTool(store), VoxelExtrudeTool(store), VoxelReplaceTool(store), VoxelCopyRegionTool(store),
        VoxelMirrorTool(store), VoxelBooleanTool(store), VoxelConfigureTool(store), VoxelUndoTool(store),
        VoxelDeleteTool(store), VoxelExportTool(store), VoxelDiffTool(store))
    for tool in registered_tools:
        host.tools.register(tool)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(LIBRARY_KIND, store.resolve_library)
    host.resources.register_resolver(WORLD_KIND, store.resolve_world)
    host.context.register(VoxelContextContributor(store))
    host.artifacts.register(SNAPSHOT_TYPE, 1, SnapshotPayload)
    host.artifacts.register_representation(SNAPSHOT_TYPE, REPRESENTATION_TYPE, VoxelRepresentationProvider(store))
    host.completion.register_support(SemanticArtifactCompletionSupport(id="dbfox.voxel.snapshot", semantic_capability=SNAPSHOT_TYPE))
    host.agent_guidance.register(CapabilityGuidanceSpec(id="voxel_world_authoring", version="1",
        instructions=("Create and incrementally edit durable voxel worlds using the named high-level Tools. "
            "Inspect the existing world before editing and preserve unrelated content. Every new invocation binds current resource authority, "
            "but expected_version must still come from the state you inspected. On a stale-version failure re-inspect; never silently replay. "
            "Use fill, box, sphere, extrusion, replace, region copy, mirror, and boolean operations for large designs; never make per-voxel Tool loops. "
            "All bounds are half-open integer ranges; palette 0 erases only the selected layer. Layers are ordered bottom to top, and Tools do not use UI visibility. "
            "Copy and boolean sources must explicitly name a layer in the same world. Split operations exceeding 2,097,152 candidate cells into regions. "
            "For ambiguous requests that could delete or replace content, clarify the intended region or operation before modifying. "
            "Inspect no-op outcomes truthfully and do not claim a new revision when changed is false. Export immutable snapshots for evidence and composition; "
            "consume their JSON representation through the public Artifact interface. Never overwrite the entire world document to achieve a local edit."),
        applies_to_resource_kinds=(LIBRARY_KIND, WORLD_KIND), applies_to_artifact_types=(SNAPSHOT_TYPE,),
        tool_refs=tuple(ToolKey(owner_id="dbfox.voxel", local_name=tool.name) for tool in registered_tools)))
    _register_operations(host, store)
