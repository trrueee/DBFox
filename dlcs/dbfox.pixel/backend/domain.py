"""Bounded integer pixel operations. No filesystem, Host state or image decoder."""
from __future__ import annotations

from collections import deque
from copy import deepcopy

from .contracts import MAX_FRAMES, MAX_SLOTS, PixelDocument, Rect


class PixelError(Exception):
    def __init__(self, code: str, message: str):
        self.code = "PIXEL_" + code
        super().__init__(message)


def require(condition, message, code="INVALID"):
    if not condition:
        raise PixelError(code, message)


def find(items, identity):
    value = next((item for item in items if item["id"] == identity), None)
    require(value is not None, "Pixel object does not exist.", "NOT_FOUND")
    return value


def check_rect(rect, width, height):
    require(rect.x + rect.width <= width and rect.y + rect.height <= height,
            "Rectangle exceeds the canvas.")


def _allocation(document, frames, layers):
    require(1 <= frames <= MAX_FRAMES and 1 <= layers <= 16 and
            document["canvas"]["width"] * document["canvas"]["height"] * frames * layers <= MAX_SLOTS,
            "Pixel document exceeds frame, layer or pixel slot budget.", "LIMIT")


def apply_operations(source, operations, born, cancelled):
    document = source.model_dump(mode="json")
    for operation in operations:
        require(not cancelled(), "Pixel operation was cancelled.", "CANCELLED")
        _apply(document, operation, born)
        try:
            # Validate structural relationships after each sequential operation.
            # Transient invalid frames/tags never become a valid final shortcut.
            checked = PixelDocument.model_validate(document)
        except ValueError as exc:
            raise PixelError("INVALID", "The operation violates Pixel document invariants.") from exc
    return checked


def _apply(d, op, born):
    kind = op.kind
    width, height = d["canvas"]["width"], d["canvas"]["height"]
    size = width * height
    frames, layers, tags = d["frames"], d["layers"], d["tags"]
    if kind in ("fill", "line", "rect", "stamp", "region_transform"):
        frame, layer = find(frames, op.frame_id), find(layers, op.layer_id)
        require(not layer["locked"], "Unlock this layer before editing its pixels.", "LOCKED")
        pixels = next(cel["pixels"] for cel in frame["cels"] if cel["layer_id"] == op.layer_id)
        if hasattr(op, "palette_index"):
            require(op.palette_index < len(d["palette"]), "Palette index is not defined.")
        if kind == "line":
            require(max(op.x0, op.x1) < width and max(op.y0, op.y1) < height, "Line exceeds canvas.")
            x, y = op.x0, op.y0
            dx, dy = abs(op.x1 - x), -abs(op.y1 - y)
            sx, sy = (1 if x < op.x1 else -1), (1 if y < op.y1 else -1)
            error = dx + dy
            while True:
                pixels[y * width + x] = op.palette_index
                if x == op.x1 and y == op.y1:
                    break
                twice = 2 * error
                if twice >= dy:
                    error += dy
                    x += sx
                if twice <= dx:
                    error += dx
                    y += sy
            return
        rect = op.rect or Rect(x=0, y=0, width=width, height=height)
        check_rect(rect, width, height)
        if kind == "fill":
            require(rect.x <= op.x < rect.x + rect.width and rect.y <= op.y < rect.y + rect.height,
                    "Fill seed must be inside its rectangle.")
            original = pixels[op.y * width + op.x]
            if original == op.palette_index:
                return
            pending = deque([(op.x, op.y)])
            pixels[op.y * width + op.x] = op.palette_index
            while pending:
                x, y = pending.popleft()
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if rect.x <= nx < rect.x + rect.width and rect.y <= ny < rect.y + rect.height:
                        index = ny * width + nx
                        if pixels[index] == original:
                            pixels[index] = op.palette_index
                            pending.append((nx, ny))
        elif kind in ("rect", "stamp"):
            if kind == "stamp":
                require(all(index < len(d["palette"]) for index in op.pixels), "Stamp contains an undefined palette index.")
            for v in range(rect.height):
                for u in range(rect.width):
                    if kind == "rect":
                        if not op.filled and u not in (0, rect.width - 1) and v not in (0, rect.height - 1):
                            continue
                        color = op.palette_index
                    else:
                        color = op.pixels[v * rect.width + u]
                        if color == 0 and op.transparent_mode == "over":
                            continue
                    pixels[(rect.y + v) * width + rect.x + u] = color
        else:
            snapshot = [pixels[(rect.y + v) * width + rect.x + u]
                        for v in range(rect.height) for u in range(rect.width)]
            target_width, target_height = ((rect.height, rect.width) if op.transform == "rotate_cw"
                                           else (rect.width, rect.height))
            dx, dy = op.destination.x, op.destination.y
            require(op.clip or (dx >= 0 and dy >= 0 and dx + target_width <= width and dy + target_height <= height),
                    "Transformed region exceeds canvas; explicit clip is required.")
            if op.mode == "move":
                for v in range(rect.height):
                    for u in range(rect.width):
                        pixels[(rect.y + v) * width + rect.x + u] = 0
            for v in range(rect.height):
                for u in range(rect.width):
                    a, b = u, v
                    if op.transform == "flip_x":
                        a = rect.width - 1 - u
                    elif op.transform == "flip_y":
                        b = rect.height - 1 - v
                    elif op.transform == "rotate_cw":
                        a, b = rect.height - 1 - v, u
                    if 0 <= dx + a < width and 0 <= dy + b < height:
                        pixels[(dy + b) * width + dx + a] = snapshot[v * rect.width + u]
    elif kind == "palette_set":
        require(op.index <= len(d["palette"]), "Palette can only update an existing slot or append at its end.")
        item = {"name": op.name, "color": op.color}
        if op.index == len(d["palette"]):
            d["palette"].append(item)
        else:
            d["palette"][op.index] = item
    elif kind in ("frame_create", "frame_duplicate"):
        _allocation(d, len(frames) + 1, len(layers))
        require(op.position <= len(frames), "Frame insertion position exceeds frame count.")
        born("frame", op.frame_id)
        frame = (deepcopy(find(frames, op.source_frame_id)) if kind == "frame_duplicate" else
                 {"id": op.frame_id, "duration_ms": op.duration_ms,
                  "cels": [{"layer_id": layer["id"], "pixels": [0] * size} for layer in layers]})
        frame["id"] = op.frame_id
        frames.insert(op.position, frame)
    elif kind == "frame_update":
        frame = find(frames, op.frame_id)
        if op.duration_ms is not None:
            frame["duration_ms"] = op.duration_ms
        if op.position is not None:
            require(op.position < len(frames), "Frame position exceeds frame count.")
            frames.remove(frame)
            frames.insert(op.position, frame)
    elif kind == "frame_delete":
        frame = find(frames, op.frame_id)
        require(len(frames) > 1, "Cannot delete the last frame.")
        require(not any(layer["locked"] for layer in layers), "Unlock all layer cels before deleting a frame.", "LOCKED")
        linked = [tag for tag in tags if op.frame_id in tag["frame_ids"]]
        require(not linked or op.remove_from_tags, "Frame is referenced by an animation tag.")
        for tag in linked:
            tag["frame_ids"].remove(op.frame_id)
            if not tag["frame_ids"]:
                tags.remove(tag)
        frames.remove(frame)
    elif kind == "layer_create":
        _allocation(d, len(frames), len(layers) + 1)
        require(op.position <= len(layers), "Layer insertion position exceeds layer count.")
        born("layer", op.layer_id)
        layers.insert(op.position, {"id": op.layer_id, "name": op.name, "visible": True, "locked": False})
        for frame in frames:
            frame["cels"].insert(op.position, {"layer_id": op.layer_id, "pixels": [0] * size})
    elif kind == "layer_update":
        layer = find(layers, op.layer_id)
        for field in ("name", "visible", "locked"):
            if getattr(op, field) is not None:
                layer[field] = getattr(op, field)
        if op.position is not None:
            require(op.position < len(layers), "Layer position exceeds layer count.")
            old_position = layers.index(layer)
            layers.remove(layer)
            layers.insert(op.position, layer)
            for frame in frames:
                frame["cels"].insert(op.position, frame["cels"].pop(old_position))
    elif kind == "layer_delete":
        layer = find(layers, op.layer_id)
        require(not layer["locked"], "Unlock this layer before deleting it.", "LOCKED")
        require(len(layers) > 1, "Cannot delete the last layer.")
        layers.remove(layer)
        for frame in frames:
            frame["cels"] = [cel for cel in frame["cels"] if cel["layer_id"] != op.layer_id]
    elif kind == "tag_set":
        tag = next((tag for tag in tags if tag["id"] == op.tag_id), None)
        if tag is None:
            require(len(tags) < 16, "Document already has 16 tags.", "LIMIT")
            born("tag", op.tag_id)
            tags.append({"id": op.tag_id, "name": op.name, "frame_ids": op.frame_ids, "loop": op.loop})
        else:
            tag.update(name=op.name, frame_ids=op.frame_ids, loop=op.loop)
    elif kind == "tag_delete":
        tags.remove(find(tags, op.tag_id))
    elif kind == "rename":
        d["title"] = op.title
    else:
        raise PixelError("INVALID", "Unknown Pixel operation.")


def frame_delta(before, after, width):
    old = {cel.layer_id: cel.pixels for cel in before.cels} if before else {}
    new = {cel.layer_id: cel.pixels for cel in after.cels} if after else {}
    result = []
    for identity in sorted(old.keys() | new.keys()):
        left, right = old.get(identity), new.get(identity)
        size = len(left or right)
        indices = [i for i in range(size) if (left[i] if left is not None else None) !=
                   (right[i] if right is not None else None)]
        if indices:
            xs, ys = [i % width for i in indices], [i // width for i in indices]
            result.append({"layer_id": identity, "changed_pixel_count": len(indices),
                "rect": {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs) + 1, "height": max(ys) - min(ys) + 1}})
    return result


def changes(before, after):
    old = {frame.id: frame for frame in before.frames} if before else {}
    new = {frame.id: frame for frame in after.frames}
    count, frames, layers = 0, [], set()
    for identity in sorted(old.keys() | new.keys()):
        left, right = old.get(identity), new.get(identity)
        if left != right:
            frames.append(identity)
            delta = frame_delta(left, right, after.canvas.width)
            count += sum(item["changed_pixel_count"] for item in delta)
            layers.update(item["layer_id"] for item in delta)
    old_layers = {layer.id: layer for layer in before.layers} if before else {}
    new_layers = {layer.id: layer for layer in after.layers}
    layers.update(identity for identity in old_layers.keys() | new_layers.keys() if old_layers.get(identity) != new_layers.get(identity))
    return {"changed_pixel_count": count, "changed_frame_ids": frames[:128],
            "changed_frame_ids_truncated": len(frames) > 128, "changed_layer_ids": sorted(layers)}


def metadata(document):
    result = document.model_dump(mode="json")
    result["frames"] = [{"id": frame.id, "duration_ms": frame.duration_ms} for frame in document.frames]
    return result


def directory(document, kind):
    if kind == "frames":
        return [{"id": frame.id, "duration_ms": frame.duration_ms} for frame in document.frames]
    if kind == "tags":
        return [{"id": tag.id, "name": tag.name, "loop": tag.loop, "frame_count": len(tag.frame_ids),
                 "frame_ids": tag.frame_ids[:8], "truncated": len(tag.frame_ids) > 8} for tag in document.tags]
    if kind == "palette":
        return [{"index": i, **item.model_dump()} for i, item in enumerate(document.palette)]
    return [item.model_dump() for item in document.layers]


def rgba(document, frame_id):
    frame = next((frame for frame in document.frames if frame.id == frame_id), None)
    require(frame is not None, "Frame does not exist.", "NOT_FOUND")
    colors = [bytes.fromhex(entry.color[1:]) for entry in document.palette]
    output = bytearray(document.canvas.width * document.canvas.height * 4)
    for layer, cel in zip(document.layers, frame.cels):
        if layer.visible:
            for index, color in enumerate(cel.pixels):
                if color:
                    output[index * 4:index * 4 + 4] = colors[color]
    return bytes(output)
