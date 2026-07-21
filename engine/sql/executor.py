from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_message,
    log_unexpected_exception,
)
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile
from engine.datasource import datasource_connection_dict
from engine.errors import (
    GuardrailValidationError,
    SQLExecutionError,
    SQLQueryCancelledError,
    SQLQueryTimeoutError,
)
from engine.models import DataSource, QueryHistory
from engine.policy.redactor import DataRedactor
from engine.policy.sensitivity import _SENSITIVE_FALLBACK
from engine.persistence.search_index import SearchIndexService


def _sql_execution_failure_message() -> str:
    return fixed_error_message(FixedErrorCode.SQL_EXECUTION_FAILED)


def _write_query_history(db: Session, history: QueryHistory) -> str | None:
    """Persist a QueryHistory record in an isolated audit session.

    Returns the history record ID on success, or ``None`` if the write fails.
    The independent session prevents the audit log from participating in the
    caller's transaction (history must survive a caller rollback).
    Also populates the FTS5 index for query history search.
    """
    if os.getenv("DBFOX_DISABLE_QUERY_HISTORY", "").strip().lower() in {"1", "true", "yes", "on"}:
        return None

    from sqlalchemy.orm import sessionmaker

    audit_db = sessionmaker(bind=db.get_bind())()
    try:
        audit_db.add(history)
        audit_db.commit()
        try:
            SearchIndexService(audit_db).index_query_history(history)
            audit_db.commit()
        except Exception as exc:
            audit_db.rollback()
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.QUERY_HISTORY_INDEX_POPULATE,
                exc=exc,
                level="warning",
            )
        history_id = getattr(history, "id", None)
        return str(history_id) if history_id else None
    except Exception as exc:
        audit_db.rollback()
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.QUERY_HISTORY_WRITE,
            exc=exc,
            level="warning",
        )
        return None
    finally:
        audit_db.close()
from engine.sql.dialect.sqlite import _execute_on_sqlite_profiled
from engine.sql.dialect.postgres import _execute_on_postgres_profiled
from engine.sql.dialect.mysql import _execute_on_mysql_profiled
from engine.sql.result_limits import MAX_CELL_CHARS, MAX_COLUMNS, MAX_RESPONSE_BYTES, MAX_ROWS
from engine.sql.row_serializer import (
    _process_rows, _serialize_value,
    JSON_OVERHEAD_BYTES,
    ResultTruncation,
)
from engine.sql.safety_gate import (
    _resolve_execution_safety_decision,
    _decision_checks_for_history,
    _decision_checks_for_error,
    _decision_block_message,
)
from engine.sql.guardrail import GuardrailResult
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
    guard_res: GuardrailResult,
    guardrail_ms: int,
    guard_checks_json: str,
    redact: bool = True,
    expected_connection_generation: int | None = None,
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
    truncation = ResultTruncation()
    response_bytes = JSON_OVERHEAD_BYTES
    error_message: str | None = None
    execution_status = "success"

    connect_ms = 0
    execute_ms = 0
    fetch_ms = 0
    serialize_ms = 0

    try:
        # Reload immediately before deriving the connection profile. A stale
        # ORM identity map must not let an Agent run use a datasource that was
        # reconfigured after the run captured its generation.
        db.refresh(ds)
        _assert_expected_connection_generation(ds, expected_connection_generation)
        profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
        factory = ConnectionFactory()
        if profile.dialect == "sqlite":
            execution_result = _execute_on_sqlite_profiled(
                safe_sql,
                profile=profile,
                execution_id=execution_id,
                datasource_id=datasource_id,
                connection_factory=factory,
            )
        elif profile.dialect == "duckdb":
            from engine.sql.dialect.duckdb import _execute_on_duckdb_profiled

            execution_result = _execute_on_duckdb_profiled(
                datasource_id,
                profile,
                safe_sql,
                execution_id=execution_id,
                connection_factory=factory,
            )
        elif profile.dialect == "postgresql":
            execution_result = _execute_on_postgres_profiled(
                datasource_id,
                profile,
                safe_sql,
                execution_id=execution_id,
                connection_factory=factory,
            )
        else:
            execution_result = _execute_on_mysql_profiled(
                datasource_id,
                profile,
                safe_sql,
                execution_id=execution_id,
                connection_factory=factory,
            )
        rows = execution_result.rows
        columns = execution_result.columns
        truncation = execution_result.truncation
        response_bytes = execution_result.response_bytes
        connect_ms = execution_result.connect_ms
        execute_ms = execution_result.execute_ms
        fetch_ms = execution_result.fetch_ms
        serialize_ms = execution_result.serialize_ms
    except SQLQueryCancelledError:
        execution_status = "cancelled"
        error_message = _sql_execution_failure_message()
        raise
    except TimeoutError:
        execution_status = "timeout"
        error_message = _sql_execution_failure_message()
        raise SQLQueryTimeoutError(error_message) from None
    except Exception:
        execution_status = "failed"
        error_message = _sql_execution_failure_message()
        raise SQLExecutionError(error_message) from None

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
        
        history_id = _write_query_history(db, history)

    # Apply redaction pipeline at the executor level if requested
    if redact:
        from engine.policy.sensitivity import load_sensitivity, redact_row
        try:
            sensitivity = load_sensitivity(db, datasource_id)
            rows = [redact_row(row, sensitivity) for row in rows]
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.SQL_SENSITIVITY_LOAD,
                exc=exc,
                level="warning",
            )
            rows = [redact_row(row, _SENSITIVE_FALLBACK) for row in rows]

        # Redaction can change the serialized byte size (for example, a number
        # can become the literal "[REDACTED]"). Re-apply the transport contract
        # to the final client-visible rows so responseBytes and its truncation
        # marker remain exact.
        redacted_payload = _process_rows(rows, columns)
        rows = redacted_payload.rows
        columns = redacted_payload.columns
        response_bytes = redacted_payload.response_bytes
        truncation = truncation.merged_with(redacted_payload.truncation)

    truncated = truncation.truncated
    cell_truncated = truncation.cells

    warnings = []
    notices = []
    if truncation.rows:
        warnings.append(f"查询结果超过最大 {MAX_ROWS} 行限制，仅返回前 {MAX_ROWS} 行")
    if truncation.columns:
        warnings.append(f"列数超过最大展示限制，仅显示前 {MAX_COLUMNS} 列")
    if truncation.response_bytes:
        warnings.append("查询结果已超过最大传输字节限制，部分行被截断")
    if cell_truncated:
        # Informational, not a problem: long text cells are clipped for preview/transfer.
        notices.append(f"部分长文本字段仅返回前 {MAX_CELL_CHARS} 字符")

    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "latencyMs": latency_ms,
        "guardrail": guard_res,
        "safetyDecision": None,  # filled by caller
        "historyId": history_id,
        "executionId": execution_id,
        "truncated": truncated,
        "rowTruncated": truncation.rows,
        "columnTruncated": truncation.columns,
        "responseBytesTruncated": truncation.response_bytes,
        "cellTruncated": cell_truncated,
        "responseBytes": response_bytes,
        "maxResponseBytes": MAX_RESPONSE_BYTES,
        "warnings": warnings,
        "notices": notices,
        "connectMs": connect_ms,
        "guardrailMs": guardrail_ms,
        "executeMs": execute_ms,
        "fetchMs": fetch_ms,
        "serializeMs": serialize_ms,
        "totalMs": latency_ms,
    }


def execute_query(
    db: Session,
    datasource_id: str,
    sql_str: str,
    question: str | None = None,
    execution_id: str | None = None,
    safety_decision: ExecutionSafetyDecision | dict[str, Any] | None = None,
    safety_policy: ExecutionPolicy = "readonly",
    redact: bool = True,
    expected_connection_generation: int | None = None,
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
    _assert_expected_connection_generation(ds, expected_connection_generation)

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
        
        _write_query_history(db, history)

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
        redact=redact,
        expected_connection_generation=expected_connection_generation,
    )
    result["safetyDecision"] = decision.model_dump(mode="json")
    return result


def _assert_expected_connection_generation(
    datasource: DataSource,
    expected_connection_generation: int | None,
) -> None:
    if expected_connection_generation is None:
        return
    if int(datasource.connection_generation) != int(expected_connection_generation):
        raise SQLExecutionError("Datasource connection profile changed.")

def _validate_explain_sql(sql: str, dialect: str) -> None:
    """Secondary safety check for EXPLAIN inputs — delegated to shared module.

    Kept as a re-export alias for backward compatibility; prefer importing
    ``validate_explain_sql`` directly from ``engine.sql.explain_validator``.
    """
    from engine.sql.explain_validator import validate_explain_sql as _impl
    _impl(sql, dialect)


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
    profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
    _validate_explain_sql(safe_sql, profile.dialect)
        
    warnings: list[str] = []
    records: list[dict[str, Any]] = []

    if profile.dialect == "sqlite":
        from engine.sql.dialect.sqlite import explain as explain_sqlite
        records, warnings = explain_sqlite(profile, safe_sql)
    elif profile.dialect == "duckdb":
        from engine.sql.dialect.duckdb import explain as explain_duckdb

        records, warnings = explain_duckdb(profile, safe_sql)
    elif profile.dialect == "postgresql":
        from engine.sql.postgres_explain import explain_postgres_sql
        return explain_postgres_sql(db, datasource_id, sql_str)
    else:
        from engine.sql.dialect.mysql import explain as explain_mysql
        records, warnings = explain_mysql(profile, safe_sql)
            
    return {
        "success": True,
        "records": records,
        "warnings": list(set(warnings)),
        "safetyDecision": decision.model_dump(mode="json"),
    }


