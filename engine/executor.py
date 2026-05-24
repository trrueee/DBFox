from __future__ import annotations

import datetime
import decimal
import json
import sqlite3
import time
import uuid
from typing import Any

import pymysql
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from engine.datasource import get_mysql_connection_params, is_demo_db
from engine.demo_db_init import DEMO_DB_PATH, init_demo_database
from engine.errors import (
    GuardrailValidationError,
    SQLExecutionError,
    SQLQueryCancelledError,
    SQLQueryTimeoutError,
)
from engine.guardrail import guardrail_check
from engine.models import DataSource, QueryHistory
from engine.query_registry import QUERY_REGISTRY

MAX_ROWS = 1000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 5000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_MS = 30_000

ProcessedRows = tuple[list[dict[str, Any]], list[str], bool, int]

# Dynamic registry of pools mapped by database cache keys to support auto-updating of ports/credentials
_MYSQL_POOLS: dict[tuple[Any, ...], QueuePool] = {}


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
            pre_ping=True
        )
    return _MYSQL_POOLS[pool_key]


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
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on the local SQLite demo database, returning timing breakdown."""
    demo_path = init_demo_database()
    
    t_conn_start = time.perf_counter()
    conn = sqlite3.connect(demo_path)
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
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_sqlite_profiled(
        safe_sql, timeout_ms, execution_id, datasource_id
    )
    return rows, columns, truncated, response_bytes


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
        raw_conn: Any = getattr(conn_proxy, "dbapi_connection", None) or getattr(conn_proxy, "connection", None) or conn_proxy
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


def execute_query(
    db: Session,
    datasource_id: str,
    sql_str: str,
    question: str | None = None,
    execution_id: str | None = None,
    bypass_guardrail: bool = False,
) -> dict[str, Any]:
    """
    Safely executes a SELECT query:
    1. Guardrail check
    2. Execute on demo SQLite or real MySQL
    3. Serialize results, log history
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    execution_id = execution_id or f"exec-{uuid.uuid4()}"
    
    t_guard_start = time.perf_counter()
    if bypass_guardrail:
        guard_res = {
            "result": "pass",
            "originalSql": sql_str,
            "safeSql": sql_str,
            "checks": [],
            "message": "Bypassed via system request"
        }
    else:
        guard_res = guardrail_check(sql_str)
    guardrail_ms = int((time.perf_counter() - t_guard_start) * 1000)
    guard_checks_json = json.dumps(guard_res["checks"], ensure_ascii=False)

    if guard_res["result"] == "reject":
        history = QueryHistory(
            data_source_id=datasource_id,
            question=question,
            submitted_sql=sql_str,
            generated_sql=sql_str,
            safe_sql="",
            executed_sql="",
            guardrail_result="reject",
            guardrail_checks=guard_checks_json,
            execution_status="failed",
            error_message=guard_res["message"],
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
            guard_res["message"], checks=guard_res["checks"]  # type: ignore[arg-type]
        )

    safe_sql = guard_res["safeSql"]
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
        if is_demo_db(str(ds.host), str(ds.database_name)):
            rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms = _execute_on_sqlite_profiled(
                safe_sql,
                execution_id=execution_id,
                datasource_id=datasource_id,
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
            submitted_sql=sql_str,
            generated_sql=sql_str,
            safe_sql=safe_sql,
            executed_sql=safe_sql if execution_status == "success" else "",
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

    # Detect cell truncation by scanning if any string value ends with "..."
    cell_truncated = any(
        isinstance(v, str) and v.endswith("...") for r in rows for v in r.values()
    )

    warnings = []
    if truncated:
        warnings.append("查询结果已超过最大传输字节限制，部分行被截断")
    if cell_truncated:
        warnings.append("部分字段内容超过最大长度限制，已被截断")
    if len(columns) > MAX_COLUMNS:
        warnings.append("列数超过最大展示限制，仅显示前 100 列")

    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "latencyMs": latency_ms,
        "guardrail": guard_res,
        "historyId": history.id,
        "executionId": execution_id,
        "truncated": truncated,
        "responseBytes": response_bytes,
        "maxResponseBytes": MAX_RESPONSE_BYTES,
        "warnings": warnings,
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
    1. Verify SELECT only
    2. Pass Guardrail check
    3. Execute EXPLAIN
    4. Format diagnostics and return warnings for slow patterns (type=ALL or key=NULL)
    """
    sql_strip = sql_str.strip().upper()
    if not sql_strip.startswith("SELECT"):
        raise ValueError("EXPLAIN 诊断仅支持 SELECT 语句")

    guard_res = guardrail_check(sql_str)
    if guard_res["result"] == "reject":
        from typing import cast
        raise GuardrailValidationError(
            guard_res["message"], checks=cast(Any, guard_res["checks"])
        )
        
    safe_sql = guard_res["safeSql"]
    
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")
        
    warnings = []
    records = []

    if is_demo_db(str(ds.host), str(ds.database_name)):
        # SQLite Explain Query Plan
        demo_path = init_demo_database()
        conn = sqlite3.connect(demo_path)
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
        "warnings": list(set(warnings))
    }
