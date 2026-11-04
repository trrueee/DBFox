"""Operations, resources, and tool registration for the dbfox.story DLC."""

from __future__ import annotations

from dbfox_dlc_api import DlcOperationError, DlcOperationSpec

from .store import ChapterConflictError, StoryStateStore
from .contracts import (
    ChapterCreateInput,
    ChapterAppendInput,
    ChapterCatalogListOutput,
    ChapterIdInput,
    ChapterMoveInput,
    ChapterOutput,
    ChapterUpdateInput,
    ChapterVersionIdInput,
    ChapterVersionListOutput,
    ChapterVersionOutput,
    ChapterVersionRestoreInput,
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
from .chapter_tools import (
    StoryAppendChapterTool,
    StoryChapterReadTool,
    StoryChaptersListTool,
    StoryUpsertEntityTool,
    StoryWriteChapterTool,
)
from .consistency import StoryChapterConsistencyConstraint
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


def _chapter_conflict(exc: ChapterConflictError) -> DlcOperationError:
    return DlcOperationError(
        code="STORY_CHAPTER_CONFLICT",
        message=str(exc),
        status_code=409,
    )


def register(host) -> None:
    store = StoryStateStore(host.runtime_info.data_path)
    host.resources.register_provider(store.list_resources)
    host.resources.register_resolver(STORY_WORLD_KIND, store.resolve)
    _register_operations(host, store)
    _register_tools(host, store)
    host.completion.register_constraint(StoryChapterConsistencyConstraint())


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

    def chapters_list(_input, context) -> ChapterCatalogListOutput:
        return ChapterCatalogListOutput(
            chapters=store.list_chapter_catalog(_project_id(context))
        )

    def chapters_read(input: ChapterIdInput, context) -> ChapterOutput:
        return store.get_chapter(_project_id(context), input.chapter_id)

    def chapters_create(input: ChapterCreateInput, context) -> ChapterOutput:
        return store.create_chapter(
            _project_id(context), title=input.title, content=input.content, author="author"
        )

    def chapters_update(input: ChapterUpdateInput, context) -> ChapterOutput:
        try:
            return store.update_chapter(
                _project_id(context),
                input.chapter_id,
                title=input.title,
                content=input.content,
                author="author",
                expected_sha256=input.expected_sha256,
            )
        except ChapterConflictError as exc:
            raise _chapter_conflict(exc) from exc

    def chapters_append(input: ChapterAppendInput, context) -> ChapterOutput:
        try:
            return store.append_chapter(
                _project_id(context),
                input.chapter_id,
                content=input.content,
                author="author",
                expected_sha256=input.expected_sha256,
            )
        except ChapterConflictError as exc:
            raise _chapter_conflict(exc) from exc

    def chapters_delete(input: ChapterIdInput, context) -> DeleteOutput:
        return DeleteOutput(deleted=store.delete_chapter(_project_id(context), input.chapter_id))

    def chapters_move(input: ChapterMoveInput, context) -> ChapterCatalogListOutput:
        store.move_chapter(_project_id(context), input.chapter_id, input.direction)
        return ChapterCatalogListOutput(
            chapters=store.list_chapter_catalog(_project_id(context))
        )

    def chapter_versions_list(
        input: ChapterIdInput,
        context,
    ) -> ChapterVersionListOutput:
        return ChapterVersionListOutput(
            versions=store.list_chapter_versions(
                _project_id(context),
                input.chapter_id,
            )
        )

    def chapter_versions_read(
        input: ChapterVersionIdInput,
        context,
    ) -> ChapterVersionOutput:
        return store.get_chapter_version(
            _project_id(context),
            input.chapter_id,
            input.version_id,
        )

    def chapter_versions_restore(
        input: ChapterVersionRestoreInput,
        context,
    ) -> ChapterOutput:
        try:
            return store.restore_chapter_version(
                _project_id(context),
                input.chapter_id,
                input.version_id,
                expected_sha256=input.expected_sha256,
                author="author",
            )
        except ChapterConflictError as exc:
            raise _chapter_conflict(exc) from exc

    specs: tuple[DlcOperationSpec, ...] = (
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
    specs = specs + (
        DlcOperationSpec(name="chapters.list", input_model=StoryEmptyInput, output_model=ChapterCatalogListOutput, handler=chapters_list, scope="project"),
        DlcOperationSpec(name="chapters.read", input_model=ChapterIdInput, output_model=ChapterOutput, handler=chapters_read, scope="project"),
        DlcOperationSpec(name="chapters.create", input_model=ChapterCreateInput, output_model=ChapterOutput, handler=chapters_create, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="chapters.update", input_model=ChapterUpdateInput, output_model=ChapterOutput, handler=chapters_update, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="chapters.append", input_model=ChapterAppendInput, output_model=ChapterOutput, handler=chapters_append, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="chapters.delete", input_model=ChapterIdInput, output_model=DeleteOutput, handler=chapters_delete, scope="project", capabilities=("filesystem_write",)),
        DlcOperationSpec(name="chapters.move", input_model=ChapterMoveInput, output_model=ChapterCatalogListOutput, handler=chapters_move, scope="project"),
        DlcOperationSpec(name="chapter_versions.list", input_model=ChapterIdInput, output_model=ChapterVersionListOutput, handler=chapter_versions_list, scope="project"),
        DlcOperationSpec(name="chapter_versions.read", input_model=ChapterVersionIdInput, output_model=ChapterVersionOutput, handler=chapter_versions_read, scope="project"),
        DlcOperationSpec(name="chapter_versions.restore", input_model=ChapterVersionRestoreInput, output_model=ChapterOutput, handler=chapter_versions_restore, scope="project", capabilities=("filesystem_write",)),
    )
    for spec in specs:
        host.operations.register(spec)


def _register_tools(host, store: StoryStateStore) -> None:
    host.tools.register(StoryGraphQueryTool(store))
    host.tools.register(StoryProposeRelationsTool(store))
    host.tools.register(StoryRevisionsTool(store))
    host.tools.register(StoryUpsertEntityTool(store))
    host.tools.register(StoryChaptersListTool(store))
    host.tools.register(StoryChapterReadTool(store))
    host.tools.register(StoryWriteChapterTool(store))
    host.tools.register(StoryAppendChapterTool(store))
