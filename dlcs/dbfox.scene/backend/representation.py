"""Immutable Scene representations and the supported glTF 2.0 export subset."""
from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import struct
from uuid import uuid4

from dbfox_dlc_api import (
    Artifact, ArtifactRepresentationContext, ArtifactRepresentationDescriptor,
    ArtifactRepresentationError, ArtifactRepresentationOperation, ArtifactRepresentationRequest,
    ArtifactRepresentationResult, ArtifactRepresentationStream, Field,
)
from pydantic import JsonValue, model_validator

from .contracts import (
    ARTIFACT_TYPE, Camera, Contract, InspectInput, Light, MAX_EXPORT_BYTES,
    Mesh, PageInput, REPRESENTATION_TYPE, Revision, RevisionArtifact,
)
from .store import SceneError, SceneStore


class PrimitiveBuffer(Contract):
    positions: list[float] = Field(min_length=9, max_length=30_000)
    normals: list[float] = Field(min_length=9, max_length=30_000)
    indices: list[int] = Field(min_length=3, max_length=60_000)

    @model_validator(mode="after")
    def layout(self) -> PrimitiveBuffer:
        count = len(self.positions) // 3
        if len(self.positions) % 3 or len(self.indices) % 3 or len(self.normals) != len(self.positions):
            raise ValueError("Invalid primitive buffer layout")
        if any(index < 0 or index >= count for index in self.indices):
            raise ValueError("Invalid primitive index")
        if any(abs(value) > 1 for value in self.positions):
            raise ValueError("Primitive exceeds unit bounds")
        for i in range(0, len(self.normals), 3):
            if abs(sum(value * value for value in self.normals[i:i + 3]) - 1) > 0.001:
                raise ValueError("Primitive normals must be normalized")
        return self


class PrimitiveCatalog(Contract):
    schema_version: int
    generator: str
    primitives: dict[str, PrimitiveBuffer]


def _quaternion(rotation: tuple[float, float, float]) -> list[float]:
    x, y, z = (angle / 2 for angle in rotation)
    a, b, c, d, e, f = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return [b * c * e + a * d * f, a * d * e - b * c * f,
            a * c * f + b * d * e, a * c * e - b * d * f]


def export_scene(revision: Revision, binary: bool, primitive_path: Path | None = None) -> bytes:
    """Pack prebuilt official Three buffers; never tessellate or load external resources."""
    path = primitive_path or Path(__file__).with_name("primitives.json")
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("oversized primitive catalog")
        catalog = PrimitiveCatalog.model_validate_json(path.read_bytes())
        if catalog.schema_version != 1 or catalog.generator != "three@0.185.1":
            raise ValueError("unsupported primitive catalog")
        if set(catalog.primitives) != {"box", "sphere", "cylinder", "cone", "plane", "torus"}:
            raise ValueError("incomplete primitive catalog")
    except (OSError, ValueError) as exc:
        raise SceneError("SCENE_EXPORT_UNAVAILABLE", "Offline primitive export resources are unavailable or invalid.") from exc
    document = revision.document
    raw = bytearray()
    views: list[dict[str, JsonValue]] = []
    accessors: list[dict[str, JsonValue]] = []

    def buffer(values: list[float] | list[int], component: int, shape: str, target: int,
               bounds: bool = False) -> int:
        offset = len(raw)
        raw.extend(struct.pack("<" + ("f" if component == 5126 else "I") * len(values), *values))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw) - offset, "target": target})
        while len(raw) % 4:
            raw.append(0)
        item: dict[str, JsonValue] = {"bufferView": len(views) - 1, "componentType": component,
            "count": len(values) // (3 if shape == "VEC3" else 1), "type": shape}
        if bounds:
            item["min"] = [min(values[axis::3]) for axis in range(3)]
            item["max"] = [max(values[axis::3]) for axis in range(3)]
        accessors.append(item)
        return len(accessors) - 1

    geometry_accessors: dict[str, tuple[int, int, int]] = {}
    geometry_kinds = {item.id: item.primitive for item in document.geometries}
    nodes_by_id = {item.id: item for item in document.objects}

    def visible(node_id: str) -> bool:
        node = nodes_by_id[node_id]
        for _ in range(64):
            if not node.visible:
                return False
            if node.parent_id is None:
                return True
            node = nodes_by_id[node.parent_id]
        return False

    included = [node for node in document.objects if visible(node.id)]
    index_by_id = {node.id: index for index, node in enumerate(included)}
    material_indices = {item.id: index for index, item in enumerate(document.materials)}
    materials: list[dict[str, JsonValue]] = []
    for item in document.materials:
        material: dict[str, JsonValue] = {"name": item.name, "extras": {"dbfoxId": item.id},
            "pbrMetallicRoughness": {"baseColorFactor": list(item.base_color),
                "metallicFactor": item.metallic, "roughnessFactor": item.roughness},
            "doubleSided": item.double_sided}
        if item.base_color[3] < 1:
            material["alphaMode"] = "BLEND"
        materials.append(material)
    meshes: list[dict[str, JsonValue]] = []
    mesh_indices: dict[tuple[str, str | None], int] = {}
    nodes: list[dict[str, JsonValue]] = []
    cameras: list[dict[str, JsonValue]] = []
    lights: list[dict[str, JsonValue]] = []
    children: dict[str, list[int]] = {}
    for child_node in included:
        if child_node.parent_id is not None:
            children.setdefault(child_node.parent_id, []).append(index_by_id[child_node.id])
    for item in included:
        node: dict[str, JsonValue] = {"name": item.name, "translation": list(item.position),
            "rotation": _quaternion(item.rotation), "scale": list(item.scale), "extras": {"dbfoxId": item.id}}
        if item.id in children:
            node["children"] = children[item.id]
        if isinstance(item, Mesh):
            primitive_name = geometry_kinds[item.geometry_id]
            if primitive_name not in geometry_accessors:
                primitive = catalog.primitives[primitive_name]
                geometry_accessors[primitive_name] = (
                    buffer(primitive.positions, 5126, "VEC3", 34962, True),
                    buffer(primitive.normals, 5126, "VEC3", 34962),
                    buffer(primitive.indices, 5125, "SCALAR", 34963),
                )
            key = (primitive_name, item.material_id)
            if key not in mesh_indices:
                position, normal, indices = geometry_accessors[primitive_name]
                mesh: dict[str, JsonValue] = {"attributes": {"POSITION": position, "NORMAL": normal}, "indices": indices}
                if item.material_id is not None:
                    mesh["material"] = material_indices[item.material_id]
                mesh_indices[key] = len(meshes)
                meshes.append({"name": primitive_name, "primitives": [mesh]})
            node["mesh"] = mesh_indices[key]
        elif isinstance(item, Camera):
            node["camera"] = len(cameras)
            cameras.append({"name": item.name, "type": "perspective", "perspective": {
                "yfov": item.yfov, "znear": item.znear, "zfar": item.zfar}})
        elif isinstance(item, Light):
            light: dict[str, JsonValue] = {"name": item.name, "type": item.light_type,
                "color": list(item.color), "intensity": item.intensity}
            if item.range is not None and item.light_type != "directional":
                light["range"] = item.range
            if item.light_type == "spot":
                light["spot"] = {"innerConeAngle": item.inner_cone_angle, "outerConeAngle": item.outer_cone_angle}
            node["extensions"] = {"KHR_lights_punctual": {"light": len(lights)}}
            lights.append(light)
        nodes.append(node)
    scene: dict[str, JsonValue] = {"name": document.title, "extras": {
        "backgroundLinearRGB": list(document.settings.background),
        "defaultCameraId": document.settings.default_camera_id}}
    roots = [index_by_id[node.id] for node in included if node.parent_id is None]
    if roots:
        scene["nodes"] = roots
    tree: dict[str, JsonValue] = {"asset": {"version": "2.0", "generator": "DBFox Scene 1.0"},
        "scene": 0, "scenes": [scene], "extras": {"sceneId": revision.scene.id,
            "version": revision.scene.version, "contentHash": revision.scene.content_hash}}
    for name, values in (("nodes", nodes), ("meshes", meshes), ("materials", materials), ("cameras", cameras)):
        if values:
            tree[name] = values
    if lights:
        tree["extensionsUsed"] = ["KHR_lights_punctual"]
        tree["extensions"] = {"KHR_lights_punctual": {"lights": lights}}
    if raw:
        descriptor: dict[str, JsonValue] = {"byteLength": len(raw)}
        if not binary:
            descriptor["uri"] = "data:application/octet-stream;base64," + base64.b64encode(raw).decode("ascii")
        tree["buffers"] = [descriptor]
        tree["bufferViews"] = views
        tree["accessors"] = accessors
    encoded = json.dumps(tree, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if binary:
        encoded += b" " * ((-len(encoded)) % 4)
        total = 12 + 8 + len(encoded) + (8 + len(raw) if raw else 0)
        result = struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(encoded), b"JSON") + encoded
        if raw:
            result += struct.pack("<I4s", len(raw), b"BIN\x00") + raw
    else:
        result = encoded
    if len(result) > MAX_EXPORT_BYTES:
        raise SceneError("SCENE_LIMIT", "Scene export exceeds 32 MiB.")
    return result


class SceneRepresentation:
    def __init__(self, store: SceneStore) -> None:
        self.store = store

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type != ARTIFACT_TYPE:
            raise ArtifactRepresentationError("UNSUPPORTED_REPRESENTATION", "Not a Scene revision.", status_code=409)
        return ArtifactRepresentationDescriptor(representation_type=REPRESENTATION_TYPE, version=1, operations=(
            ArtifactRepresentationOperation(name="summary"),
            ArtifactRepresentationOperation(name="objects_page"),
            ArtifactRepresentationOperation(name="materials_page"),
            ArtifactRepresentationOperation(name="geometry_catalog"),
            ArtifactRepresentationOperation(name="export_gltf", result_kind="stream", media_type="model/gltf+json"),
            ArtifactRepresentationOperation(name="export_glb", result_kind="stream", media_type="model/gltf-binary"),
        ))

    def execute(self, artifact: Artifact, request: ArtifactRepresentationRequest,
                context: ArtifactRepresentationContext) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        del context
        self.describe(artifact)
        try:
            payload = RevisionArtifact.model_validate(artifact.payload)
            revision = self.store.get_revision(payload.project_id, payload.scene_id, payload.version)
            if revision.scene.content_hash != payload.content_hash:
                raise SceneError("SCENE_CORRUPT", "Artifact revision fingerprint does not match stored content.")
            operation = request.operation
            if operation in ("export_gltf", "export_glb"):
                if request.parameters:
                    raise ValueError("Export accepts no external options")
                binary = operation == "export_glb"
                content = export_scene(revision, binary)
                return ArtifactRepresentationStream(
                    chunks=(content[index:index + 65536] for index in range(0, len(content), 65536)),
                    media_type="model/gltf-binary" if binary else "model/gltf+json",
                    file_name=f"scene-{payload.scene_id}-v{payload.version}.{'glb' if binary else 'gltf'}",
                    metadata={"source-version": str(payload.version), "source-fingerprint": payload.content_hash,
                              "consistency": "durable_snapshot"},
                )
            if operation == "summary":
                if request.parameters:
                    raise ValueError("Summary accepts no parameters")
                result = {"scene": revision.scene.model_dump(mode="json"), "settings": revision.document.settings.model_dump(mode="json")}
            elif operation in ("objects_page", "materials_page", "geometry_catalog"):
                page = PageInput.model_validate(request.parameters)
                section = {"objects_page": "objects", "materials_page": "materials", "geometry_catalog": "geometries"}[operation]
                result = self.store.page(payload.project_id, InspectInput(scene_id=payload.scene_id,
                    version=payload.version, section=section, offset=page.offset, limit=page.limit)).model_dump(mode="json")
            else:
                raise ValueError("Unsupported operation")
            return ArtifactRepresentationResult(representation_type=REPRESENTATION_TYPE, representation_version=1,
                operation=operation, payload=result, consistency="durable_snapshot",
                original_observed_at=revision.scene.updated_at, read_at=datetime.now(UTC).isoformat(),
                read_id=uuid4().hex, source_version=str(payload.version), source_fingerprint=payload.content_hash)
        except SceneError as exc:
            raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", str(exc), status_code=409) from exc
        except ValueError as exc:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Invalid Scene representation request.", status_code=422) from exc
