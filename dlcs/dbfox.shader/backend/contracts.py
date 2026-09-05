"""Strict canonical and public wire contracts for Shader Studio v1."""
from __future__ import annotations

import json
from typing import Annotated, Literal, Union

from dbfox_dlc_api import BaseModel, ConfigDict, Field
from pydantic import AfterValidator, JsonValue, model_validator

OWNER = "dbfox.shader"
STUDIO_KIND = OWNER + ".studio"
DOCUMENT_ARTIFACT = OWNER + ".document-revision"
REPORT_ARTIFACT = OWNER + ".compile-report"
PREVIEW_ARTIFACT = OWNER + ".preview"
MAX_DOCUMENT = 1_048_576
MAX_HISTORY = 256 * 1024 * 1024
MAX_REPORT = 262_144
MAX_RECEIPT = 32_768


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def title_check(value: str) -> str:
    if not value.strip():
        raise ValueError("Title must contain non-whitespace characters")
    return value


def name_check(value: str) -> str:
    if value.startswith("gl_") or value in {"u_resolution", "u_time"}:
        raise ValueError("Reserved GLSL binding name")
    return value


def source_check(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = value.split("\n")
    if len(value.encode("utf-8")) > 262_144 or len(lines) > 16_384 or any(len(line.encode("utf-8")) > 2048 for line in lines):
        raise ValueError("Stage source budget exceeded")
    return value


Id = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Token = Hash
Title = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(title_check)]
Name = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"), AfterValidator(name_check)]
LocalRef = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
Source = Annotated[str, Field(max_length=262_144), AfterValidator(source_check)]
Nonnegative = Annotated[int, Field(ge=0, le=2**53 - 1)]
Version = Annotated[int, Field(ge=1, le=2**53 - 1)]
Dimension = Annotated[int, Field(ge=1, le=512)]
PreviewDimension = Annotated[int, Field(ge=1, le=256)]
Component = Annotated[float, Field(ge=-1e6, le=1e6, allow_inf_nan=False)]
Color = Annotated[list[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]], Field(min_length=4, max_length=4)]
UniformType = Literal["float", "int", "bool", "vec2", "vec3", "vec4", "mat2", "mat3", "mat4"]
UniformValue = Union[bool, Annotated[int, Field(ge=-(2**31), le=2**31-1)], Component, Annotated[list[Component], Field(min_length=2, max_length=16)]]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Input(Contract):
    @model_validator(mode="before")
    @classmethod
    def no_explicit_null(cls, value: object) -> object:
        def check(item: object) -> None:
            if item is None:
                raise ValueError("Omit optional fields; explicit null is not supported")
            if isinstance(item, dict):
                for nested in item.values():
                    check(nested)
            elif isinstance(item, list):
                for nested in item:
                    check(nested)
        check(value)
        return value


class ObjectId(Input):
    id: Id


class ObjectRef(Input):
    ref: LocalRef


ObjectSelector = Union[ObjectId, ObjectRef]


class Stage(Contract):
    id: Id
    kind: Literal["vertex", "fragment"]
    title: Title
    source: Source


class TextureSource(Contract):
    kind: Literal["texture"]
    texture_id: Id


class PassSource(Contract):
    kind: Literal["pass"]
    pass_id: Id


BindingSource = Annotated[Union[TextureSource, PassSource], Field(discriminator="kind")]


class Binding(Contract):
    name: Name
    source: BindingSource
    filter: Literal["nearest", "linear"] = "nearest"
    wrap: Literal["clamp"] = "clamp"


class Pass(Contract):
    id: Id
    title: Title
    vertex_stage_id: Id
    fragment_stage_id: Id
    width: Dimension
    height: Dimension
    clear_color: Color
    bindings: list[Binding] = Field(default_factory=list, max_length=8)


class Uniform(Contract):
    id: Id
    pass_id: Id
    name: Name
    type: UniformType
    value: UniformValue

    @model_validator(mode="after")
    def value_type(self) -> Uniform:
        lengths = {"vec2": 2, "vec3": 3, "vec4": 4, "mat2": 4, "mat3": 9, "mat4": 16}
        if self.type == "bool":
            valid = type(self.value) is bool
        elif self.type == "int":
            valid = type(self.value) is int
        elif self.type == "float":
            valid = isinstance(self.value, (float, int)) and not isinstance(self.value, bool) and -1e6 <= self.value <= 1e6
        else:
            valid = isinstance(self.value, list) and len(self.value) == lengths[self.type]
        if not valid:
            raise ValueError("Uniform value does not match its declared type")
        return self


class Texture(Contract):
    id: Id
    title: Title
    width: Dimension
    height: Dimension
    format: Literal["rgba8"] = "rgba8"
    content_hash: Hash


class Preview(Contract):
    pass_id: Id
    width: PreviewDimension
    height: PreviewDimension
    time_seconds: Annotated[float, Field(ge=0, le=86400, allow_inf_nan=False)]


class Document(Contract):
    id: Id
    schema_version: Literal[1] = 1
    language: Literal["glsl-es-300"] = "glsl-es-300"
    title: Title
    stages: list[Stage] = Field(min_length=2, max_length=64)
    passes: list[Pass] = Field(min_length=1, max_length=32)
    uniforms: list[Uniform] = Field(default_factory=list, max_length=128)
    textures: list[Texture] = Field(default_factory=list, max_length=16)
    preview: Preview

    @model_validator(mode="before")
    @classmethod
    def schema_integer(cls, value: object) -> object:
        if isinstance(value, dict) and "schema_version" in value and type(value["schema_version"]) is not int:
            raise ValueError("schema_version must be a strict integer")
        return value

    @model_validator(mode="after")
    def references(self) -> Document:
        objects = [*self.stages, *self.passes, *self.uniforms, *self.textures]
        if len({item.id for item in objects}) != len(objects) or self.id in {item.id for item in objects}:
            raise ValueError("Object ids must be unique across the document")
        stages = {item.id: item for item in self.stages}
        textures = {item.id: item for item in self.textures}
        preceding: set[str] = set()
        names: set[tuple[str, str]] = set()
        for item in self.passes:
            if item.vertex_stage_id not in stages or stages[item.vertex_stage_id].kind != "vertex" or item.fragment_stage_id not in stages or stages[item.fragment_stage_id].kind != "fragment":
                raise ValueError("Pass stage reference is missing or has wrong kind")
            for binding in item.bindings:
                key = (item.id, binding.name)
                if key in names:
                    raise ValueError("Duplicate sampler binding")
                names.add(key)
                if isinstance(binding.source, TextureSource):
                    if binding.source.texture_id not in textures:
                        raise ValueError("Missing texture")
                elif binding.source.pass_id not in preceding:
                    raise ValueError("Pass inputs must reference an earlier pass")
            preceding.add(item.id)
        for uniform in self.uniforms:
            key = (uniform.pass_id, uniform.name)
            if uniform.pass_id not in preceding or key in names:
                raise ValueError("Missing pass or duplicate uniform/sampler name")
            names.add(key)
        if self.preview.pass_id not in preceding:
            raise ValueError("Missing preview pass")
        if sum(len(item.source.encode("utf-8")) for item in self.stages) > 524_288:
            raise ValueError("Document source budget exceeded")
        if sum(item.width * item.height for item in self.passes) > 2_097_152:
            raise ValueError("Pass target budget exceeded")
        unique_textures = {item.content_hash: item.width * item.height * 4 for item in self.textures}
        if sum(unique_textures.values()) > 4_194_304:
            raise ValueError("Document texture budget exceeded")
        if len(encoded(self.model_dump(mode="json"))) > MAX_DOCUMENT:
            raise ValueError("Canonical document budget exceeded")
        return self


class SelectTextureSource(Input):
    kind: Literal["texture"]
    texture_id: ObjectSelector


class SelectPassSource(Input):
    kind: Literal["pass"]
    pass_id: ObjectSelector


class BindingInput(Input):
    name: Name
    source: Annotated[Union[SelectTextureSource, SelectPassSource], Field(discriminator="kind")]
    filter: Literal["nearest", "linear"] = "nearest"
    wrap: Literal["clamp"] = "clamp"


class CreateObject(Input):
    ref: LocalRef | None = None


class RenameDocument(Input):
    kind: Literal["rename_document"]
    title: Title


class StageCreate(CreateObject):
    kind: Literal["stage_create"]
    stage_kind: Literal["vertex", "fragment"]
    title: Title
    source: Source


class StageReplace(Input):
    kind: Literal["stage_replace"]
    stage_id: ObjectSelector
    source: Source


class StagePatch(Input):
    kind: Literal["stage_patch"]
    stage_id: ObjectSelector
    old_text: Annotated[Source, Field(min_length=1)]
    new_text: Source


class StageRemove(Input):
    kind: Literal["stage_remove"]
    stage_id: ObjectSelector


class PassCreate(CreateObject):
    kind: Literal["pass_create"]
    title: Title
    vertex_stage_id: ObjectSelector
    fragment_stage_id: ObjectSelector
    width: Dimension
    height: Dimension
    clear_color: Color
    bindings: list[BindingInput] = Field(default_factory=list, max_length=8)


class PassUpdate(Input):
    kind: Literal["pass_update"]
    pass_id: ObjectSelector
    title: Title | None = None
    vertex_stage_id: ObjectSelector | None = None
    fragment_stage_id: ObjectSelector | None = None
    width: Dimension | None = None
    height: Dimension | None = None
    clear_color: Color | None = None


class PassRemove(Input):
    kind: Literal["pass_remove"]
    pass_id: ObjectSelector


class PassReorder(Input):
    kind: Literal["pass_reorder"]
    pass_ids: list[ObjectSelector] = Field(min_length=1, max_length=32)


class UniformCreate(CreateObject):
    kind: Literal["uniform_create"]
    pass_id: ObjectSelector
    name: Name
    type: UniformType
    value: UniformValue


class UniformUpdate(Input):
    kind: Literal["uniform_update"]
    uniform_id: ObjectSelector
    pass_id: ObjectSelector | None = None
    name: Name | None = None
    type: UniformType | None = None
    value: UniformValue | None = None


class UniformRemove(Input):
    kind: Literal["uniform_remove"]
    uniform_id: ObjectSelector


class BindingSet(BindingInput):
    kind: Literal["binding_set"]
    pass_id: ObjectSelector


class BindingRemove(Input):
    kind: Literal["binding_remove"]
    pass_id: ObjectSelector
    name: Name


class TextureCreate(CreateObject):
    kind: Literal["texture_create"]
    title: Title
    width: Dimension
    height: Dimension
    rgba_base64: str = Field(max_length=1_398_104)


class TextureRemove(Input):
    kind: Literal["texture_remove"]
    texture_id: ObjectSelector


class PreviewSet(Input):
    kind: Literal["preview_set"]
    pass_id: ObjectSelector | None = None
    width: PreviewDimension | None = None
    height: PreviewDimension | None = None
    time_seconds: Annotated[float, Field(ge=0, le=86400)] | None = None


Operation = Annotated[Union[RenameDocument, StageCreate, StageReplace, StagePatch, StageRemove, PassCreate, PassUpdate, PassRemove, PassReorder, UniformCreate, UniformUpdate, UniformRemove, BindingSet, BindingRemove, TextureCreate, TextureRemove, PreviewSet], Field(discriminator="kind")]


class CreateInput(Input):
    title: Title
    expected_generation: Nonnegative


class VersionInput(Input):
    document_id: Id
    expected_version: Version


class ApplyInput(VersionInput):
    operations: list[Operation] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def budget(self) -> ApplyInput:
        uploads = [item for item in self.operations if isinstance(item, TextureCreate)]
        raw = self.model_dump(mode="json", exclude_none=True)
        if len(uploads) > 1 or len(encoded(raw)) > (1_500_000 if uploads else 786_432):
            raise ValueError("Mutation input budget exceeded")
        for op in raw["operations"]:
            op.pop("rgba_base64", None)
        if len(encoded(raw)) > 786_432:
            raise ValueError("Non-texture mutation budget exceeded")
        refs = [item.ref for item in self.operations if isinstance(item, CreateObject) and item.ref is not None]
        if len(set(refs)) != len(refs):
            raise ValueError("Duplicate local ref")
        return self


class UndoInput(VersionInput):
    target_version: Version


class UniformSetInput(VersionInput):
    uniform_id: Id
    value: UniformValue


class TextureBindInput(VersionInput):
    pass_id: Id
    name: Name
    source: BindingSource
    filter: Literal["nearest", "linear"] = "nearest"
    wrap: Literal["clamp"] = "clamp"


class PassCreateInput(VersionInput):
    title: Title
    vertex_stage_id: Id
    fragment_stage_id: Id
    width: Dimension
    height: Dimension
    clear_color: Color
    bindings: list[Binding] = Field(default_factory=list, max_length=8)


class PageInput(Input):
    offset: Nonnegative = 0
    limit: Annotated[int, Field(ge=1, le=50)] = 20


class InspectInput(PageInput):
    document_id: Id | None = None
    version: Version | None = None
    section: Literal["documents", "summary", "stages", "passes", "uniforms", "textures", "source"] = "summary"
    stage_id: Id | None = None

    @model_validator(mode="after")
    def locator(self) -> InspectInput:
        if self.section == "documents":
            if self.document_id is not None or self.version is not None or self.stage_id is not None:
                raise ValueError("documents listing has no document selector")
        elif self.document_id is None or (self.section == "source" and self.stage_id is None):
            raise ValueError("Missing document or source stage selector")
        if self.offset and self.section != "documents" and self.version is None:
            raise ValueError("Further pages require fixed version")
        return self


class HeadInput(Input):
    document_id: Id


class ReadParameters(Input):
    section: Literal["summary", "stages", "passes", "uniforms", "textures", "source", "texture_bytes"] = "summary"
    offset: Nonnegative = 0
    limit: Annotated[int, Field(ge=1, le=16384)] = 20
    stage_id: Id | None = None
    texture_id: Id | None = None

    @model_validator(mode="after")
    def read_locator(self) -> ReadParameters:
        if self.section == "texture_bytes":
            if self.texture_id is None or self.stage_id is not None:
                raise ValueError("texture_bytes requires only a texture_id locator")
        elif self.texture_id is not None or self.limit > 50:
            raise ValueError("Object/source pages use limit<=50 and no texture_id")
        return self


class GetInput(ReadParameters):
    document_id: Id
    version: Version | None = None

    @model_validator(mode="after")
    def fixed_version(self) -> GetInput:
        if (self.section == "texture_bytes" or self.offset > 0) and self.version is None:
            raise ValueError("Byte reads and subsequent pages require fixed version")
        return self


class RevisionsInput(PageInput):
    document_id: Id
    version: Version | None = None

    @model_validator(mode="after")
    def fixed_page(self) -> RevisionsInput:
        if self.offset and self.version is None:
            raise ValueError("Further revision pages require fixed version")
        return self


class DiffInput(PageInput):
    document_id: Id
    from_version: Version
    to_version: Version
    section: Literal["summary", "source"] = "summary"
    stage_id: Id | None = None


class ReportInput(PageInput):
    report_id: Id


class CreateRequest(CreateInput):
    request_id: Id


class ApplyRequest(ApplyInput):
    request_id: Id


class VersionRequest(VersionInput):
    request_id: Id


class UndoRequest(UndoInput):
    request_id: Id


class Summary(Contract):
    id: Id
    title: Title
    version: Version
    content_hash: Hash
    deleted: bool


class HeadResult(Contract):
    id: Id
    version: Version
    content_hash: Hash
    deleted: bool


class Revision(Contract):
    document: Document
    version: Version
    studio_generation: Version
    content_hash: Hash
    deleted: bool

    def summary(self) -> Summary:
        return Summary(id=self.document.id, title=self.document.title, version=self.version, content_hash=self.content_hash, deleted=self.deleted)


class MutationResult(Contract):
    document: Summary
    studio_generation: Nonnegative
    changed: bool
    changed_ids: list[Id] = Field(default_factory=list, max_length=64)
    truncated: bool = False
    created_refs: dict[LocalRef, Id] = Field(default_factory=dict, max_length=64)


class TexturePage(Contract):
    texture_id: Id
    content_hash: Hash
    total_bytes: Nonnegative
    rgba_base64: str = Field(max_length=21848)


class PageResult(Contract):
    document: Summary | None = None
    studio_generation: Nonnegative
    section: str
    items: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=50)
    source: str | None = None
    stage_id: Id | None = None
    offset: Nonnegative
    next_offset: Nonnegative
    total: Nonnegative
    has_more: bool
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    texture_bytes: TexturePage | None = None


class Capabilities(Contract):
    version: str = Field(min_length=1, max_length=256)
    shading_language_version: str = Field(min_length=1, max_length=256)
    max_texture_size: Annotated[int, Field(ge=1, le=1_048_576)]
    max_renderbuffer_size: Annotated[int, Field(ge=1, le=1_048_576)]
    max_texture_image_units: Annotated[int, Field(ge=1, le=1024)]
    max_combined_texture_image_units: Annotated[int, Field(ge=1, le=1024)]
    max_fragment_uniform_vectors: Annotated[int, Field(ge=1, le=1_048_576)]
    max_vertex_uniform_vectors: Annotated[int, Field(ge=1, le=1_048_576)]
    parallel_shader_compile: bool


class Diagnostic(Contract):
    severity: Literal["error", "warning", "info"]
    code: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")]
    message: str = Field(max_length=1024)
    stage_id: Id | None = None
    pass_id: Id | None = None
    line: Annotated[int, Field(ge=1, le=16_384)] | None = None


class DriverLog(Contract):
    stage_id: Id | None = None
    pass_id: Id | None = None
    text: str = Field(max_length=65_536)


class ComputeResult(Input):
    compiled: bool
    rendered: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list, max_length=128)
    logs: list[DriverLog] = Field(default_factory=list, max_length=96)
    log_truncated: Nonnegative = 0
    rgba_base64: str | None = Field(default=None, max_length=349_528)
    width: PreviewDimension | None = None
    height: PreviewDimension | None = None
    row_order: Literal["bottom-left"] | None = None

    @model_validator(mode="after")
    def log_budget(self) -> ComputeResult:
        if sum(len(item.text.encode("utf-8")) for item in self.logs) > 65_536:
            raise ValueError("Driver log budget exceeded")
        if len(encoded(self.model_dump(mode="json", exclude_none=True))) > 1_048_576:
            raise ValueError("Compute result budget exceeded")
        return self


class Report(Contract):
    id: Id
    document_id: Id
    version: Version
    content_hash: Hash
    kind: Literal["compile", "preview"]
    compiled: bool
    rendered: bool
    diagnostics: list[Diagnostic] = Field(max_length=128)
    logs: list[DriverLog] = Field(max_length=96)
    log_truncated: Nonnegative
    capabilities: Capabilities
    elapsed_ms: Annotated[int, Field(ge=0, le=10_000)]
    width: PreviewDimension | None = None
    height: PreviewDimension | None = None
    pixel_hash: Hash | None = None
    pixel_format: Literal["rgba8-unorm"] | None = None


class ComputeOutcome(Contract):
    document: Summary
    report_id: Id
    compiled: bool
    rendered: bool
    diagnostics: list[Diagnostic] = Field(max_length=20)
    diagnostic_count: Nonnegative
    truncated: bool


class ArtifactLocator(Contract):
    project_id: str = Field(min_length=1, max_length=256)
    document_id: Id
    version: Version
    content_hash: Hash
    title: Title
    report_id: Id | None = None


class ActionResult(Contract):
    session_id: str
    run_id: str
    artifact_ids: list[str]
    outcome: dict[str, JsonValue]


class AttachInput(Input):
    client_id: Id
    registration_counter: Version
    package_digest: Hash
    available: bool
    capabilities: Capabilities


class AttachResult(Contract):
    epoch: Id
    lease: Token
    lease_ms: Literal[5000] = 5000
    server_status: Literal["ready", "unavailable"]


class LeaseInput(Input):
    epoch: Id
    lease: Token
    registration_counter: Version


class TextureBytes(Contract):
    content_hash: Hash
    rgba_base64: str = Field(max_length=1_398_104)


class Snapshot(Contract):
    document: Document
    textures: list[TextureBytes] = Field(max_length=16)


class ComputeRequest(Contract):
    request_id: Id
    claim: Token
    invocation_id: str = Field(min_length=1, max_length=256)
    document_id: Id
    version: Version
    content_hash: Hash
    request_hash: Hash
    remaining_ms: Annotated[int, Field(ge=1, le=10_000)]
    kind: Literal["compile", "preview"]
    snapshot: Snapshot


class NextResult(Contract):
    status: Literal["idle", "busy", "request"]
    request: ComputeRequest | None = None


class CompleteInput(LeaseInput):
    package_digest: Hash
    request_id: Id
    claim: Token
    invocation_id: str = Field(min_length=1, max_length=256)
    document_id: Id
    version: Version
    content_hash: Hash
    request_hash: Hash
    result: ComputeResult


class Accepted(Contract):
    accepted: Literal[True] = True


class DetachInput(Input):
    epoch: Id
    lease: Token
    reason: Literal["deactivate", "hidden", "context_lost", "network_error"]


class Studio(Contract):
    project_id: str
    generation: Nonnegative
