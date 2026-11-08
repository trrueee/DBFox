"""Public Voxel contracts. Coordinates use half-open integer bounds."""
from __future__ import annotations

from typing import Annotated, Literal

from dbfox_dlc_api import BaseModel, ConfigDict, Field, ToolInputModel, ToolOutputModel

LIBRARY_KIND = "dbfox.voxel.library"
WORLD_KIND = "dbfox.voxel.world"
SNAPSHOT_TYPE = "dbfox.voxel.snapshot"
REPRESENTATION_TYPE = "dbfox.voxel.world.v1"
CHUNK_SIZE = 16
CHUNK_BYTES = 4096
MAX_CANDIDATES = 2_097_152
MAX_LIVE_CHUNKS = 8192
MAX_METADATA_BYTES = 65_536
MAX_HISTORY_BYTES = 128 * 1024 * 1024

Integer = Annotated[int, Field(strict=True)]
Version = Annotated[int, Field(strict=True, ge=1)]
Index = Annotated[int, Field(strict=True, ge=0, le=255)]
Identity = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
Name = Annotated[str, Field(min_length=1, max_length=80)]
Vector = Annotated[list[Integer], Field(min_length=3, max_length=3)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Bounds(Contract):
    min: Vector
    max: Vector

    def model_post_init(self, __context: object) -> None:
        if any(lo < 0 or hi <= lo for lo, hi in zip(self.min, self.max)):
            raise ValueError("Bounds must be nonempty half-open positive integer ranges.")


class PaletteEntry(Contract):
    index: Index
    name: Name
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class Layer(Contract):
    id: Identity
    name: Name
    locked: bool = Field(default=False, strict=True)


class Region(Contract):
    id: Identity
    name: Name
    bounds: Bounds


class Metadata(Contract):
    description: str = Field(default="", max_length=4096)
    tags: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=32)


def default_palette() -> list[PaletteEntry]:
    return [PaletteEntry(index=0, name="Air", color="#000000"),
            PaletteEntry(index=1, name="Stone", color="#64748b"),
            PaletteEntry(index=2, name="Neon pink", color="#f472b6"),
            PaletteEntry(index=3, name="Neon cyan", color="#22d3ee"),
            PaletteEntry(index=4, name="Gold", color="#fbbf24")]


class WorldDocument(Contract):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    size: Vector
    title: Name
    status: Literal["active", "deleted"] = "active"
    palette: list[PaletteEntry] = Field(default_factory=default_palette, min_length=1, max_length=256)
    layers: list[Layer] = Field(default_factory=lambda: [Layer(id="base", name="Base")], min_length=1, max_length=16)
    regions: list[Region] = Field(default_factory=list, max_length=128)
    metadata: Metadata = Field(default_factory=Metadata)

    def model_post_init(self, __context: object) -> None:
        if any(not 1 <= n <= 256 for n in self.size):
            raise ValueError("World dimensions must be between 1 and 256.")
        if len({p.index for p in self.palette}) != len(self.palette):
            raise ValueError("Palette indices must be unique.")
        if not any(p.index == 0 and p.name == "Air" and p.color == "#000000" for p in self.palette):
            raise ValueError("Palette slot zero must remain Air (#000000).")
        if len({layer.id for layer in self.layers}) != len(self.layers):
            raise ValueError("Layer IDs must be unique.")
        if len({region.id for region in self.regions}) != len(self.regions):
            raise ValueError("Region IDs must be unique.")
        for region in self.regions:
            if any(hi > size for hi, size in zip(region.bounds.max, self.size)):
                raise ValueError("A named region is outside the world.")


class FillOperation(Contract):
    kind: Literal["fill"] = "fill"
    layer_id: Identity
    bounds: Bounds
    palette_index: Index


class BoxOperation(Contract):
    kind: Literal["box"] = "box"
    layer_id: Identity
    bounds: Bounds
    palette_index: Index
    hollow: bool = Field(default=False, strict=True)
    thickness: Annotated[int, Field(strict=True, ge=1, le=256)] = 1
    clear_inside: bool = Field(default=False, strict=True)


class SphereOperation(Contract):
    kind: Literal["sphere"] = "sphere"
    layer_id: Identity
    center: Vector
    radius: Annotated[int, Field(strict=True, ge=0, le=127)]
    palette_index: Index
    hollow: bool = Field(default=False, strict=True)
    thickness: Annotated[int, Field(strict=True, ge=1, le=128)] = 1
    clear_inside: bool = Field(default=False, strict=True)


class ExtrudeOperation(Contract):
    kind: Literal["extrude"] = "extrude"
    layer_id: Identity
    source_layer_id: Identity
    bounds: Bounds
    axis: Literal["x", "y", "z"]
    depth: Annotated[int, Field(strict=True, ge=1, le=255)]
    direction: Annotated[int, Field(strict=True, ge=-1, le=1)] = 1

    def model_post_init(self, __context: object) -> None:
        if self.direction not in (-1, 1):
            raise ValueError("Direction must be -1 or 1.")


class ReplaceOperation(Contract):
    kind: Literal["replace"] = "replace"
    layer_id: Identity
    bounds: Bounds
    from_index: Index
    to_index: Index


class CopyOperation(Contract):
    kind: Literal["copy_region"] = "copy_region"
    layer_id: Identity
    source_layer_id: Identity
    bounds: Bounds
    destination: Vector
    mode: Literal["replace", "over"] = "replace"


class MirrorOperation(Contract):
    kind: Literal["mirror"] = "mirror"
    layer_id: Identity
    source_layer_id: Identity
    bounds: Bounds
    destination: Vector
    axis: Literal["x", "y", "z"]
    mode: Literal["replace", "over"] = "replace"


class BooleanOperation(Contract):
    kind: Literal["boolean"] = "boolean"
    layer_id: Identity
    source_layer_id: Identity
    bounds: Bounds
    mode: Literal["union", "intersection", "difference", "xor"]


GeometryOperation = Annotated[FillOperation | BoxOperation | SphereOperation | ExtrudeOperation | ReplaceOperation | CopyOperation | MirrorOperation | BooleanOperation, Field(discriminator="kind")]


class Rename(Contract):
    kind: Literal["rename"] = "rename"
    title: Name


class PalettePut(Contract):
    kind: Literal["palette_put"] = "palette_put"
    entry: PaletteEntry


class PaletteRemove(Contract):
    kind: Literal["palette_remove"] = "palette_remove"
    index: Index


class LayerPut(Contract):
    kind: Literal["layer_put"] = "layer_put"
    layer: Layer


class LayerRemove(Contract):
    kind: Literal["layer_remove"] = "layer_remove"
    layer_id: Identity


class LayerOrder(Contract):
    kind: Literal["layer_order"] = "layer_order"
    layer_ids: list[Identity] = Field(min_length=1, max_length=16)


class RegionPut(Contract):
    kind: Literal["region_put"] = "region_put"
    region: Region


class RegionRemove(Contract):
    kind: Literal["region_remove"] = "region_remove"
    region_id: Identity


class MetadataSet(Contract):
    kind: Literal["metadata_set"] = "metadata_set"
    metadata: Metadata


ConfigureOperation = Annotated[Rename | PalettePut | PaletteRemove | LayerPut | LayerRemove | LayerOrder | RegionPut | RegionRemove | MetadataSet, Field(discriminator="kind")]


class CreateInput(ToolInputModel):
    title: Name
    size: Vector = Field(default_factory=lambda: [64, 64, 64])
    expected_version: Annotated[int, Field(strict=True, ge=0, le=0)] = 0


class WorldInput(ToolInputModel):
    world_id: Identity


class WriteInput(WorldInput):
    expected_version: Version


class ApplyInput(WriteInput):
    operation: GeometryOperation


class FillInput(WriteInput):
    operation: FillOperation


class BoxInput(WriteInput):
    operation: BoxOperation


class SphereInput(WriteInput):
    operation: SphereOperation


class ExtrudeInput(WriteInput):
    operation: ExtrudeOperation


class ReplaceInput(WriteInput):
    operation: ReplaceOperation


class CopyInput(WriteInput):
    operation: CopyOperation


class MirrorInput(WriteInput):
    operation: MirrorOperation


class BooleanInput(WriteInput):
    operation: BooleanOperation


class ConfigureInput(WriteInput):
    operation: ConfigureOperation


class UndoInput(WriteInput):
    target_version: Version


class ReadInput(WorldInput):
    version: Version | None = None


class InspectInput(ReadInput):
    bounds: Bounds | None = None
    layer_id: Identity | None = None
    object_offset: Annotated[int, Field(strict=True, ge=0, le=512)] = 0
    object_limit: Annotated[int, Field(strict=True, ge=1, le=32)] = 16


class DiffInput(WorldInput):
    from_version: Version
    to_version: Version
    limit: Annotated[int, Field(strict=True, ge=1, le=64)] = 32
    after: str | None = Field(default=None, max_length=512)


class ChunkPageInput(ReadInput):
    version: Version
    limit: Annotated[int, Field(strict=True, ge=1, le=16)] = 16
    after: str | None = Field(default=None, max_length=512)
    since_version: Version | None = None


class RepresentationPage(Contract):
    limit: Annotated[int, Field(strict=True, ge=1, le=16)] = 16
    after: str | None = Field(default=None, max_length=512)
    since_version: Version | None = None


class HumanCreateInput(CreateInput):
    mutation_id: Identity


class HumanApplyInput(ApplyInput):
    mutation_id: Identity


class HumanConfigureInput(ConfigureInput):
    mutation_id: Identity


class HumanUndoInput(UndoInput):
    mutation_id: Identity


class HumanDeleteInput(WriteInput):
    mutation_id: Identity


class SnapshotActionInput(ReadInput):
    mutation_id: Identity


class ListInput(Contract):
    include_deleted: bool = Field(default=False, strict=True)
    limit: Annotated[int, Field(strict=True, ge=1, le=128)] = 32
    after: str | None = Field(default=None, max_length=128)


class RevisionsInput(WorldInput):
    before_version: Version | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=64)] = 32


class WorldSummary(ToolOutputModel):
    world_id: str
    project_id: str
    version: int
    parent_version: int | None
    title: str
    status: Literal["active", "deleted"]
    size: list[int]
    content_hash: str
    chunk_count: int
    nonzero_count: int
    layer_count: int
    palette_count: int
    region_count: int


class MutationOutput(WorldSummary):
    changed: bool
    changed_chunk_count: int
    changed_voxel_count: int
    operation_kind: str


class SnapshotPayload(WorldSummary):
    pass


class WorldOutput(WorldSummary):
    document: WorldDocument


class WorldListOutput(ToolOutputModel):
    worlds: list[WorldSummary]
    next_after: str | None = None


class InspectOutput(WorldSummary):
    layers: list[Layer]
    palette: list[PaletteEntry]
    regions: list[Region]
    object_offset: int
    next_object_offset: int | None
    truncated: bool
    selected_nonzero_count: int | None = None


class ChunkData(Contract):
    layer_id: str
    coord: list[int]
    hash: str
    values: list[int] | None


class ChunkPageOutput(ToolOutputModel):
    world_id: str
    version: int
    since_version: int | None
    chunks: list[ChunkData]
    next_after: str | None
    metadata_changed: bool


class RevisionSummary(Contract):
    version: int
    parent_version: int | None
    operation_kind: str
    restored_from_version: int | None
    content_hash: str
    created_at: str


class RevisionsOutput(ToolOutputModel):
    world_id: str
    revisions: list[RevisionSummary]
    next_before_version: int | None


class ChunkDifference(Contract):
    layer_id: str
    coord: list[int]
    before_hash: str | None
    after_hash: str | None


class DiffOutput(ToolOutputModel):
    world_id: str
    from_version: int
    to_version: int
    metadata_changed: bool
    changed_chunk_count: int
    chunks: list[ChunkDifference]
    next_after: str | None
    truncated: bool


class SnapshotActionOutput(ToolOutputModel):
    run_id: str
    session_id: str
    artifact_ids: list[str]


class EmptyInput(Contract):
    pass
