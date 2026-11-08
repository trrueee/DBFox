"""Bounded integer-grid operations over an immutable source snapshot."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from math import prod

from .contracts import (
    MAX_CANDIDATES, BooleanOperation, Bounds, BoxOperation, CopyOperation,
    ExtrudeOperation, FillOperation, GeometryOperation, MirrorOperation,
    ReplaceOperation, SphereOperation, WorldDocument,
)

ChunkKey = tuple[str, int, int, int]
Cell = tuple[int, int, int]
EMPTY_CHUNK = bytes(4096)


class VoxelError(Exception):
    """Small public errors; never include local paths or SQLite exception text."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def check_cancel(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise VoxelError("CANCELLED", "The voxel operation was cancelled before commit.", 409)


def validate_bounds(bounds: Bounds, document: WorldDocument, *, budget: bool = True) -> int:
    if any(hi > n for hi, n in zip(bounds.max, document.size)):
        raise VoxelError("OUT_OF_BOUNDS", "The operation extends outside the world.")
    count = prod(hi - lo for lo, hi in zip(bounds.min, bounds.max))
    if budget and count > MAX_CANDIDATES:
        raise VoxelError("OPERATION_TOO_LARGE", "A geometry operation may visit at most 2,097,152 cells; split it into regions.")
    return count


def layer_exists(document: WorldDocument, layer_id: str, *, writable: bool = False) -> None:
    layer = next((item for item in document.layers if item.id == layer_id), None)
    if layer is None:
        raise VoxelError("LAYER_NOT_FOUND", "The selected layer does not exist.", 404)
    if writable and layer.locked:
        raise VoxelError("LAYER_LOCKED", "Unlock the selected layer before editing it.", 409)


def palette_exists(document: WorldDocument, value: int) -> None:
    if not any(item.index == value for item in document.palette):
        raise VoxelError("PALETTE_NOT_FOUND", "The palette index is not defined in this world.")


def positions(bounds: Bounds) -> Iterator[Cell]:
    for y in range(bounds.min[1], bounds.max[1]):
        for z in range(bounds.min[2], bounds.max[2]):
            for x in range(bounds.min[0], bounds.max[0]):
                yield x, y, z


def locate(layer_id: str, cell: Cell) -> tuple[ChunkKey, int]:
    x, y, z = cell
    return (layer_id, x // 16, y // 16, z // 16), x % 16 + 16 * (z % 16) + 256 * (y % 16)


@dataclass(frozen=True)
class GeometryDelta:
    chunks: dict[ChunkKey, bytes]
    changed_voxel_count: int


class Canvas:
    """Local operation buffers; reads always use pre-operation bytes."""

    def __init__(self, loader: Callable[[ChunkKey], bytes], cancelled: Callable[[], bool]) -> None:
        self.loader = loader
        self.cancelled = cancelled
        self.before: dict[ChunkKey, bytes] = {}
        self.after: dict[ChunkKey, bytearray] = {}
        self.visits = 0

    def source(self, key: ChunkKey) -> bytes:
        if key not in self.before:
            self.before[key] = self.loader(key)
        return self.before[key]

    def get(self, layer_id: str, cell: Cell) -> int:
        key, offset = locate(layer_id, cell)
        return self.source(key)[offset]

    def put(self, layer_id: str, cell: Cell, value: int) -> None:
        key, offset = locate(layer_id, cell)
        if key not in self.after:
            self.after[key] = bytearray(self.source(key))
        self.after[key][offset] = value

    def tick(self) -> None:
        self.visits += 1
        if self.visits % 4096 == 0:
            check_cancel(self.cancelled)

    def delta(self) -> GeometryDelta:
        chunks: dict[ChunkKey, bytes] = {}
        changed = 0
        for key, value in self.after.items():
            check_cancel(self.cancelled)
            raw = bytes(value)
            before = self.before[key]
            if raw != before:
                chunks[key] = raw
                changed += sum(a != b for a, b in zip(before, raw))
        return GeometryDelta(chunks, changed)


def apply_geometry(document: WorldDocument, operation: GeometryOperation, loader: Callable[[ChunkKey], bytes], cancelled: Callable[[], bool]) -> GeometryDelta:
    check_cancel(cancelled)
    layer_exists(document, operation.layer_id, writable=True)
    canvas = Canvas(loader, cancelled)
    if isinstance(operation, SphereOperation):
        radius = operation.radius
        try:
            bounds = Bounds(min=[n - radius for n in operation.center], max=[n + radius + 1 for n in operation.center])
        except ValueError as exc:
            raise VoxelError("OUT_OF_BOUNDS", "The sphere extends outside the world.") from exc
    else:
        bounds = operation.bounds
    volume = validate_bounds(bounds, document)
    if isinstance(operation, (FillOperation, BoxOperation, SphereOperation)):
        palette_exists(document, operation.palette_index)
    elif isinstance(operation, ReplaceOperation):
        palette_exists(document, operation.from_index)
        palette_exists(document, operation.to_index)
    else:
        layer_exists(document, operation.source_layer_id)
    axis = 0
    if isinstance(operation, (MirrorOperation, ExtrudeOperation)):
        axis = ("x", "y", "z").index(operation.axis)
    if isinstance(operation, (CopyOperation, MirrorOperation)):
        try:
            destination_bounds = Bounds(min=operation.destination, max=[dest + hi - lo for dest, lo, hi in zip(operation.destination, bounds.min, bounds.max)])
        except ValueError as exc:
            raise VoxelError("OUT_OF_BOUNDS", "The copy destination is invalid.") from exc
        validate_bounds(destination_bounds, document)
    if isinstance(operation, ExtrudeOperation):
        if bounds.max[axis] - bounds.min[axis] != 1:
            raise VoxelError("INVALID_EXTRUSION", "Extrusion requires a source region exactly one cell thick along its axis.")
        if volume * operation.depth > MAX_CANDIDATES:
            raise VoxelError("OPERATION_TOO_LARGE", "The extrusion exceeds 2,097,152 destination cells.")
        end = bounds.min[axis] + operation.direction * operation.depth
        if not 0 <= end < document.size[axis]:
            raise VoxelError("OUT_OF_BOUNDS", "The extrusion extends outside the world.")
    for cell in positions(bounds):
        canvas.tick()
        if isinstance(operation, FillOperation):
            canvas.put(operation.layer_id, cell, operation.palette_index)
        elif isinstance(operation, BoxOperation):
            shell = any(c - lo < operation.thickness or hi - 1 - c < operation.thickness for c, lo, hi in zip(cell, bounds.min, bounds.max))
            if not operation.hollow or shell:
                canvas.put(operation.layer_id, cell, operation.palette_index)
            elif operation.clear_inside:
                canvas.put(operation.layer_id, cell, 0)
        elif isinstance(operation, SphereOperation):
            distance = sum((c - center) ** 2 for c, center in zip(cell, operation.center))
            inner = operation.radius - operation.thickness
            if distance <= operation.radius ** 2:
                if not operation.hollow or inner < 0 or distance > inner ** 2:
                    canvas.put(operation.layer_id, cell, operation.palette_index)
                elif operation.clear_inside:
                    canvas.put(operation.layer_id, cell, 0)
        elif isinstance(operation, ReplaceOperation):
            if canvas.get(operation.layer_id, cell) == operation.from_index:
                canvas.put(operation.layer_id, cell, operation.to_index)
        elif isinstance(operation, (CopyOperation, MirrorOperation)):
            source_value = canvas.get(operation.source_layer_id, cell)
            if source_value or operation.mode == "replace":
                local = [c - lo for c, lo in zip(cell, bounds.min)]
                if isinstance(operation, MirrorOperation):
                    local[axis] = bounds.max[axis] - bounds.min[axis] - 1 - local[axis]
                target = tuple(local[n] + operation.destination[n] for n in range(3))
                canvas.put(operation.layer_id, (target[0], target[1], target[2]), source_value)
        elif isinstance(operation, ExtrudeOperation):
            source_value = canvas.get(operation.source_layer_id, cell)
            if source_value:
                for step in range(1, operation.depth + 1):
                    canvas.tick()
                    extruded = list(cell)
                    extruded[axis] += operation.direction * step
                    canvas.put(operation.layer_id, (extruded[0], extruded[1], extruded[2]), source_value)
        elif isinstance(operation, BooleanOperation):
            a, b = canvas.get(operation.layer_id, cell), canvas.get(operation.source_layer_id, cell)
            if operation.mode == "union":
                value = a or b
            elif operation.mode == "intersection":
                value = a if b else 0
            elif operation.mode == "difference":
                value = a if not b else 0
            else:
                value = (a or b) if bool(a) != bool(b) else 0
            canvas.put(operation.layer_id, cell, value)
    return canvas.delta()
