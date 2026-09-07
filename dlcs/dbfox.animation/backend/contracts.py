"""Durable Animation contracts. Integer millisecond time; scalar local TRS tracks."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

OWNER = "dbfox.animation"
DOCUMENT_KIND = "dbfox.animation.document"
LIBRARY_KIND = "dbfox.animation.library"
ARTIFACT_TYPE = "dbfox.animation.revision"
REPRESENTATION_TYPE = "dbfox.animation.document.v1"
MAX_BYTES = 16 * 1024 * 1024
Id = Annotated[str, Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Tick = Annotated[int, Field(strict=True, ge=0, le=3_600_000)]
Value = Annotated[float, Field(allow_inf_nan=False, ge=-1_000_000, le=1_000_000)]
Name = Annotated[str, Field(min_length=1, max_length=120)]
Section = Literal["targets", "tracks", "keyframes", "curves", "clips", "markers"]
Property = Literal["position.x", "position.y", "position.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y", "scale.z"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True, allow_inf_nan=False)


class Timing(Contract):
    duration: Tick = 8000
    fps: Literal[24, 25, 30, 48, 50, 60, 120] = 30
    rate: float = Field(default=1, ge=0.1, le=4)
    loop: bool = False

    @model_validator(mode="after")
    def positive(self):
        if self.duration < 1:
            raise ValueError("duration must be positive")
        return self


class SceneBinding(Contract):
    artifact_id: Id
    scene_id: Id
    version: int = Field(strict=True, ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_id: Id


class Target(Contract):
    id: Id
    name: Name
    position: tuple[Value, Value, Value] = (0, 0, 0)
    rotation: tuple[Value, Value, Value] = (0, 0, 0)
    scale: tuple[Value, Value, Value] = (1, 1, 1)
    source: SceneBinding | None = None


class Track(Contract):
    id: Id
    name: Name
    target_id: Id
    property: Property
    enabled: bool = True


class Curve(Contract):
    id: Id
    kind: Literal["linear", "hold", "bezier"] = "linear"
    x1: float = Field(default=1 / 3, ge=0, le=1)
    y1: float = Field(default=1 / 3, ge=-4, le=4)
    x2: float = Field(default=2 / 3, ge=0, le=1)
    y2: float = Field(default=2 / 3, ge=-4, le=4)

    @model_validator(mode="after")
    def monotonic(self):
        if self.x1 > self.x2:
            raise ValueError("Bezier control times must be monotone: x1 <= x2")
        return self


class Keyframe(Contract):
    id: Id
    track_id: Id
    tick: Tick
    value: Value
    curve_id: Id | None = None


class Clip(Contract):
    id: Id
    name: Name
    track_ids: list[Id] = Field(min_length=1, max_length=128)
    start: Tick
    end: Tick

    @model_validator(mode="after")
    def window(self):
        if self.start >= self.end or len(set(self.track_ids)) != len(self.track_ids):
            raise ValueError("Clip needs a nonempty window and unique tracks")
        return self


class Marker(Contract):
    id: Id
    name: Name
    tick: Tick


class Document(Contract):
    schema_version: Literal[1] = 1
    title: Name
    timing: Timing = Field(default_factory=Timing)
    targets: list[Target] = Field(default_factory=list, max_length=1000)
    tracks: list[Track] = Field(default_factory=list, max_length=500)
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=20000)
    curves: list[Curve] = Field(default_factory=list, max_length=20000)
    clips: list[Clip] = Field(default_factory=list, max_length=1000)
    markers: list[Marker] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def references(self):
        ids = [item.id for section in SECTIONS for item in getattr(self, section)]
        if len(ids) != len(set(ids)):
            raise ValueError("Entity IDs must be globally unique")
        targets = {item.id for item in self.targets}
        tracks = {item.id for item in self.tracks}
        curves = {item.id for item in self.curves}
        bindings = [(item.target_id, item.property) for item in self.tracks]
        if len(bindings) != len(set(bindings)) or any(item.target_id not in targets for item in self.tracks):
            raise ValueError("Track targets must exist and properties must be unique per target")
        times = [(item.track_id, item.tick) for item in self.keyframes]
        if len(times) != len(set(times)):
            raise ValueError("Two keys cannot occupy the same track time")
        for item in self.keyframes:
            if item.track_id not in tracks or item.tick > self.timing.duration or (item.curve_id is not None and item.curve_id not in curves):
                raise ValueError("Invalid key track, curve or duration")
        if any(item.tick > self.timing.duration for item in self.markers):
            raise ValueError("Marker outside duration")
        if any(item.end > self.timing.duration or not set(item.track_ids) <= tracks for item in self.clips):
            raise ValueError("Invalid clip tracks or duration")
        return self


SECTIONS = ("targets", "tracks", "keyframes", "curves", "clips", "markers")


class TargetCreate(Contract):
    kind: Literal["target_create"] = "target_create"
    target: Target

    @model_validator(mode="after")
    def local(self):
        if self.target.source is not None:
            raise ValueError("Scene sources require the authorized scene_bind tool")
        return self


class TrackCreate(Contract):
    kind: Literal["track_create"] = "track_create"
    track: Track


class TrackModify(Contract):
    kind: Literal["track_modify"] = "track_modify"
    track: Track


class KeyframeAdd(Contract):
    kind: Literal["keyframe_add"] = "keyframe_add"
    keyframes: list[Keyframe] = Field(min_length=1, max_length=256)


class KeyMove(Contract):
    id: Id
    tick: Tick
    value: Value


class KeyframeMove(Contract):
    kind: Literal["keyframe_move"] = "keyframe_move"
    keyframes: list[KeyMove] = Field(min_length=1, max_length=256)


class EasingSet(Contract):
    kind: Literal["easing_set"] = "easing_set"
    curve: Curve
    keyframe_ids: list[Id] = Field(min_length=1, max_length=256)


class ClipCreate(Contract):
    kind: Literal["clip_create"] = "clip_create"
    clip: Clip


class ClipTrim(Contract):
    kind: Literal["clip_trim"] = "clip_trim"
    clip_id: Id
    start: Tick
    end: Tick


class ClipModify(Contract):
    kind: Literal["clip_modify"] = "clip_modify"
    clip: Clip


class TimingModify(Contract):
    kind: Literal["timing_modify"] = "timing_modify"
    timing: Timing


class MarkerSet(Contract):
    kind: Literal["marker_set"] = "marker_set"
    marker: Marker


class EntityDelete(Contract):
    kind: Literal["entity_delete"] = "entity_delete"
    section: Section
    ids: list[Id] = Field(min_length=1, max_length=256)
    cascade: bool = False


class Rename(Contract):
    kind: Literal["animation_rename"] = "animation_rename"
    title: Name


Operation = Annotated[TargetCreate | TrackCreate | TrackModify | KeyframeAdd | KeyframeMove | EasingSet | ClipCreate | ClipTrim | ClipModify | TimingModify | MarkerSet | EntityDelete | Rename, Field(discriminator="kind")]
OPERATIONS = (TargetCreate, TrackCreate, TrackModify, KeyframeAdd, KeyframeMove, EasingSet, ClipCreate, ClipTrim, ClipModify, TimingModify, MarkerSet, EntityDelete, Rename)


class CreateInput(Contract):
    title: Name


class VersionInput(Contract):
    animation_id: Id
    expected_version: int = Field(strict=True, ge=1)


class MutationInput(VersionInput):
    operation: Operation


class UndoInput(VersionInput):
    target_version: int = Field(strict=True, ge=1)


class BindInput(VersionInput):
    artifact_id: Id
    object_ids: list[Id] = Field(min_length=1, max_length=100)


class PageInput(Contract):
    offset: int = Field(default=0, strict=True, ge=0, le=100000)
    limit: int = Field(default=100, strict=True, ge=1, le=100)


class InspectInput(PageInput):
    animation_id: Id
    version: int | None = Field(default=None, strict=True, ge=1)
    section: Section = "tracks"
    track_id: Id | None = None


class DiffInput(PageInput):
    animation_id: Id
    from_version: int = Field(strict=True, ge=1)
    to_version: int = Field(strict=True, ge=1)


class Summary(Contract):
    id: Id
    project_id: str
    title: Name
    version: int = Field(strict=True, ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["active", "deleted"] = "active"
    counts: dict[str, int]


class Revision(Contract):
    animation: Summary
    document: Document


class MutationResult(Contract):
    animation: Summary
    changed: bool
    changed_ids: list[str] = Field(default_factory=list, max_length=100)
    truncated: bool = False


class PageResult(Contract):
    animation: Summary
    timing: Timing
    section: Section
    items: list[Target | Track | Keyframe | Curve | Clip | Marker]
    offset: int
    total: int
    next_offset: int
    has_more: bool


class ListResult(Contract):
    animations: list[Summary]
    total: int


class Difference(Contract):
    section: str
    id: str
    change: Literal["added", "removed", "modified"]
    fields: list[str]


class DiffResult(Contract):
    differences: list[Difference]
    total: int
    next_offset: int
    has_more: bool


class Library(Contract):
    project_id: str


class RevisionArtifact(Contract):
    animation_id: Id
    project_id: str
    version: int = Field(strict=True, ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: Name


class CreateRequest(CreateInput):
    request_id: Id


class MutationRequest(MutationInput):
    request_id: Id


class UndoRequest(UndoInput):
    request_id: Id


class VersionRequest(VersionInput):
    request_id: Id


class ArtifactResult(Contract):
    artifact_id: str
    run_id: str
    session_id: str
