"""Completion guard for the story fact-check workflow."""

from __future__ import annotations

from dbfox_dlc_api import CompletionConstraintResult, ResourceScopeRef

from .resource_kind import STORY_WORLD_KIND


def _world_ref(refs: tuple[ResourceScopeRef, ...]) -> ResourceScopeRef | None:
    return next((ref for ref in refs if ref.kind == STORY_WORLD_KIND), None)


class StoryChapterConsistencyConstraint:
    id = "dbfox.story.chapter_consistency"

    def evaluate(self, *, context, model_result) -> CompletionConstraintResult:
        del model_result
        observations = sorted(context.observations, key=lambda item: item.sequence)
        writes = [
            item
            for item in observations
            if item.status == "succeeded"
            and "dbfox.story.chapter_write" in item.capabilities
        ]
        if not writes:
            return CompletionConstraintResult(
                kind="pass",
                reason="No chapter write requires a story consistency check.",
            )
        checks: dict[tuple[ResourceScopeRef, int], list[int]] = {}
        for observation in observations:
            if observation.status != "succeeded" or "dbfox.story.graph_check" not in observation.capabilities:
                continue
            world = _world_ref(observation.resource_refs)
            generation = observation.facts.get("world_generation")
            if world is not None and type(generation) is int and generation > 0:
                checks.setdefault((world, generation), []).append(observation.sequence)

        latest_writes: dict[str, tuple[int, int, int]] = {}
        for write in writes:
            chapter = write.facts.get("chapter")
            generation = (
                chapter.get("checked_world_generation")
                if isinstance(chapter, dict)
                else None
            )
            world = _world_ref(write.resource_refs)
            if world is not None and type(generation) is int:
                sequences = checks.get((world, generation))
                if sequences and sequences[0] < write.sequence:
                    latest_writes[world.id] = (write.sequence, sequences[-1], generation)
                    continue
            return CompletionConstraintResult(
                kind="missing",
                reason="Each chapter write needs a preceding facts check for its exact world resource and generation.",
                requirements=["story_graph_query_before_chapter_write"],
            )
        for world_id, (write_sequence, check_sequence, generation) in latest_writes.items():
            if check_sequence <= write_sequence:
                return CompletionConstraintResult(
                    kind="missing",
                    reason=(
                        f"Call story_graph_query for world_id {world_id} after its last chapter write "
                        f"and verify world_generation {generation} before delivering the answer. "
                        "Leave the saved chapter intact."
                    ),
                    requirements=["story_graph_query_after_chapter_write"],
                )
        return CompletionConstraintResult(
            kind="pass",
            reason="Chapter writes are bracketed by confirmed-facts checks.",
        )
