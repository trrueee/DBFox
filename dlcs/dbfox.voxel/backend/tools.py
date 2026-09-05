"""Provider-neutral high-level Tools; Host owns invocation and Artifact lifecycles."""
from __future__ import annotations

from dbfox_dlc_api import (
    ArtifactDraft, BaseTool, ExtensionToolRunContext, ResourceScopeRef,
    ToolExecutionSpec, ToolInputError, ToolObservationProjection, ToolOutcome,
    ToolPolicy, ToolPresentation, ToolReconciliation, ToolResourceRequirement,
    ToolSemanticSpec,
)

from .contracts import (
    LIBRARY_KIND, SNAPSHOT_TYPE, WORLD_KIND, ApplyInput, BooleanInput, BoxInput,
    ConfigureInput, CopyInput, CreateInput, DiffInput, DiffOutput, ExtrudeInput,
    FillInput, InspectInput, InspectOutput, MirrorInput, MutationOutput, ReadInput,
    ReplaceInput, SnapshotPayload, SphereInput, UndoInput, WorldInput, WorldSummary,
    WriteInput,
)
from .geometry import VoxelError, check_cancel
from .store import Library, VoxelStore, WorldSnapshot

GeometryInput = FillInput | BoxInput | SphereInput | ExtrudeInput | ReplaceInput | CopyInput | MirrorInput | BooleanInput
MutationInput = GeometryInput | ConfigureInput | UndoInput | WriteInput

# Every Tool below declares max_output_bytes=16_384, enforced by the Host before
# observation projection. Inspect and diff additionally page at 12,000 bytes in
# the store, so their complete output fits both the 32,768-byte facts and the
# 65,536-byte provider payload budgets without a second truncation policy.


def _failure(exc: VoxelError | ValueError) -> ToolInputError:
    if isinstance(exc, VoxelError):
        return ToolInputError(f"{exc.code}: {exc.message}")
    return ToolInputError("INVALID_INPUT: The voxel request violates the domain contract.")


def _world(input: WorldInput, context: ExtensionToolRunContext) -> WorldSnapshot:
    resource = context.require_one(WORLD_KIND)
    if not isinstance(resource, WorldSnapshot) or resource.world_id != input.world_id:
        raise ToolInputError("The selected world is not this invocation's authorized voxel resource.")
    refs = context.scopes(WORLD_KIND)
    if len(refs) != 1 or refs[0].id != resource.world_id or str(refs[0].version) != str(resource.version):
        raise ToolInputError("The voxel resource does not match the frozen invocation reference.")
    return resource


def snapshot_artifact(output: WorldSummary, scope: ResourceScopeRef) -> ArtifactDraft:
    payload = SnapshotPayload.model_validate({key: value for key, value in output.model_dump(mode="json").items() if key in SnapshotPayload.model_fields})
    return ArtifactDraft(
        key="voxel_snapshot", type=SNAPSHOT_TYPE, schema_version=1, title=output.title,
        payload=payload.model_dump(mode="json"),
        summary=f"Voxel world v{output.version}: {output.nonzero_count} layer voxels, {output.chunk_count} chunks.",
        semantic_key=f"voxel_world:{output.world_id}", resource_refs=(scope,), select_if_none=True,
    )


def _mutation_outcome(output: MutationOutput, context: ExtensionToolRunContext, kind: str = WORLD_KIND) -> ToolOutcome[MutationOutput]:
    refs = context.scopes(kind)
    if len(refs) != 1:
        raise ToolInputError("The voxel operation requires one exact resource reference.")
    return ToolOutcome(output=output, artifacts=(snapshot_artifact(output, refs[0]),))


def _read_spec() -> ToolExecutionSpec:
    return ToolExecutionSpec(recovery="retry_safe", concurrency="parallel_safe", max_output_bytes=16_384,
        required_resources=(ToolResourceRequirement(kind=WORLD_KIND, selector_field="world_id"),))


class _WriteTool:
    group = "voxel"
    version = "1"
    output_model = MutationOutput
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential", timeout_seconds=120, max_output_bytes=16_384,
        required_resources=(ToolResourceRequirement(kind=WORLD_KIND, selector_field="world_id"),))
    semantics = ToolSemanticSpec(produces=(SNAPSHOT_TYPE,))
    presentation = ToolPresentation(title="编辑体素世界", category="manage")
    operation_kind: str

    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    def project_observation(self, *, status: str, output: dict[str, object], artifacts: list[object]) -> ToolObservationProjection:
        if status != "success":
            return ToolObservationProjection(summary="Voxel world edit did not complete.")
        result = MutationOutput.model_validate(output)
        payload = result.model_dump(mode="json")
        return ToolObservationProjection(
            summary=f"Voxel {result.operation_kind}: world {result.world_id} v{result.version}; changed={result.changed}, {result.changed_voxel_count} changed layer voxels.",
            facts=payload, provider_payload=payload,
        )

    @staticmethod
    def _input(input: MutationInput) -> ApplyInput | ConfigureInput | UndoInput | WriteInput:
        if isinstance(input, (FillInput, BoxInput, SphereInput, ExtrudeInput, ReplaceInput, CopyInput, MirrorInput, BooleanInput)):
            return ApplyInput.model_validate(input.model_dump(mode="json"))
        return input

    def run(self, input: MutationInput, context: ExtensionToolRunContext) -> ToolOutcome[MutationOutput]:
        source = _world(input, context)
        try:
            output = self.store.mutate(source.project_id, self._input(input), kind=self.operation_kind,
                origin="tool", request_id=context.invocation_id, frozen_version=source.version, cancelled=context.is_cancelled)
            return _mutation_outcome(output, context)
        except (VoxelError, ValueError) as exc:
            raise _failure(exc) from exc

    def reconcile(self, input: MutationInput, context: ExtensionToolRunContext) -> ToolReconciliation:
        source = _world(input, context)
        try:
            output = self.store.receipt(source.project_id, "tool", context.invocation_id, self.operation_kind, self._input(input))
        except (VoxelError, ValueError) as exc:
            return ToolReconciliation(status="failed", error=str(_failure(exc)), error_code="VOXEL_RECONCILIATION_FAILED")
        if output is None:
            return ToolReconciliation(status="not_applied")
        outcome = _mutation_outcome(output, context)
        return ToolReconciliation(status="succeeded", output=output.model_dump(mode="json"), artifacts=outcome.artifacts)


class VoxelFillTool(_WriteTool, BaseTool[FillInput, MutationOutput]):
    name = "voxel_fill"
    description = "Fill a bounded region in one voxel layer; palette index zero erases. Use expected_version from inspect."
    input_model = FillInput
    operation_kind = "fill"
    reconcile = _WriteTool.reconcile


class VoxelBoxTool(_WriteTool, BaseTool[BoxInput, MutationOutput]):
    name = "voxel_box"
    description = "Create a solid or hollow voxel box. Hollow interiors retain existing content unless clear_inside is explicit."
    input_model = BoxInput
    operation_kind = "box"
    reconcile = _WriteTool.reconcile


class VoxelSphereTool(_WriteTool, BaseTool[SphereInput, MutationOutput]):
    name = "voxel_sphere"
    description = "Create a bounded integer-center voxel sphere or shell with a version fence."
    input_model = SphereInput
    operation_kind = "sphere"
    reconcile = _WriteTool.reconcile


class VoxelExtrudeTool(_WriteTool, BaseTool[ExtrudeInput, MutationOutput]):
    name = "voxel_extrude"
    description = "Extrude nonempty cells from a one-cell-thick source plane by a signed axis and depth."
    input_model = ExtrudeInput
    operation_kind = "extrude"
    reconcile = _WriteTool.reconcile


class VoxelReplaceTool(_WriteTool, BaseTool[ReplaceInput, MutationOutput]):
    name = "voxel_replace"
    description = "Replace one palette index only inside a bounded region of one voxel layer."
    input_model = ReplaceInput
    operation_kind = "replace"
    reconcile = _WriteTool.reconcile


class VoxelCopyRegionTool(_WriteTool, BaseTool[CopyInput, MutationOutput]):
    name = "voxel_copy_region"
    description = "Copy a region from an explicit source layer snapshot, safely handling overlap; replace includes air, over skips air."
    input_model = CopyInput
    operation_kind = "copy_region"
    reconcile = _WriteTool.reconcile


class VoxelMirrorTool(_WriteTool, BaseTool[MirrorInput, MutationOutput]):
    name = "voxel_mirror"
    description = "Mirror a source region along one axis into an explicit destination; use its origin for an in-place reflection."
    input_model = MirrorInput
    operation_kind = "mirror"
    reconcile = _WriteTool.reconcile


class VoxelBooleanTool(_WriteTool, BaseTool[BooleanInput, MutationOutput]):
    name = "voxel_boolean"
    description = "Apply union, intersection, difference, or xor between target and explicit source layers in one world region."
    input_model = BooleanInput
    operation_kind = "boolean"
    reconcile = _WriteTool.reconcile


class VoxelConfigureTool(_WriteTool, BaseTool[ConfigureInput, MutationOutput]):
    name = "voxel_configure"
    description = "Perform one explicit metadata, palette, layer, or named-region operation without replacing world geometry."
    input_model = ConfigureInput
    operation_kind = "configure"
    reconcile = _WriteTool.reconcile


class VoxelUndoTool(_WriteTool, BaseTool[UndoInput, MutationOutput]):
    name = "voxel_undo"
    description = "Restore an explicit historical world version as a new revision. Requires current expected_version; also supports undo-of-undo."
    input_model = UndoInput
    operation_kind = "undo"
    reconcile = _WriteTool.reconcile


class VoxelDeleteTool(_WriteTool, BaseTool[WriteInput, MutationOutput]):
    name = "voxel_delete"
    description = "Soft-delete the selected voxel world at expected_version, preserving immutable snapshots and undo history."
    input_model = WriteInput
    operation_kind = "delete"
    reconcile = _WriteTool.reconcile


class VoxelCreateTool(BaseTool[CreateInput, MutationOutput]):
    name = "voxel_create"
    group = "voxel"
    version = "1"
    description = "Create a durable blank voxel world with a default palette and base layer, then develop it using high-level geometry Tools."
    input_model = CreateInput
    output_model = MutationOutput
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential", max_output_bytes=16_384,
        required_resources=(ToolResourceRequirement(kind=LIBRARY_KIND),))
    semantics = ToolSemanticSpec(produces=(SNAPSHOT_TYPE,))
    presentation = ToolPresentation(title="创建体素世界", category="manage")

    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    def project_observation(self, *, status: str, output: dict[str, object], artifacts: list[object]) -> ToolObservationProjection:
        if status != "success":
            return ToolObservationProjection(summary="Voxel world creation did not complete.")
        result = MutationOutput.model_validate(output)
        payload = result.model_dump(mode="json")
        return ToolObservationProjection(
            summary=f"Created voxel world {result.world_id} v{result.version}; inspect its layer and palette IDs before editing.",
            facts=payload, provider_payload=payload,
        )

    @staticmethod
    def _library(context: ExtensionToolRunContext) -> Library:
        resource = context.require_one(LIBRARY_KIND)
        if not isinstance(resource, Library):
            raise ToolInputError("The invocation has no authorized voxel library.")
        refs = context.scopes(LIBRARY_KIND)
        if len(refs) != 1 or refs[0].id != resource.project_id or str(refs[0].version) != "1":
            raise ToolInputError("The voxel library does not match this invocation's frozen reference.")
        return resource

    def run(self, input: CreateInput, context: ExtensionToolRunContext) -> ToolOutcome[MutationOutput]:
        library = self._library(context)
        try:
            output = self.store.create(library.project_id, input, origin="tool", request_id=context.invocation_id, cancelled=context.is_cancelled)
            return _mutation_outcome(output, context, LIBRARY_KIND)
        except (VoxelError, ValueError) as exc:
            raise _failure(exc) from exc

    def reconcile(self, input: CreateInput, context: ExtensionToolRunContext) -> ToolReconciliation:
        library = self._library(context)
        try:
            output = self.store.receipt(library.project_id, "tool", context.invocation_id, "create", input)
        except (VoxelError, ValueError) as exc:
            return ToolReconciliation(status="failed", error=str(_failure(exc)), error_code="VOXEL_RECONCILIATION_FAILED")
        if output is None:
            return ToolReconciliation(status="not_applied")
        return ToolReconciliation(status="succeeded", output=output.model_dump(mode="json"), artifacts=_mutation_outcome(output, context, LIBRARY_KIND).artifacts)


class VoxelInspectTool(BaseTool[InspectInput, InspectOutput]):
    name = "voxel_inspect"
    group = "voxel"
    version = "1"
    description = "Inspect a voxel world's exact version, bounded layer/palette/region page, and optional region occupancy before editing. No full voxel arrays."
    input_model = InspectInput
    output_model = InspectOutput
    execution = _read_spec()
    policy = ToolPolicy(risk_level="safe")
    presentation = ToolPresentation(title="检查体素世界", category="explore")

    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    def project_observation(self, *, status: str, output: dict[str, object], artifacts: list[object]) -> ToolObservationProjection:
        if status != "success":
            return ToolObservationProjection(summary="Voxel world inspection did not complete.")
        result = InspectOutput.model_validate(output)
        # The store bounds complete object pages to 12,000 UTF-8 bytes. Preserve
        # both the exact objects and revision-pinned continuation in observation.
        payload = result.model_dump(mode="json")
        continuation = f" Continue at object_offset={result.next_object_offset} with version={result.version}." if result.truncated else ""
        return ToolObservationProjection(
            summary=f"Inspected voxel world {result.world_id} v{result.version}; {result.nonzero_count} layer voxels.{continuation}",
            facts=payload, provider_payload=payload,
        )

    def run(self, input: InspectInput, context: ExtensionToolRunContext) -> ToolOutcome[InspectOutput]:
        source = _world(input, context)
        if input.version is not None and input.version > source.version:
            raise ToolInputError("The requested revision exceeds this invocation's frozen voxel version.")
        request = input.model_copy(update={"version": input.version or source.version})
        try:
            return ToolOutcome(output=self.store.inspect(source.project_id, request, context.is_cancelled))
        except (VoxelError, ValueError) as exc:
            raise _failure(exc) from exc


class VoxelDiffTool(BaseTool[DiffInput, DiffOutput]):
    name = "voxel_diff"
    group = "voxel"
    version = "1"
    description = "Compare two fixed voxel revisions using a bounded page of changed chunk hashes and metadata-change evidence."
    input_model = DiffInput
    output_model = DiffOutput
    execution = _read_spec()
    policy = ToolPolicy(risk_level="safe")
    presentation = ToolPresentation(title="比较体素版本", category="explore")

    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    def project_observation(self, *, status: str, output: dict[str, object], artifacts: list[object]) -> ToolObservationProjection:
        if status != "success":
            return ToolObservationProjection(summary="Voxel revision comparison did not complete.")
        result = DiffOutput.model_validate(output)
        # Diff uses the same complete-page byte budget as inspect; the opaque
        # cursor is retained verbatim for these exact from/to revisions.
        payload = result.model_dump(mode="json")
        continuation = " Continue with next_after and the same revision pair." if result.truncated else ""
        return ToolObservationProjection(
            summary=f"Compared voxel world {result.world_id} v{result.from_version} to v{result.to_version}; {result.changed_chunk_count} changed chunks.{continuation}",
            facts=payload, provider_payload=payload,
        )

    def run(self, input: DiffInput, context: ExtensionToolRunContext) -> ToolOutcome[DiffOutput]:
        source = _world(input, context)
        if max(input.from_version, input.to_version) > source.version:
            raise ToolInputError("The comparison exceeds this invocation's frozen voxel version.")
        try:
            check_cancel(context.is_cancelled)
            return ToolOutcome(output=self.store.diff(source.project_id, input))
        except (VoxelError, ValueError) as exc:
            raise _failure(exc) from exc


class VoxelExportTool(BaseTool[ReadInput, WorldSummary]):
    name = "voxel_export"
    group = "voxel"
    version = "1"
    description = "Publish an immutable voxel snapshot Artifact with a paginated JSON representation for inspection and cross-DLC composition."
    input_model = ReadInput
    output_model = WorldSummary
    execution = _read_spec()
    policy = ToolPolicy(risk_level="safe")
    semantics = ToolSemanticSpec(produces=(SNAPSHOT_TYPE,), publishes_artifact_references=True)
    presentation = ToolPresentation(title="保存体素快照", category="manage")

    def __init__(self, store: VoxelStore) -> None:
        self.store = store

    def project_observation(self, *, status: str, output: dict[str, object], artifacts: list[object]) -> ToolObservationProjection:
        if status != "success":
            return ToolObservationProjection(summary="Voxel snapshot export did not complete.")
        result = WorldSummary.model_validate(output)
        payload = result.model_dump(mode="json")
        # The Host supplies persisted Artifact IDs in the observation envelope.
        return ToolObservationProjection(
            summary=f"Exported immutable voxel world {result.world_id} v{result.version}; {result.nonzero_count} layer voxels.",
            facts=payload, provider_payload=payload,
        )

    def run(self, input: ReadInput, context: ExtensionToolRunContext) -> ToolOutcome[WorldSummary]:
        source = _world(input, context)
        if input.version is not None and input.version > source.version:
            raise ToolInputError("The requested snapshot exceeds this invocation's frozen voxel version.")
        try:
            check_cancel(context.is_cancelled)
            snapshot = self.store.snapshot(source.project_id, source.world_id, input.version or source.version)
            output = self.store.summary(snapshot)
            return ToolOutcome(output=output, artifacts=(snapshot_artifact(output, context.scopes(WORLD_KIND)[0]),))
        except (VoxelError, ValueError) as exc:
            raise _failure(exc) from exc
