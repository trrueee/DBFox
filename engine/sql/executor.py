from __future__ import annotations

import datetime
import decimal
import json
import logging
import os
import sqlite3
import time
import uuid
from typing import Any

import pymysql
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from engine.datasource import get_mysql_connection_params, get_postgres_connection_params
from engine.errors import (
    GuardrailValidationError,
    SQLExecutionError,
    SQLQueryCancelledError,
    SQLQueryTimeoutError,
)
from engine.models import DataSource, QueryHistory
from engine.policy.redactor import DataRedactor
from engine.query_registry import QUERY_REGISTRY
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate

logger = logging.getLogger("databox.sql.executor")

MAX_ROWS = 1000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 5000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_MS = 30_000

ProcessedRows = tuple[list[dict[str, Any]], list[str], bool, int]

# Dynamic registry of pools mapped by database cache keys to support auto-updating of ports/credentials
_MYSQL_POOLS: dict[tuple[Any, ...], QueuePool] = {}
_POSTGRES_POOLS: dict[tuple[Any, ...], QueuePool] = {}


def get_postgres_pool(datasource_id: str, params: dict[str, Any]) -> QueuePool:
    """Creates or retrieves a connection pool for the datasource with requested timeout properties."""
    pool_params = params.copy()
    pool_key = (
        datasource_id,
        pool_params.get("host"),
        pool_params.get("port"),
        pool_params.get("user"),
        pool_params.get("database"),
    )
    if pool_key not in _POSTGRES_POOLS:
        def creator() -> Any:
            import psycopg2
            return psycopg2.connect(
                host=pool_params.get("host"),
                port=pool_params.get("port"),
                user=pool_params.get("user"),
                password=pool_params.get("password"),
                database=pool_params.get("database"),
                connect_timeout=5,
            )
        from typing import cast
        _POSTGRES_POOLS[pool_key] = QueuePool(
            cast(Any, creator),
            pool_size=5,
            max_overflow=10,
            recycle=1800,
        )
    return _POSTGRES_POOLS[pool_key]


def get_mysql_pool(datasource_id: str, params: dict[str, Any]) -> QueuePool:
    """Creates or retrieves a connection pool for the datasource with requested timeout properties."""
    pool_params = params.copy()
    pool_params["connect_timeout"] = 5
    pool_params["read_timeout"] = 30
    pool_params["write_timeout"] = 30

    pool_key = (
        datasource_id,
        pool_params.get("host"),
        pool_params.get("port"),
        pool_params.get("user"),
        pool_params.get("database"),
        pool_params.get("ssl_ca"),
        pool_params.get("ssl_cert")
    )
    
    if pool_key not in _MYSQL_POOLS:
        def creator() -> pymysql.Connection:
            return pymysql.connect(**pool_params)
            
        from typing import cast
        _MYSQL_POOLS[pool_key] = QueuePool(
            cast(Any, creator),
            pool_size=5,
            max_overflow=10,
            recycle=1800,
        )
    return _MYSQL_POOLS[pool_key]


def _ping_mysql_connection(conn_proxy: Any) -> Any:
    """Validate a raw PyMySQL connection checked out from QueuePool."""
    raw_conn: Any = getattr(conn_proxy, "dbapi_connection", None) or getattr(conn_proxy, "connection", None) or conn_proxy
    try:
        raw_conn.ping(reconnect=True)
    except TypeError:
        raw_conn.ping(True)
    return raw_conn


def _serialize_value(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, decimal.Decimal):
        return str(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return "<binary>"
    return str(val)


def _process_rows(
    raw_rows: list[Any],
    columns: list[str],
    max_columns: int = MAX_COLUMNS,
    max_cell_chars: int = MAX_CELL_CHARS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> ProcessedRows:
    """Process raw cursor rows into a list of serialized dicts with limits applied."""
    if len(columns) > max_columns:
        columns = columns[:max_columns]

    rows = []
    response_bytes = 2  # JSON array brackets
    truncated = False

    for r in raw_rows:
        row_dict = {}
        for col in columns:
            val = r[col]
            if isinstance(val, str) and len(val) > max_cell_chars:
                val = val[:max_cell_chars] + "..."
            row_dict[col] = _serialize_value(val)

        row_bytes = len(json.dumps(row_dict, ensure_ascii=False, default=str).encode("utf-8")) + 1
        if response_bytes + row_bytes > max_response_bytes:
            truncated = True
            break

        response_bytes += row_bytes
        rows.append(row_dict)

    return rows, columns, truncated, response_bytes


def _execute_on_sqlite_profiled(
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    sqlite_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on the SQLite database, returning timing breakdown."""
    db_path = sqlite_path
    if not db_path:
        raise ValueError("SQLite database path is required for query execution")
    
    t_conn_start = time.perf_counter()
    conn = sqlite3.connect(db_path)
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
    
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + (timeout_ms / 1000)
    timed_out = False

    def abort_when_timed_out() -> int:
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1
        return 0

    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.set_progress_handler(abort_when_timed_out, 1000)
        if execution_id:
            QUERY_REGISTRY.register_sqlite(execution_id, datasource_id, conn)
        cursor = conn.cursor()
        
        t_exec_start = time.perf_counter()
        try:
            cursor.execute(safe_sql)
        except sqlite3.OperationalError as exc:
            if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                raise SQLQueryCancelledError("SQL query cancelled by user") from exc
            if timed_out:
                raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
            raise
        execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

        columns: list[str] = []
        rows: list[dict[str, Any]] = []
        truncated = False
        response_bytes = 2
        fetch_ms = 0
        serialize_ms = 0

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            
            t_fetch_start = time.perf_counter()
            raw_rows = cursor.fetchmany(MAX_ROWS)
            fetch_ms = int((time.perf_counter() - t_fetch_start) * 1000)
            
            t_ser_start = time.perf_counter()
            rows, columns, truncated, response_bytes = _process_rows(raw_rows, columns)
            serialize_ms = int((time.perf_counter() - t_ser_start) * 1000)
            
        return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn.set_progress_handler(None, 0)
        conn.close()


def _execute_on_sqlite(
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    sqlite_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_sqlite_profiled(
        safe_sql, timeout_ms, execution_id, datasource_id, sqlite_path
    )
    return rows, columns, truncated, response_bytes


def _execute_on_postgres_profiled(
    datasource_id: str,
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on a real PostgreSQL database, returning timing breakdown."""
    t_conn_start = time.perf_counter()
    pool = get_postgres_pool(datasource_id, params)
    conn_proxy: Any = pool.connect()
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
    
    try:
        raw_conn = conn_proxy.connection if hasattr(conn_proxy, "connection") else conn_proxy
        if execution_id:
            QUERY_REGISTRY.register_postgres(
                execution_id,
                datasource_id,
                raw_conn,
            )

        with conn_proxy.cursor() as cursor:
            # Set postgres statement timeout
            try:
                cursor.execute(f"SET statement_timeout = {timeout_ms}")
            except Exception:
                pass

            t_exec_start = time.perf_counter()
            try:
                cursor.execute(safe_sql)
            except Exception as exc:
                if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                    raise SQLQueryCancelledError("SQL query cancelled by user") from exc
                
                # Check for Postgres cancel/timeout error code (57014)
                pgcode = getattr(exc, "pgcode", None)
                if pgcode == "57014":
                    raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
                raise
            execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

            columns: list[str] = []
            rows: list[dict[str, Any]] = []
            truncated = False
            response_bytes = 2
            fetch_ms = 0
            serialize_ms = 0

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                
                t_fetch_start = time.perf_counter()
                raw_rows = cursor.fetchmany(MAX_ROWS)
                fetch_ms = int((time.perf_counter() - t_fetch_start) * 1000)
                
                # Convert tuples to dicts
                mapped_rows = []
                for row in raw_rows:
                    mapped_rows.append(dict(zip(columns, row)))
                    
                t_ser_start = time.perf_counter()
                rows, columns, truncated, response_bytes = _process_rows(mapped_rows, columns)
                serialize_ms = int((time.perf_counter() - t_ser_start) * 1000)
                
            return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn_proxy.close()


def _execute_on_mysql_profiled(
    datasource_id: str,
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on a real MySQL database via PyMySQL, returning timing breakdown."""
    t_conn_start = time.perf_counter()
    pool = get_mysql_pool(datasource_id, params)
    conn_proxy: Any = pool.connect()
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
    
    try:
        raw_conn = _ping_mysql_connection(conn_proxy)
        if execution_id:
            QUERY_REGISTRY.register_mysql(
                execution_id,
                datasource_id,
                params,
                int(raw_conn.thread_id()),
            )

        with conn_proxy.cursor() as cursor:
            try:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (timeout_ms,))
            except Exception:
                pass

            t_exec_start = time.perf_counter()
            try:
                cursor.execute(safe_sql)
            except pymysql.err.OperationalError as exc:
                code = exc.args[0] if exc.args else None
                if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                    raise SQLQueryCancelledError("SQL query cancelled by user") from exc
                if code in {1317, 3024}:
                    raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
                raise
            execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

            columns: list[str] = []
            rows: list[dict[str, Any]] = []
            truncated = False
            response_bytes = 2
            fetch_ms = 0
            serialize_ms = 0

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                
                t_fetch_start = time.perf_counter()
                raw_rows = cursor.fetchmany(MAX_ROWS)
                fetch_ms = int((time.perf_counter() - t_fetch_start) * 1000)
                
                t_ser_start = time.perf_counter()
                rows, columns, truncated, response_bytes = _process_rows(raw_rows, columns)
                serialize_ms = int((time.perf_counter() - t_ser_start) * 1000)
                
            return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn_proxy.close()


def _execute_on_mysql(
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_mysql_profiled(
        datasource_id, params, safe_sql, timeout_ms, execution_id
    )
    return rows, columns, truncated, response_bytes


def _resolve_execution_safety_decision(
    db: Session,
    datasource_id: str,
    sql_str: str,
    bypass_guardrail: bool,
    safety_decision: ExecutionSafetyDecision | dict[str, Any] | None,
    policy: ExecutionPolicy = "readonly",
) -> ExecutionSafetyDecision:
    if safety_decision is not None:
        decision = (
            safety_decision
            if isinstance(safety_decision, ExecutionSafetyDecision)
            else ExecutionSafetyDecision.model_validate(safety_decision)
        )
        if decision.datasource_id != datasource_id:
            raise GuardrailValidationError(
                "TrustGate decision datasource does not match the execution datasource.",
                checks=[{
                    "rule": "safety_decision_datasource_mismatch",
                    "level": "reject",
                    "message": "The supplied safety decision belongs to a different datasource.",
                }],
            )
        supplied_sql = sql_str.strip()
        decision_sqls = {
            decision.original_sql.strip(),
            str(decision.safe_sql or "").strip(),
        }
        if supplied_sql not in decision_sqls:
            raise GuardrailValidationError(
                "TrustGate decision SQL does not match the SQL requested for execution.",
                checks=[{
                    "rule": "safety_decision_sql_mismatch",
                    "level": "reject",
                    "message": "The supplied safety decision was created for different SQL text.",
                }],
            )
        return decision

    if bypass_guardrail:
        if os.environ.get("DATABOX_TESTING") != "1":
            raise GuardrailValidationError(
                "TrustGate bypass is only available in the test environment.",
                checks=[{
                    "rule": "trust_gate_bypass_disabled",
                    "level": "reject",
                    "message": "bypass_guardrail requires DATABOX_TESTING=1 and cannot be used in normal execution.",
                }],
            )
        # Double-gate: bypass is only allowed on dev/test datasources.
        # Prevents DATABOX_TESTING=1 from being inadvertently set in staging/prod.
        ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
        ds_env = (ds.env or "").lower() if ds else ""
        if ds_env not in ("", "dev", "test", "unknown"):
            raise GuardrailValidationError(
                "TrustGate bypass is not allowed on non-dev datasources.",
                checks=[{
                    "rule": "trust_gate_bypass_env_blocked",
                    "level": "reject",
                    "message": f"bypass_guardrail blocked: datasource env is '{ds_env}', only dev/test allowed.",
                }],
            )
        logger.warning(
            "TrustGate bypass active: datasource=%s env=%s policy=%s",
            datasource_id, ds_env, policy,
        )
        guard_res = {
            "result": "pass",
            "originalSql": sql_str,
            "safeSql": sql_str,
            "checks": [],
            "message": "Bypassed via system request (DATABOX_TESTING=1 + dev/test env)",
        }
        return ExecutionSafetyDecision(
            datasource_id=datasource_id,
            policy=policy,
            original_sql=sql_str,
            safe_sql=sql_str,
            passed=True,
            can_execute=True,
            requires_confirmation=False,
            guardrail=guard_res,  # type: ignore[arg-type]
            schema_warnings=[],
            scope_state={
                "datasource_id": datasource_id,
                "bypass_guardrail": True,
                "testing": os.environ.get("DATABOX_TESTING") == "1",
            },
            messages=["Legacy system bypass was used; prefer explicit non-query execution helpers."],
        )

    from engine.sql.generator import validate_sql_schema

    return TrustGate(db, validate_sql_schema).execution_decision(datasource_id, sql_str, policy=policy)


def _decision_checks_for_history(decision: ExecutionSafetyDecision) -> list[dict[str, Any]]:
    checks = [dict(item) for item in decision.guardrail.get("checks", [])]
    checks.extend(
        {
            "rule": "schema_validation",
            "level": "reject",
            "message": warning,
        }
        for warning in decision.schema_warnings
    )
    if decision.requires_confirmation:
        checks.append(
            {
                "rule": "requires_confirmation",
                "level": "reject",
                "message": "Execution requires manual confirmation before a result set can be produced.",
            }
        )
    for reason in decision.blocked_reasons:
        if reason in {"guardrail_reject", "schema_validation", "requires_confirmation"}:
            continue
        checks.append(
            {
                "rule": reason,
                "level": "reject",
                "message": f"TrustGate blocked execution because of {reason}.",
            }
        )
    if not decision.scope_state.get("datasource_exists", True):
        checks.append(
            {
                "rule": "datasource_scope",
                "level": "reject",
                "message": "Datasource scope could not be resolved for this execution.",
            }
        )
    return checks


def _decision_checks_for_error(decision: ExecutionSafetyDecision) -> list[dict[str, str]]:
    return [
        {
            "rule": str(item.get("rule", "trust_gate")),
            "level": str(item.get("level", "reject")),
            "message": str(item.get("message", "")),
        }
        for item in _decision_checks_for_history(decision)
    ]


def _decision_block_message(decision: ExecutionSafetyDecision) -> str:
    if decision.guardrail.get("result") == "reject":
        return str(decision.guardrail.get("message") or "TrustGate blocked execution.")
    if "select_star" in decision.blocked_reasons:
        return "Agent execution requires explicit projected columns instead of SELECT *."
    if "schema_validation" in decision.blocked_reasons or decision.schema_warnings:
        return "TrustGate blocked execution because schema validation found unknown tables or columns."
    if "requires_confirmation" in decision.blocked_reasons or decision.requires_confirmation:
        return "TrustGate blocked execution because this datasource requires manual confirmation."
    if "safe_sql_missing" in decision.blocked_reasons:
        return "Guardrail did not produce safe_sql. Execution is blocked."
    if "datasource_scope" in decision.blocked_reasons:
        return "Datasource scope could not be resolved."

    explain_detail = next(
        (
            msg
            for msg in decision.messages
            if msg.startswith("EXPLAIN dry-run failed") or msg.startswith("EXPLAIN dry-run unavailable")
        ),
        "",
    )
    suffix = f"（{explain_detail}）" if explain_detail else ""
    if "schema_error" in decision.blocked_reasons:
        return f"表或字段在目标数据库中不存在，本地 Schema 元数据可能已过期，请重新同步 Schema 后重试。{suffix}"
    if "syntax_error" in decision.blocked_reasons:
        return f"SQL 语法未通过目标数据库校验，请检查语句。{suffix}"
    if "explain_unavailable" in decision.blocked_reasons:
        return f"无法连接到目标数据库，数据源可能已离线，请在数据源管理中检查连接后重试。{suffix}"
    if explain_detail:
        return explain_detail

    return "TrustGate blocked execution before SQL reached the database."


def execute_query(
    db: Session,
    datasource_id: str,
    sql_str: str,
    question: str | None = None,
    execution_id: str | None = None,
    bypass_guardrail: bool = False,
    safety_decision: ExecutionSafetyDecision | dict[str, Any] | None = None,
    safety_policy: ExecutionPolicy = "readonly",
) -> dict[str, Any]:
    """
    Safely executes a SQL query:
    1. Resolve an ExecutionSafetyDecision through TrustGate
    2. Execute the approved safe SQL on the target datasource
    3. Serialize results and log history
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    execution_id = execution_id or f"exec-{uuid.uuid4()}"
    
    t_guard_start = time.perf_counter()
    decision = _resolve_execution_safety_decision(
        db=db,
        datasource_id=datasource_id,
        sql_str=sql_str,
        bypass_guardrail=bypass_guardrail,
        safety_decision=safety_decision,
        policy=safety_policy,
    )
    guard_res = decision.guardrail
    guardrail_ms = int((time.perf_counter() - t_guard_start) * 1000)
    guard_checks_json = json.dumps(_decision_checks_for_history(decision), ensure_ascii=False)

    if not decision.can_execute or not str(decision.safe_sql or "").strip():
        redacted_sql = DataRedactor.redact_sql(sql_str)
        message = _decision_block_message(decision)
        history = QueryHistory(
            data_source_id=datasource_id,
            question=question,
            submitted_sql=redacted_sql,
            generated_sql=redacted_sql,
            safe_sql="",
            executed_sql="",
            guardrail_result=guard_res["result"],
            guardrail_checks=guard_checks_json,
            execution_status="failed",
            error_message=message,
            execution_time_ms=guardrail_ms,
            connect_ms=0,
            guardrail_ms=guardrail_ms,
            execute_ms=0,
            fetch_ms=0,
            serialize_ms=0,
        )
        db.add(history)
        db.commit()
        raise GuardrailValidationError(
            message, checks=_decision_checks_for_error(decision)
        )

    safe_sql = str(decision.safe_sql or "").strip()
    start_time = time.time()
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    truncated = False
    response_bytes = 2
    error_message: str | None = None
    execution_status = "success"

    connect_ms = 0
    execute_ms = 0
    fetch_ms = 0
    serialize_ms = 0

    try:
        db_type = ds.db_type or "mysql"
        if db_type == "sqlite":
            rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms = _execute_on_sqlite_profiled(
                safe_sql,
                execution_id=execution_id,
                datasource_id=datasource_id,
                sqlite_path=ds.database_name,  # type: ignore[arg-type]
            )
        elif db_type == "postgresql":
            conn_params = get_postgres_connection_params({
                "host": ds.host,
                "port": ds.port,
                "username": ds.username,
                "database_name": ds.database_name,
                "password_ciphertext": ds.password_ciphertext,
                "password_nonce": ds.password_nonce,
                "ssh_enabled": ds.ssh_enabled,
                "ssh_host": ds.ssh_host,
                "ssh_port": ds.ssh_port,
                "ssh_username": ds.ssh_username,
                "ssh_password_ciphertext": ds.ssh_password_ciphertext,
                "ssh_password_nonce": ds.ssh_password_nonce,
                "ssh_pkey_path": ds.ssh_pkey_path,
                "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
                "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
            })
            rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms = _execute_on_postgres_profiled(
                datasource_id,
                conn_params,
                safe_sql,
                execution_id=execution_id,
            )
        else:
            conn_params = get_mysql_connection_params({
                "host": ds.host,
                "port": ds.port,
                "username": ds.username,
                "database_name": ds.database_name,
                "password_ciphertext": ds.password_ciphertext,
                "password_nonce": ds.password_nonce,
                "ssh_enabled": ds.ssh_enabled,
                "ssh_host": ds.ssh_host,
                "ssh_port": ds.ssh_port,
                "ssh_username": ds.ssh_username,
                "ssh_password_ciphertext": ds.ssh_password_ciphertext,
                "ssh_password_nonce": ds.ssh_password_nonce,
                "ssh_pkey_path": ds.ssh_pkey_path,
                "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
                "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
                "ssl_enabled": ds.ssl_enabled,
                "ssl_ca_path": ds.ssl_ca_path,
                "ssl_cert_path": ds.ssl_cert_path,
                "ssl_key_path": ds.ssl_key_path,
                "ssl_verify_identity": ds.ssl_verify_identity,
            })
            rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms = _execute_on_mysql_profiled(
                datasource_id,
                conn_params,
                safe_sql,
                execution_id=execution_id,
            )
    except SQLQueryCancelledError as e:
        execution_status = "cancelled"
        error_message = e.message
        raise
    except TimeoutError as e:
        execution_status = "timeout"
        error_message = f"SQL query timed out after {QUERY_TIMEOUT_MS} ms"
        raise SQLQueryTimeoutError(error_message) from e
    except Exception as e:
        execution_status = "failed"
        error_message = f"执行 SQL 遇到错误: {str(e)}"
        raise SQLExecutionError(error_message) from e

    finally:
        latency_ms = int((time.time() - start_time) * 1000)

        history = QueryHistory(
            data_source_id=datasource_id,
            question=question,
            submitted_sql=DataRedactor.redact_sql(sql_str),
            generated_sql=DataRedactor.redact_sql(sql_str),
            safe_sql=DataRedactor.redact_sql(safe_sql),
            executed_sql=DataRedactor.redact_sql(safe_sql) if execution_status == "success" else "",
            guardrail_result=guard_res["result"],
            guardrail_checks=guard_checks_json,
            execution_status=execution_status,
            execution_time_ms=latency_ms,
            connect_ms=connect_ms,
            guardrail_ms=guardrail_ms,
            execute_ms=execute_ms,
            fetch_ms=fetch_ms,
            serialize_ms=serialize_ms,
            rows_returned=len(rows) if execution_status == "success" else 0,
            columns_returned=len(columns) if execution_status == "success" else 0,
            error_message=error_message,
        )
        db.add(history)
        db.commit()

    # Detect cell truncation precisely: _process_rows cuts long strings to exactly
    # MAX_CELL_CHARS chars + "...", so only that shape indicates a truncated cell.
    # (Checking just endswith("...") false-positives on legitimate data.)
    cell_truncated = any(
        isinstance(v, str) and len(v) == MAX_CELL_CHARS + 3 and v.endswith("...")
        for r in rows
        for v in r.values()
    )

    warnings = []
    notices = []
    if truncated:
        warnings.append("查询结果已超过最大传输字节限制，部分行被截断")
    if cell_truncated:
        # Informational, not a problem: long text cells are clipped for preview/transfer.
        notices.append(f"部分长文本字段仅返回前 {MAX_CELL_CHARS} 字符")
    if len(columns) > MAX_COLUMNS:
        warnings.append("列数超过最大展示限制，仅显示前 100 列")

    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "latencyMs": latency_ms,
        "guardrail": guard_res,
        "safetyDecision": decision.model_dump(mode="json"),
        "historyId": history.id,
        "executionId": execution_id,
        "truncated": truncated,
        "cellTruncated": cell_truncated,
        "responseBytes": response_bytes,
        "maxResponseBytes": MAX_RESPONSE_BYTES,
        "warnings": warnings,
        "notices": notices,
        # Timing latency breakdown properties (camelCase for frontend TS, snake_case for Python tests)
        "connectMs": connect_ms,
        "guardrailMs": guardrail_ms,
        "executeMs": execute_ms,
        "fetchMs": fetch_ms,
        "serializeMs": serialize_ms,
        "totalMs": latency_ms,
        "connect_ms": connect_ms,
        "guardrail_ms": guardrail_ms,
        "execute_ms": execute_ms,
        "fetch_ms": fetch_ms,
        "serialize_ms": serialize_ms,
        "total_ms": latency_ms,
    }


def explain_sql(
    db: Session,
    datasource_id: str,
    sql_str: str,
) -> dict[str, Any]:
    """
    Diagnose query execution plans:
    1. Resolve a TrustGate execution decision
    2. Execute EXPLAIN against the approved safe SQL
    3. Format diagnostics and return warnings for slow patterns (type=ALL or key=NULL)
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    decision = _resolve_execution_safety_decision(
        db=db,
        datasource_id=datasource_id,
        sql_str=sql_str,
        bypass_guardrail=False,
        safety_decision=None,
        policy="explain",
    )
    if not decision.can_execute or not str(decision.safe_sql or "").strip():
        raise GuardrailValidationError(
            _decision_block_message(decision),
            checks=_decision_checks_for_error(decision),
        )
    safe_sql = str(decision.safe_sql or "").strip()
        
    warnings = []
    records = []

    if ds.db_type == "sqlite":
        # SQLite Explain Query Plan
        conn = sqlite3.connect(str(ds.database_name))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(f"EXPLAIN QUERY PLAN {safe_sql}")
            raw_rows = cursor.fetchall()
            for r in raw_rows:
                detail = str(r["detail"])
                is_scan = "SCAN" in detail.upper()
                is_search = "SEARCH" in detail.upper()
                
                q_type = "ALL" if is_scan else "RANGE" if is_search else "INDEX"
                q_key = None
                if "USING INDEX" in detail.upper():
                    parts = detail.split("USING INDEX")
                    if len(parts) > 1:
                        q_key = parts[1].strip().split()[0]
                        
                records.append({
                    "type": q_type,
                    "key": q_key,
                    "rows": None,
                    "Extra": detail
                })
                
                if q_type == "ALL":
                    warnings.append("检测到全表扫描 (Type=ALL)，建议在过滤字段上建立索引")
                if q_key is None or q_key == "NULL":
                    warnings.append("未命中任何索引 (Key=NULL)，查询性能可能受限")
        finally:
            conn.close()
    else:
        # Real MySQL Explain
        conn_params = get_mysql_connection_params({
            "host": ds.host,
            "port": ds.port,
            "username": ds.username,
            "database_name": ds.database_name,
            "password_ciphertext": ds.password_ciphertext,
            "password_nonce": ds.password_nonce,
            "ssh_enabled": ds.ssh_enabled,
            "ssh_host": ds.ssh_host,
            "ssh_port": ds.ssh_port,
            "ssh_username": ds.ssh_username,
            "ssh_password_ciphertext": ds.ssh_password_ciphertext,
            "ssh_password_nonce": ds.ssh_password_nonce,
            "ssh_pkey_path": ds.ssh_pkey_path,
            "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
            "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
            "ssl_enabled": ds.ssl_enabled,
            "ssl_ca_path": ds.ssl_ca_path,
            "ssl_cert_path": ds.ssl_cert_path,
            "ssl_key_path": ds.ssl_key_path,
            "ssl_verify_identity": ds.ssl_verify_identity,
        })
        
        pool = get_mysql_pool(datasource_id, conn_params)
        conn_proxy: Any = pool.connect()
        try:
            _ping_mysql_connection(conn_proxy)
            with conn_proxy.cursor() as cursor:
                cursor.execute(f"EXPLAIN {safe_sql}")
                raw_rows = cursor.fetchall()
                for r in raw_rows:
                    q_type = r.get("type") or r.get("Type")
                    q_key = r.get("key") or r.get("Key")
                    q_rows = r.get("rows") or r.get("Rows")
                    q_extra = r.get("Extra") or r.get("extra") or ""
                    
                    records.append({
                        "type": q_type,
                        "key": q_key,
                        "rows": q_rows,
                        "Extra": q_extra
                    })
                    
                    type_str = str(q_type).upper() if q_type is not None else ""
                    key_str = str(q_key).upper() if q_key is not None else ""
                    
                    if type_str == "ALL":
                        warnings.append(f"表 {r.get('table') or ''} 检测到全表扫描 (Type=ALL)，建议针对过滤/连接字段创建索引。")
                    if not q_key or key_str == "NULL":
                        warnings.append(f"表 {r.get('table') or ''} 未命中任何索引 (Key=NULL)，查询性能可能受限。")
        finally:
            conn_proxy.close()
            
    return {
        "success": True,
        "records": records,
        "warnings": list(set(warnings)),
        "safetyDecision": decision.model_dump(mode="json"),
    }
