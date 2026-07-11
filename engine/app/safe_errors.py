"""Fixed public-error and diagnostic catalogs for untrusted exceptions.

This module deliberately has no DBFox imports so low-level runtime modules can
use it without creating a dependency cycle.  Error boundaries may select only
catalog members; arbitrary exception text and caller-supplied log labels are
never rendered into public payloads or diagnostics.
"""
from __future__ import annotations

from enum import Enum
from logging import Logger
from typing import Final, Literal


class FixedErrorCode(str, Enum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATASOURCE_POOL_RELEASE_FAILED = "DATASOURCE_POOL_RELEASE_FAILED"
    DATASOURCE_CONNECTION_FAILED = "DATASOURCE_CONNECTION_FAILED"
    DATASOURCE_NOT_FOUND = "DATASOURCE_NOT_FOUND"
    CONSOLE_EXECUTION_ERROR = "CONSOLE_EXECUTION_ERROR"
    RESULT_PAGE_ERROR = "RESULT_PAGE_ERROR"
    TABLE_RESULT_PAGE_ERROR = "TABLE_RESULT_PAGE_ERROR"
    TABLE_RESULT_EXPORT_ERROR = "TABLE_RESULT_EXPORT_ERROR"
    RESULT_EXPORT_ERROR = "RESULT_EXPORT_ERROR"
    SOURCE_ARTIFACT_NOT_FOUND = "SOURCE_ARTIFACT_NOT_FOUND"
    SOURCE_ARTIFACT_UNSUPPORTED = "SOURCE_ARTIFACT_UNSUPPORTED"
    SOURCE_SQL_MISSING = "SOURCE_SQL_MISSING"
    SOURCE_SQL_MISMATCH = "SOURCE_SQL_MISMATCH"
    SOURCE_SQL_VALIDATION_FAILED = "SOURCE_SQL_VALIDATION_FAILED"
    TABLE_SOURCE_NOT_FOUND = "TABLE_SOURCE_NOT_FOUND"
    TABLE_COLUMNS_NOT_FOUND = "TABLE_COLUMNS_NOT_FOUND"
    DERIVED_SQL_VALIDATION_FAILED = "DERIVED_SQL_VALIDATION_FAILED"
    DERIVED_SQL_BUILD_FAILED = "DERIVED_SQL_BUILD_FAILED"
    COUNT_SQL_BUILD_FAILED = "COUNT_SQL_BUILD_FAILED"
    FILTER_COLUMN_NOT_ALLOWED = "FILTER_COLUMN_NOT_ALLOWED"
    SORT_COLUMN_NOT_ALLOWED = "SORT_COLUMN_NOT_ALLOWED"
    FILTER_OPERATOR_NOT_ALLOWED = "FILTER_OPERATOR_NOT_ALLOWED"
    AGENT_REQUEST_ERROR = "AGENT_REQUEST_ERROR"
    AGENT_RUNTIME_ERROR = "AGENT_RUNTIME_ERROR"
    EVAL_RUN_ERROR = "EVAL_RUN_ERROR"
    IMPORT_ERROR = "IMPORT_ERROR"
    SQL_EMPTY = "SQL_EMPTY"
    BACKUP_OPERATION_FAILED = "BACKUP_OPERATION_FAILED"
    BACKUP_CLIENT_NOT_FOUND = "BACKUP_CLIENT_NOT_FOUND"
    QUERY_EXECUTION_FAILED = "QUERY_EXECUTION_FAILED"
    QUERY_CANCELLATION_FAILED = "QUERY_CANCELLATION_FAILED"
    SCHEMA_SYNC_FAILED = "SCHEMA_SYNC_FAILED"
    SQL_EXECUTION_FAILED = "SQL_EXECUTION_FAILED"
    SQL_SEMANTIC_PARSE_FAILED = "SQL_SEMANTIC_PARSE_FAILED"
    TABLE_DESIGN_ERROR = "TABLE_DESIGN_ERROR"
    TEST_DATA_FAILED = "TEST_DATA_FAILED"
    AGENT_CONTEXT_UNAVAILABLE = "AGENT_CONTEXT_UNAVAILABLE"


_FIXED_ERROR_MESSAGES: Final[dict[FixedErrorCode, str]] = {
    FixedErrorCode.INTERNAL_ERROR: "The request could not be completed.",
    FixedErrorCode.DATASOURCE_POOL_RELEASE_FAILED: "Datasource connection pool could not be released.",
    FixedErrorCode.DATASOURCE_CONNECTION_FAILED: "数据库连接健康检查失败，请检查连接配置。",
    FixedErrorCode.DATASOURCE_NOT_FOUND: "Datasource not found.",
    FixedErrorCode.CONSOLE_EXECUTION_ERROR: "The SQL Console request could not be completed.",
    FixedErrorCode.RESULT_PAGE_ERROR: "The result page could not be retrieved.",
    FixedErrorCode.TABLE_RESULT_PAGE_ERROR: "The table result page could not be retrieved.",
    FixedErrorCode.TABLE_RESULT_EXPORT_ERROR: "The table result export could not be generated.",
    FixedErrorCode.RESULT_EXPORT_ERROR: "The result export could not be generated.",
    FixedErrorCode.SOURCE_ARTIFACT_NOT_FOUND: "The requested source artifact was not found.",
    FixedErrorCode.SOURCE_ARTIFACT_UNSUPPORTED: "The selected source artifact is not supported.",
    FixedErrorCode.SOURCE_SQL_MISSING: "The source artifact does not contain safe SQL.",
    FixedErrorCode.SOURCE_SQL_MISMATCH: "Requested SQL does not match the source artifact.",
    FixedErrorCode.SOURCE_SQL_VALIDATION_FAILED: "The source SQL could not be validated.",
    FixedErrorCode.TABLE_SOURCE_NOT_FOUND: "The requested table source was not found.",
    FixedErrorCode.TABLE_COLUMNS_NOT_FOUND: "The table source does not have synced columns.",
    FixedErrorCode.DERIVED_SQL_VALIDATION_FAILED: "The derived SQL could not be validated.",
    FixedErrorCode.DERIVED_SQL_BUILD_FAILED: "Derived SQL could not be built.",
    FixedErrorCode.COUNT_SQL_BUILD_FAILED: "Count SQL could not be built.",
    FixedErrorCode.FILTER_COLUMN_NOT_ALLOWED: "The requested filter column is not allowed.",
    FixedErrorCode.SORT_COLUMN_NOT_ALLOWED: "The requested sort column is not allowed.",
    FixedErrorCode.FILTER_OPERATOR_NOT_ALLOWED: "The requested filter operator is not allowed.",
    FixedErrorCode.AGENT_REQUEST_ERROR: "The agent request could not be completed.",
    FixedErrorCode.AGENT_RUNTIME_ERROR: "The agent run could not be completed.",
    FixedErrorCode.EVAL_RUN_ERROR: "The evaluation run could not be completed.",
    FixedErrorCode.IMPORT_ERROR: "Benchmark import could not be completed.",
    FixedErrorCode.SQL_EMPTY: "SQL cannot be empty.",
    FixedErrorCode.BACKUP_OPERATION_FAILED: "The backup operation could not be completed.",
    FixedErrorCode.BACKUP_CLIENT_NOT_FOUND: "The database backup client is unavailable.",
    FixedErrorCode.QUERY_EXECUTION_FAILED: "The query could not be completed.",
    FixedErrorCode.QUERY_CANCELLATION_FAILED: "The query cancellation request could not be completed.",
    FixedErrorCode.SCHEMA_SYNC_FAILED: "Schema synchronization failed.",
    FixedErrorCode.SQL_EXECUTION_FAILED: "The SQL request could not be completed.",
    FixedErrorCode.SQL_SEMANTIC_PARSE_FAILED: "SQL could not be parsed.",
    FixedErrorCode.TABLE_DESIGN_ERROR: "The table design operation could not be completed.",
    FixedErrorCode.TEST_DATA_FAILED: "Test data could not be generated.",
    FixedErrorCode.AGENT_CONTEXT_UNAVAILABLE: "Agent context is temporarily unavailable.",
}


class SafeLogOperation(str, Enum):
    UNEXPECTED = "unexpected_internal_error"
    AGENT_SQL_CONSOLE_EXECUTION = "agent_sql_console_execution"
    AGENT_RESULT_PAGE = "agent_result_page"
    AGENT_TABLE_RESULT_PAGE = "agent_table_result_page"
    AGENT_TABLE_RESULT_EXPORT = "agent_table_result_export"
    AGENT_RESULT_EXPORT = "agent_result_export"
    AGENT_EVAL_BENCHMARK_IMPORT = "agent_eval_benchmark_import"
    AGENT_EVAL_RUN = "agent_eval_run"
    AGENT_EVALUATION_CASE = "agent_evaluation_case"
    AGENT_OBSERVE_TOOL_OBSERVATION = "agent_observe_tool_observation"
    AGENT_OBSERVE_CONTEXT_PACK = "agent_observe_context_pack"
    AGENT_PERSISTENCE_START = "agent_persistence_start"
    AGENT_PERSISTENCE_EVENT = "agent_persistence_event"
    AGENT_PERSISTENCE_ARTIFACT = "agent_persistence_artifact"
    AGENT_PERSISTENCE_FLUSH = "agent_persistence_flush"
    AGENT_PERSISTENCE_APPROVAL_CHECKPOINT = "agent_persistence_approval_checkpoint"
    AGENT_PERSISTENCE_FINAL_RESPONSE = "agent_persistence_final_response"
    AGENT_PERSISTENCE_RUNTIME_EVENT = "agent_persistence_runtime_event"
    AGENT_PERSISTENCE_ARTIFACT_RECORD = "agent_persistence_artifact_record"
    AGENT_PERSISTENCE_COMPLETE_RUN = "agent_persistence_complete_run"
    AGENT_PERSISTENCE_FAIL_RUN = "agent_persistence_fail_run"
    AGENT_PERSISTENCE_CANCEL_RUN = "agent_persistence_cancel_run"
    AGENT_SSE_CANCEL_QUERY = "agent_sse_cancel_query"
    AGENT_CONTEXT_BUILD_WORKSPACE = "agent_context_build_workspace"
    AGENT_CONTEXT_BUILD_ENVIRONMENT = "agent_context_build_environment"
    AGENT_MEMORY_LOAD_SESSION = "agent_memory_load_session"
    AGENT_MEMORY_LIST_REUSABLE_SQL = "agent_memory_list_reusable_sql"
    AGENT_MEMORY_SAVE_PROJECTION = "agent_memory_save_projection"
    TABLE_DESIGN_TEST_DATA = "table_design_test_data"
    TOOL_RUNTIME_INPUT_CONTRACT_FAILED = "tool_runtime_tool_input_contract_failed"
    TOOL_RUNTIME_OUTPUT_CONTRACT_FAILED = "tool_runtime_tool_output_contract_failed"
    TOOL_RUNTIME_EXECUTION_FAILED = "tool_runtime_tool_execution_failed"
    DB_TOOL_GUARDRAIL_BLOCKED = "db_tool_guardrail_blocked"
    DB_TOOL_EXECUTION = "db_tool_execution"
    DATASOURCE_TEST_SSH_TUNNEL = "datasource_test_ssh_tunnel"
    DATASOURCE_TEST_SQLITE_CONNECTION = "datasource_test_sqlite_connection"
    DATASOURCE_TEST_POSTGRES_CONNECTION = "datasource_test_postgres_connection"
    DATASOURCE_TEST_MYSQL_CONNECTION = "datasource_test_mysql_connection"
    DATASOURCE_HEALTH_CHECK = "datasource_health_check"
    DATASOURCE_CREDENTIAL_LEASE_RELEASE = "datasource_credential_lease_release"
    DATASOURCE_CONNECTION_TEST = "datasource_connection_test"
    DATASOURCE_POOL_RELEASE = "datasource_pool_release"
    SSH_TUNNEL_CLOSE = "ssh_tunnel_close"
    SSH_TUNNEL_CLOSE_ALL = "ssh_tunnel_close_all"
    SSH_TUNNEL_HEALTH_PROBE = "ssh_tunnel_health_probe"
    SSH_TUNNEL_RECONNECT_STOP_PREVIOUS = "ssh_tunnel_reconnect_stop_previous"
    SSH_TUNNEL_RECONNECT = "ssh_tunnel_reconnect"
    SSH_TUNNEL_CLEANUP_STALE = "ssh_tunnel_cleanup_stale"
    SCHEMA_INTROSPECTION_MYSQL_CONNECT = "schema_introspection_mysql_connect"
    SCHEMA_INTROSPECTION_DUCKDB_CONNECT = "schema_introspection_duckdb_connect"
    QUERY_EXPLAIN = "query_explain"
    QUERY_HISTORY_INDEX_DELETE = "query_history_index_delete"
    QUERY_HISTORY_INDEX_CLEAR = "query_history_index_clear"
    QUERY_HISTORY_INDEX_POPULATE = "query_history_index_populate"
    QUERY_HISTORY_WRITE = "query_history_write"
    SQL_SENSITIVITY_LOAD = "sql_sensitivity_load"
    BACKUP_REFRESH_CATALOG = "backup_refresh_catalog"
    DB_SEARCH_FTS_FALLBACK = "db_search_fts_fallback"
    DB_INSPECT_INDEXES = "db_inspect_indexes"
    DB_INSPECT_ROW_ESTIMATE = "db_inspect_row_estimate"
    DB_INSPECT_TABLE_COMMENT = "db_inspect_table_comment"
    DB_INSPECT_SQLITE_ROW_COUNT = "db_inspect_sqlite_row_count"


def _safe_error_code(code: object) -> FixedErrorCode:
    return code if isinstance(code, FixedErrorCode) else FixedErrorCode.INTERNAL_ERROR


def fixed_error_detail(code: FixedErrorCode) -> dict[str, str]:
    """Return a cataloged public error without accepting arbitrary text."""
    safe_code = _safe_error_code(code)
    return {"code": safe_code.value, "message": _FIXED_ERROR_MESSAGES[safe_code]}


def fixed_error_message(code: FixedErrorCode) -> str:
    """Return only the fixed message for a catalog member."""
    return fixed_error_detail(code)["message"]


def log_unexpected_exception(
    logger: Logger,
    *,
    operation: SafeLogOperation,
    exc: Exception,
    level: Literal["warning", "error"] = "error",
) -> None:
    """Log a static operation label and exception class, never exception text."""
    safe_operation = operation if isinstance(operation, SafeLogOperation) else SafeLogOperation.UNEXPECTED
    log = logger.warning if level == "warning" else logger.error
    log("%s failed (%s)", safe_operation.value, type(exc).__name__)
