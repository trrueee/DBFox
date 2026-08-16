"""Semantic contracts exported by tools to the Agent harness.

These capabilities describe what a successful observation proves. They are
stable domain contracts, not aliases for concrete tool names.
"""

from __future__ import annotations

from enum import StrEnum

import re

from pydantic import BaseModel, ConfigDict, field_validator


class ToolSemanticCapability(StrEnum):
    ENVIRONMENT_PROFILE = "environment_profile"
    SCHEMA_METADATA = "schema_metadata"
    SAMPLE_ROWS = "sample_rows"
    QUERY_RESULT = "query_result"
    RESULT_PROFILE = "result_profile"
    VALIDATED_QUERY = "validated_query"


_LEGACY_SEMANTIC_CAPABILITIES = frozenset(
    item.value for item in ToolSemanticCapability
)
_NAMESPACED_CAPABILITY_PATTERN = re.compile(
    r"^[a-z][a-z0-9_.-]*[.:][a-z][a-z0-9_.-]*$"
)


class ToolSemanticSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    produces: tuple[str, ...] = ()
    contributes_progress: bool = True
    publishes_artifact_references: bool = False

    @field_validator("produces")
    @classmethod
    def validate_open_capability_ids(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        for value in values:
            candidate = str(value)
            if candidate in _LEGACY_SEMANTIC_CAPABILITIES:
                continue
            if _NAMESPACED_CAPABILITY_PATTERN.fullmatch(candidate) is None:
                raise ValueError(
                    "New semantic capability must use a namespaced ID "
                    "like dbfox.workspace.file_snapshot"
                )
        return tuple(str(value) for value in values)
