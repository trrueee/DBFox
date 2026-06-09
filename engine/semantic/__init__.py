"""Agent Semantic Understanding Layer — maps user business language to database objects.

Modules:
  alias            — SemanticAliasResolver (legacy)
  schema_linker    — SchemaLinker, SchemaLinkingResult (legacy)
  semantic_context — SchemaContextBuilder (legacy, renders DDL-style context)
  query_plan       — QueryPlan, QueryPlanBuilder (legacy)
  models           — SemanticResolution, ResolvedTerm, ResolvedMetric, etc.
  resolver         — SemanticResolver (LLM + verifier)
  verifier         — SemanticVerifier (deterministic catalog checks)
  prompts          — System prompt for semantic resolution
  tools            — semantic.resolve agent tool handler
"""

from engine.semantic.alias import AliasMatch, SemanticAliasResolver
from engine.semantic.query_plan import QueryDimension, QueryFilter, QueryJoin, QueryMetric, QueryPlan, QueryPlanBuilder
from engine.semantic.schema_linker import ColumnLink, SchemaLinker, SchemaLinkingResult, TableLink
from engine.semantic.semantic_context import SchemaContextBuilder
from engine.semantic.models import (
    Ambiguity,
    CandidateColumn,
    CandidateTable,
    JoinPathCandidate,
    ResolvedDimension,
    ResolvedFilter,
    ResolvedMetric,
    ResolvedTerm,
    SemanticResolution,
    SemanticSource,
)
from engine.semantic.verifier import SemanticVerifier, VerificationIssue, VerificationResult
from engine.semantic.resolver import SemanticResolver

__all__ = [
    # Legacy
    "AliasMatch",
    "SemanticAliasResolver",
    "ColumnLink",
    "SchemaLinker",
    "SchemaLinkingResult",
    "SchemaContextBuilder",
    "TableLink",
    "QueryDimension",
    "QueryFilter",
    "QueryJoin",
    "QueryMetric",
    "QueryPlan",
    "QueryPlanBuilder",
    # New agent semantic layer
    "Ambiguity",
    "CandidateColumn",
    "CandidateTable",
    "JoinPathCandidate",
    "ResolvedDimension",
    "ResolvedFilter",
    "ResolvedMetric",
    "ResolvedTerm",
    "SemanticResolution",
    "SemanticSource",
    "SemanticResolver",
    "SemanticVerifier",
    "VerificationIssue",
    "VerificationResult",
]
