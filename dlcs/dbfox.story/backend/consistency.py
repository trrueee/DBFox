"""Completion guard for the story fact-check workflow."""

from __future__ import annotations

from dbfox_dlc_api import CompletionConstraintResult


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
        checks = [
            item
            for item in observations
            if item.status == "succeeded"
            and "dbfox.story.graph_check" in item.capabilities
        ]
        for write in writes:
            chapter = write.facts.get("chapter")
            generation = (
                chapter.get("checked_world_generation")
                if isinstance(chapter, dict)
                else None
            )
            if not any(
                check.sequence < write.sequence
                and check.facts.get("world_generation") == generation
                for check in checks
            ):
                return CompletionConstraintResult(
                    kind="missing",
                    reason="Each chapter write must use a preceding confirmed-facts snapshot.",
                    requirements=["story_graph_query_before_chapter_write"],
                )
        last_chapter = writes[-1].facts.get("chapter")
        last_generation = (
            last_chapter.get("checked_world_generation")
            if isinstance(last_chapter, dict)
            else None
        )
        if not any(
            check.sequence > writes[-1].sequence
            and check.facts.get("world_generation") == last_generation
            for check in checks
        ):
            return CompletionConstraintResult(
                kind="missing",
                reason=(
                    "Call story_graph_query now for the written chapter's world and verify "
                    f"world_generation {last_generation} before the final answer. A chapter read "
                    "or revisions list is not this check. Do not rewrite the saved chapter; "
                    "repeating the answer cannot satisfy the missing observation."
                ),
                requirements=["story_graph_query_after_chapter_write"],
            )
        return CompletionConstraintResult(
            kind="pass",
            reason="Chapter writes are bracketed by confirmed-facts checks.",
        )
