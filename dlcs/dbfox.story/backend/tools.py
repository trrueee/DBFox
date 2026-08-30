"""Agent-facing tools contributed by the dbfox.story DLC.

Three rules encoded here:
- tools never emit or accept coordinates (layout is frontend view state);
- the graph query exposes CONFIRMED facts only (pending/rejected stay in the
  author workspace, never enter a Run);
- proposals always land in the batch-review queue — the author decides.
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
)

from .contracts import (
    GraphFactsOutput,
    RelationProposeInput,
    RevisionListOutput,
    StoryGraphQueryInput,
    StoryProposeOutput,
    StoryRevisionsInput,
)
from .store import StoryStateStore
from .world_selection import select_world

class StoryGraphQueryTool(BaseTool[StoryGraphQueryInput, GraphFactsOutput]):
    name = "story_graph_query"
    group = "story"
    description = (
        "Read the confirmed facts of the project's story world: entities "
        "(characters, scenes, plotlines) and confirmed relations with kinds "
        "and reasons. Pending proposals and rejected vetoes are intentionally "
        "excluded. Call this before writing any chapter so the prose stays "
        "consistent with established facts."
    )
    input_model = StoryGraphQueryInput
    output_model = GraphFactsOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(capabilities=())
    presentation = ToolPresentation(title="查询故事设定", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryGraphQueryInput,
        context: ExtensionToolRunContext,
    ) -> GraphFactsOutput:
        _ref, world = select_world(context, tool_input.world_id)
        entities, relations = self._store.graph_facts(
            world.project_id,
            entity_kind=tool_input.entity_kind,
            name_contains=tool_input.name_contains,
        )
        return GraphFactsOutput(entities=entities, relations=relations)

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="故事设定查询失败。")
        return ToolObservationProjection(
            summary=(
                f"已读取故事设定：{len(output.entities)} 个实体、"
                f"{len(output.relations)} 条既定关系。"
            ),
            facts={
                "entities": list(output.entities),
                "relations": list(output.relations),
            },
        )


class StoryProposeRelationsTool(BaseTool[RelationProposeInput, StoryProposeOutput]):
    name = "story_propose_relations"
    group = "story"
    description = (
        "Propose new relationships between existing story entities. Each "
        "proposal needs from_name, to_name, a short relation kind (for example "
        "师徒/宿敌/同盟), and a reason grounded in the story. Proposals land in "
        "the author's batch-review queue as pending edges; they do NOT become "
        "world facts until the author confirms them."
    )
    input_model = RelationProposeInput
    output_model = StoryProposeOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(capabilities=())
    presentation = ToolPresentation(title="提出关系提案", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: RelationProposeInput,
        context: ExtensionToolRunContext,
    ) -> StoryProposeOutput:
        _ref, world = select_world(context, tool_input.world_id)
        items = [
            {
                "from_name": relation.from_name,
                "to_name": relation.to_name,
                "kind": relation.kind,
                "reason": relation.reason,
            }
            for relation in tool_input.relations
        ]
        created, unknown = self._store.propose_relations(world.project_id, items)
        if unknown:
            raise ToolInputError(
                "以下实体名不存在于故事世界中，请先用实体创建流程补充："
                + "、".join(sorted(set(unknown)))
            )
        if not created:
            raise ToolInputError("所有提案都与既有待审或已确认关系重复，未创建新提案。")
        return StoryProposeOutput(
            created_count=len(created),
            created=[
                {
                    "from": edge.from_name,
                    "to": edge.to_name,
                    "kind": edge.kind,
                    "reason": edge.reason,
                }
                for edge in created
            ],
            message="提案已进入作者审阅队列，等待确认或否决。",
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="关系提案提交失败。")
        return ToolObservationProjection(
            summary=(
                f"已提交 {output.created_count} 条关系提案，等待作者批量审阅。"
                "提案在确认前不是世界事实。"
            ),
            facts={"created": list(output.created)},
        )


class StoryRevisionsTool(BaseTool[StoryRevisionsInput, RevisionListOutput]):
    name = "story_revisions"
    group = "story"
    description = (
        "List the immutable revisions of the story world. Each revision is a "
        "batch of confirmed relations; revision history is append-only and can "
        "be used to check what the world knew at any point."
    )
    input_model = StoryRevisionsInput
    output_model = RevisionListOutput
    version = "1"
    policy = ToolPolicy(risk_level="safe")
    execution = ToolExecutionSpec(capabilities=())
    presentation = ToolPresentation(title="查询修订历史", category="explore")

    def __init__(self, store: StoryStateStore) -> None:
        self._store = store

    def run(
        self,
        tool_input: StoryRevisionsInput,
        context: ExtensionToolRunContext,
    ) -> RevisionListOutput:
        _ref, world = select_world(context, tool_input.world_id)
        return RevisionListOutput(revisions=self._store.list_revisions(world.project_id))

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="修订历史查询失败。")
        return ToolObservationProjection(
            summary=f"故事世界共有 {len(output.revisions)} 个不可变修订。",
            facts={},
        )
