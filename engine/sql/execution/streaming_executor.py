from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from engine.datasource import (
    datasource_connection_dict,
    get_mysql_connection_params,
    get_postgres_connection_params,
)
from engine.errors import GuardrailValidationError
from engine.models import DataSource
from engine.policy.sensitivity import _SENSITIVE_FALLBACK, load_sensitivity, redact_row
from engine.sql.pool_manager import _ping_mysql_connection, get_mysql_pool, get_postgres_pool
from engine.sql.row_serializer import _serialize_value
from engine.sql.safety_gate import _resolve_execution_safety_decision
from engine.sql.trust_gate import ExecutionSafetyDecision


DEFAULT_EXPORT_MAX_ROWS = 100_000


def export_max_rows_from_env() -> int:
    raw = os.environ.get("DBFOX_EXPORT_MAX_ROWS")
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_EXPORT_MAX_ROWS


class StreamingQueryExecutor:
    def __init__(self, db: Session, *, max_rows: int | None = None) -> None:
        self.db = db
        self.max_rows = max_rows or export_max_rows_from_env()

    def stream_rows(
        self,
        datasource_id: str,
        sql: str,
        decision: ExecutionSafetyDecision | dict[str, Any],
        chunk_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        resolved = _resolve_execution_safety_decision(
            db=self.db,
            datasource_id=datasource_id,
            sql_str=sql,
            bypass_guardrail=False,
            safety_decision=decision,
            policy="export",
        )
        if not resolved.can_execute or not str(resolved.safe_sql or "").strip():
            raise GuardrailValidationError("Export SQL is blocked by safety rules.")

        ds = self.db.query(DataSource).filter(DataSource.id == datasource_id).first()
        if ds is None:
            raise ValueError("Data source not found")

        safe_sql = str(resolved.safe_sql or "").strip()
        sensitivity = self._load_sensitivity(datasource_id)
        db_type = str(ds.db_type or "mysql").lower()
        if db_type == "sqlite":
            yield from self._stream_sqlite(ds, safe_sql, chunk_size, sensitivity)
        elif db_type in {"postgresql", "postgres"}:
            yield from self._stream_postgres(datasource_id, ds, safe_sql, chunk_size, sensitivity)
        else:
            yield from self._stream_mysql(datasource_id, ds, safe_sql, chunk_size, sensitivity)

    def _load_sensitivity(self, datasource_id: str) -> Any:
        try:
            return load_sensitivity(self.db, datasource_id)
        except Exception:
            return _SENSITIVE_FALLBACK

    def _redact(self, row: dict[str, Any], sensitivity: Any) -> dict[str, Any]:
        try:
            return redact_row(row, sensitivity)
        except Exception:
            return redact_row(row, _SENSITIVE_FALLBACK)

    def _stream_sqlite(
        self,
        ds: DataSource,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
    ) -> Iterator[dict[str, Any]]:
        conn = sqlite3.connect(str(ds.database_name or ""))
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [item[0] for item in cursor.description or []]
            yielded = 0
            while yielded < self.max_rows:
                rows = cursor.fetchmany(min(chunk_size, self.max_rows - yielded))
                if not rows:
                    break
                for raw in rows:
                    row = {column: _serialize_value(value) for column, value in zip(columns, raw)}
                    yield self._redact(row, sensitivity)
                    yielded += 1
                    if yielded >= self.max_rows:
                        break
        finally:
            conn.close()

    def _stream_postgres(
        self,
        datasource_id: str,
        ds: DataSource,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
    ) -> Iterator[dict[str, Any]]:
        params = get_postgres_connection_params(datasource_connection_dict(ds))
        pool = get_postgres_pool(datasource_id, params)
        conn_proxy: Any = pool.connect()
        cursor: Any | None = None
        try:
            raw_conn = getattr(conn_proxy, "connection", None) or conn_proxy
            cursor = raw_conn.cursor(name=f"dbfox_export_{uuid.uuid4().hex}")
            cursor.itersize = chunk_size
            cursor.execute(sql)
            columns = [item[0] for item in cursor.description or []]
            yielded = 0
            while yielded < self.max_rows:
                rows = cursor.fetchmany(min(chunk_size, self.max_rows - yielded))
                if not rows:
                    break
                for raw in rows:
                    row = {column: _serialize_value(value) for column, value in zip(columns, raw)}
                    yield self._redact(row, sensitivity)
                    yielded += 1
                    if yielded >= self.max_rows:
                        break
        finally:
            if cursor is not None:
                cursor.close()
            conn_proxy.close()

    def _stream_mysql(
        self,
        datasource_id: str,
        ds: DataSource,
        sql: str,
        chunk_size: int,
        sensitivity: Any,
    ) -> Iterator[dict[str, Any]]:
        import pymysql

        params = get_mysql_connection_params(datasource_connection_dict(ds))
        pool = get_mysql_pool(datasource_id, params)
        conn_proxy: Any = pool.connect()
        cursor: Any | None = None
        try:
            raw_conn = _ping_mysql_connection(conn_proxy)
            cursor = raw_conn.cursor(pymysql.cursors.SSCursor)
            cursor.execute(sql)
            columns = [item[0] for item in cursor.description or []]
            yielded = 0
            while yielded < self.max_rows:
                rows = cursor.fetchmany(min(chunk_size, self.max_rows - yielded))
                if not rows:
                    break
                for raw in rows:
                    row = {column: _serialize_value(value) for column, value in zip(columns, raw)}
                    yield self._redact(row, sensitivity)
                    yielded += 1
                    if yielded >= self.max_rows:
                        break
        finally:
            if cursor is not None:
                cursor.close()
            conn_proxy.close()

