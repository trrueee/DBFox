"""Operations, resources, and tool registration for the dbfox.story DLC."""

from __future__ import annotations

from dbfox_dlc_api import DlcOperationSpec

from .store import StoryStateStore
from .contracts import (
    DeleteOutput,
    EntityCreateInput,
    EntityIdInput,
    EntityListOutput,
    EntityOutput,
    EntityUpdateInput,
    RelationDecideBatchInput,
    RelationDecideInput,
    RelationListInput,
    RelationListOutput,
    RelationProposeInput,
    RevisionCommitInput,
    RevisionListOutput,
    RevisionOutput,
    StoryEmptyInput,
    WorldEnsureInput,
    WorldOutput,
)
from .resource_kind import STORY_WORLD_KIND
from .tools import (
    StoryGraphQueryTool,
    StoryProposeRelationsTool,
    StoryRevisionsTool,
)


def _project_id(context) -> str:
    project_id = context.project_id
    if not project_id:
        raise ValueError("This operation requires a project scope.")
    return project_id


def register(host) -> None:
    store = StoryStateStore(host.runtime_info.data_path)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(STORY_WORLD_KIND, store.resolve)
    _register_operations(host, store)
    _register_tools(host, store)


def _register_operations(host, store: StoryStateStore) -> None:
    def worlds_ensure(input: WorldEnsureInput, context) -> WorldOutput:
        return store.ensure_world(_project_id(context), input.title)

    def worlds_get(_input, context) -> WorldOutput | None:
        return store.get_world(_project_id(context))

    def entities_list(_input, context) -> EntityListOutput:
        return EntityListOutput(entities=store.list_entities(_project_id(context)))

    def entities_create(input: EntityCreateInput, context) -> EntityOutput:
        return store.create_entity(
            _project_id(context),
            kind=input.kind,
            name=input.name,
            summary=input.summary,
        )

    def entities_update(input: EntityUpdateInput, context) -> EntityOutput:
        return store.update_entity(
            _project_id(context),
            input.entity_id,
            name=input.name,
            summary=input.summary,
        )

    def entities_delete(input: EntityIdInput, context) -> DeleteOutput:
        return DeleteOutput(
            deleted=store.delete_entity(_project_id(context), input.entity_id)
        )

    def relations_list(input: RelationListInput, context) -> RelationListOutput:
        return RelationListOutput(
            edges=store.list_edges(_project_id(context), status=input.status)
        )

    def relations_propose(input: RelationProposeInput, context) -> RelationListOutput:
        items = [
            dict(relation) if isinstance(relation, dict) else {
                "from_name": relation.from_name,
                "to_name": relation.to_name,
                "kind": relation.kind,
                "reason": relation.reason,
            }
            for relation in input.relations
        ]
        created, unknown = store.propose_relations(_project_id(context), items)
        if unknown:
            raise ValueError(
                "以下实体名不存在：" + "、".join(sorted(set(unknown)))
            )
        if not created:
            raise ValueError("所有提案都与既有待审或已确认关系重复。")
        return RelationListOutput(edges=created)

    def relations_decide(input: RelationDecideInput, context) -> RelationListOutput:
        edge = store.decide_edge(_project_id(context), input.edge_id, input.decision)
        return RelationListOutput(edges=(edge,))

    def relations_decide_batch(
        input: RelationDecideBatchInput, context
    ) -> RelationListOutput:
        decisions = [
            {"edge_id": decision.edge_id, "decision": decision.decision}
            for decision in input.decisions
        ]
        return RelationListOutput(
            edges=store.decide_batch(_project_id(context), decisions)
        )

    def revisions_commit(input: RevisionCommitInput, context) -> RevisionOutput:
        revision, confirmed_count = store.commit_revision(
            _project_id(context), input.note
        )
        return RevisionOutput(
            id=revision.id,
            seq=revision.seq,
            note=revision.note,
            confirmed_count=confirmed_count,
            created_at=revision.created_at,
        )

    def revisions_list(_input, context) -> RevisionListOutput:
        return RevisionListOutput(revisions=store.list_revisions(_project_id(context)))

    specs = (
        DlcOperationSpec(name="worlds.ensure", input_model=WorldEnsureInput, output_model=WorldOutput, handler=worlds_ensure, scope="project"),
        DlcOperationSpec(name="worlds.get", input_model=WorldEnsureInput, output_model=WorldOutput, handler=worlds_get, scope="project"),
        DlcOperationSpec(name="entities.list", input_model=StoryEmptyInput, output_model=EntityListOutput, handler=entities_list, scope="project"),
        DlcOperationSpec(name="entities.create", input_model=EntityCreateInput, output_model=EntityOutput, handler=entities_create, scope="project"),
        DlcOperationSpec(name="entities.update", input_model=EntityUpdateInput, output_model=EntityOutput, handler=entities_update, scope="project"),
        DlcOperationSpec(name="entities.delete", input_model=EntityIdInput, output_model=DeleteOutput, handler=entities_delete, scope="project"),
        DlcOperationSpec(name="relations.list", input_model=RelationListInput, output_model=RelationListOutput, handler=relations_list, scope="project"),
        DlcOperationSpec(name="relations.propose", input_model=RelationProposeInput, output_model=RelationListOutput, handler=relations_propose, scope="project"),
        DlcOperationSpec(name="relations.decide", input_model=RelationDecideInput, output_model=RelationListOutput, handler=relations_decide, scope="project"),
        DlcOperationSpec(name="relations.decide_batch", input_model=RelationDecideBatchInput, output_model=RelationListOutput, handler=relations_decide_batch, scope="project"),
        DlcOperationSpec(name="revisions.commit", input_model=RevisionCommitInput, output_model=RevisionOutput, handler=revisions_commit, scope="project"),
        DlcOperationSpec(name="revisions.list", input_model=StoryEmptyInput, output_model=RevisionListOutput, handler=revisions_list, scope="project"),
    )
    for spec in specs:
        host.operations.register(spec)


def _register_tools(host, store: StoryStateStore) -> None:
    host.tools.register(StoryGraphQueryTool(store))
    host.tools.register(StoryProposeRelationsTool(store))
    host.tools.register(StoryRevisionsTool(store))
