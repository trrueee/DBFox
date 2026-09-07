"""Comic visual narration: one canonical document for page and storyboard views."""
from __future__ import annotations

from typing import Annotated, Literal
from dbfox_dlc_api import BaseModel, ConfigDict, Field, ToolInputModel, ToolOutputModel
from pydantic import model_validator

OWNER = "dbfox.comic"
LIBRARY_KIND = "dbfox.comic.library"
DOCUMENT_KIND = "dbfox.comic.document"
ARTIFACT_TYPE = "dbfox.comic.revision"
REPRESENTATION_TYPE = "dbfox.comic.document.v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 128
MAX_ELEMENTS = 4096
Id = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")]
Integer = Annotated[int, Field(strict=True)]
Unit = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Color = Annotated[str, Field(strict=True, pattern=r"^#[0-9a-fA-F]{6}$")]
Text = Annotated[str, Field(strict=True, max_length=2000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, allow_inf_nan=False)


class Rect(Contract):
    x: Unit = 0.05
    y: Unit = 0.05
    width: Unit = Field(default=0.4, ge=0.02)
    height: Unit = Field(default=0.25, ge=0.02)

    @model_validator(mode="after")
    def within_parent(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Rectangle must fit its parent coordinate space")
        return self


class Shot(Contract):
    framing: Literal["wide", "full", "medium", "close", "detail"] = "medium"
    angle: Literal["eye", "high", "low", "overhead"] = "eye"
    movement: Literal["static", "pan", "tilt", "track", "zoom"] = "static"
    duration_seconds: Annotated[float, Field(strict=True, ge=0.1, le=600, allow_inf_nan=False)] = 3
    description: Text = ""


class Element(Contract):
    id: Id
    rect: Rect = Field(default_factory=Rect)


class CharacterPlacement(Element):
    kind: Literal["character"] = "character"
    label: str = Field(min_length=1, max_length=120)
    pose: Literal["standing", "walking", "seated", "reaching"] = "standing"
    facing: Literal["left", "right", "front"] = "front"
    color: Color = "#527E94"


class SpeechBubble(Element):
    kind: Literal["bubble"] = "bubble"
    text: Text = ""
    style: Literal["speech", "thought", "shout"] = "speech"
    tail_x: Unit = 0.5
    tail_y: Unit = 1
    speaker_id: Id | None = None
    font_size: Integer = Field(default=22, ge=10, le=72)


class Caption(Element):
    kind: Literal["caption"] = "caption"
    text: Text = ""
    font_size: Integer = Field(default=20, ge=10, le=72)
    color: Color = "#F4E8CB"


class VisualNote(Element):
    kind: Literal["note"] = "note"
    text: Text = ""


ComicElement = Annotated[CharacterPlacement | SpeechBubble | Caption | VisualNote, Field(discriminator="kind")]


class Panel(Contract):
    id: Id
    title: str = Field(default="Panel", min_length=1, max_length=120)
    rect: Rect = Field(default_factory=Rect)
    background: Color = "#E8EDF0"
    shot: Shot = Field(default_factory=Shot)
    elements: list[ComicElement] = Field(default_factory=list, max_length=128)


class Page(Contract):
    id: Id
    title: str = Field(default="Page", min_length=1, max_length=120)
    width: Integer = Field(default=720, ge=240, le=2400)
    height: Integer = Field(default=960, ge=240, le=2400)
    background: Color = "#FFFFFF"
    panels: list[Panel] = Field(default_factory=list, max_length=24)


class ComicProject(Contract):
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=160)
    pages: list[Page] = Field(default_factory=list, max_length=MAX_PAGES)

    @model_validator(mode="after")
    def validate_references(self):
        ids = set()
        total = 0
        for page in self.pages:
            elements = [element for panel in page.panels for element in panel.elements]
            if len(elements) > 128:
                raise ValueError("A page supports at most 128 visual elements")
            texts = [getattr(element, "text", "") for element in elements] + [p.shot.description for p in page.panels]
            if sum(len(text.encode("utf-8")) for text in texts) > 64_000:
                raise ValueError("Page dialogue and notes exceed 64000 UTF-8 bytes")
            total += len(elements)
            for item in [page, *page.panels, *elements]:
                if item.id in ids:
                    raise ValueError("IDs must be unique throughout the comic")
                ids.add(item.id)
            for panel in page.panels:
                characters = {e.id for e in panel.elements if e.kind == "character"}
                for element in panel.elements:
                    if element.kind == "bubble" and element.speaker_id is not None and element.speaker_id not in characters:
                        raise ValueError("Bubble speaker must be a character in the same panel")
        if total > MAX_ELEMENTS:
            raise ValueError("Comic exceeds 4096 visual elements")
        return self


class PageCreate(Contract):
    kind: Literal["page_create"] = "page_create"
    page: Page


class PanelCreate(Contract):
    kind: Literal["panel_create"] = "panel_create"
    page_id: Id
    panels: list[Panel] = Field(min_length=1, max_length=24)


class Placement(Contract):
    panel_id: Id
    rect: Rect


class PanelLayout(Contract):
    kind: Literal["panel_layout"] = "panel_layout"
    page_id: Id
    placements: list[Placement] = Field(min_length=1, max_length=24)


class ShotSet(Contract):
    kind: Literal["shot_set"] = "shot_set"
    panel_id: Id
    shot: Shot


class CharacterPlace(Contract):
    kind: Literal["character_place"] = "character_place"
    panel_id: Id
    character: CharacterPlacement


class BubbleCreate(Contract):
    kind: Literal["bubble_create"] = "bubble_create"
    panel_id: Id
    bubble: SpeechBubble


class CaptionCreate(Contract):
    kind: Literal["caption_create"] = "caption_create"
    panel_id: Id
    caption: Caption


class NoteCreate(Contract):
    kind: Literal["note_create"] = "note_create"
    panel_id: Id
    note: VisualNote


class ElementUpdate(Contract):
    kind: Literal["element_update"] = "element_update"
    panel_id: Id
    element: ComicElement


class PanelReorder(Contract):
    kind: Literal["panel_reorder"] = "panel_reorder"
    page_id: Id
    panel_ids: list[Id] = Field(max_length=24)


class PageReorder(Contract):
    kind: Literal["page_reorder"] = "page_reorder"
    page_ids: list[Id] = Field(max_length=MAX_PAGES)


class ObjectDelete(Contract):
    kind: Literal["object_delete"] = "object_delete"
    object_id: Id


class PageUpdate(Contract):
    kind: Literal["page_update"] = "page_update"
    page_id: Id
    title: str = Field(min_length=1, max_length=120)
    background: Color
    width: Integer = Field(ge=240, le=2400)
    height: Integer = Field(ge=240, le=2400)


class PanelUpdate(Contract):
    kind: Literal["panel_update"] = "panel_update"
    panel_id: Id
    title: str = Field(min_length=1, max_length=120)
    background: Color


Operation = Annotated[PageCreate | PanelCreate | PanelLayout | ShotSet | CharacterPlace | BubbleCreate |
    CaptionCreate | NoteCreate | ElementUpdate | PanelReorder | PageReorder | ObjectDelete | PageUpdate | PanelUpdate,
    Field(discriminator="kind")]
OPERATIONS = (PageCreate, PanelCreate, PanelLayout, ShotSet, CharacterPlace, BubbleCreate, CaptionCreate,
              NoteCreate, ElementUpdate, PanelReorder, PageReorder, ObjectDelete, PageUpdate, PanelUpdate)


class CreateInput(ToolInputModel):
    title: str = Field(min_length=1, max_length=160)


class VersionInput(ToolInputModel):
    comic_id: Id
    expected_version: Integer = Field(ge=1)


class ApplyInput(VersionInput):
    operation: Operation


class UndoInput(VersionInput):
    target_version: Integer = Field(ge=1)


class PageInput(ToolInputModel):
    offset: Integer = Field(default=0, ge=0, le=16384)
    limit: Integer = Field(default=8, ge=1, le=32)


class InspectInput(PageInput):
    comic_id: Id
    version: Integer | None = Field(default=None, ge=1)
    section: Literal["pages", "panels", "elements", "page"] = "pages"
    object_id: Id | None = None


class DiffInput(PageInput):
    comic_id: Id
    from_version: Integer = Field(ge=1)
    to_version: Integer = Field(ge=1)


class ToolInspectInput(InspectInput):
    section: Literal["pages", "panels", "elements"] = "pages"


class CreateRequest(CreateInput):
    request_id: Id


class ApplyRequest(ApplyInput):
    request_id: Id


class VersionRequest(VersionInput):
    request_id: Id


class UndoRequest(UndoInput):
    request_id: Id


class Summary(Contract):
    id: str
    project_id: str
    title: str
    version: Integer
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["active", "deleted"]
    page_count: Integer
    panel_count: Integer
    element_count: Integer


class Revision(Contract):
    comic: Summary
    parent_version: Integer | None
    document: ComicProject


class MutationResult(ToolOutputModel):
    comic: Summary
    changed: bool


class InspectResult(ToolOutputModel):
    comic: Summary
    items: list[dict]
    total: Integer
    offset: Integer
    next_offset: Integer
    has_more: bool


class ListResult(ToolOutputModel):
    comics: list[Summary]
    total: Integer
    offset: Integer
    next_offset: Integer


class DiffResult(ToolOutputModel):
    comic_id: str
    from_version: Integer
    to_version: Integer
    differences: list[dict]
    total: Integer
    offset: Integer
    next_offset: Integer


class ArtifactResult(ToolOutputModel):
    artifact_id: str
    run_id: str
    session_id: str


class Library(Contract):
    project_id: str


RevisionArtifact = Summary
