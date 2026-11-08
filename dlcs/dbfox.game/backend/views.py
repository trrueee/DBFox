"""Bounded fixed-revision projections; never a second editable document."""
from __future__ import annotations

import base64

from pydantic import JsonValue

from . import contracts as c
from .store import GameError, Store
from .validation import object_index


def page(section: str, revision: c.Revision | None, library_version: int, items: list[dict[str, JsonValue]], offset: int, limit: int, *, metadata: dict[str, JsonValue] | None = None, budget: int = 32768, total: int | None = None) -> c.Page:
    count = len(items) if total is None else total
    start = min(offset, count)
    result = c.Page(section=section, game=revision.summary() if revision else None, library_version=library_version, offset=offset, next_offset=start, total=count, has_more=start < count, metadata=metadata or {})
    candidates = items[start:start + limit] if total is None else items[:limit]
    for item in candidates:
        result.items.append(item)
        result.next_offset += 1
        result.has_more = result.next_offset < count
        if len(c.encoded(result.data())) > budget:
            result.items.pop()
            result.next_offset -= 1
            result.has_more = result.next_offset < count
            if not result.items:
                raise GameError("PAGE_BUDGET", "Requested object is too large for this page; inspect its components separately")
            break
    if len(c.encoded(result.data())) > budget:
        raise GameError("PAGE_BUDGET", "Game page exceeds its byte budget")
    return result


def read(store: Store, revision: c.Revision, request: c.GetInput, *, budget: int = 32768) -> c.Page:
    if request.game_id != revision.game.id or (request.version is not None and request.version != revision.version):
        raise GameError("VERSION_MISMATCH", "Read must use the fixed Game revision", 409)
    game = revision.game
    if request.section == "asset_bytes":
        if request.asset_id is None or request.version is None or request.scene_id is not None or request.entity_id is not None:
            raise GameError("INVALID_PAGE", "Asset bytes require fixed version and asset_id only")
        raw = store.asset_bytes(revision, request.asset_id)
        if request.offset > len(raw):
            raise GameError("INVALID_PAGE", "Asset offset exceeds its raw byte length")
        end = min(len(raw), request.offset + request.limit)
        asset = next(item for item in game.assets if item.id == request.asset_id)
        result = c.Page(section="asset_bytes", game=revision.summary(), library_version=revision.library_version, offset=request.offset, next_offset=end, total=len(raw), has_more=end < len(raw), metadata={"asset": asset.data(), "rgba_base64": base64.b64encode(raw[request.offset:end]).decode("ascii")})
        if len(c.encoded(result.data())) > budget:
            raise GameError("PAGE_BUDGET", "Reduce the asset byte page limit")
        return result
    if request.limit > 50 or request.asset_id is not None:
        raise GameError("INVALID_PAGE", "Object pages accept at most 50 objects and no asset byte selector")
    if request.scene_id is not None and request.scene_id not in {item.id for item in game.scenes}:
        raise GameError("NOT_FOUND", "Scene does not belong to this Game revision", 404)
    if request.entity_id is not None and request.entity_id not in {item.id for item in game.entities}:
        raise GameError("NOT_FOUND", "Entity does not belong to this Game revision", 404)
    items: list[dict[str, JsonValue]] = []
    metadata: dict[str, JsonValue] = {}
    if request.section == "summary":
        metadata = {"schema_version": game.schema_version, "engine": game.engine, "tick_hz": game.tick_hz, "initial_scene_id": game.initial_scene_id, "counts": {"scenes": len(game.scenes), "entities": len(game.entities), "components": sum(len(item.components) for item in game.entities), "behaviors": len(game.behaviors), "rules": len(game.rules), "variables": len(game.variables), "assets": len(game.assets)}}
    elif request.section == "scenes":
        items = [item.data() for item in game.scenes if request.scene_id is None or item.id == request.scene_id]
    elif request.section == "entities":
        items = [item.data() for item in game.entities if (request.scene_id is None or item.scene_id == request.scene_id) and (request.entity_id is None or item.id == request.entity_id)]
    elif request.section == "components":
        items = [{**part.data(), "entity_id": item.id} for item in game.entities if (request.scene_id is None or item.scene_id == request.scene_id) and (request.entity_id is None or item.id == request.entity_id) for part in item.components]
    elif request.section == "behaviors":
        members = {item.id for item in game.entities if request.scene_id is None or item.scene_id == request.scene_id}
        items = [item.data() for item in game.behaviors if item.spec.entity_id in members and (request.entity_id is None or item.spec.entity_id == request.entity_id)]
    elif request.section == "rules":
        items = [item.data() for item in game.rules if request.scene_id is None or item.spec.scene_id == request.scene_id]
    elif request.section == "variables":
        items = [item.data() for item in game.variables]
    elif request.section == "assets":
        items = [item.data() for item in game.assets]
    return page(request.section, revision, revision.library_version, items, request.offset, request.limit, metadata=metadata, budget=budget)


def differences(before: c.Revision, after: c.Revision) -> list[dict[str, JsonValue]]:
    old = {identity: item.data() for identity, item in object_index(before.game).items()}
    new = {identity: item.data() for identity, item in object_index(after.game).items()}
    changes: list[dict[str, JsonValue]] = []
    for identity in sorted(old.keys() | new.keys()):
        if old.get(identity) == new.get(identity):
            continue
        left, right = old.get(identity, {}), new.get(identity, {})
        changes.append({"id": identity, "change": "added" if identity not in old else "removed" if identity not in new else "modified", "fields": sorted(key for key in left.keys() | right.keys() if left.get(key) != right.get(key))})
    fields = []
    for key in ("title", "initial_scene_id"):
        if before.game.data()[key] != after.game.data()[key]:
            fields.append(key)
    if before.deleted != after.deleted:
        fields.append("deleted")
    if [item.id for item in before.game.rules] != [item.id for item in after.game.rules]:
        fields.append("rule_order")
    if fields:
        changes.insert(0, {"id": after.game.id, "change": "modified", "fields": fields})
    return changes
