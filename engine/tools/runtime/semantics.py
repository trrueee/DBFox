"""Semantic contracts exported by tools to the Agent harness.

These capabilities describe what a successful observation proves. They are
stable domain contracts, not aliases for concrete tool names.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ToolSemanticCapability(StrEnum):
    ENVIRONMENT_PROFILE = "environment_profile"
    SCHEMA_METADATA = "schema_metadata"
    SAMPLE_ROWS = "sample_rows"
    QUERY_RESULT = "query_result"
    RESULT_PROFILE = "result_profile"
    VALIDATED_QUERY = "validated_query"


class ToolSemanticSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    produces: tuple[ToolSemanticCapability, ...] = ()
    contributes_progress: bool = True
    publishes_artifact_references: bool = False
