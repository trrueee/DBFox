"""Data models for the Memory Layer.

All memory records use a unified MemoryRecord envelope with typed
content payloads for different memory categories.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

MemoryType = Literal[
    "user_preference",
    "project_rule",
    "metric_definition",
    "schema_alias",
    "join_path",
    "successful_trajectory",
    "failure_learning",
    "artifact_reference",
    "conversation_summary",
]

MemorySource = Literal[
    "user_explicit",
    "agent_inferred",
    "system_generated",
    "admin_configured",
    "trajectory_eval",
]

MemoryStatus = Literal["active", "stale", "deleted", "pending_review"]


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=_new_id)
    namespace: tuple[str, ...] = ()

    type: MemoryType

    content: dict[str, Any] = Field(default_factory=dict)
    text: str = ""

    source: MemorySource = "system_generated"
    confidence: float = 1.0
    status: MemoryStatus = "active"

    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)
    expires_at: str | None = None

    source_run_id: str | None = None
    source_session_id: str | None = None
    datasource_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None

    tags: list[str] = Field(default_factory=list)

    @property
    def key(self) -> str:
        """Return a stable key built from namespace + id for Store compatibility."""
        parts = list(self.namespace) + [self.id]
        return "/".join(parts)


# ---------------------------------------------------------------------------
# Typed content models
# ---------------------------------------------------------------------------

class UserPreferenceContent(BaseModel):
    preference_type: Literal[
        "language", "answer_style", "export_format",
        "chart_style", "sql_style", "default_granularity",
    ]
    value: Any
    evidence: str = ""


class MetricDefinitionContent(BaseModel):
    metric_name: str
    business_definition: str
    sql_expression: str | None = None
    grain: str | None = None
    filters: list[str] = Field(default_factory=list)
    owner: str | None = None


class SchemaAliasContent(BaseModel):
    alias: str
    target_type: Literal["table", "column", "metric"] = "table"
    datasource_id: str = ""
    table_name: str | None = None
    column_name: str | None = None
    target: str = ""
    confidence: float = 0.8


class JoinPathContent(BaseModel):
    datasource_id: str = ""
    from_table: str = ""
    to_table: str = ""
    join_sql: str = ""
    path_tables: list[str] = Field(default_factory=list)
    confidence: float = 0.8


class SuccessfulTrajectoryContent(BaseModel):
    question_pattern: str = ""
    datasource_id: str = ""
    tools_used: list[str] = Field(default_factory=list)
    selected_tables: list[str] = Field(default_factory=list)
    final_sql: str | None = None
    result_summary: str | None = None


class FailureLearningContent(BaseModel):
    failure_type: str = ""
    error_message: str = ""
    attempted_tool: str | None = None
    attempted_sql: str | None = None
    lesson: str = ""


# ---------------------------------------------------------------------------
# Session memory
# ---------------------------------------------------------------------------

class SessionMemory(BaseModel):
    session_id: str
    user_id: str | None = None
    project_id: str | None = None
    datasource_id: str | None = None
    workspace_id: str | None = None

    recent_run_ids: list[str] = Field(default_factory=list)
    recent_artifact_ids: list[str] = Field(default_factory=list)

    last_question: str | None = None
    last_sql: str | None = None
    last_execution_id: str | None = None
    last_table_artifact_id: str | None = None
    last_result_artifact_id: str | None = None
    last_source_sql_artifact_id: str | None = None
    last_result_safe_sql: str | None = None
    last_result_sql_fingerprint: str | None = None
    last_chart_artifact_id: str | None = None
    last_report_artifact_id: str | None = None

    current_topic: str | None = None
    current_dataset_summary: str | None = None

    summary: str | None = None

    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)
