"""Incremental domain operations, independent of Host and playback caches."""
from .contracts import Document, Difference, Operation, SECTIONS


class AnimationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = "ANIMATION_" + code


def require(items, ids):
    if len(set(ids)) != len(ids) or not set(ids) <= {item["id"] for item in items}:
        raise AnimationError("REFERENCE", "Selection must contain unique existing stable IDs.")


def apply(document: Document, operation: Operation) -> Document:
    data = document.model_dump(mode="json")
    op = operation.model_dump(mode="json")
    kind = op.pop("kind")
    if kind in ("target_create", "track_create", "clip_create"):
        singular = kind.split("_")[0]
        data[singular + "s"].append(op[singular])
    elif kind in ("track_modify", "clip_modify"):
        singular = kind.split("_")[0]
        replacement = op[singular]
        require(data[singular + "s"], [replacement["id"]])
        data[singular + "s"] = [replacement if item["id"] == replacement["id"] else item for item in data[singular + "s"]]
    elif kind == "keyframe_add":
        data["keyframes"].extend(op["keyframes"])
    elif kind == "keyframe_move":
        require(data["keyframes"], [item["id"] for item in op["keyframes"]])
        changes = {item["id"]: item for item in op["keyframes"]}
        for item in data["keyframes"]:
            item.update(changes.get(item["id"], {}))
    elif kind == "easing_set":
        require(data["keyframes"], op["keyframe_ids"])
        curve = op["curve"]
        data["curves"] = [item for item in data["curves"] if item["id"] != curve["id"]] + [curve]
        for item in data["keyframes"]:
            if item["id"] in op["keyframe_ids"]:
                item["curve_id"] = curve["id"]
    elif kind == "clip_trim":
        require(data["clips"], [op["clip_id"]])
        for item in data["clips"]:
            if item["id"] == op["clip_id"]:
                item.update(start=op["start"], end=op["end"])
    elif kind == "timing_modify":
        data["timing"] = op["timing"]
    elif kind == "marker_set":
        marker = op["marker"]
        data["markers"] = [item for item in data["markers"] if item["id"] != marker["id"]] + [marker]
    elif kind == "animation_rename":
        data["title"] = op["title"]
    elif kind == "entity_delete":
        section, ids = op["section"], set(op["ids"])
        require(data[section], op["ids"])
        data[section] = [item for item in data[section] if item["id"] not in ids]
        if op["cascade"]:
            if section == "targets":
                data["tracks"] = [item for item in data["tracks"] if item["target_id"] not in ids]
            remaining = {item["id"] for item in data["tracks"]}
            data["keyframes"] = [item for item in data["keyframes"] if item["track_id"] in remaining]
            for clip in data["clips"]:
                clip["track_ids"] = [identity for identity in clip["track_ids"] if identity in remaining]
            data["clips"] = [clip for clip in data["clips"] if clip["track_ids"]]
            if section == "curves":
                for key in data["keyframes"]:
                    if key["curve_id"] in ids:
                        key["curve_id"] = None
    try:
        # Stable collection order makes equality/hash independent of caller batch order.
        for section in SECTIONS:
            data[section].sort(key=lambda item: item["id"])
        return Document.model_validate(data)
    except ValueError as exc:
        raise AnimationError("INVALID", str(exc)) from exc


def differences(before: Document, after: Document) -> list[Difference]:
    results = []
    for section in SECTIONS:
        old = {item.id: item.model_dump(mode="json") for item in getattr(before, section)}
        new = {item.id: item.model_dump(mode="json") for item in getattr(after, section)}
        for identity in sorted(old.keys() | new.keys()):
            if old.get(identity) != new.get(identity):
                a, b = old.get(identity, {}), new.get(identity, {})
                results.append(Difference(section=section, id=identity,
                    change="added" if not a else "removed" if not b else "modified",
                    fields=sorted(key for key in a.keys() | b.keys() if a.get(key) != b.get(key))))
    for field in ("title", "timing"):
        if getattr(before, field) != getattr(after, field):
            results.append(Difference(section="document", id=field, change="modified", fields=[field]))
    return results
