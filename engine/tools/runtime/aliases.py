from __future__ import annotations

"""Canonical tool-name alias maps shared by runtime and agent nodes."""

ALIAS_TO_INTERNAL: dict[str, str] = {
    "schema_list_tables": "schema.list_tables",
    "schema_list_tables_page": "schema.list_tables_page",
    "schema_expand_related_tables": "schema.expand_related_tables",
    "schema_describe_table": "schema.describe_table",
    "schema_refresh_catalog": "schema.refresh_catalog",
    "sql_validate": "sql.validate",
    "sql_execute_readonly": "sql.execute_readonly",
    "db_observe": "db.observe",
    "db_search": "db.search",
    "db_inspect": "db.inspect",
    "db_preview": "db.preview",
    "db_query": "db.query",
    "escalate_tool_group": "escalate.tool_group",
    "chart_suggest": "chart.suggest",
    "answer_synthesize": "answer.synthesize",
}

INTERNAL_TO_ALIAS: dict[str, str] = {v: k for k, v in ALIAS_TO_INTERNAL.items()}

STEP_NAME_MAP: dict[str, str] = {
    "schema.list_tables": "list_tables",
    "schema.list_tables_page": "list_tables_page",
    "schema.expand_related_tables": "expand_related_tables",
    "schema.describe_table": "describe_table",
    "schema.refresh_catalog": "refresh_catalog",
    "sql.validate": "validate_sql",
    "sql.execute_readonly": "execute_readonly",
    "db.observe": "observe_database",
    "db.search": "search_database",
    "db.inspect": "inspect_database",
    "db.preview": "preview_table",
    "db.query": "query_database",
    "chart.suggest": "suggest_chart",
    "answer.synthesize": "synthesize_answer",
}

STEP_NAME_TO_INTERNAL: dict[str, str] = {}


def _rebuild_step_name_reverse() -> None:
    STEP_NAME_TO_INTERNAL.clear()
    STEP_NAME_TO_INTERNAL.update({v: k for k, v in STEP_NAME_MAP.items()})


_rebuild_step_name_reverse()


def to_alias(internal_name: str) -> str:
    return INTERNAL_TO_ALIAS.get(internal_name, internal_name)


def to_internal(alias: str) -> str:
    return ALIAS_TO_INTERNAL.get(alias, alias)


def is_alias(name: str) -> bool:
    return name in ALIAS_TO_INTERNAL


def is_internal(name: str) -> bool:
    return name in INTERNAL_TO_ALIAS
