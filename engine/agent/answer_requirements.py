"""User-admitted delivery requirements; model proposals cannot edit this policy."""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class AnswerRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: Literal["when_observed", "required"] = Field(
        default="when_observed",
        description=(
            "Require structured submit_answer citations when public Artifacts have been observed, "
            "or require at least one observed source even when none is available yet. "
            "This delivery requirement grants no access and does not prove task correctness."
        ),
    )

    def is_satisfied(
        self,
        *,
        submitted_artifact_ids: Collection[str] | None,
        citable_artifact_ids: Collection[str],
        has_observed_public_artifacts: bool = False,
    ) -> bool:
        if self.evidence == "when_observed" and not (has_observed_public_artifacts or citable_artifact_ids):
            return True
        return submitted_artifact_ids is not None and bool(
            set(submitted_artifact_ids).intersection(citable_artifact_ids)
        )
