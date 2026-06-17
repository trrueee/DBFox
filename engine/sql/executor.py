from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from engine.datasource import (
    datasource_connection_dict,
    get_mysql_connection_params,
    get_postgres_connection_params,
)
from engine.errors import (
    GuardrailValidationError,
    SQLExecutionError,
    SQLQueryCancelledError,
    SQLQueryTimeoutError,
)
from engine.models import DataSource, QueryHistory
from engine.policy.redactor import DataRedactor
from engine.query_registry import QUERY_REGISTRY
from engine.sql.pool_manager import get_mysql_pool, get_postgres_pool, _ping_mysql_connection
from engine.sql.dialect.sqlite import _execute_on_sqlite, _execute_on_sqlite_profiled
from engine.sql.dialect.postgres import _execute_on_postgres_profiled
from engine.sql.dialect.mysql import _execute_on_mysql, _execute_on_mysql_profiled
from engine.sql.row_serializer import (
    _fetch_and_serialize, _serialize_value, _process_rows,
    MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS, MAX_RESPONSE_BYTES,
    QUERY_TIMEOUT_MS, ProcessedRows,
)
from engine.sql.safety_gate import (
    guardrail_bypass_allowed,
    _resolve_execution_safety_decision,
    _decision_checks_for_history,
    _decision_checks_for_error,
    _decision_block_message,
    validate_sql_schema,
    _is_projection_alias_reference,
)
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision

logger = logging.getLogger("dbfox.sql.executor")





def _run_approved_query(
    db: Session,
    ds: DataSource,
    datasource_id: str,
    safe_sql: str,
    sql_str: str,
    question: str | None,
    execution_id: str,
    guard_res: dict,
    guardrail_ms: int,
    guard_checks_json: str,
) -> dict[str, Any]:
    """Execute safety-approved SQL on the target datasource and record history.

    This is the shared execution tail called by both ``execute_query`` (public,
    bypass_guardrail=False) and ``execute_query_for_test`` (test-only,
    bypass_guardrail=True).  It assumes the caller has already resolved the
    safety decision and verified ``can_execute`` / ``safe_sql``.
    """
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
            conn_params = get_postgres_connection_params(datasource_connection_dict(ds))
            rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms = _execute_on_postgres_profiled(
                datasource_id,
                conn_params,
                safe_sql,
                execution_id=execution_id,
            )
        else:
            conn_params = get_mysql_connection_params(datasource_connection_dict(ds))
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
        "safetyDecision": None,  # filled by caller
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


def execute_query(
    db: Session,
    datasource_id: str,
    sql_str: str,
    question: str | None = None,
    execution_id: str | None = None,
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
        bypass_guardrail=False,
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
    result = _run_approved_query(
        db=db,
        ds=ds,
        datasource_id=datasource_id,
        safe_sql=safe_sql,
        sql_str=sql_str,
        question=question,
        execution_id=execution_id,
        guard_res=guard_res,
        guardrail_ms=guardrail_ms,
        guard_checks_json=guard_checks_json,
    )
    result["safetyDecision"] = decision.model_dump(mode="json")
    return result


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
        conn_params = get_mysql_connection_params(datasource_connection_dict(ds))
        
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


