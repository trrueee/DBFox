"""Payload, input, and output contracts for the dbfox.story DLC."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .resource_kind import ENTITY_KINDS

EntityKind = Literal["character", "scene", "plotline"]
EdgeStatus = Literal["pending", "confirmed", "rejected"]


class WorldHandle(BaseModel):
    """Resolved story world handed to authorized tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    project_id: str
    title: str
    generation: int


class WorldOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    generation: int
    created_at: str
    updated_at: str


class EntityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: EntityKind
    name: str
    summary: str
    updated_at: str


class EntityListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entities: tuple[EntityOutput, ...] = ()


class RelationEdgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    from_entity_id: str
    from_name: str
    to_entity_id: str
    to_name: str
    kind: str
    reason: str
    status: EdgeStatus
    revision_id: str | None = None
    created_at: str
    decided_at: str | None = None


class RelationListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edges: tuple[RelationEdgeOutput, ...] = ()


class RevisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    seq: int
    note: str
    confirmed_count: int
    created_at: str


class RevisionListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revisions: tuple[RevisionOutput, ...] = ()


# ── Operation inputs ──


class WorldEnsureInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str | None = Field(default=None, max_length=120)


class EntityCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal[ENTITY_KINDS]  # type: ignore[misc]
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=2_000)


class EntityUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    entity_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=2_000)


class EntityIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    entity_id: str = Field(min_length=1, max_length=64)


class RelationEdgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_name: str = Field(min_length=1, max_length=120)
    to_name: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=60)
    reason: str = Field(default="", max_length=2_000)


class RelationProposeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    relations: tuple[RelationEdgeInput, ...] = Field(min_length=1, max_length=32)


class RelationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    edge_id: str = Field(min_length=1, max_length=64)
    decision: Literal["confirmed", "rejected", "pending"]


class RelationDecideInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    edge_id: str = Field(min_length=1, max_length=64)
    decision: Literal["confirmed", "rejected", "pending"]


class RelationDecideBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    decisions: tuple[RelationDecision, ...] = Field(min_length=1, max_length=64)


class RevisionCommitInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    note: str = Field(default="", max_length=500)


class RelationListInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: EdgeStatus | None = None


class DeleteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deleted: bool


class StoryEmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChapterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    seq: int
    title: str
    content: str
    updated_at: str


class ChapterListOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chapters: tuple[ChapterOutput, ...] = ()


class ChapterCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str = Field(min_length=1, max_length=160)
    content: str = Field(default="", max_length=100_000)


class ChapterUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    chapter_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, max_length=100_000)


class ChapterIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    chapter_id: str = Field(min_length=1, max_length=64)


class ChapterMoveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    chapter_id: str = Field(min_length=1, max_length=64)
    direction: Literal["up", "down"]


class StoryUpsertEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    world_id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["character", "scene", "plotline"] = "character"
    summary: str = Field(default="", max_length=2_000)


class StoryChaptersListInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    world_id: str | None = Field(default=None, min_length=1, max_length=64)


class EntityUpsertOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["created", "updated"]
    name: str
    kind: str
    summary: str


class ChapterReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    content: str
    updated_at: str


class ChapterWriteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["created", "updated"]
    chapter_id: str
    title: str
    length: int


class StoryChapterReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    world_id: str | None = Field(default=None, min_length=1, max_length=64)
    chapter_id: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=160)


class StoryWriteChapterInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    world_id: str | None = Field(default=None, min_length=1, max_length=64)
    chapter_id: str | None = Field(default=None, min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=100_000)


class StoryGraphQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    world_id: str | None = Field(default=None, min_length=1, max_length=64)
    entity_kind: Literal["character", "scene", "plotline"] | None = None
    name_contains: str | None = Field(default=None, max_length=120)


class StoryProposeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created_count: int
    created: tuple[dict[str, Any], ...] = ()
    message: str


class StoryRevisionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    world_id: str | None = Field(default=None, min_length=1, max_length=64)


class GraphFactsOutput(BaseModel):
    """Confirmed world facts exposed to the Agent. Never includes pending or
    rejected edges — rejected paths are author vetoes, not world truth."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entities: tuple[dict[str, Any], ...] = ()
    relations: tuple[dict[str, Any], ...] = ()
