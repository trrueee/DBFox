from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

from sqlalchemy.orm import Session

from engine.models import AgentArtifactRecord, AgentRun, DataSource
from engine.sql.dialect_context import DialectContext
from engine.sql.execution.csv_export import CsvExportService
from engine.sql.execution.streaming_executor import StreamingQueryExecutor
from engine.sql.guardrail import GuardrailResult
from engine.sql.result_view.compiler import ResultViewCompiler
from engine.sql.result_view.fingerprint import result_source_fingerprint
from engine.sql.result_view.models import (
    ResultColumn,
    ResultExportQuery,
    ResultPage,
    ResultPageQuery,
    ResultSourceRef,
    ResultViewError,
    ResultViewQuery,
    VerifiedResultSource,
)
from engine.sql.safety.service import SqlSafetyService
from engine.sql.trust_gate import ExecutionSafetyDecision

logger = logging.getLogger("dbfox.sql.result_view")

RowExecutor = Callable[..., dict[str, Any]]


class ResultViewService:
    def __init__(
        self,
        db: Session,
        *,
        row_executor: RowExecutor | None = None,
        streaming_executor: StreamingQueryExecutor | None = None,
        compiler: ResultViewCompiler | None = None,
    ) -> None:
        self.db = db
        self.row_executor = row_executor
        self.streaming_executor = streaming_executor or StreamingQueryExecutor(db)
        self.compiler = compiler or ResultViewCompiler()

    def load_verified_source(self, source_ref: ResultSourceRef, ctx: DialectContext | None = None) -> VerifiedResultSource:
        ctx = ctx or DialectContext.from_datasource_id(self.db, source_ref.datasource_id)
        source = self._load_source_artifact(source_ref.datasource_id, source_ref.source_sql_artifact_id)
        if source is None:
            raise ResultViewError(
                "SOURCE_ARTIFACT_NOT_FOUND",
                "Source result artifact was not found.",
                status_code=404,
            )
        if source.type not in {"result_view", "table", "sql"}:
            raise ResultViewError("SOURCE_ARTIFACT_UNSUPPORTED", "Source artifact cannot back pagination.")

        payload = _artifact_payload(source)
        persisted_safe_sql = _safe_sql_from_payload(payload)
        if not persisted_safe_sql:
            raise ResultViewError("SOURCE_SQL_MISSING", "Source artifact does not contain safe SQL.")

        artifact_dialect = str(payload.get("dialect") or ctx.dialect)
        persisted_fp = _artifact_fingerprint(payload, persisted_safe_sql, artifact_dialect)
        requested_fp = _result_source_fingerprint(source_ref.safe_sql, artifact_dialect)
        if persisted_fp != requested_fp:
            raise ResultViewError("SOURCE_SQL_MISMATCH", "Requested SQL does not match the source artifact.")

        source_ctx = DialectContext(
            datasource_id=source_ref.datasource_id,
            dialect=ctx.dialect,
            schema_cache=ctx.schema_cache,
        )
        warnings = SqlSafetyService().validate_source_artifact_sql(persisted_safe_sql, source_ctx)
        if warnings:
            raise ResultViewError("SOURCE_SQL_VALIDATION_FAILED", warnings[0])

        columns = _result_columns_from_payload(payload)
        return VerifiedResultSource(
            datasource_id=source_ref.datasource_id,
            source_sql_artifact_id=source_ref.source_sql_artifact_id,
            safe_sql=persisted_safe_sql,
            dialect=artifact_dialect,
            columns=columns,
            fingerprint=persisted_fp,
        )

    def build_page_sql(self, query: ResultPageQuery) -> str:
        ctx = DialectContext.from_datasource_id(self.db, query.source.datasource_id)
        source = self.load_verified_source(query.source, ctx)
        return self.compiler.build_page_sql(query, source, ctx)

    def build_count_sql(self, query: ResultPageQuery) -> str:
        ctx = DialectContext.from_datasource_id(self.db, query.source.datasource_id)
        source = self.load_verified_source(query.source, ctx)
        count_sql = self.compiler.build_count_sql(query, source, ctx)
        self._validate_derived_sql(count_sql, ctx)
        return count_sql

    def build_export_sql(self, query: ResultExportQuery) -> str:
        ctx = DialectContext.from_datasource_id(self.db, query.source.datasource_id)
        source = self.load_verified_source(query.source, ctx)
        export_sql = self.compiler.build_export_sql(query, source, ctx)
        self._validate_derived_sql(export_sql, ctx)
        return export_sql

    def page(self, query: ResultPageQuery) -> ResultPage:
        ctx = DialectContext.from_datasource_id(self.db, query.source.datasource_id)
        source = self.load_verified_source(query.source, ctx)
        page_sql = self.compiler.build_page_sql(query, source, ctx)
        self._validate_derived_sql(page_sql, ctx)
        page_decision = self._result_view_decision(query.source.datasource_id, source.safe_sql, page_sql, scope="page")
        res = self._execute_query(
            self.db,
            query.source.datasource_id,
            page_sql,
            safety_decision=page_decision,
            safety_policy="readonly",
        )

        rows = list(res.get("rows") or [])
        has_next = len(rows) > query.page_size
        returned_rows = rows[: query.page_size]
        row_count: int | None = None
        if query.count_mode == "exact":
            try:
                count_sql = self.compiler.build_count_sql(query, source, ctx)
                self._validate_derived_sql(count_sql, ctx)
                count_decision = self._result_view_decision(
                    query.source.datasource_id,
                    source.safe_sql,
                    count_sql,
                    scope="count",
                )
                count_res = self._execute_query(
                    self.db,
                    query.source.datasource_id,
                    count_sql,
                    safety_decision=count_decision,
                    safety_policy="readonly",
                )
                count_rows = list(count_res.get("rows") or [])
                if count_rows and count_rows[0]:
                    row_count = int(list(count_rows[0].values())[0])
            except Exception as exc:
                logger.warning("Failed to execute exact count query: %s", exc)

        return ResultPage(
            columns=list(res.get("columns") or []),
            rows=returned_rows,
            page=query.page,
            page_size=query.page_size,
            row_count=row_count,
            has_next_page=has_next,
            executed_sql=page_sql,
            latency_ms=int(res.get("latencyMs") or 0),
            warnings=res.get("warnings"),
            notices=res.get("notices"),
        )

    def export_csv_stream(self, query: ResultExportQuery, *, chunk_size: int = 1000) -> tuple[Iterator[str], list[str]]:
        ctx = DialectContext.from_datasource_id(self.db, query.source.datasource_id)
        source = self.load_verified_source(query.source, ctx)
        export_sql = self.compiler.build_export_sql(query, source, ctx)
        self._validate_derived_sql(export_sql, ctx)
        decision = self._result_view_decision(query.source.datasource_id, source.safe_sql, export_sql, scope="export")
        columns = source.column_names
        rows = self.streaming_executor.stream_rows(
            query.source.datasource_id,
            export_sql,
            decision,
            chunk_size=chunk_size,
        )
        return CsvExportService.stream_csv(rows, columns), columns

    def _execute_query(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self.row_executor is not None:
            return self.row_executor(*args, **kwargs)
        from engine.sql.executor import execute_query

        return execute_query(*args, **kwargs)

    def _load_source_artifact(self, datasource_id: str, source_artifact_id: str) -> AgentArtifactRecord | None:
        base_query = (
            self.db.query(AgentArtifactRecord)
            .join(AgentRun, AgentRun.id == AgentArtifactRecord.run_id)
            .filter(AgentRun.datasource_id == datasource_id)
        )
        by_id = base_query.filter(AgentArtifactRecord.id == source_artifact_id).first()
        if by_id is not None:
            return by_id
        return (
            base_query.filter(AgentArtifactRecord.semantic_id == source_artifact_id)
            .order_by(AgentArtifactRecord.created_at.desc())
            .first()
        )

    def _validate_derived_sql(self, sql: str, ctx: DialectContext) -> None:
        warnings = SqlSafetyService().validate_derived_sql(sql, ctx)
        if warnings:
            raise ResultViewError("DERIVED_SQL_VALIDATION_FAILED", warnings[0])

    def _result_view_decision(
        self,
        datasource_id: str,
        original_sql: str,
        safe_sql: str,
        *,
        scope: str,
    ) -> ExecutionSafetyDecision:
        guardrail: GuardrailResult = {
            "result": "pass",
            "originalSql": original_sql,
            "safeSql": safe_sql,
            "checks": [],
            "message": "Result view SQL derived from persisted safe SQL artifact.",
        }
        return ExecutionSafetyDecision(
            datasource_id=datasource_id,
            policy="export" if scope == "export" else "readonly",
            original_sql=original_sql,
            safe_sql=safe_sql,
            passed=True,
            can_execute=True,
            requires_confirmation=False,
            guardrail=guardrail,
            schema_warnings=[],
            scope_state={"source": f"result_view:{scope}"},
            messages=[],
        )


def _artifact_payload(record: AgentArtifactRecord) -> dict[str, object]:
    try:
        payload_json = record.payload_json if isinstance(record.payload_json, str) else "{}"
        payload = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_sql_from_payload(payload: dict[str, object]) -> str:
    for key in ("safeSql", "safe_sql", "sourceSql", "source_sql", "sql"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _result_columns_from_payload(payload: dict[str, object]) -> list[ResultColumn]:
    raw_columns = payload.get("columns")
    if not isinstance(raw_columns, list):
        return []

    columns: list[ResultColumn] = []
    seen: set[str] = set()
    for item in raw_columns:
        name = ""
        column_type: str | None = None
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            raw_name = item.get("name") or item.get("field") or item.get("column")
            name = raw_name if isinstance(raw_name, str) else ""
            raw_type = item.get("type") or item.get("dataType") or item.get("data_type")
            column_type = raw_type if isinstance(raw_type, str) else None
        name = name.strip()
        normalized = _normalize_result_column_name(name)
        if name and normalized not in seen:
            seen.add(normalized)
            columns.append(ResultColumn(name=name, type=column_type))
    return columns


def _normalize_result_column_name(column: str) -> str:
    return column.strip().strip('`"[]').lower()


def _artifact_fingerprint(payload: dict[str, object], safe_sql: str, dialect: str) -> str:
    raw = payload.get("fingerprint") or payload.get("sqlFingerprint") or payload.get("sql_fingerprint")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return result_source_fingerprint(safe_sql, dialect)


def _result_source_fingerprint(sql: str, dialect: str) -> str:
    return result_source_fingerprint(sql, dialect)
