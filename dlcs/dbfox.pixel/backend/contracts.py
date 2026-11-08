"""Single strict contract for Human operations, Agent tools and durable documents."""
from __future__ import annotations

from typing import Annotated, Literal
import json

from dbfox_dlc_api import BaseModel, ConfigDict, Field
from pydantic import JsonValue, field_validator, model_validator
from pydantic_core import PydanticCustomError

OWNER = "dbfox.pixel"
DOCUMENT_KIND = OWNER + ".document"
LIBRARY_KIND = OWNER + ".library"
ARTIFACT_TYPE = OWNER + ".revision"
REPRESENTATION_TYPE = OWNER + ".sprite.v1"
MAX_SLOTS = 262144
MAX_FRAMES = 256
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_INPUT_BYTES = 65536
MAX_OUTPUT_BYTES = 16384
MAX_HISTORY_BYTES = 128 * 1024 * 1024
Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
Name = Annotated[str, Field(min_length=1, max_length=80)]
Index = Annotated[int, Field(strict=True, ge=0, le=255)]
Coordinate = Annotated[int, Field(strict=True, ge=0, le=127)]
Positive = Annotated[int, Field(strict=True, ge=1)]
Duration = Annotated[int, Field(strict=True, ge=20, le=2000)]
Kind = Literal["frames", "layers", "tags", "palette"]


def canonical(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_defaults(cls, value):
        # Only optional/defaulted operation fields accept null; canonical models
        # override this flag. Required values never silently acquire a default.
        if isinstance(value, dict) and issubclass(cls, Input):
            return {k: v for k, v in value.items()
                    if v is not None or k not in cls.model_fields or cls.model_fields[k].is_required()}
        return value


class Input(Contract):
    @model_validator(mode="after")
    def bounded_input(self):
        if len(canonical(self).encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Pixel input exceeds 64 KiB")
        return self


class Canvas(Contract):
    width: int = Field(strict=True, ge=1, le=128)
    height: int = Field(strict=True, ge=1, le=128)


class PaletteEntry(Contract):
    name: Name
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{8}$")

    @field_validator("color")
    @classmethod
    def uppercase(cls, value):
        return value.upper()


class Layer(Contract):
    id: Id
    name: Name
    visible: bool
    locked: bool


class Cel(Contract):
    layer_id: Id
    pixels: list[Index] = Field(max_length=16384)


class Frame(Contract):
    id: Id
    duration_ms: Duration
    cels: list[Cel] = Field(min_length=1, max_length=16)


class Tag(Contract):
    id: Id
    name: Name
    frame_ids: list[Id] = Field(min_length=1, max_length=MAX_FRAMES)
    loop: bool


class PixelDocument(Contract):
    schema_version: int = Field(strict=True, ge=1, le=1)
    title: str = Field(min_length=1, max_length=160)
    canvas: Canvas
    palette: list[PaletteEntry] = Field(min_length=1, max_length=256)
    layers: list[Layer] = Field(min_length=1, max_length=16)
    frames: list[Frame] = Field(min_length=1, max_length=MAX_FRAMES)
    tags: list[Tag] = Field(max_length=16)

    @model_validator(mode="after")
    def consistent(self):
        validate_palette(self.palette)
        size = self.canvas.width * self.canvas.height
        if size * len(self.frames) * len(self.layers) > MAX_SLOTS:
            raise ValueError("Pixel document exceeds 262144 pixel slots")
        for items in (self.layers, self.frames, self.tags):
            if len({item.id for item in items}) != len(items):
                raise ValueError("Duplicate object identity")
        layer_ids = [item.id for item in self.layers]
        frame_ids = {item.id for item in self.frames}
        for frame in self.frames:
            if [cel.layer_id for cel in frame.cels] != layer_ids:
                raise ValueError("Each frame must have one ordered cel per layer")
            for cel in frame.cels:
                if len(cel.pixels) != size or any(index >= len(self.palette) for index in cel.pixels):
                    raise ValueError("Invalid cel dimensions or palette index")
        for tag in self.tags:
            if len(set(tag.frame_ids)) != len(tag.frame_ids) or not set(tag.frame_ids) <= frame_ids:
                raise ValueError("Invalid tag frame references")
        if len(canonical(self).encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError("Pixel document exceeds 2 MiB")
        return self


def validate_palette(palette):
    if palette[0].name != "Transparent" or palette[0].color != "#00000000":
        raise ValueError("Palette slot zero must be Transparent/#00000000")
    if any(entry.color[-2:] != "FF" for entry in palette[1:]):
        raise ValueError("Nonzero palette entries must be opaque")


class Rect(Contract):
    x: Coordinate
    y: Coordinate
    width: int = Field(strict=True, ge=1, le=128)
    height: int = Field(strict=True, ge=1, le=128)


class Point(Contract):
    x: int = Field(strict=True, ge=-128, le=255)
    y: int = Field(strict=True, ge=-128, le=255)


class PixelTarget(Input):
    frame_id: Id
    layer_id: Id


class Fill(PixelTarget):
    kind: Literal["fill"]
    x: Coordinate
    y: Coordinate
    palette_index: Index
    rect: Rect | None = None


class Line(PixelTarget):
    kind: Literal["line"]
    x0: Coordinate
    y0: Coordinate
    x1: Coordinate
    y1: Coordinate
    palette_index: Index


class Rectangle(PixelTarget):
    kind: Literal["rect"]
    rect: Rect
    palette_index: Index
    filled: bool = True


class Stamp(PixelTarget):
    kind: Literal["stamp"]
    rect: Rect
    pixels: list[Index] = Field(
        min_length=1, max_length=4096,
        description=("Flat row-major palette indices, exactly rect.width * rect.height entries. "
                     "A 16 by 16 rectangle requires exactly 256 indices; slot 0 is transparent. "
                     "Use smaller rectangular stamps when the full list is difficult to count."),
    )
    transparent_mode: Literal["replace", "over"] = "replace"

    @model_validator(mode="after")
    def shape(self):
        if len(self.pixels) != self.rect.width * self.rect.height:
            raise PydanticCustomError(
                "pixel_stamp_pixel_count_must_equal_rectangle_area",
                "Stamp pixel count must equal its rectangle area",
            )
        return self


class PaletteSet(Input):
    kind: Literal["palette_set"]
    index: Index
    name: Name
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{8}$")

    @field_validator("color")
    @classmethod
    def uppercase(cls, value):
        return value.upper()


class FrameCreate(Input):
    kind: Literal["frame_create"]
    frame_id: Id
    position: int = Field(strict=True, ge=0, le=MAX_FRAMES - 1)
    duration_ms: Duration = 100


class FrameDuplicate(Input):
    kind: Literal["frame_duplicate"]
    source_frame_id: Id
    frame_id: Id
    position: int = Field(strict=True, ge=0, le=MAX_FRAMES - 1)


class FrameUpdate(Input):
    kind: Literal["frame_update"]
    frame_id: Id
    duration_ms: Duration | None = None
    position: Annotated[int, Field(strict=True, ge=0, le=MAX_FRAMES - 1)] | None = None

    @model_validator(mode="after")
    def update_required(self):
        if self.duration_ms is None and self.position is None:
            raise ValueError("At least one frame update is required")
        return self


class FrameDelete(Input):
    kind: Literal["frame_delete"]
    frame_id: Id
    remove_from_tags: bool = False


class LayerCreate(Input):
    kind: Literal["layer_create"]
    layer_id: Id
    name: Name
    position: int = Field(strict=True, ge=0, le=15)


class LayerUpdate(Input):
    kind: Literal["layer_update"]
    layer_id: Id
    name: Name | None = None
    visible: bool | None = None
    locked: bool | None = None
    position: Annotated[int, Field(strict=True, ge=0, le=15)] | None = None

    @model_validator(mode="after")
    def update_required(self):
        if all(getattr(self, field) is None for field in ("name", "visible", "locked", "position")):
            raise ValueError("At least one layer update is required")
        return self


class LayerDelete(Input):
    kind: Literal["layer_delete"]
    layer_id: Id


class TagSet(Input):
    kind: Literal["tag_set"]
    tag_id: Id
    name: Name
    frame_ids: list[Id] = Field(min_length=1, max_length=MAX_FRAMES)
    loop: bool = True


class TagDelete(Input):
    kind: Literal["tag_delete"]
    tag_id: Id


class Rename(Input):
    kind: Literal["rename"]
    title: str = Field(min_length=1, max_length=160)


class RegionTransform(PixelTarget):
    kind: Literal["region_transform"]
    rect: Rect
    transform: Literal["translate", "flip_x", "flip_y", "rotate_cw"]
    destination: Point
    mode: Literal["copy", "move"] = "copy"
    clip: bool = False


Operation = Annotated[Fill | Line | Rectangle | Stamp | PaletteSet | FrameCreate | FrameDuplicate |
    FrameUpdate | FrameDelete | LayerCreate | LayerUpdate | LayerDelete | TagSet | TagDelete | Rename |
    RegionTransform, Field(discriminator="kind")]


class CreateInput(Input):
    title: str = Field(min_length=1, max_length=160)
    width: int = Field(strict=True, ge=1, le=128)
    height: int = Field(strict=True, ge=1, le=128)
    palette: list[PaletteEntry] | None = Field(default=None, min_length=1, max_length=256)
    expected_version: int = Field(strict=True, ge=0, le=0)


class VersionInput(Input):
    document_id: Id
    expected_version: Positive


class ApplyInput(VersionInput):
    operations: list[Operation] = Field(min_length=1, max_length=128)


class SingleInput(VersionInput):
    operation: Operation


class UndoInput(VersionInput):
    restore_revision: Positive


class RestoreInput(VersionInput):
    library_id: str = Field(min_length=1, max_length=256)


class CreateToolInput(CreateInput):
    library_id: str = Field(min_length=1, max_length=256)


class MutationId(Input):
    mutation_id: str = Field(min_length=1, max_length=128)


class CreateRequest(CreateInput, MutationId):
    pass


class ApplyRequest(ApplyInput, MutationId):
    pass


class UndoRequest(UndoInput, MutationId):
    pass


class VersionRequest(VersionInput, MutationId):
    pass


class PageInput(Input):
    page: int = Field(default=0, strict=True, ge=0, le=1000000)
    page_size: int = Field(default=16, strict=True, ge=1, le=16)


class ListInput(PageInput):
    page_size: int = Field(default=16, strict=True, ge=1, le=32)
    include_deleted: bool = False


class DocumentsInput(ListInput):
    library_id: str = Field(min_length=1, max_length=256)
    page_size: int = Field(default=8, strict=True, ge=1, le=8)


class ReadInput(Input):
    document_id: Id
    revision: Positive | None = None


class HeadInput(Input):
    document_id: Id


class FrameReadInput(ReadInput):
    revision: Positive
    frame_id: Id


class MetadataInput(PageInput):
    kind: Kind = "frames"
    tag_id: Id | None = None

    @model_validator(mode="after")
    def tag_selection(self):
        if self.tag_id is not None and self.kind != "tags":
            raise ValueError("tag_id is only valid for tag metadata")
        return self


class InspectInput(ReadInput, MetadataInput):
    frame_id: Id | None = None
    layer_id: Id | None = None
    rect: Rect | None = None

    @model_validator(mode="after")
    def selection(self):
        count = sum(x is not None for x in (self.frame_id, self.layer_id, self.rect))
        if count not in (0, 3) or (self.rect and (self.rect.width > 16 or self.rect.height > 16)):
            raise ValueError("Inspect requires frame/layer/rect together, at most 16x16")
        if self.tag_id is not None and count:
            raise ValueError("Tag member inspection cannot include a cel window")
        return self


class DiffInput(PageInput):
    document_id: Id
    from_revision: Positive
    to_revision: Positive
    kind: Kind = "frames"


class RevisionsInput(HeadInput):
    before_revision: Positive | None = None
    limit: int = Field(default=16, strict=True, ge=1, le=32)


class DocumentSummary(Contract):
    project_id: str = Field(min_length=1, max_length=256)
    document_id: Id
    revision: Positive
    parent_revision: Positive | None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=160)
    width: int = Field(strict=True, ge=1, le=128)
    height: int = Field(strict=True, ge=1, le=128)
    frame_count: int = Field(strict=True, ge=1, le=MAX_FRAMES)
    layer_count: int = Field(strict=True, ge=1, le=16)
    palette_count: int = Field(strict=True, ge=1, le=256)
    tag_count: int = Field(strict=True, ge=0, le=16)
    status: Literal["active", "deleted"]


class MutationResult(DocumentSummary):
    changed: bool
    changed_pixel_count: int = Field(strict=True, ge=0)
    changed_frame_ids: list[Id] = Field(max_length=128)
    changed_frame_ids_truncated: bool = False
    changed_layer_ids: list[Id] = Field(max_length=32)


class Revision(Contract):
    summary: DocumentSummary
    document: PixelDocument


class Library(Contract):
    project_id: str


class ListResult(Contract):
    documents: list[DocumentSummary]
    has_more: bool


class MetadataResult(Contract):
    summary: DocumentSummary
    document: dict[str, JsonValue]


class HeadResult(Contract):
    document_id: Id
    revision: Positive
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["active", "deleted"]


class FrameResult(Contract):
    document_id: Id
    revision: Positive
    content_hash: str
    canvas: Canvas
    palette: list[PaletteEntry]
    frame: Frame


class PageResult(Contract):
    summary: DocumentSummary
    kind: Kind
    tag_id: Id | None = None
    page: int
    page_size: int
    total: int
    has_more: bool
    items: list[dict[str, JsonValue]]
    pixels: list[Index] | None = None
    selection: dict[str, JsonValue] | None = None


class DiffResult(Contract):
    document_id: Id
    from_revision: Positive
    to_revision: Positive
    kind: Kind
    page: int
    page_size: int
    total: int
    has_more: bool
    items: list[dict[str, JsonValue]]


class RevisionsResult(Contract):
    revisions: list[DocumentSummary]
    next_before_revision: int | None


class ExportResult(Contract):
    run_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    artifact_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(min_length=1, max_length=32)
