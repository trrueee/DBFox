"""Agent Semantic Layer models.

These models represent BUSINESS SEMANTICS — terms, metrics, dimensions,
join paths — not database schema.  Schema facts come from the Environment layer.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SemanticSource(str, Enum):
    """Origin of a semantic fact.  Lower sources must not be treated as verified."""

    verified_project_semantic = "verified_project_semantic"     # curated by team
    database_metadata = "database_metadata"                      # FK, PK, column types
    historical_accepted_sql = "historical_accepted_sql"          # previously approved SQL
    llm_inference = "llm_inference"                              # LLM reasoned
    ephemeral_hypothesis = "ephemeral_hypothesis"                # transient guess


class ResolvedTerm(BaseModel):
    """A business term mapped to database objects."""

    term: str = Field(description="The original business term from the user, e.g. 'GMV', '活跃用户'.")
    definition: str = Field(description="Human-readable definition.")
    mapped_table: str | None = Field(default=None, description="Table this term maps to, if any.")
    mapped_column: str | None = Field(default=None, description="Column this term maps to, if any.")
    mapped_expression: str | None = Field(default=None, description="SQL expression, e.g. 'SUM(total_amount)'.")
    source: SemanticSource = Field(default=SemanticSource.llm_inference)


class ResolvedMetric(BaseModel):
    """A business metric (aggregatable value)."""

    name: str = Field(description="Metric name, e.g. 'GMV', 'DAU'.")
    definition: str = Field(description="Human-readable definition.")
    expression: str | None = Field(default=None, description="SQL aggregation expression.")
    table: str | None = Field(default=None)
    column: str | None = Field(default=None)
    source: SemanticSource = Field(default=SemanticSource.llm_inference)


class ResolvedDimension(BaseModel):
    """A business dimension (group-by / slice-by attribute)."""

    name: str = Field(description="Dimension name, e.g. '日期', '地区'.")
    definition: str = Field(default=None, description="Human-readable definition.")  # type: ignore[assignment]
    table: str | None = Field(default=None)
    column: str | None = Field(default=None)
    grain: str | None = Field(default=None, description="Time grain: day, week, month, quarter, year.")
    source: SemanticSource = Field(default=SemanticSource.llm_inference)


class ResolvedFilter(BaseModel):
    """A business filter condition."""

    description: str = Field(description="Natural language filter description.")
    expression: str | None = Field(default=None, description="SQL WHERE clause fragment.")
    table: str | None = Field(default=None)
    column: str | None = Field(default=None)
    source: SemanticSource = Field(default=SemanticSource.llm_inference)


class JoinPathCandidate(BaseModel):
    """A candidate join path between two or more tables."""

    tables: list[str] = Field(description="Tables involved in the join.")
    joins: list[str] = Field(description="Join conditions, e.g. ['orders.user_id = users.id'].")
    source: Literal["foreign_key", "user_defined", "history", "naming_convention", "llm_inferred"] = "llm_inferred"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class CandidateTable(BaseModel):
    """A table identified as relevant to the user's question."""

    table_name: str
    relevance: str = Field(description="Why this table is relevant.")
    columns_of_interest: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CandidateColumn(BaseModel):
    """A column identified as relevant."""

    table_name: str
    column_name: str
    relevance: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Ambiguity(BaseModel):
    """An ambiguity detected in the user's question."""

    description: str = Field(description="What is ambiguous.")
    possible_interpretations: list[str] = Field(default_factory=list)
    suggested_clarification: str | None = None


class SemanticResolution(BaseModel):
    """Complete semantic resolution for a user question.

    Produced by SemanticResolver.  Used by the ReAct model and SQL generator
    to understand business intent before writing queries.
    """

    user_goal: str = Field(description="One-sentence summary of what the user wants.")

    task_shape: Literal[
        "schema_question",
        "detail_lookup",
        "aggregation",
        "trend",
        "comparison",
        "ranking",
        "funnel",
        "cohort",
        "anomaly_detection",
        "result_explanation",
        "unknown",
    ] = "unknown"

    resolved_terms: list[ResolvedTerm] = Field(default_factory=list)
    resolved_metrics: list[ResolvedMetric] = Field(default_factory=list)
    resolved_dimensions: list[ResolvedDimension] = Field(default_factory=list)
    resolved_filters: list[ResolvedFilter] = Field(default_factory=list)

    candidate_tables: list[CandidateTable] = Field(default_factory=list)
    candidate_columns: list[CandidateColumn] = Field(default_factory=list)
    join_paths: list[JoinPathCandidate] = Field(default_factory=list)

    ambiguity: list[Ambiguity] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    confidence: Literal["high", "medium", "low"] = "medium"
    sources_used: list[SemanticSource] = Field(default_factory=list)

    semantic_context_text: str = Field(
        default="",
        description="Rendered text block for injection into model context and SQL generation.",
    )
