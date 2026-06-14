from __future__ import annotations

"""Model-facing tool-name aliases.

OpenAI-compatible function-calling providers often restrict function/tool names
to [a-zA-Z0-9_-] and may reject names containing dots (.).  DataBox internal
tool names use dots as namespace separators (``schema.build_context``,
``sql.generate``, etc.).

This module provides a bidirectional mapping so that:

* The LLM sees alias names (e.g. ``sql_generate``).
* All internal logic continues to use the dotted internal name.

Adding a new tool: just add an entry to ALIAS_TO_INTERNAL.
"""

# Alias → internal name (underscore-safe names for model-facing usage)
ALIAS_TO_INTERNAL: dict[str, str] = {
    # Environment tools
    "schema_list_tables": "schema.list_tables",
    "schema_describe_table": "schema.describe_table",
    "schema_refresh_catalog": "schema.refresh_catalog",
    # db.* exploration tools
    "db_observe": "db.observe",
    "db_search": "db.search",
    "db_inspect": "db.inspect",
    "db_preview": "db.preview",
    "db_query": "db.query",
    "db_remember": "db.remember",
    # Escalate
    "escalate_tool_group": "escalate.tool_group",
    # Memory tools
    "memory_search": "memory.search",
    "memory_write": "memory.write",
    "memory_delete": "memory.delete",
    "memory_summarize_session": "memory.summarize_session",
}

# Internal name → alias (reverse lookup, built once at import time)
INTERNAL_TO_ALIAS: dict[str, str] = {v: k for k, v in ALIAS_TO_INTERNAL.items()}


def to_alias(internal_name: str) -> str:
    """Return the model-facing alias for an internal tool name.

    If no alias is defined, the internal name is returned unchanged.
    """
    return INTERNAL_TO_ALIAS.get(internal_name, internal_name)


def to_internal(alias: str) -> str:
    """Return the internal tool name for a model-supplied alias.

    If the name is already an internal name (no alias defined), it is
    returned unchanged so the mapping is idempotent.
    """
    return ALIAS_TO_INTERNAL.get(alias, alias)


def is_alias(name: str) -> bool:
    """Check whether *name* is a known model-facing alias."""
    return name in ALIAS_TO_INTERNAL


def is_internal(name: str) -> bool:
    """Check whether *name* is a known internal tool name."""
    return name in INTERNAL_TO_ALIAS
