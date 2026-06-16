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
    # Analysis tools
    "result_profile": "result.profile",
    "chart_suggest": "chart.suggest",
    "answer_synthesize": "answer.synthesize",
}

# Internal name → alias (reverse lookup, built once at import time)
INTERNAL_TO_ALIAS: dict[str, str] = {v: k for k, v in ALIAS_TO_INTERNAL.items()}

# Step-name ↔ internal-name bidirectional map.
# _step_name() in tool_node.py and _tool_name_from_step() in observe_node.py
# MUST both derive from this single source of truth.
STEP_NAME_MAP: dict[str, str] = {
    "schema.list_tables": "list_tables",
    "schema.describe_table": "describe_table",
    "schema.refresh_catalog": "refresh_catalog",
    "db.observe": "observe_database",
    "db.search": "search_database",
    "db.inspect": "inspect_database",
    "db.preview": "preview_table",
    "db.query": "query_database",
    "db.remember": "remember_database_semantics",
    "memory.search": "memory_search",
    "memory.write": "memory_write",
    "memory.delete": "memory_delete",
    "memory.summarize_session": "summarize_session",
    "result.profile": "profile_result",
    "chart.suggest": "suggest_chart",
    "answer.synthesize": "synthesize_answer",
    # New tool — step name equals internal name (identity mapping, but must
    # be present so _step_name() and _tool_name_from_step() handle it).
    "analyze_data": "analyze_data",
}

# Reverse lookup: step name → internal name.
# IMPORTANT: computed once at import time. If STEP_NAME_MAP is mutated after
# import, call _rebuild_step_name_reverse() to update this dict.
STEP_NAME_TO_INTERNAL: dict[str, str] = {}


def _rebuild_step_name_reverse() -> None:
    """Rebuild STEP_NAME_TO_INTERNAL from STEP_NAME_MAP."""
    STEP_NAME_TO_INTERNAL.clear()
    STEP_NAME_TO_INTERNAL.update({v: k for k, v in STEP_NAME_MAP.items()})


_rebuild_step_name_reverse()


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
