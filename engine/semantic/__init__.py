"""Semantic Understanding Layer — maps user business language to database objects.

Modules:
  alias            — SemanticAliasResolver
  schema_linker    — SchemaLinker, SchemaLinkingResult
  semantic_context — SchemaContextBuilder (renders DDL-style context)
  models           — SemanticResolution, ResolvedTerm, ResolvedMetric, etc.
  resolver         — SemanticResolver (LLM + verifier)
  verifier         — SemanticVerifier (deterministic catalog checks)
  prompts          — System prompt for semantic resolution
  tools            — semantic.resolve agent tool handler
"""

from engine.semantic.alias import AliasMatch, SemanticAliasResolver
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
    "AliasMatch",
    "Ambiguity",
    "CandidateColumn",
    "CandidateTable",
    "ColumnLink",
    "JoinPathCandidate",
    "ResolvedDimension",
    "ResolvedFilter",
    "ResolvedMetric",
    "ResolvedTerm",
    "SchemaContextBuilder",
    "SchemaLinker",
    "SchemaLinkingResult",
    "SemanticAliasResolver",
    "SemanticResolution",
    "SemanticResolver",
    "SemanticSource",
    "SemanticVerifier",
    "TableLink",
    "VerificationIssue",
    "VerificationResult",
]
