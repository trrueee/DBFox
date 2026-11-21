"""Untrusted, structured answer input for the native submit_answer function.

Only the model-to-Runtime boundary uses this contract. Evidence remains owned
by Terminalizer; the durable Markdown/Evidence and frontend contracts are unchanged.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from engine.tools.runtime.base import ToolInputModel


class AnswerPart(ToolInputModel):
    text: str = Field(
        min_length=1, max_length=32_000,
        description="Markdown fragment. Parts are concatenated verbatim; include needed newlines.",
    )
    citations: list[Annotated[str, Field(pattern=r"^artifact_[A-Za-z0-9_-]+$", max_length=128)]] = Field(
        default_factory=list, max_length=8,
        description="Exact observed Artifact IDs supporting this fragment; not Evidence IDs or permissions.",
    )

    @model_validator(mode="after")
    def validate_references(self) -> AnswerPart:
        if "{{cite:" in self.text:
            raise ValueError("Put Artifact IDs in citations instead of writing citation markup")
        if len(set(self.citations)) != len(self.citations):
            raise ValueError("Each fragment must cite an Artifact at most once")
        if self.citations and not self.text.strip():
            raise ValueError("Citations must accompany a non-blank claim")
        return self


class AnswerSubmission(ToolInputModel):
    parts: list[AnswerPart] = Field(
        min_length=1, max_length=64,
        description="The complete answer in reading order, with citations attached to the supported fragments.",
    )

    @model_validator(mode="after")
    def validate_size(self) -> AnswerSubmission:
        if not any(part.text.strip() for part in self.parts):
            raise ValueError("The answer must contain non-blank text")
        if sum(len(part.text) for part in self.parts) > 32_000:
            raise ValueError("The answer text exceeds its size limit")
        if sum(len(part.citations) for part in self.parts) > 64:
            raise ValueError("The answer exceeds its citation limit")
        return self

    @property
    def text(self) -> str:
        return "".join(
            part.text + "".join("{{cite:" + artifact_id + "}}" for artifact_id in part.citations)
            for part in self.parts
        )

    @property
    def cited_artifact_ids(self) -> set[str]:
        return {artifact_id for part in self.parts for artifact_id in part.citations}

    @property
    def citation_claims(self) -> list[str]:
        """Exact submitted fragment for each generated citation, in render order."""
        return [part.text.strip()[:1_000] for part in self.parts for _ in part.citations]
