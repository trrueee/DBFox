"""Canonical graph invariants shared by mutation, reload and immutable reads."""
from __future__ import annotations

from collections import Counter

from . import contracts as c


def object_index(game: c.GameProject) -> dict[str, c.Contract]:
    objects: list[c.Contract] = [*game.scenes, *game.entities, *game.behaviors, *game.rules, *game.variables, *game.assets]
    objects.extend(component for entity in game.entities for component in entity.components)
    result: dict[str, c.Contract] = {}
    for item in objects:
        identity = item.data()["id"]
        if not isinstance(identity, str) or identity == game.id or identity in result:
            raise ValueError("Object identities must be unique across the game")
        result[identity] = item
    return result


def references(item: c.Contract) -> set[str]:
    """Only typed reference fields, never incidental names or free-form strings."""
    def walk(value: object) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {"scene_id", "entity_id", "target_id", "template_id", "variable_id", "asset_id", "target"} and isinstance(nested, str) and nested not in {"left", "right"}:
                    found.add(nested)
                else:
                    found.update(walk(nested))
        elif isinstance(value, list):
            for nested in value:
                found.update(walk(nested))
        return found
    return walk(item.data())


def validate_game(game: c.GameProject) -> None:
    object_index(game)
    scenes = {scene.id for scene in game.scenes}
    entities = {entity.id: entity for entity in game.entities}
    variables = {variable.id: variable for variable in game.variables}
    assets = {asset.id for asset in game.assets}
    if game.initial_scene_id not in scenes:
        raise ValueError("Initial scene does not exist")
    if len({variable.name for variable in game.variables}) != len(variables):
        raise ValueError("Variable names must be unique")
    if any(count > 512 for count in Counter(entity.scene_id for entity in game.entities).values()):
        raise ValueError("A scene may contain at most 512 entities including templates")
    components = {entity.id: {part.spec.kind: part.spec for part in entity.components} for entity in game.entities}
    for entity in game.entities:
        parts = components[entity.id]
        if entity.scene_id not in scenes or len(parts) != len(entity.components) or "transform" not in parts:
            raise ValueError("Entity needs an existing scene and unique components including transform")
        if len(set(entity.tags)) != len(entity.tags):
            raise ValueError("Entity tags must be unique")
        visual = parts.get("visual")
        if isinstance(visual, c.Visual) and visual.asset_id is not None and visual.asset_id not in assets:
            raise ValueError("Visual asset does not exist in this game")
        body = parts.get("body")
        transform = parts["transform"]
        if isinstance(body, c.Body):
            if body.body_type == "static" and (body.vx != 0 or body.vy != 0):
                raise ValueError("Static body velocity must be zero")
            if body.shape == "circle" and isinstance(transform, c.Transform) and transform.width != transform.height:
                raise ValueError("Circular Arcade bodies require equal width and height")

    def entity_ref(identity: str, scene: str | None = None, component: str | None = None) -> c.Entity:
        entity = entities.get(identity)
        if entity is None or (scene is not None and entity.scene_id != scene):
            raise ValueError("Entity reference must exist in the same scene")
        if component and component not in components[identity]:
            raise ValueError("Referenced entity is missing the required " + component + " component")
        return entity

    controllers: set[str] = set()
    for behavior in game.behaviors:
        spec = behavior.spec
        entity = entity_ref(spec.entity_id)
        if isinstance(spec, (c.Control, c.Seek, c.Patrol, c.Wander)):
            body = components[entity.id].get("body")
            if not isinstance(body, c.Body) or body.body_type != "dynamic":
                raise ValueError("Movement behaviors require a dynamic body")
            if behavior.enabled and entity.id in controllers:
                raise ValueError("An entity may have only one enabled movement behavior")
            if behavior.enabled:
                controllers.add(entity.id)
        if isinstance(spec, c.Seek):
            entity_ref(spec.target_id, entity.scene_id)
            if spec.target_id == entity.id:
                raise ValueError("Seek target must be a different entity")
        if isinstance(spec, c.Spawner):
            entity_ref(spec.template_id, entity.scene_id)
            if spec.template_id == entity.id:
                raise ValueError("A spawner cannot use itself as its template")

    def variable_ref(identity: str) -> c.Variable:
        variable = variables.get(identity)
        if variable is None:
            raise ValueError("Variable reference does not exist")
        return variable

    for rule in game.rules:
        spec = rule.spec
        if spec.scene_id not in scenes:
            raise ValueError("Rule scene does not exist")
        trigger = spec.trigger
        if isinstance(trigger, c.VariableCompare):
            variable = variable_ref(trigger.variable_id)
            c.check_value(variable.value_type, trigger.value)
            if variable.value_type == "bool" and trigger.comparison not in {"eq", "ne"}:
                raise ValueError("Boolean variables support equality comparisons only")
        if isinstance(trigger, c.HealthCompare):
            entity_ref(trigger.entity_id, spec.scene_id, "health")
        for action in spec.actions:
            if isinstance(action, c.VariableSet):
                c.check_value(variable_ref(action.variable_id).value_type, action.value)
            if isinstance(action, c.VariableAdd):
                kind = variable_ref(action.variable_id).value_type
                if kind == "bool" or (kind == "int" and not float(action.amount).is_integer()):
                    raise ValueError("Variable addition requires a compatible numeric amount")
            if isinstance(action, (c.Damage, c.Despawn)):
                required = "health" if isinstance(action, c.Damage) else None
                if action.target in {"left", "right"}:
                    if not isinstance(trigger, c.Overlap):
                        raise ValueError("Left/right targets are available only for overlap rules")
                    tag = trigger.left_tag if action.target == "left" else trigger.right_tag
                    for entity in game.entities:
                        if entity.scene_id == spec.scene_id and tag in entity.tags:
                            entity_ref(entity.id, spec.scene_id, required)
                else:
                    entity_ref(action.target, spec.scene_id, required)
            if isinstance(action, c.Spawn):
                entity_ref(action.template_id, spec.scene_id)
            if isinstance(action, c.SceneChange) and action.scene_id not in scenes:
                raise ValueError("Scene-change destination does not exist")
    hashes: dict[str, int] = {}
    for asset in game.assets:
        size = asset.width * asset.height * 4
        if asset.content_hash in hashes and hashes[asset.content_hash] != size:
            raise ValueError("Asset hash is used with inconsistent dimensions")
        hashes[asset.content_hash] = size
    if sum(hashes.values()) > c.MAX_ASSETS:
        raise ValueError("Game exceeds the 4 MiB unique asset budget")
    if len(c.encoded(game.data())) > c.MAX_DOCUMENT:
        raise ValueError("Game exceeds the 2 MiB canonical JSON budget")
