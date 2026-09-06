"""One typed Game model; generics resolve local input references once at the boundary."""
from __future__ import annotations

import json
from typing import Annotated, ClassVar, Generic, Literal, TypeVar, Union

from dbfox_dlc_api import BaseModel, ConfigDict, Field
from pydantic import AfterValidator, JsonValue, model_validator

OWNER = "dbfox.game"
LIBRARY = OWNER + ".library"
RESOURCE = OWNER + ".project"
DOCUMENT_ARTIFACT = OWNER + ".project-revision"
REPORT_ARTIFACT = OWNER + ".playtest-report"
ENGINE: Literal["phaser-arcade-4.2.1"] = "phaser-arcade-4.2.1"
MAX_DOCUMENT = 2 * 1024 * 1024
MAX_HISTORY = 256 * 1024 * 1024
MAX_REPORT = 1024 * 1024
MAX_ASSETS = 4 * 1024 * 1024


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def nonempty(value: str) -> str:
    if not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("Name must contain visible text without control characters")
    return value


Id = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
ExternalId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(nonempty)]
Tag = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
Version = Annotated[int, Field(ge=1, le=2**53-1)]
Offset = Annotated[int, Field(ge=0, le=2**31-1)]
Scalar = Annotated[float, Field(ge=-1e9, le=1e9, allow_inf_nan=False)]
Coordinate = Annotated[float, Field(ge=-8192, le=8192, allow_inf_nan=False)]
Speed = Annotated[float, Field(ge=0, le=2000, allow_inf_nan=False)]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$"), AfterValidator(str.lower)]
Value = Union[bool, Annotated[int, Field(ge=-1_000_000_000, le=1_000_000_000)], Scalar]
RefT = TypeVar("RefT")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def optional_null(cls, value: object) -> object:
        # Native strict function schemas require nullable optional members. Only
        # an explicitly declared None default means omission, never arbitrary
        # null coercion for booleans, numbers, required or unknown fields.
        input_generic = cls.__pydantic_generic_metadata__.get("args", ()) == (Selector,)
        if isinstance(value, dict) and (issubclass(cls, Input) or input_generic):
            return {key: item for key, item in value.items() if item is not None or key not in cls.model_fields or cls.model_fields[key].is_required() or cls.model_fields[key].default is not None}
        return value

    def data(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json", exclude_none=True)


class Input(Contract):
    max_bytes: ClassVar[int] = 262144

    @model_validator(mode="before")
    @classmethod
    def nesting_budget(cls, value: object) -> object:
        def check(item: object, depth: int = 0) -> None:
            if depth > 32:
                raise ValueError("Game input nesting exceeds its budget")
            if isinstance(item, dict):
                for nested in item.values():
                    check(nested, depth + 1)
            elif isinstance(item, list):
                for nested in item:
                    check(nested, depth + 1)
        check(value)
        return value

    @model_validator(mode="after")
    def check_budget(self) -> "Input":
        if len(encoded(self.data())) > self.max_bytes:
            raise ValueError("Game input exceeds its byte budget")
        return self


class ById(Input):
    id: Id


class ByRef(Input):
    ref: Tag


Selector = Union[ById, ByRef]


class Point(Contract):
    x: Coordinate
    y: Coordinate


class Region(Point):
    width: Annotated[float, Field(gt=0, le=4096)]
    height: Annotated[float, Field(gt=0, le=4096)]


class Transform(Contract):
    kind: Literal["transform"] = "transform"
    x: Coordinate = 64
    y: Coordinate = 64
    width: Annotated[float, Field(ge=1, le=1024)] = 32
    height: Annotated[float, Field(ge=1, le=1024)] = 32
    angle: Annotated[float, Field(ge=-360, le=360)] = 0


class Visual(Contract, Generic[RefT]):
    kind: Literal["visual"] = "visual"
    shape: Literal["rect", "ellipse", "fox", "slime", "asset"] = "rect"
    asset_id: RefT | None = None
    color: Color = "#f39a42"
    opacity: Annotated[float, Field(ge=0, le=1)] = 1
    depth: Annotated[int, Field(ge=-1000, le=1000)] = 0

    @model_validator(mode="after")
    def asset_source(self) -> "Visual[RefT]":
        if (self.shape == "asset") != (self.asset_id is not None):
            raise ValueError("Only asset visuals require an asset_id")
        return self


class Body(Contract):
    kind: Literal["body"] = "body"
    body_type: Literal["dynamic", "static"] = "dynamic"
    shape: Literal["rectangle", "circle"] = "rectangle"
    vx: Annotated[float, Field(ge=-2000, le=2000)] = 0
    vy: Annotated[float, Field(ge=-2000, le=2000)] = 0
    drag: Annotated[float, Field(ge=0, le=5000)] = 0
    bounce: Annotated[float, Field(ge=0, le=1)] = 0
    world_bounds: bool = True
    solid: bool = False


class Health(Contract):
    kind: Literal["health"] = "health"
    initial: Annotated[int, Field(ge=1, le=1_000_000)] = 1
    maximum: Annotated[int, Field(ge=1, le=1_000_000)] = 1

    @model_validator(mode="after")
    def range_check(self) -> "Health":
        if self.initial > self.maximum:
            raise ValueError("Initial health exceeds maximum")
        return self


ComponentSpec = Annotated[Union[Transform, Visual[Id], Body, Health], Field(discriminator="kind")]
ComponentInputSpec = Annotated[Union[Transform, Visual[Selector], Body, Health], Field(discriminator="kind")]


class Component(Contract):
    id: Id
    spec: ComponentSpec


class SceneSpec(Contract):
    name: Name
    width: Annotated[int, Field(ge=64, le=4096)] = 800
    height: Annotated[int, Field(ge=64, le=4096)] = 600
    background: Color = "#152333"
    gravity_x: Annotated[float, Field(ge=-2000, le=2000)] = 0
    gravity_y: Annotated[float, Field(ge=-2000, le=2000)] = 0


class Scene(SceneSpec):
    id: Id


class Entity(Contract):
    id: Id
    scene_id: Id
    name: Name
    enabled: bool = True
    tags: Annotated[list[Tag], Field(max_length=16)] = Field(default_factory=list)
    components: Annotated[list[Component], Field(min_length=1, max_length=4)]


class Control(Contract, Generic[RefT]):
    kind: Literal["player_control"]
    entity_id: RefT
    speed: Speed = 220


class Seek(Contract, Generic[RefT]):
    kind: Literal["seek"]
    entity_id: RefT
    target_id: RefT
    speed: Speed = 60


class Patrol(Contract, Generic[RefT]):
    kind: Literal["patrol"]
    entity_id: RefT
    waypoints: Annotated[list[Point], Field(min_length=1, max_length=64)]
    speed: Speed = 80
    loop: bool = True


class Wander(Contract, Generic[RefT]):
    kind: Literal["wander"]
    entity_id: RefT
    speed: Speed = 50
    turn_interval_ticks: Annotated[int, Field(ge=1, le=7200)] = 120


class Spawner(Contract, Generic[RefT]):
    kind: Literal["spawn"]
    entity_id: RefT
    template_id: RefT
    interval_ticks: Annotated[int, Field(ge=1, le=7200)] = 180
    count: Annotated[int, Field(ge=1, le=16)] = 1
    max_alive: Annotated[int, Field(ge=1, le=256)] = 16
    region: Region


class Lifetime(Contract, Generic[RefT]):
    kind: Literal["lifetime"]
    entity_id: RefT
    ticks: Annotated[int, Field(ge=1, le=7200)]


BehaviorSpec = Annotated[Union[Control[Id], Seek[Id], Patrol[Id], Wander[Id], Spawner[Id], Lifetime[Id]], Field(discriminator="kind")]
BehaviorInputSpec = Annotated[Union[Control[Selector], Seek[Selector], Patrol[Selector], Wander[Selector], Spawner[Selector], Lifetime[Selector]], Field(discriminator="kind")]


class Behavior(Contract):
    id: Id
    enabled: bool = True
    spec: BehaviorSpec


class VariableSpec(Contract):
    name: Tag
    value_type: Literal["int", "float", "bool"]
    initial: Value

    @model_validator(mode="after")
    def value_check(self) -> "VariableSpec":
        check_value(self.value_type, self.initial)
        if self.value_type == "float":
            self.initial = float(self.initial)
        return self


def check_value(kind: str, value: Value) -> None:
    if kind == "bool" and type(value) is not bool:
        raise ValueError("Boolean variable requires a boolean")
    if kind == "int" and type(value) is not int:
        raise ValueError("Integer variable requires an integer")
    if kind == "float" and type(value) not in (int, float):
        raise ValueError("Float variable requires a number")


class Variable(VariableSpec):
    id: Id


Comparison = Literal["eq", "ne", "lt", "le", "gt", "ge"]


class Elapsed(Contract):
    kind: Literal["elapsed_tick"]
    at_tick: Annotated[int, Field(ge=1, le=7200)]


class Overlap(Contract):
    kind: Literal["overlap"]
    left_tag: Tag
    right_tag: Tag
    phase: Literal["enter", "stay"] = "enter"


class VariableCompare(Contract, Generic[RefT]):
    kind: Literal["variable_compare"]
    variable_id: RefT
    comparison: Comparison = "ge"
    value: Value


class HealthCompare(Contract, Generic[RefT]):
    kind: Literal["health_compare"]
    entity_id: RefT
    comparison: Comparison = "le"
    value: Annotated[int, Field(ge=0, le=1_000_000)] = 0




class Finish(Contract):
    kind: Literal["finish"]
    result: Literal["won", "lost"]
    message: Name = "Game finished"


class VariableSet(Contract, Generic[RefT]):
    kind: Literal["variable_set"]
    variable_id: RefT
    value: Value


class VariableAdd(Contract, Generic[RefT]):
    kind: Literal["variable_add"]
    variable_id: RefT
    amount: Scalar


class Damage(Contract, Generic[RefT]):
    kind: Literal["damage"]
    target: Union[RefT, Literal["left", "right"]]
    amount: Annotated[int, Field(ge=1, le=1_000_000)] = 1


class Despawn(Contract, Generic[RefT]):
    kind: Literal["despawn"]
    target: Union[RefT, Literal["left", "right"]]


class Spawn(Contract, Generic[RefT]):
    kind: Literal["spawn"]
    template_id: RefT
    count: Annotated[int, Field(ge=1, le=16)] = 1
    region: Region


class SceneChange(Contract, Generic[RefT]):
    kind: Literal["scene_change"]
    scene_id: RefT




class RuleSpec(Contract, Generic[RefT]):
    scene_id: RefT
    name: Name
    trigger: Annotated[Union[Elapsed, Overlap, VariableCompare[RefT], HealthCompare[RefT]], Field(discriminator="kind")]
    actions: Annotated[list[Annotated[Union[Finish, VariableSet[RefT], VariableAdd[RefT], Damage[RefT], Despawn[RefT], Spawn[RefT], SceneChange[RefT]], Field(discriminator="kind")]], Field(min_length=1, max_length=16)]


class Rule(Contract):
    id: Id
    enabled: bool = True
    spec: RuleSpec[Id]


class PixelRect(Contract):
    x: Annotated[int, Field(ge=0, le=127)]
    y: Annotated[int, Field(ge=0, le=127)]
    width: Annotated[int, Field(ge=1, le=128)]
    height: Annotated[int, Field(ge=1, le=128)]


class Source(Contract):
    artifact_id: Annotated[str, Field(min_length=1, max_length=128)]
    representation_type: Annotated[str, Field(min_length=1, max_length=128)]
    source_version: Annotated[str, Field(min_length=1, max_length=128)]
    source_fingerprint: Annotated[str, Field(min_length=1, max_length=256)]
    frame_id: ExternalId
    rect: PixelRect


class Asset(Contract):
    id: Id
    name: Name
    width: Annotated[int, Field(ge=1, le=512)]
    height: Annotated[int, Field(ge=1, le=512)]
    format: Literal["rgba8"] = "rgba8"
    content_hash: Hash
    source: Source | None = None


class GameProject(Contract):
    id: Id
    schema_version: Literal[1] = 1
    title: Name
    engine: Literal["phaser-arcade-4.2.1"] = ENGINE
    tick_hz: Literal[60] = 60
    initial_scene_id: Id
    scenes: Annotated[list[Scene], Field(min_length=1, max_length=16)]
    entities: Annotated[list[Entity], Field(max_length=2048)] = Field(default_factory=list)
    behaviors: Annotated[list[Behavior], Field(max_length=2048)] = Field(default_factory=list)
    rules: Annotated[list[Rule], Field(max_length=256)] = Field(default_factory=list)
    variables: Annotated[list[Variable], Field(max_length=128)] = Field(default_factory=list)
    assets: Annotated[list[Asset], Field(max_length=64)] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def integer_literals(cls, value: object) -> object:
        def reject_null(item: object) -> None:
            if item is None:
                raise ValueError("Canonical Game data cannot contain null")
            if isinstance(item, dict):
                for nested in item.values():
                    reject_null(nested)
            elif isinstance(item, list):
                for nested in item:
                    reject_null(nested)
        reject_null(value)
        if isinstance(value, dict):
            for field in ("schema_version", "tick_hz"):
                if field in value and type(value[field]) is not int:
                    raise ValueError(field + " must be an integer")
        return value

    @model_validator(mode="after")
    def validate_graph(self) -> "GameProject":
        from .validation import validate_game
        validate_game(self)
        return self


class Summary(Contract):
    id: Id
    project_id: str
    title: Name
    version: Version
    content_hash: Hash
    deleted: bool
    scene_count: int
    entity_count: int
    rule_count: int


class Revision(Contract):
    game: GameProject
    project_id: str
    version: Version
    library_version: Version
    content_hash: Hash
    deleted: bool

    def summary(self) -> Summary:
        return Summary(id=self.game.id, project_id=self.project_id, title=self.game.title, version=self.version, content_hash=self.content_hash, deleted=self.deleted, scene_count=len(self.game.scenes), entity_count=len(self.game.entities), rule_count=len(self.game.rules))


class LibraryScope(Contract):
    project_id: str
    version: Version


class Mutation(Contract):
    game: Summary
    library_version: Version
    changed: bool
    changed_ids: Annotated[list[Id], Field(max_length=64)] = Field(default_factory=list)
    truncated: bool = False
    created_refs: dict[str, Id] = Field(default_factory=dict)
    report: PlaytestSummary | None = None


class Rename(Input):
    kind: Literal["game_rename"]
    title: Name


class EntryScene(Input):
    kind: Literal["game_entry"]
    scene_id: Selector


class SceneCreate(Input):
    kind: Literal["scene_create"]
    scene: SceneSpec
    ref: Tag | None = None


class SceneModify(Input):
    kind: Literal["scene_modify"]
    scene_id: Selector
    scene: SceneSpec


class Remove(Input):
    kind: Literal["object_remove"]
    object_id: Selector
    cascade: bool = False


class EntityDraft(Input):
    scene_id: Selector
    name: Name
    enabled: bool = True
    tags: Annotated[list[Tag], Field(max_length=16)] = Field(default_factory=list)
    components: Annotated[list[ComponentInputSpec], Field(min_length=1, max_length=4)] = Field(default_factory=lambda: [Transform(), Visual[Selector]()])
    ref: Tag | None = None


class EntityCreate(Input):
    kind: Literal["entity_create"]
    entities: Annotated[list[EntityDraft], Field(min_length=1, max_length=128)]


class EntityModify(Input):
    kind: Literal["entity_modify"]
    entity_id: Selector
    name: Name | None = None
    enabled: bool | None = None
    tags: Annotated[list[Tag], Field(max_length=16)] | None = None
    scene_id: Selector | None = None


class TransformEntities(Input):
    kind: Literal["entities_transform"]
    entity_ids: Annotated[list[Selector], Field(min_length=1, max_length=128)]
    dx: Coordinate = 0
    dy: Coordinate = 0


class DeleteEntities(Input):
    kind: Literal["entity_delete"]
    entity_ids: Annotated[list[Selector], Field(min_length=1, max_length=128)]
    cascade: bool = False


class ComponentAdd(Input):
    kind: Literal["component_add"]
    entity_id: Selector
    component: ComponentInputSpec
    ref: Tag | None = None


class ComponentModify(Input):
    kind: Literal["component_modify"]
    component_id: Selector
    component: ComponentInputSpec


class BehaviorCreate(Input):
    kind: Literal["behavior_create"]
    behavior: BehaviorInputSpec
    enabled: bool = True
    ref: Tag | None = None


class BehaviorModify(Input):
    kind: Literal["behavior_modify"]
    behavior_id: Selector
    behavior: BehaviorInputSpec
    enabled: bool = True


class RuleCreate(Input):
    kind: Literal["rule_create"]
    rule: RuleSpec[Selector]
    enabled: bool = True
    ref: Tag | None = None


class RuleModify(Input):
    kind: Literal["rule_modify"]
    rule_id: Selector
    rule: RuleSpec[Selector]
    enabled: bool = True


class RuleReorder(Input):
    kind: Literal["rule_reorder"]
    rule_ids: Annotated[list[Selector], Field(max_length=256)]


class VariableCreate(Input):
    kind: Literal["variable_create"]
    variable: VariableSpec
    ref: Tag | None = None


class VariableModify(Input):
    kind: Literal["variable_modify"]
    variable_id: Selector
    variable: VariableSpec


Operation = Annotated[Union[Rename, EntryScene, SceneCreate, SceneModify, Remove, EntityCreate, EntityModify, TransformEntities, DeleteEntities, ComponentAdd, ComponentModify, BehaviorCreate, BehaviorModify, RuleCreate, RuleModify, RuleReorder, VariableCreate, VariableModify], Field(discriminator="kind")]


class CreateInput(Input):
    title: Name
    expected_library_version: Version


class CreateRequest(CreateInput):
    request_id: Id


class VersionInput(Input):
    game_id: Id
    expected_version: Version


class VersionRequest(VersionInput):
    request_id: Id


class ApplyInput(VersionInput):
    operations: Annotated[list[Operation], Field(min_length=1, max_length=64)]


class ApplyRequest(ApplyInput):
    request_id: Id


class UndoInput(VersionInput):
    target_version: Version


class UndoRequest(UndoInput):
    request_id: Id


class PageInput(Input):
    offset: Offset = 0
    limit: Annotated[int, Field(ge=1, le=50)] = 20


class HeadInput(Input):
    game_id: Id


class ListInput(PageInput):
    version: Version | None = None


class HeadOutput(Contract):
    game: Summary
    library_version: Version


class ViewParameters(Input):
    section: Literal["summary", "scenes", "entities", "components", "behaviors", "rules", "variables", "assets", "asset_bytes"] = "summary"
    scene_id: Id | None = None
    entity_id: Id | None = None
    asset_id: Id | None = None
    offset: Offset = 0
    limit: Annotated[int, Field(ge=1, le=16384)] = 20


class GetInput(HeadInput, ViewParameters):
    version: Version | None = None


class HistoryInput(HeadInput, PageInput):
    version: Version


class DiffInput(HeadInput, PageInput):
    from_version: Version
    to_version: Version


class UploadInput(VersionInput):
    max_bytes: ClassVar[int] = 1572864
    name: Name
    width: Annotated[int, Field(ge=1, le=512)]
    height: Annotated[int, Field(ge=1, le=512)]
    rgba_base64: Annotated[str, Field(max_length=1_398_104)]


class UploadRequest(UploadInput):
    request_id: Id


class ImportInput(VersionInput):
    name: Name
    source_artifact_id: Annotated[str, Field(min_length=1, max_length=128)]
    frame_id: ExternalId
    rect: PixelRect


class PixelFramePage(Contract):
    frame_id: ExternalId
    rect: PixelRect
    rgba: Annotated[list[Annotated[int, Field(ge=0, le=255)]], Field(max_length=4096)]


class InputEvent(Input):
    tick: Annotated[int, Field(ge=0, le=7199)]
    entity_id: Id
    actions: Annotated[list[Literal["up", "down", "left", "right"]], Field(max_length=4)]


class PlaytestInput(VersionInput):
    ticks: Annotated[int, Field(ge=1, le=7200)] = 3600
    seed: Annotated[int, Field(ge=0, le=2**31-1)] = 1
    inputs: Annotated[list[InputEvent], Field(max_length=1024)] = Field(default_factory=list)

    @model_validator(mode="after")
    def input_order(self) -> "PlaytestInput":
        keys = [(item.tick, item.entity_id) for item in self.inputs]
        if keys != sorted(set(keys)) or any(item.tick >= self.ticks or len(set(item.actions)) != len(item.actions) for item in self.inputs):
            raise ValueError("Inputs must be unique, ordered by tick/entity and within requested ticks")
        return self


class PlaytestRequest(PlaytestInput):
    request_id: Id


class Page(Contract):
    section: str
    game: Summary | None = None
    library_version: Version
    offset: Offset
    next_offset: Offset
    total: Offset
    has_more: bool
    items: list[dict[str, JsonValue]] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ArtifactLocator(Contract):
    project_id: str
    game_id: Id
    version: Version
    content_hash: Hash
    title: Name
    report_id: Id | None = None


class ActionResult(Contract):
    session_id: str
    run_id: str
    artifact_ids: list[str]
    outcome: dict[str, JsonValue]


class SceneCreateInput(VersionInput):
    operation: SceneCreate


class EntityCreateInput(VersionInput):
    operation: EntityCreate


class EntityDeleteInput(VersionInput):
    operation: DeleteEntities


class ComponentAddInput(VersionInput):
    operation: ComponentAdd


class ComponentModifyInput(VersionInput):
    operation: ComponentModify


class BehaviorCreateInput(VersionInput):
    operation: BehaviorCreate


class RuleCreateInput(VersionInput):
    operation: RuleCreate


class VariableCreateInput(VersionInput):
    operation: VariableCreate


RuntimeId = Annotated[str, Field(max_length=64, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?::[1-9][0-9]{0,6})?$")]


class GameEvent(Contract):
    tick: Annotated[int, Field(ge=0, le=7200)]
    scene_id: Id
    kind: Literal["overlap", "spawn", "despawn", "damage", "variable", "scene_change", "ignored_scene_change", "finish", "budget_exceeded"]
    detail: Annotated[str, Field(max_length=256)]
    entity_ids: Annotated[list[RuntimeId], Field(max_length=2)] = Field(default_factory=list)


class FinalEntity(Contract):
    id: RuntimeId
    template_id: Id
    scene_id: Id
    x: Scalar
    y: Scalar
    vx: Scalar
    vy: Scalar
    health: Annotated[int, Field(ge=0, le=1_000_000)] | None = None


class SimulationReport(Contract):
    engine: Literal["phaser-arcade-4.2.1"]
    seed: Annotated[int, Field(ge=0, le=2**31-1)]
    ticks_requested: Annotated[int, Field(ge=1, le=7200)]
    ticks_completed: Annotated[int, Field(ge=0, le=7200)]
    scene_tick: Annotated[int, Field(ge=0, le=7200)]
    scene_id: Id
    outcome: Literal["won", "lost", "exhausted", "budget_exceeded"]
    reason: Name
    event_count: Annotated[int, Field(ge=0, le=1_000_000)]
    events_truncated: bool
    events: Annotated[list[GameEvent], Field(max_length=1024)]
    entities: Annotated[list[FinalEntity], Field(max_length=512)]
    variables: Annotated[dict[Id, Value], Field(max_length=128)]

    @model_validator(mode="after")
    def coherent(self) -> "SimulationReport":
        if self.ticks_completed > self.ticks_requested or self.scene_tick > self.ticks_completed:
            raise ValueError("Report tick counters are inconsistent")
        if self.outcome == "exhausted" and self.ticks_completed != self.ticks_requested:
            raise ValueError("Exhausted report must complete all requested ticks")
        if self.event_count < len(self.events) or self.events_truncated != (self.event_count > len(self.events)):
            raise ValueError("Event truncation counters are inconsistent")
        if len({item.id for item in self.entities}) != len(self.entities):
            raise ValueError("Runtime entity IDs must be unique")
        if any(item.tick > self.ticks_completed for item in self.events) or any(left.tick > right.tick for left, right in zip(self.events, self.events[1:])):
            raise ValueError("Events must be ordered and within completed ticks")
        if len(encoded(self.data())) > MAX_REPORT:
            raise ValueError("Playtest report exceeds 1 MiB")
        return self


class PlaytestSummary(Contract):
    id: Id
    engine: Literal["phaser-arcade-4.2.1"]
    seed: int
    ticks_requested: int
    ticks_completed: int
    outcome: Literal["won", "lost", "exhausted", "budget_exceeded"]
    reason: Name
    event_count: int
    events_truncated: bool
    entity_count: int


class ReportParameters(PageInput):
    section: Literal["summary", "events", "entities", "variables"] = "summary"


class AttachInput(Input):
    client_id: Id
    registration_counter: Version
    package_digest: Hash
    engine: Literal["phaser-arcade-4.2.1"]
    available: bool


class Lease(Input):
    epoch: Id
    lease: Id
    registration_counter: Version


class Attachment(Contract):
    epoch: Id
    lease: Id
    registration_counter: Version
    available: bool
    lease_ms: Literal[5000] = 5000


class Proof(Contract):
    request_id: Id
    invocation_id: Annotated[str, Field(min_length=1, max_length=128)]
    game_id: Id
    version: Version
    source_hash: Hash
    input_hash: Hash
    claim_id: Id


class ComputeRequest(Proof):
    remaining_ms: Annotated[int, Field(ge=1, le=20000)]
    input: PlaytestInput
    snapshot: dict[str, JsonValue]


class PollOutput(Contract):
    status: Literal["idle", "request"]
    request: ComputeRequest | None = None


class CompleteInput(Lease, Proof):
    max_bytes: ClassVar[int] = 1100000
    package_digest: Hash
    report: SimulationReport | None = None
    error: Literal["ENGINE_UNAVAILABLE", "ENGINE_FAILURE", "DEADLINE_EXCEEDED", "CANCELLED"] | None = None

    @model_validator(mode="after")
    def one_outcome(self) -> "CompleteInput":
        if (self.report is None) == (self.error is None):
            raise ValueError("Provide exactly one report or execution error")
        return self


class Acknowledged(Contract):
    accepted: bool


Mutation.model_rebuild()
