"""Structured edits of one copied canonical graph; validation precedes commit."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pydantic import JsonValue

from . import contracts as c
from .validation import object_index, references


@dataclass(frozen=True)
class Applied:
    game: c.GameProject
    created_refs: dict[str, str]
    allocated_ids: set[str]


def new_game(title: str) -> c.GameProject:
    scene = c.Scene(id=str(uuid4()), name="Main scene")
    return c.GameProject(id=str(uuid4()), title=title, initial_scene_id=scene.id, scenes=[scene])


def apply_operations(original: c.GameProject, operations: list[c.Operation]) -> Applied:
    game = original.model_copy(deep=True)
    aliases: dict[str, str] = {}
    allocated: set[str] = set()

    def allocate(alias: str | None = None) -> str:
        identity = str(uuid4())
        allocated.add(identity)
        if alias is not None:
            if alias in aliases or len(aliases) >= 64:
                raise ValueError("An action accepts at most 64 unique local creation refs")
            aliases[alias] = identity
        return identity

    def select(selector: c.Selector) -> str:
        if isinstance(selector, c.ById):
            return selector.id
        if selector.ref not in aliases:
            raise ValueError("Local ref must name an earlier creation in this action")
        return aliases[selector.ref]

    def resolve(model: c.Contract) -> dict[str, JsonValue]:
        def walk(value: JsonValue) -> JsonValue:
            if isinstance(value, dict):
                if set(value) == {"id"} and isinstance(value["id"], str):
                    return value["id"]
                if set(value) == {"ref"} and isinstance(value["ref"], str):
                    return select(c.ByRef(ref=value["ref"]))
                return {key: walk(nested) for key, nested in value.items()}
            if isinstance(value, list):
                return [walk(nested) for nested in value]
            return value
        return {key: walk(value) for key, value in model.data().items()}

    def entity(identity: str) -> c.Entity:
        for item in game.entities:
            if item.id == identity:
                return item
        raise ValueError("Entity does not exist")

    def remove(identities: set[str], cascade: bool) -> None:
        index = object_index(game)
        if not identities or not identities.issubset(index):
            raise ValueError("Every removed object must exist")
        # Entity components are owned children. Other references require cascade
        # or an explicit repair elsewhere in the same atomic action.
        removed = set(identities)
        while True:
            previous = set(removed)
            for item in game.entities:
                if item.id in removed:
                    removed.update(part.id for part in item.components)
            if cascade:
                for identity, item in index.items():
                    if references(item) & removed:
                        # Components inside an entity do not make their parent a
                        # reference-dependent object (e.g. deleting one asset).
                        if isinstance(item, c.Entity):
                            if item.scene_id in removed:
                                removed.add(identity)
                        else:
                            removed.add(identity)
            if previous == removed:
                break
        game.scenes = [item for item in game.scenes if item.id not in removed]
        game.entities = [item for item in game.entities if item.id not in removed]
        for item in game.entities:
            item.components = [part for part in item.components if part.id not in removed]
        game.behaviors = [item for item in game.behaviors if item.id not in removed]
        game.rules = [item for item in game.rules if item.id not in removed]
        game.variables = [item for item in game.variables if item.id not in removed]
        game.assets = [item for item in game.assets if item.id not in removed]

    for operation in operations:
        if isinstance(operation, c.Rename):
            game.title = operation.title
        elif isinstance(operation, c.EntryScene):
            game.initial_scene_id = select(operation.scene_id)
        elif isinstance(operation, c.SceneCreate):
            game.scenes.append(c.Scene(id=allocate(operation.ref), **operation.scene.data()))
        elif isinstance(operation, c.SceneModify):
            identity = select(operation.scene_id)
            if identity not in {item.id for item in game.scenes}:
                raise ValueError("Scene does not exist")
            game.scenes = [c.Scene(id=identity, **operation.scene.data()) if item.id == identity else item for item in game.scenes]
        elif isinstance(operation, c.Remove):
            remove({select(operation.object_id)}, operation.cascade)
        elif isinstance(operation, c.EntityCreate):
            for draft in operation.entities:
                identity = allocate(draft.ref)
                parts = [c.Component.model_validate({"id": allocate(), "spec": resolve(spec)}) for spec in draft.components]
                game.entities.append(c.Entity(id=identity, scene_id=select(draft.scene_id), name=draft.name, enabled=draft.enabled, tags=draft.tags, components=parts))
        elif isinstance(operation, c.EntityModify):
            item = entity(select(operation.entity_id))
            if operation.name is not None:
                item.name = operation.name
            if operation.enabled is not None:
                item.enabled = operation.enabled
            if operation.tags is not None:
                item.tags = operation.tags
            if operation.scene_id is not None:
                item.scene_id = select(operation.scene_id)
        elif isinstance(operation, c.TransformEntities):
            identities = [select(selector) for selector in operation.entity_ids]
            if len(identities) != len(set(identities)):
                raise ValueError("Transform selection contains duplicate identities")
            for identity in identities:
                for part in entity(identity).components:
                    if isinstance(part.spec, c.Transform):
                        part.spec = c.Transform.model_validate({**part.spec.data(), "x": part.spec.x + operation.dx, "y": part.spec.y + operation.dy})
        elif isinstance(operation, c.DeleteEntities):
            identities = [select(selector) for selector in operation.entity_ids]
            if len(identities) != len(set(identities)):
                raise ValueError("Delete selection contains duplicate identities")
            for identity in identities:
                entity(identity)
            remove(set(identities), operation.cascade)
        elif isinstance(operation, c.ComponentAdd):
            entity(select(operation.entity_id)).components.append(c.Component.model_validate({"id": allocate(operation.ref), "spec": resolve(operation.component)}))
        elif isinstance(operation, c.ComponentModify):
            identity = select(operation.component_id)
            existing = object_index(game).get(identity)
            if not isinstance(existing, c.Component):
                raise ValueError("Component does not exist")
            replacement = c.Component.model_validate({"id": identity, "spec": resolve(operation.component)})
            if existing.spec.kind != replacement.spec.kind:
                raise ValueError("Component kind is immutable; remove and add a new component")
            for item in game.entities:
                item.components = [replacement if part.id == identity else part for part in item.components]
        elif isinstance(operation, c.BehaviorCreate):
            game.behaviors.append(c.Behavior.model_validate({"id": allocate(operation.ref), "enabled": operation.enabled, "spec": resolve(operation.behavior)}))
        elif isinstance(operation, c.BehaviorModify):
            identity = select(operation.behavior_id)
            if identity not in {item.id for item in game.behaviors}:
                raise ValueError("Behavior does not exist")
            replacement_behavior = c.Behavior.model_validate({"id": identity, "enabled": operation.enabled, "spec": resolve(operation.behavior)})
            game.behaviors = [replacement_behavior if item.id == identity else item for item in game.behaviors]
        elif isinstance(operation, c.RuleCreate):
            game.rules.append(c.Rule.model_validate({"id": allocate(operation.ref), "enabled": operation.enabled, "spec": resolve(operation.rule)}))
        elif isinstance(operation, c.RuleModify):
            identity = select(operation.rule_id)
            if identity not in {item.id for item in game.rules}:
                raise ValueError("Rule does not exist")
            replacement_rule = c.Rule.model_validate({"id": identity, "enabled": operation.enabled, "spec": resolve(operation.rule)})
            game.rules = [replacement_rule if item.id == identity else item for item in game.rules]
        elif isinstance(operation, c.RuleReorder):
            order = [select(selector) for selector in operation.rule_ids]
            if len(order) != len(set(order)) or set(order) != {item.id for item in game.rules}:
                raise ValueError("Rule reorder must contain every rule exactly once")
            rules = {item.id: item for item in game.rules}
            game.rules = [rules[identity] for identity in order]
        elif isinstance(operation, c.VariableCreate):
            game.variables.append(c.Variable(id=allocate(operation.ref), **operation.variable.data()))
        elif isinstance(operation, c.VariableModify):
            identity = select(operation.variable_id)
            if identity not in {item.id for item in game.variables}:
                raise ValueError("Variable does not exist")
            game.variables = [c.Variable(id=identity, **operation.variable.data()) if item.id == identity else item for item in game.variables]
    return Applied(c.GameProject.model_validate(game.data()), aliases, allocated)
