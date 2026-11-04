"""Agent tools for entity editing and chapter authoring (dbfox.story).

These tools let the Agent modify the world and write chapters directly:
entities are upserted by name; chapters can be created, replaced, or appended. Every write is
version-tracked in the store with the author recorded (`author="ai"`), so
the reader view can show provenance and the author can diff or revert.
Relationship edges stay out of these tools on purpose — they keep their
proposal/review lifecycle.
"""

from __future__ import annotations

from dbfox_dlc_api import (
    BaseTool,
    ExtensionToolRunContext,
    ToolExecutionSpec,
    ToolInputError,
    ToolObservationProjection,
    ToolPolicy,
    ToolPresentation,
    ToolResourceRequirement,
    ToolSemanticSpec,
)

from .contracts import (
    ChapterCatalogListOutput,
    ChapterReadOutput,
    ChapterWriteOutput,
    EntityUpsertOutput,
    StoryAppendChapterInput,
    StoryChapterReadInput,
    StoryChaptersListInput,
    StoryUpsertEntityInput,
    StoryWriteChapterInput,
)
from .store import ChapterConflictError, StoryStateStore
from .resource_kind import STORY_WORLD_KIND
from .world_selection import select_world


def _require_generation(world, expected: int) -> None:
    if world.generation != expected:
        raise ToolInputError(
            "故事设定已变化；请重新调用 story_graph_query，并使用最新 world_generation。"
        )


class StoryUpsertEntityTool(BaseTool[StoryUpsertEntityInput, object]):
    name = "story_upsert_entity"
    group = "story"
    description = (
        "Create or update one story entity (character, scene, or plotline) by "
        "name. Use this when the story establishes or evolves a setting — for "
        "example after a chapter reveals new facts about a character. Updating "
        "keeps the entity identity and replaces the summary."
    )
    input_model = StoryUpsertEntityInput
    output_model = EntityUpsertOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        required_resources=(ToolResourceRequirement(kind=STORY_WORLD_KIND, selector_field="world_id"),),
        capabilities=(),
    )
    presentation = ToolPresentation(title="写入故事实体", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryUpsertEntityInput,
        context: ExtensionToolRunContext,
    ) -> EntityUpsertOutput:
        _ref, world = select_world(context, tool_input.world_id)
        existing = [
            entity
            for entity in self._store.list_entities(
                world.project_id, kind=tool_input.kind
            )
            if entity.name == tool_input.name
        ]
        if existing:
            updated = self._store.update_entity(
                world.project_id,
                existing[0].id,
                name=None,
                summary=tool_input.summary or None,
            )
            return EntityUpsertOutput(
                op="updated", name=updated.name, kind=updated.kind, summary=updated.summary
            )
        created = self._store.create_entity(
            world.project_id,
            kind=tool_input.kind,
            name=tool_input.name,
            summary=tool_input.summary,
        )
        return EntityUpsertOutput(
            op="created", name=created.name, kind=created.kind, summary=created.summary
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="故事实体写入失败。")
        return ToolObservationProjection(
            summary=f"已{('更新' if output['op'] == 'updated' else '创建')}实体「{output['name']}」。",
            facts={"entity": dict(output)},
        )


class StoryChaptersListTool(BaseTool[StoryChaptersListInput, ChapterCatalogListOutput]):
    name = "story_chapters_list"
    group = "story"
    description = (
        "List the chapters of the project's story in reading order: id, title, "
        "and last-updated time. Content is not included; read a chapter with "
        "story_chapter_read."
    )
    input_model = StoryChaptersListInput
    output_model = ChapterCatalogListOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        required_resources=(ToolResourceRequirement(kind=STORY_WORLD_KIND, selector_field="world_id"),),
        capabilities=(),
    )
    presentation = ToolPresentation(title="列出章节", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryChaptersListInput,
        context: ExtensionToolRunContext,
    ) -> ChapterCatalogListOutput:
        _ref, world = select_world(context, tool_input.world_id)
        return ChapterCatalogListOutput(
            chapters=self._store.list_chapter_catalog(world.project_id)
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="章节列表查询失败。")
        chapters = list(output.get("chapters") or [])
        return ToolObservationProjection(
            summary=f"故事共有 {len(chapters)} 章。",
            facts={
                "chapters": [
                    {"id": chapter.get("id"), "title": chapter.get("title")}
                    for chapter in chapters
                    if isinstance(chapter, dict)
                ]
            },
        )


class StoryChapterReadTool(BaseTool[StoryChapterReadInput, object]):
    name = "story_chapter_read"
    group = "story"
    description = (
        "Read one chapter's full content by chapter_id or by exact title. Use "
        "before writing a sequel chapter or checking consistency."
    )
    input_model = StoryChapterReadInput
    output_model = ChapterReadOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        required_resources=(ToolResourceRequirement(kind=STORY_WORLD_KIND, selector_field="world_id"),),
        capabilities=(),
    )
    presentation = ToolPresentation(title="阅读章节", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryChapterReadInput,
        context: ExtensionToolRunContext,
    ) -> ChapterReadOutput:
        _ref, world = select_world(context, tool_input.world_id)
        chapters = self._store.list_chapters(world.project_id)
        chapter = None
        if tool_input.chapter_id:
            chapter = next(
                (item for item in chapters if item.id == tool_input.chapter_id), None
            )
            if chapter is None:
                raise ToolInputError("指定章节不存在。")
        elif tool_input.title:
            chapter = next(
                (item for item in chapters if item.title == tool_input.title), None
            )
            if chapter is None:
                raise ToolInputError(f"没有标题为「{tool_input.title}」的章节。")
        else:
            raise ToolInputError("需要提供 chapter_id 或 title 之一。")
        return ChapterReadOutput(
            id=chapter.id,
            title=chapter.title,
            content=chapter.content,
            content_path=chapter.content_path,
            content_sha256=chapter.content_sha256,
            updated_at=chapter.updated_at,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="章节阅读失败。")
        return ToolObservationProjection(
            summary=f"已读取章节「{output['title']}」（{len(output['content'])} 字）。",
            facts={"chapter": dict(output)},
        )


class StoryWriteChapterTool(BaseTool[StoryWriteChapterInput, object]):
    name = "story_write_chapter"
    group = "story"
    description = (
        "Write a chapter's full content. With no chapter_id, a new chapter is "
        "appended (title must be unique); with a chapter_id the chapter is "
        "replaced. Every write is version-tracked with author recorded, so the "
        "human author can review the history. Call story_graph_query first and "
        "provide its world_generation. Existing chapters must first be read with "
        "story_chapter_read and use its content_sha256 for compare-and-swap. "
        "Write the complete chapter text "
        "in Chinese prose — never outlines or bullet summaries."
    )
    input_model = StoryWriteChapterInput
    output_model = ChapterWriteOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        required_resources=(ToolResourceRequirement(kind=STORY_WORLD_KIND, selector_field="world_id"),),
        backend="isolated_process",
        timeout_seconds=60,
        recovery="never_retry",
        capabilities=("filesystem_write",),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.story.chapter_write",))
    presentation = ToolPresentation(title="写章节", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryWriteChapterInput,
        context: ExtensionToolRunContext,
    ) -> ChapterWriteOutput:
        _ref, world = select_world(context, tool_input.world_id)
        _require_generation(world, tool_input.expected_world_generation)
        if tool_input.chapter_id:
            try:
                chapter = self._store.update_chapter(
                    world.project_id,
                    tool_input.chapter_id,
                    title=tool_input.title,
                    content=tool_input.content,
                    author="ai",
                    expected_sha256=str(tool_input.expected_chapter_sha256),
                )
            except ChapterConflictError as exc:
                raise ToolInputError(str(exc)) from exc
            return ChapterWriteOutput(
                op="updated",
                chapter_id=chapter.id,
                title=chapter.title,
                length=len(chapter.content),
                checked_world_generation=world.generation,
            )
        duplicate = any(
            chapter.title == tool_input.title
            for chapter in self._store.list_chapters(world.project_id)
        )
        if duplicate:
            raise ToolInputError(
                f"已有标题为「{tool_input.title}」的章节；如需改写请提供 chapter_id。"
            )
        chapter = self._store.create_chapter(
            world.project_id,
            title=tool_input.title,
            content=tool_input.content,
            author="ai",
        )
        return ChapterWriteOutput(
            op="created",
            chapter_id=chapter.id,
            title=chapter.title,
            length=len(chapter.content),
            checked_world_generation=world.generation,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="章节写作失败。")
        return ToolObservationProjection(
            summary=(
                f"已{('改写' if output['op'] == 'updated' else '写完')}章节"
                f"「{output['title']}」（{output['length']} 字），等待作者阅读。"
            ),
            facts={"chapter": dict(output)},
        )


class StoryAppendChapterTool(BaseTool[StoryAppendChapterInput, object]):
    name = "story_append_chapter"
    group = "story"
    description = (
        "Append prose to an existing chapter without resending its current text. "
        "Call story_graph_query first and provide its world_generation. The resulting "
        "complete chapter is stored as a new AI-authored version. Read the chapter "
        "first and provide its content_sha256 for compare-and-swap."
    )
    input_model = StoryAppendChapterInput
    output_model = ChapterWriteOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(
        required_resources=(ToolResourceRequirement(kind=STORY_WORLD_KIND, selector_field="world_id"),),
        backend="isolated_process",
        timeout_seconds=60,
        recovery="never_retry",
        capabilities=("filesystem_write",),
    )
    semantics = ToolSemanticSpec(produces=("dbfox.story.chapter_write",))
    presentation = ToolPresentation(title="续写章节", category="manage")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryAppendChapterInput,
        context: ExtensionToolRunContext,
    ) -> ChapterWriteOutput:
        _ref, world = select_world(context, tool_input.world_id)
        _require_generation(world, tool_input.expected_world_generation)
        try:
            chapter = self._store.append_chapter(
                world.project_id,
                tool_input.chapter_id,
                content=tool_input.content,
                author="ai",
                expected_sha256=tool_input.expected_chapter_sha256,
            )
        except ValueError as exc:
            raise ToolInputError(str(exc)) from exc
        return ChapterWriteOutput(
            op="updated",
            chapter_id=chapter.id,
            title=chapter.title,
            length=len(chapter.content),
            checked_world_generation=world.generation,
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="章节续写失败。")
        return ToolObservationProjection(
            summary=f"已续写章节「{output['title']}」，当前共 {output['length']} 字。",
            facts={"chapter": dict(output)},
        )
