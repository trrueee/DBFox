"""Canonical Scene schema and the shared Human/Agent operation contract."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from dbfox_dlc_api import BaseModel, ConfigDict, Field, ToolInputModel, ToolOutputModel
from pydantic import model_validator

OWNER = "dbfox.scene"
LIBRARY_KIND = "dbfox.scene.library"
SCENE_KIND = "dbfox.scene.document"
ARTIFACT_TYPE = "dbfox.scene.revision"
REPRESENTATION_TYPE = "dbfox.scene.document.v1"
MAX_OBJECTS = 10_000
MAX_MATERIALS = 1_000
MAX_BATCH = 500
MAX_PAGE = 100
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_EXPORT_BYTES = 32 * 1024 * 1024

Integer = Annotated[int, Field(strict=True)]
Boolean = Annotated[bool, Field(strict=True)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]

Identifier = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")]
Unit = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Coordinate = Annotated[float, Field(strict=True, ge=-1_000_000, le=1_000_000, allow_inf_nan=False)]
Angle = Annotated[float, Field(strict=True, ge=-math.tau * 100, le=math.tau * 100, allow_inf_nan=False)]
Scale = Annotated[float, Field(strict=True, ge=0.0001, le=100_000, allow_inf_nan=False)]
Position = tuple[Coordinate, Coordinate, Coordinate]
Rotation = tuple[Angle, Angle, Angle]
Scaling = tuple[Scale, Scale, Scale]
Primitive = Literal["box", "sphere", "cylinder", "cone", "plane", "torus"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, validate_default=True)


class Geometry(Contract):
    id: Identifier
    primitive: Primitive


class Material(Contract):
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    base_color: tuple[Unit, Unit, Unit, Unit] = (0.65, 0.65, 0.65, 1)
    metallic: Unit = 0
    roughness: Unit = 0.6
    double_sided: Boolean = False


class Node(Contract):
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    parent_id: Identifier | None = None
    position: Position = (0, 0, 0)
    rotation: Rotation = (0, 0, 0)
    scale: Scaling = (1, 1, 1)
    visible: Boolean = True


class Mesh(Node):
    kind: Literal["mesh"] = "mesh"
    geometry_id: Identifier = "geometry.box"
    material_id: Identifier | None = None


class Group(Node):
    kind: Literal["group"] = "group"


class Light(Node):
    kind: Literal["light"] = "light"
    light_type: Literal["point", "directional", "spot"] = "point"
    color: tuple[Unit, Unit, Unit] = (1, 1, 1)
    intensity: Number = Field(default=1, ge=0, le=1_000_000, allow_inf_nan=False)
    range: Number | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)
    inner_cone_angle: Number = Field(default=0, ge=0, le=math.pi / 2, allow_inf_nan=False)
    outer_cone_angle: Number = Field(default=math.pi / 4, gt=0, le=math.pi / 2, allow_inf_nan=False)

    @model_validator(mode="after")
    def cones(self) -> Light:
        if self.inner_cone_angle >= self.outer_cone_angle:
            raise ValueError("Light inner cone must be smaller than outer cone")
        return self


class Camera(Node):
    kind: Literal["camera"] = "camera"
    yfov: Number = Field(default=math.pi / 3, gt=0.01, lt=math.pi, allow_inf_nan=False)
    znear: Number = Field(default=0.01, gt=0, le=100_000, allow_inf_nan=False)
    zfar: Number = Field(default=1000, gt=0, le=1_000_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def clipping(self) -> Camera:
        if self.zfar <= self.znear:
            raise ValueError("Camera far plane must exceed near plane")
        return self


SceneObject = Annotated[Mesh | Group | Light | Camera, Field(discriminator="kind")]


class Settings(Contract):
    background: tuple[Unit, Unit, Unit] = (0.025, 0.03, 0.04)
    default_camera_id: Identifier | None = None


def primitive_catalog() -> list[Geometry]:
    return [Geometry(id=f"geometry.{kind}", primitive=kind) for kind in
            ("box", "sphere", "cylinder", "cone", "plane", "torus")]


class SceneDocument(Contract):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    title: str = Field(min_length=1, max_length=160)
    settings: Settings = Field(default_factory=Settings)
    geometries: list[Geometry] = Field(default_factory=primitive_catalog, max_length=6)
    materials: list[Material] = Field(default_factory=list, max_length=MAX_MATERIALS)
    objects: list[SceneObject] = Field(default_factory=list, max_length=MAX_OBJECTS)

    @model_validator(mode="after")
    def invariants(self) -> SceneDocument:
        entities = [*self.geometries, *self.materials, *self.objects]
        ids = [entity.id for entity in entities]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene entity IDs must be unique")
        if self.geometries != primitive_catalog():
            raise ValueError("Geometry catalog must be the fixed primitive catalog")
        geometries = {item.id for item in self.geometries}
        materials = {item.id for item in self.materials}
        nodes = {item.id: item for item in self.objects}
        for node in self.objects:
            if node.parent_id is not None and node.parent_id not in nodes:
                raise ValueError("Parent does not exist in this scene")
            if isinstance(node, Mesh) and (node.geometry_id not in geometries or
                    (node.material_id is not None and node.material_id not in materials)):
                raise ValueError("Mesh geometry or material does not exist")
            seen: set[str] = set()
            current: Node | None = node
            max_log_scale = 0.0
            min_log_scale = 0.0
            # A conservative spectral-norm bound avoids implementing a second matrix engine.
            translation_bound = 0.0
            while current is not None:
                if current.id in seen or len(seen) >= 64:
                    raise ValueError("Hierarchy has a cycle or exceeds depth 64")
                seen.add(current.id)
                max_log_scale += math.log(max(current.scale))
                min_log_scale += math.log(min(current.scale))
                translation_bound = math.sqrt(sum(value * value for value in current.position)) + max(current.scale) * translation_bound
                if not math.isfinite(translation_bound) or translation_bound > 1e12:
                    raise ValueError("World translation exceeds the supported numeric range")
                current = nodes.get(current.parent_id) if current.parent_id else None
            if max_log_scale > math.log(1e9) or min_log_scale < math.log(1e-9):
                raise ValueError("Hierarchy scale composition exceeds the supported numeric range")
        camera = self.settings.default_camera_id
        if camera is not None and not isinstance(nodes.get(camera), Camera):
            raise ValueError("Default camera must identify a camera in this scene")
        return self


class CreateObjects(Contract):
    kind: Literal["object_create"] = "object_create"
    objects: list[SceneObject] = Field(min_length=1, max_length=MAX_BATCH)


class TransformItem(Contract):
    object_id: Identifier
    position: Position | None = None
    rotation: Rotation | None = None
    scale: Scaling | None = None

    @model_validator(mode="after")
    def nonempty(self) -> TransformItem:
        if self.position is None and self.rotation is None and self.scale is None:
            raise ValueError("Transform must specify position, rotation or scale")
        return self


class TransformObjects(Contract):
    kind: Literal["object_transform"] = "object_transform"
    transforms: list[TransformItem] = Field(min_length=1, max_length=MAX_BATCH)


class DuplicateObjects(Contract):
    kind: Literal["object_duplicate"] = "object_duplicate"
    object_ids: list[Identifier] = Field(min_length=1, max_length=MAX_BATCH)
    include_subtree: Boolean = False
    offset: Position = (1, 0, 0)


class DeleteObjects(Contract):
    kind: Literal["object_delete"] = "object_delete"
    object_ids: list[Identifier] = Field(min_length=1, max_length=MAX_BATCH)
    include_subtree: Boolean = False


class ReparentObjects(Contract):
    kind: Literal["object_reparent"] = "object_reparent"
    object_ids: list[Identifier] = Field(min_length=1, max_length=MAX_BATCH)
    parent_id: Identifier | None = None


class UpdateObject(Contract):
    kind: Literal["object_update"] = "object_update"
    object_id: Identifier
    name: str | None = Field(default=None, min_length=1, max_length=120)
    visible: Boolean | None = None


class CreateMaterial(Contract):
    kind: Literal["material_create"] = "material_create"
    material: Material


class UpdateMaterial(Contract):
    kind: Literal["material_update"] = "material_update"
    material: Material


class AssignMaterial(Contract):
    kind: Literal["material_assign"] = "material_assign"
    object_ids: list[Identifier] = Field(min_length=1, max_length=MAX_BATCH)
    material_id: Identifier | None = None


class CreateLight(Contract):
    kind: Literal["light_create"] = "light_create"
    light: Light


class CreateCamera(Contract):
    kind: Literal["camera_create"] = "camera_create"
    camera: Camera


class UpdateLight(Contract):
    kind: Literal["light_update"] = "light_update"
    light_id: Identifier
    color: tuple[Unit, Unit, Unit] | None = None
    intensity: Number | None = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    range: Number | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)
    clear_range: Boolean = False
    inner_cone_angle: Number | None = Field(default=None, ge=0, le=math.pi / 2, allow_inf_nan=False)
    outer_cone_angle: Number | None = Field(default=None, gt=0, le=math.pi / 2, allow_inf_nan=False)

    @model_validator(mode="after")
    def patch(self) -> UpdateLight:
        fields = self.model_fields_set - {"kind", "light_id", "clear_range"}
        if (not fields and not self.clear_range) or any(getattr(self, name) is None for name in fields):
            raise ValueError("Light update requires changed fields; use clear_range to remove range")
        if self.clear_range and self.range is not None:
            raise ValueError("Cannot set and clear light range together")
        return self


class UpdateCamera(Contract):
    kind: Literal["camera_update"] = "camera_update"
    camera_id: Identifier
    yfov: Number | None = Field(default=None, gt=0.01, lt=math.pi, allow_inf_nan=False)
    znear: Number | None = Field(default=None, gt=0, le=100_000, allow_inf_nan=False)
    zfar: Number | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def patch(self) -> UpdateCamera:
        fields = self.model_fields_set - {"kind", "camera_id"}
        if not fields or any(getattr(self, name) is None for name in fields):
            raise ValueError("Camera update requires valid changed fields")
        return self


class UpdateSettings(Contract):
    kind: Literal["scene_settings_update"] = "scene_settings_update"
    settings: Settings
    title: str | None = Field(default=None, min_length=1, max_length=160)


Operation = Annotated[
    CreateObjects | TransformObjects | DuplicateObjects | DeleteObjects | ReparentObjects |
    UpdateObject | CreateMaterial | UpdateMaterial | AssignMaterial | CreateLight |
    CreateCamera | UpdateLight | UpdateCamera | UpdateSettings, Field(discriminator="kind")]


class CreateInput(ToolInputModel):
    title: str = Field(min_length=1, max_length=160)


class CreateRequest(CreateInput):
    request_id: Identifier


class MutationInput(ToolInputModel):
    scene_id: Identifier
    expected_version: Integer = Field(ge=1, strict=True)
    operation: Operation


class MutationRequest(MutationInput):
    request_id: Identifier


class VersionInput(ToolInputModel):
    scene_id: Identifier
    expected_version: Integer = Field(ge=1, strict=True)


class VersionRequest(VersionInput):
    request_id: Identifier


class UndoInput(VersionInput):
    target_version: Integer = Field(ge=1, strict=True)


class UndoRequest(UndoInput):
    request_id: Identifier


class PageInput(ToolInputModel):
    offset: Integer = Field(default=0, ge=0, le=MAX_OBJECTS, strict=True)
    limit: Integer = Field(default=100, ge=1, le=MAX_PAGE, strict=True)


class InspectInput(PageInput):
    scene_id: Identifier
    version: Integer | None = Field(default=None, ge=1, strict=True)
    section: Literal["objects", "materials", "geometries"] = "objects"


class DiffInput(PageInput):
    scene_id: Identifier
    from_version: Integer = Field(ge=1, strict=True)
    to_version: Integer = Field(ge=1, strict=True)


class SceneSummary(Contract):
    id: str
    project_id: str
    title: str
    version: Integer
    content_hash: str
    status: Literal["active", "deleted"] = "active"
    object_count: Integer
    material_count: Integer
    created_at: str
    updated_at: str


class Revision(Contract):
    scene: SceneSummary
    parent_version: Integer | None
    document: SceneDocument


class MutationResult(ToolOutputModel):
    scene: SceneSummary
    changed: Boolean
    changed_ids: list[str] = Field(default_factory=list, max_length=MAX_PAGE)
    truncated: Boolean = False


class PageResult(ToolOutputModel):
    scene: SceneSummary
    settings: Settings
    objects: list[SceneObject] = Field(default_factory=list, max_length=MAX_PAGE)
    materials: list[Material] = Field(default_factory=list, max_length=MAX_PAGE)
    geometries: list[Geometry] = Field(default_factory=list, max_length=MAX_PAGE)
    total: Integer
    offset: Integer
    limit: Integer


class ListResult(ToolOutputModel):
    scenes: list[SceneSummary] = Field(max_length=MAX_PAGE)
    total: Integer
    offset: Integer
    limit: Integer


class Difference(Contract):
    id: str
    entity: Literal["object", "material", "settings", "title"]
    change: Literal["added", "deleted", "modified"]
    fields: list[str]


class DiffResult(ToolOutputModel):
    scene_id: str
    from_version: Integer
    to_version: Integer
    differences: list[Difference] = Field(max_length=MAX_PAGE)
    total: Integer
    offset: Integer
    limit: Integer


class RevisionArtifact(Contract):
    scene_id: str
    project_id: str
    version: Integer = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(max_length=160)
    object_count: Integer = Field(ge=0, le=MAX_OBJECTS)
    material_count: Integer = Field(ge=0, le=MAX_MATERIALS)


class ArtifactResult(ToolOutputModel):
    artifact_id: str
    run_id: str
    session_id: str


class Library(Contract):
    project_id: str
