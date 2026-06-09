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
    "followup_load_context": "followup.load_context",
    "schema_build_context": "schema.build_context",
    "query_plan_build": "query_plan.build",
    "sql_generate": "sql.generate",
    "sql_validate": "sql.validate",
    "sql_execute_readonly": "sql.execute_readonly",
    "sql_skip_execution": "sql.skip_execution",
    "sql_revise": "sql.revise",
    "result_profile": "result.profile",
    "chart_suggest": "chart.suggest",
    "followup_suggest": "followup.suggest",
    "answer_synthesize": "answer.synthesize",
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
