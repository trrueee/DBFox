"""db.* tool handlers — the agent's database exploration toolkit.

Design principles:
  - Agent decides what to do and in what order.
  - Tools enforce safety at the boundary layer.
  - Live introspection hits the real database, not a stale catalog.
  - Synonyms and sensitivity rules live in the database, not in code.

This module is a thin re-export layer. The actual implementations live in
``engine/tools/db/`` sub-modules:

  - ``_common.py``  — shared constants and helpers
  - ``observe.py``  — ``db.observe`` handler
  - ``search.py``   — ``db.search`` handler
  - ``inspect.py``  — ``db.inspect`` handler
  - ``preview.py``  — ``db.preview`` handler
  - ``sql_execution.py`` — ``sql.validate`` / ``sql.execute_readonly`` handlers
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Public tool handlers
# ---------------------------------------------------------------------------
from engine.tools.db.observe import db_observe
from engine.tools.db.search import db_search
from engine.tools.db.inspect import db_inspect
from engine.tools.db.preview import db_preview
from engine.tools.db.sql_execution import sql_validate, sql_execute_readonly

__all__ = [
    "db_observe",
    "db_search",
    "db_inspect",
    "db_preview",
    "sql_validate",
    "sql_execute_readonly",
]

# ---------------------------------------------------------------------------
# Shared helpers that tests and downstream code import directly
# ---------------------------------------------------------------------------
from engine.tools.db._common import (
    DEFAULT_PREVIEW_ROWS,
    DEFAULT_SEARCH_LIMIT,
    MAX_PREVIEW_ROWS,
    _catalog_table,
    _catalog_tables,
    _clamp,
    _column_summary,
    _execution_failed,
    _failed,
    _filter_tables,
    _limit_was_injected,
    _looks_sensitive,
    _missing_table_names,
    _normalize_sql,
    _ordered_columns,
    _redact_row,
    _string_list,
    _success,
)
from engine.tools.db.observe import (
    _connected_table_names,
    _domain_sections,
    _fk_summary,
    _query_stats_for_table,
    _schema_sections,
    _schema_table_summary,
    _table_card,
    _table_tags,
    _validate_mode,
)
from engine.tools.db.search import (
    _compute_reasons,
    _compute_total_score,
    _fallback_keyword_search,
    _fts_search,
    _row_to_search_result,
)
from engine.tools.db.inspect import (
    _INSPECT_CACHE,
    _mysql_inspect_detail,
    _mysql_table_exists,
    _mysql_table_payload,
    _parse_target,
    _pg_inspect_detail,
    _pg_table_exists,
    _pg_table_payload,
    _row_value,
    _sqlite_fk_map,
    _sqlite_indexes,
    _sqlite_inspect_detail,
    _sqlite_reverse_fks,
    _sqlite_row_count,
    _sqlite_table_exists,
    _sqlite_table_payload,
    _sqlite_table_type,
    TTLMemoryCache,
    escape_identifier,
)
from engine.tools.db.preview import (
    _build_order_clause,
    _build_preview_sql,
    _build_where_clause,
    _column_summary_preview,
    _infer_column_types,
    _resolve_dialect,
    _resolve_preview_columns,
)
