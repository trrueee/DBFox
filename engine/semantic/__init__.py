"""Semantic Understanding Layer — maps user business language to database objects.

Modules:
  alias            — SemanticAliasResolver
  schema_linker    — SchemaLinker, SchemaLinkingResult
  semantic_context — SchemaContextBuilder (renders DDL-style context)
"""

from engine.semantic.alias import AliasMatch, SemanticAliasResolver
from engine.semantic.schema_linker import ColumnLink, SchemaLinker, SchemaLinkingResult, TableLink
from engine.semantic.semantic_context import SchemaContextBuilder

__all__ = [
    "AliasMatch",
    "ColumnLink",
    "SchemaContextBuilder",
    "SchemaLinker",
    "SchemaLinkingResult",
    "SemanticAliasResolver",
    "TableLink",
]
