"""Formal Tool Runtime leaves: exact frozen Resource, one canonical write path."""
from __future__ import annotations

from typing import ClassVar, Literal, cast

from dbfox_dlc_api import (
    Artifact, ArtifactDraft, ArtifactRelationDraft, ArtifactRelationType, ArtifactRepresentationRequest, BaseTool, ExtensionToolRunContext, ResourceScopeRef,
    ToolExecutionSpec, ToolInputError, ToolObservationProjection, ToolOutcome,
    ToolPolicy, ToolPresentation, ToolReconciliation, ToolResourceRequirement, ToolSemanticSpec,
)
from pydantic import JsonValue, ValidationError

from . import contracts as c
from . import views
from .compute import Bridge
from .representation import bundle
from .store import GameError, Store

WRITE = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential", max_output_bytes=32768, required_resources=(ToolResourceRequirement(kind=c.RESOURCE, selector_field="game_id"),))
READ = ToolExecutionSpec(recovery="retry_safe", retryable=True, max_retries=1, concurrency="parallel_safe", max_output_bytes=32768, required_resources=(ToolResourceRequirement(kind=c.RESOURCE, selector_field="game_id"),))


def check_cancelled(context: ExtensionToolRunContext) -> None:
    if context.is_cancelled():
        raise GameError("CANCELLED", "Game operation was cancelled", 409)


def selected(context: ExtensionToolRunContext, data: c.Input) -> tuple[ResourceScopeRef, c.LibraryScope | c.Revision]:
    kind = c.LIBRARY if isinstance(data, c.CreateInput) else c.RESOURCE
    refs = context.scopes(kind)
    if len(refs) != 1 or type(refs[0].version) is not int:
        raise GameError("INVALID_SCOPE", "Game tool requires one fixed Resource")
    ref = refs[0]
    resource: object = context.resource(ref)
    if isinstance(data, c.CreateInput):
        if not isinstance(resource, c.LibraryScope) or resource.project_id != ref.id or resource.version != ref.version or data.expected_library_version != ref.version:
            raise GameError("STALE_VERSION", "Create must use the frozen Game library version", 409)
    else:
        if not isinstance(resource, c.Revision) or resource.game.id != ref.id or resource.version != ref.version:
            raise GameError("INVALID_SCOPE", "Game Resource did not resolve to its exact revision")
        if not isinstance(data, (c.HeadInput, c.VersionInput)) or data.game_id != ref.id:
            raise GameError("INVALID_SCOPE", "Input Game is not the authorized Game")
        if isinstance(data, c.VersionInput) and data.expected_version != ref.version:
            raise GameError("STALE_VERSION", "Edit must use the frozen Game version", 409)
    if not isinstance(resource, (c.LibraryScope, c.Revision)):
        raise GameError("INVALID_SCOPE", "Resource does not belong to Game")
    return ref, resource


def draft(result: c.Mutation, ref: ResourceScopeRef) -> ArtifactDraft:
    game = result.game
    if result.report is not None:
        report = result.report
        return ArtifactDraft(key="game_playtest", type=c.REPORT_ARTIFACT, schema_version=1, title=game.title + " · Playtest", payload=c.ArtifactLocator(project_id=game.project_id, game_id=game.id, version=game.version, content_hash=game.content_hash, title=game.title, report_id=report.id).data(), summary=f"{report.outcome}; {report.ticks_completed}/{report.ticks_requested} ticks; seed {report.seed}; {report.event_count} events", semantic_key="game_playtest:" + report.id, resource_refs=(ref,), select_if_none=True)
    return ArtifactDraft(key="game_revision", type=c.DOCUMENT_ARTIFACT, schema_version=1, title=game.title, payload=c.ArtifactLocator(project_id=game.project_id, game_id=game.id, version=game.version, content_hash=game.content_hash, title=game.title).data(), summary=f"Game revision {game.version}; {game.entity_count} entities, {game.rule_count} rules" + ("; deleted" if game.deleted else ""), semantic_key="game:" + game.id, resource_refs=(ref,), select_if_none=True)


def apply_input(data: c.Input) -> c.ApplyInput:
    if isinstance(data, c.ApplyInput):
        return data
    if isinstance(data, (c.SceneCreateInput, c.EntityCreateInput, c.EntityDeleteInput, c.ComponentAddInput, c.ComponentModifyInput, c.BehaviorCreateInput, c.RuleCreateInput, c.VariableCreateInput)):
        return c.ApplyInput(game_id=data.game_id, expected_version=data.expected_version, operations=[data.operation])
    raise GameError("INVALID_OPERATION", "Tool input is not a structured Game edit")


class GameTool(BaseTool[c.Input, c.Contract]):
    name = "game_operation"
    description = "Apply a typed Game operation through one canonical state path."
    group = "game"
    version = "1"
    input_model: ClassVar[type[c.Input]] = c.ApplyInput
    output_model: ClassVar[type[c.Contract]] = c.Mutation
    action: ClassVar[Literal["create", "apply", "undo", "delete", "export", "inspect", "diff", "playtest", "import"]] = "apply"
    policy = ToolPolicy(risk_level="warning", requires_approval=False)
    execution = WRITE
    semantics = ToolSemanticSpec(produces=(c.DOCUMENT_ARTIFACT,))
    presentation = ToolPresentation(title="Edit game", category="manage")

    def __init__(self, store: Store, bridge: Bridge) -> None:
        self.store = store
        self.bridge = bridge

    def normalized(self, data: c.Input) -> c.Input:
        return apply_input(data) if self.action == "apply" else data

    def run(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolOutcome[c.Contract]:
        try:
            check_cancelled(context)
            data = self.normalized(tool_input)
            ref, resource = selected(context, data)
            if self.action == "create" and isinstance(data, c.CreateInput) and isinstance(resource, c.LibraryScope):
                result = self.store.create(resource.project_id, "agent", context.invocation_id, data, lambda: check_cancelled(context))
            elif isinstance(resource, c.Revision):
                if self.action == "inspect" and isinstance(data, c.GetInput):
                    if data.section == "asset_bytes":
                        raise GameError("INVALID_PAGE", "Agent inspection excludes raw assets; use the explicit public Representation")
                    page = views.read(self.store, resource, data, budget=14000)
                    check_cancelled(context)
                    return ToolOutcome(output=page)
                if self.action == "diff" and isinstance(data, c.DiffInput):
                    if max(data.from_version, data.to_version) > resource.version:
                        raise GameError("STALE_VERSION", "Diff versions exceed the frozen Game scope", 409)
                    before = self.store.get(resource.project_id, data.game_id, data.from_version)
                    after = self.store.get(resource.project_id, data.game_id, data.to_version)
                    page = views.page("diff", after, after.library_version, views.differences(before, after), data.offset, data.limit, budget=14000)
                    check_cancelled(context)
                    return ToolOutcome(output=page)
                if self.action == "export" and isinstance(data, c.VersionInput):
                    result = self.store.export(resource.project_id, "agent", context.invocation_id, data, lambda: check_cancelled(context))
                elif self.action in ("apply", "undo", "delete") and isinstance(data, c.VersionInput):
                    result = self.store.mutate(resource.project_id, "agent", context.invocation_id, cast(Literal["apply", "undo", "delete"], self.action), data, lambda: check_cancelled(context))
                else:
                    raise GameError("INVALID_OPERATION", "Tool operation and input do not match")
            else:
                raise GameError("INVALID_SCOPE", "Game operation requires an authorized project")
            return ToolOutcome(output=result, artifacts=(draft(result, ref),))
        except GameError as exc:
            raise ToolInputError(exc.code + ": " + str(exc)) from exc
        except ValidationError as exc:
            raise ToolInputError("INVALID_GAME: Game model or references are invalid") from exc
        except ValueError as exc:
            raise ToolInputError("INVALID_GAME: " + str(exc)[:300]) from exc

    def reconcile(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolReconciliation:
        if self.action in {"inspect", "diff"}:
            return ToolReconciliation(status="unknown")
        try:
            data = self.normalized(tool_input)
            ref, resource = selected(context, data)
            result = self.store.receipt(resource.project_id, "agent", context.invocation_id, self.action, data)
            if result is None:
                return ToolReconciliation(status="unknown")
            return ToolReconciliation(status="succeeded", output=result.data(), artifacts=(draft(result, ref),))
        except ValueError:
            return ToolReconciliation(status="unknown")

    def project_observation(self, *, status: str, output: dict[str, JsonValue] | None, artifacts: tuple[Artifact, ...]) -> ToolObservationProjection:
        value = output or {}
        budget = 16384 if self.action in {"inspect", "diff"} else 8192
        if len(c.encoded(value)) > budget:
            raise ValueError("Game observation exceeds its declared budget")
        facts = {key: item for key, item in value.items() if key != "items"} if self.action in {"inspect", "diff"} else value
        if len(c.encoded(facts)) > 8192:
            raise ValueError("Game facts exceed their declared budget")
        return ToolObservationProjection(summary=self.name + ": " + status, facts=facts, provider_payload=value)


class Create(GameTool):
    reconcile = GameTool.reconcile
    name, description = "game_create", "Create a durable Game with one scene using the observed Game library version. Then inspect its stable IDs and incrementally edit it."
    input_model = c.CreateInput
    action = "create"
    execution = ToolExecutionSpec(recovery="reconcile", retryable=False, concurrency="sequential", max_output_bytes=32768, required_resources=(ToolResourceRequirement(kind=c.LIBRARY),))


class Modify(GameTool):
    reconcile = GameTool.reconcile
    name, description = "game_modify", "Atomically apply up to 64 typed operations to one Game. Use observed expected_version and stable IDs; local refs name earlier creations in this action."


class Inspect(GameTool):
    name, description = "game_inspect", "Read a bounded page of the authorized Game revision: summary, scenes, entities, components, behaviors, rules, variables or asset metadata. Inspect before editing."
    action, input_model, output_model = "inspect", c.GetInput, c.Page
    policy, execution, semantics = ToolPolicy(risk_level="safe"), READ, ToolSemanticSpec()


class Diff(GameTool):
    name, description = "game_diff", "Compare two fixed revisions of the authorized Game by stable object ID and changed fields. Does not modify the Game."
    action, input_model, output_model = "diff", c.DiffInput, c.Page
    policy, execution, semantics = ToolPolicy(risk_level="safe"), READ, ToolSemanticSpec()


class Undo(GameTool):
    reconcile = GameTool.reconcile
    name, description = "game_undo", "Restore historical Game content and deletion state as a new revision; requires the current expected_version."
    action, input_model = "undo", c.UndoInput


class Delete(GameTool):
    reconcile = GameTool.reconcile
    name, description = "game_delete", "Tombstone the Game using its current expected_version. History remains readable and game_undo can restore it."
    action, input_model = "delete", c.VersionInput


class Export(GameTool):
    reconcile = GameTool.reconcile
    name, description = "game_export", "Create an immutable Game revision Artifact with public document/asset Representations and JSON export; does not change Game content."
    action, input_model = "export", c.VersionInput


class SceneCreate(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "scene_create", "Create a scene with typed dimensions, background and Arcade gravity in the authorized Game.", c.SceneCreateInput


class EntityCreate(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "entity_create", "Create up to 128 entities with typed components and local refs in one atomic Game edit.", c.EntityCreateInput


class EntityDelete(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "entity_delete", "Delete up to 128 entities; explicit cascade also removes dependent behaviors/rules. No silent dangling references.", c.EntityDeleteInput


class ComponentAdd(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "component_add", "Add one typed component to a Game entity. Transform, visual, body and health kinds must remain unique.", c.ComponentAddInput


class ComponentModify(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "component_modify", "Edit a typed component while retaining its stable ID and kind. Use this for position, speed, visuals and health parameters.", c.ComponentModifyInput


class BehaviorCreate(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "behavior_create", "Create a data-only movement, spawn or lifetime behavior. Movement requires a dynamic body and exactly one enabled controller.", c.BehaviorCreateInput


class RuleCreate(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "rule_create", "Create a typed rule with elapsed/overlap/variable/health trigger and ordered actions. No executable script is accepted.", c.RuleCreateInput


class VariableCreate(GameTool):
    reconcile = GameTool.reconcile
    name, description, input_model = "variable_create", "Create a named int, float or bool Game variable with a strictly typed initial value.", c.VariableCreateInput


class Playtest(GameTool):
    name = "playtest"
    description = "Run the fixed Game revision in the active Phaser executor for up to 7200 fixed ticks with a seed and bounded action inputs. Returns immutable event/terminal-state evidence; no Game edits. No executor or stale source fails explicitly."
    action, input_model = "playtest", c.PlaytestInput
    execution = WRITE.model_copy(update={"timeout_seconds": 25})
    semantics = ToolSemanticSpec(produces=(c.REPORT_ARTIFACT,))
    reconcile = GameTool.reconcile

    def run(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolOutcome[c.Contract]:
        try:
            check_cancelled(context)
            if not isinstance(tool_input, c.PlaytestInput):
                raise GameError("INVALID_OPERATION", "Playtest requires its typed input")
            ref, source = selected(context, tool_input)
            if not isinstance(source, c.Revision):
                raise GameError("INVALID_SCOPE", "Playtest requires a Game Resource")
            previous = self.store.receipt(source.project_id, "agent", context.invocation_id, "playtest", tool_input)
            if previous is not None:
                return ToolOutcome(output=previous, artifacts=(draft(previous, ref),))
            current = self.store.get(source.project_id, source.game.id)
            if current.version != source.version or current.deleted:
                raise GameError("STALE_VERSION", "Game changed before playtest", 409)
            controlled = {item.spec.entity_id for item in source.game.behaviors if item.enabled and isinstance(item.spec, c.Control)}
            if any(item.entity_id not in controlled for item in tool_input.inputs):
                raise GameError("INVALID_INPUT", "Playtest input requires an enabled player_control behavior")
            task = self.bridge.request(source, tool_input, context.invocation_id, bundle(self.store, source), lambda: check_cancelled(context))
            try:
                def guard() -> None:
                    check_cancelled(context)
                    self.bridge.check(task)
                report = self.bridge.wait(task, lambda: check_cancelled(context))
                result = self.store.save_report(source.project_id, context.invocation_id, tool_input, report, guard)
                return ToolOutcome(output=result, artifacts=(draft(result, ref),))
            finally:
                self.bridge.finish(task)
        except GameError as exc:
            raise ToolInputError(exc.code + ": " + str(exc)) from exc
        except ValueError as exc:
            raise ToolInputError("INVALID_REPORT: " + str(exc)[:300]) from exc


class AssetImport(GameTool):
    name = "asset_import"
    description = "Import an explicit rectangle from a fixed Pixel frame Artifact in this Run, using only dbfox.pixel.sprite.v1 public RGBA pages. Stores immutable Game asset bytes and provenance; never reads files or URLs."
    action, input_model = "import", c.ImportInput

    @staticmethod
    def artifact(result: c.Mutation, ref: ResourceScopeRef, source: Artifact) -> ArtifactDraft:
        refs = {ref.canonical(): ref}
        for dependency in source.resource_refs:
            if dependency.canonical() in refs and refs[dependency.canonical()] != dependency:
                raise GameError("SOURCE_MISMATCH", "Asset dependency versions conflict")
            refs[dependency.canonical()] = dependency
        return draft(result, ref).model_copy(update={"resource_refs": tuple(refs.values()), "relations": (ArtifactRelationDraft(relation=ArtifactRelationType.DERIVED_FROM, artifact_id=source.id),)})

    def run(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolOutcome[c.Contract]:
        try:
            check_cancelled(context)
            if not isinstance(tool_input, c.ImportInput):
                raise GameError("INVALID_OPERATION", "Asset import requires its typed input")
            ref, game = selected(context, tool_input)
            if not isinstance(game, c.Revision):
                raise GameError("INVALID_SCOPE", "Asset import requires a Game Resource")
            artifact = context.artifact(tool_input.source_artifact_id)
            if artifact.type != "dbfox.pixel.revision" or artifact.payload.get("project_id") != game.project_id:
                raise GameError("SOURCE_MISMATCH", "Source must be a Pixel revision Artifact in this Project")
            previous = self.store.receipt(game.project_id, "agent", context.invocation_id, "import", tool_input)
            if previous is not None:
                return ToolOutcome(output=previous, artifacts=(self.artifact(previous, ref, artifact),))
            live = self.store.get(game.project_id, game.game.id)
            if live.version != game.version or live.deleted:
                raise GameError("STALE_VERSION", "Game changed before asset import", 409)
            rect = tool_input.rect
            raw = bytearray(rect.width * rect.height * 4)
            provenance: c.Source | None = None
            for y in range(0, rect.height, 32):
                for x in range(0, rect.width, 32):
                    check_cancelled(context)
                    tile = c.PixelRect(x=rect.x + x, y=rect.y + y, width=min(32, rect.width - x), height=min(32, rect.height - y))
                    result = context.read_artifact_representation(artifact.id, "dbfox.pixel.sprite.v1", ArtifactRepresentationRequest(operation="frame", parameters={"frame_id": tool_input.frame_id, "rect": tile.data()}))
                    if result.representation_type != "dbfox.pixel.sprite.v1" or result.representation_version != 1 or result.operation != "frame" or result.consistency != "durable_snapshot":
                        raise GameError("SOURCE_MISMATCH", "Pixel source is not a fixed public frame Representation")
                    page = c.PixelFramePage.model_validate(result.payload)
                    if page.frame_id != tool_input.frame_id or page.rect != tile or len(page.rgba) != tile.width * tile.height * 4:
                        raise GameError("SOURCE_MISMATCH", "Pixel frame page does not match its requested rectangle")
                    current = c.Source(artifact_id=artifact.id, representation_type=result.representation_type, source_version=result.source_version, source_fingerprint=result.source_fingerprint, frame_id=tool_input.frame_id, rect=rect)
                    if provenance is not None and provenance != current:
                        raise GameError("SOURCE_MISMATCH", "Pixel source changed between fixed frame pages")
                    provenance = current
                    tile_raw = bytes(page.rgba)
                    for row in range(tile.height):
                        start = ((y + row) * rect.width + x) * 4
                        raw[start:start + tile.width * 4] = tile_raw[row * tile.width * 4:(row + 1) * tile.width * 4]
            if provenance is None:
                raise GameError("SOURCE_MISMATCH", "Pixel import returned no source evidence")
            result_mutation = self.store.import_asset(game.project_id, context.invocation_id, tool_input, bytes(raw), provenance, lambda: check_cancelled(context))
            return ToolOutcome(output=result_mutation, artifacts=(self.artifact(result_mutation, ref, artifact),))
        except GameError as exc:
            raise ToolInputError(exc.code + ": " + str(exc)) from exc
        except ValueError as exc:
            raise ToolInputError("INVALID_ASSET: " + str(exc)[:300]) from exc

    def reconcile(self, tool_input: c.Input, context: ExtensionToolRunContext) -> ToolReconciliation:
        try:
            if not isinstance(tool_input, c.ImportInput):
                return ToolReconciliation(status="unknown")
            ref, game = selected(context, tool_input)
            source = context.artifact(tool_input.source_artifact_id)
            if not isinstance(game, c.Revision) or source.type != "dbfox.pixel.revision" or source.payload.get("project_id") != game.project_id:
                return ToolReconciliation(status="unknown")
            result = self.store.receipt(game.project_id, "agent", context.invocation_id, "import", tool_input)
            if result is None:
                return ToolReconciliation(status="unknown")
            return ToolReconciliation(status="succeeded", output=result.data(), artifacts=(self.artifact(result, ref, source),))
        except ValueError:
            return ToolReconciliation(status="unknown")


TOOL_TYPES = (Create, Modify, Inspect, Diff, Undo, Delete, Export, SceneCreate, EntityCreate, EntityDelete, ComponentAdd, ComponentModify, BehaviorCreate, RuleCreate, VariableCreate, Playtest, AssetImport)
