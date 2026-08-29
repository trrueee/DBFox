"""Data-owned Artifact representations for analytical results."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import cmp_to_key
import time
from typing import Any
from uuid import uuid4

from dbfox_dlc_api import (
    DATAFRAME_REPRESENTATION_TYPE,
    Artifact,
    ArtifactRepresentationContext,
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationError,
    ArtifactRepresentationOperation,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
    ArtifactRepresentationStream,
    DataFrameExportRequest,
    DataFrameField,
    DataFrameFilter,
    DataFramePage,
    DataFramePageRequest,
    DataFrameSort,
)

from .artifact_contracts import (
    RESULT_VIEW_ARTIFACT_TYPE,
    SNAPSHOT_ARTIFACT_TYPE,
    SQL_ARTIFACT_TYPE,
    SqlArtifactPayload,
)
from .connection import DataConnectionBoundary
from .query_identity import query_fingerprint
from .resource_kind import DATABASE_RESOURCE_KIND
from .sql.execution.csv_export import CsvExportService
from .sql.sql_backed_view import (
    SqlBackedFilter,
    SqlBackedSort,
    SqlBackedViewError,
    build_sql_backed_count_sql,
    build_sql_backed_page_sql,
)
from .store import DataStateStore, StoredResultPage

def _error(
    code: str,
    message: str,
    *,
    status_code: int = 400,
) -> ArtifactRepresentationError:
    return ArtifactRepresentationError(code, message, status_code=status_code)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _compare(left: Any, right: Any) -> int:
    if left is None or right is None:
        return 0 if left is right else (-1 if left is None else 1)
    left_number = _decimal(left)
    right_number = _decimal(right)
    if left_number is not None and right_number is not None:
        return (left_number > right_number) - (left_number < right_number)
    left_text = _text(left).casefold()
    right_text = _text(right).casefold()
    return (left_text > right_text) - (left_text < right_text)


def _matches_filter(value: Any, spec: DataFrameFilter) -> bool:
    operator = spec.operator
    expected = spec.value
    if operator == "is_null":
        return value is None
    if operator == "is_not_null":
        return value is not None
    if operator in {"in", "not_in"}:
        expected_values = expected if isinstance(expected, list) else [expected]
        matched = any(_compare(value, item) == 0 for item in expected_values)
        return matched if operator == "in" else not matched
    if operator in {"contains", "starts_with", "ends_with"}:
        actual_text = _text(value).casefold()
        expected_text = _text(expected).casefold()
        if operator == "contains":
            return expected_text in actual_text
        if operator == "starts_with":
            return actual_text.startswith(expected_text)
        return actual_text.endswith(expected_text)
    comparison = _compare(value, expected)
    if operator == "equals":
        return comparison == 0
    if operator == "not_equals":
        return comparison != 0
    if value is None or expected is None:
        return False
    return {
        "gt": comparison > 0,
        "gte": comparison >= 0,
        "lt": comparison < 0,
        "lte": comparison <= 0,
    }[operator]


def _apply_view(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    filters: tuple[DataFrameFilter, ...],
    sort: tuple[DataFrameSort, ...],
    search: str | None,
) -> list[dict[str, Any]]:
    allowed = set(columns)
    requested_fields = {item.field for item in (*filters, *sort)}
    unknown = sorted(requested_fields - allowed)
    if unknown:
        raise _error(
            "INVALID_REQUEST",
            f"DataFrame request references unavailable fields: {', '.join(unknown)}",
            status_code=422,
        )
    search_text = str(search or "").strip().casefold()
    viewed = [
        row
        for row in rows
        if all(_matches_filter(row.get(spec.field), spec) for spec in filters)
        and (
            not search_text
            or any(search_text in _text(row.get(column)).casefold() for column in columns)
        )
    ]
    if sort:

        def compare_rows(left: dict[str, Any], right: dict[str, Any]) -> int:
            for spec in sort:
                result = _compare(left.get(spec.field), right.get(spec.field))
                if result:
                    return -result if spec.direction == "desc" else result
            return 0

        viewed.sort(key=cmp_to_key(compare_rows))
    return viewed


def _field_type(artifact: Artifact, column: str, values: list[Any]) -> str:
    declared = ""
    payload_columns = artifact.payload.get("columns")
    if isinstance(payload_columns, list):
        for candidate in payload_columns:
            if isinstance(candidate, dict) and str(candidate.get("name") or "") == column:
                declared = str(candidate.get("type") or "").casefold()
                break
    if "bool" in declared:
        return "boolean"
    if "int" in declared:
        return "integer"
    if any(token in declared for token in ("number", "numeric", "decimal", "float", "double", "real")):
        return "number"
    if "datetime" in declared or "timestamp" in declared:
        return "datetime"
    if declared == "date" or declared.endswith(" date"):
        return "date"
    if declared == "time" or declared.endswith(" time"):
        return "time"
    if "json" in declared:
        return "json"
    if any(token in declared for token in ("binary", "blob", "byte")):
        return "binary"
    if any(token in declared for token in ("char", "text", "string", "uuid")):
        return "string"

    present = [value for value in values if value is not None]
    if not present:
        return "unknown"
    if all(isinstance(value, bool) for value in present):
        return "boolean"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in present):
        return "integer"
    if all(isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) for value in present):
        return "number"
    if all(isinstance(value, (dict, list)) for value in present):
        return "json"
    if all(isinstance(value, (bytes, bytearray, memoryview)) for value in present):
        return "binary"
    if all(isinstance(value, str) for value in present):
        return "string"
    return "unknown"


@dataclass(frozen=True)
class DataRepresentationRows:
    columns: list[str]
    rows: list[dict[str, Any]]
    source_version: str
    source_fingerprint: str
    source_truncated: bool
    consistency: str


@dataclass(frozen=True)
class _LiveSource:
    sql: str
    parameters: dict[str, Any]
    dialect: str
    columns: list[str]
    database_id: str
    resource_version: str
    query_fingerprint: str
    handle: Any


def _execution_latency_ms(result: Any) -> int:
    return sum(
        int(getattr(result, field, 0) or 0)
        for field in ("connect_ms", "execute_ms", "fetch_ms", "serialize_ms")
    )


class DataResultRepresentation:
    """DataFrame provider for live Results and exact durable Snapshots."""

    def __init__(
        self,
        store: DataStateStore,
        connection: DataConnectionBoundary,
    ) -> None:
        self._store = store
        self._connection = connection

    def describe(self, artifact: Artifact) -> ArtifactRepresentationDescriptor:
        if artifact.type not in {RESULT_VIEW_ARTIFACT_TYPE, SNAPSHOT_ARTIFACT_TYPE}:
            raise _error(
                "UNSUPPORTED_REPRESENTATION",
                "Artifact is not a Data Result or Snapshot.",
                status_code=409,
            )
        return ArtifactRepresentationDescriptor(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            version=1,
            operations=(
                ArtifactRepresentationOperation(name="page"),
                ArtifactRepresentationOperation(
                    name="export.csv",
                    result_kind="stream",
                    media_type="text/csv",
                ),
            ),
        )

    def _load_snapshot(self, artifact: Artifact) -> StoredResultPage:
        is_historical_result = (
            artifact.type == RESULT_VIEW_ARTIFACT_TYPE and artifact.schema_version == 1
        )
        is_snapshot = artifact.type == SNAPSHOT_ARTIFACT_TYPE
        if not (is_historical_result or is_snapshot) or not artifact.payload_ref:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "This Artifact is not backed by a durable Data snapshot.",
                status_code=409,
            )
        database_refs = tuple(
            ref for ref in artifact.resource_refs if ref.kind == DATABASE_RESOURCE_KIND
        )
        if len(database_refs) != 1 or len(artifact.resource_refs) != 1:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The snapshot has an invalid database binding.",
                status_code=409,
            )
        try:
            header = self._store.load_query_result_page(
                artifact.payload_ref,
                offset=0,
                limit=1,
            )
            stored = self._store.load_query_result_page(
                artifact.payload_ref,
                offset=0,
                limit=max(header.row_count, 1),
            )
        except (KeyError, ValueError, RuntimeError) as exc:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The durable Data result payload is unavailable.",
                status_code=404,
            ) from exc
        database_ref = database_refs[0]
        if (
            stored.database_resource_id != database_ref.id
            or stored.resource_version != str(database_ref.version or "")
            or stored.query_fingerprint
            != str(artifact.payload.get("queryFingerprint") or "")
        ):
            raise _error(
                "SOURCE_CHANGED",
                "The snapshot does not match its durable payload.",
                status_code=409,
            )
        return stored

    def _live_source(
        self,
        artifact: Artifact,
        context: ArtifactRepresentationContext,
    ) -> _LiveSource:
        if (
            artifact.type != RESULT_VIEW_ARTIFACT_TYPE
            or artifact.schema_version != 2
            or artifact.payload.get("backend") != "sql_reexecution"
            or artifact.payload_ref is not None
        ):
            raise _error(
                "UNSUPPORTED_REPRESENTATION",
                "The Result Artifact does not use the live SQL backend contract.",
                status_code=409,
            )
        source_id = str(artifact.payload.get("sourceSqlArtifactId") or "").strip()
        derived_source_ids = {
            relation.artifact_id
            for relation in artifact.relations
            if relation.relation.value == "derived_from"
        }
        if not source_id or derived_source_ids != {source_id}:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The Result Artifact has no unambiguous SQL source.",
                status_code=409,
            )
        source = context.artifact(source_id)
        if (
            source.type != SQL_ARTIFACT_TYPE
            or source.session_id != artifact.session_id
            or source.resource_refs != artifact.resource_refs
        ):
            raise _error(
                "SOURCE_CHANGED",
                "The Result Artifact no longer matches its SQL source.",
                status_code=409,
            )
        try:
            sql_payload = SqlArtifactPayload.model_validate(source.payload)
        except ValueError as exc:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The SQL source payload is invalid.",
                status_code=409,
            ) from exc
        database_refs = tuple(
            ref for ref in artifact.resource_refs if ref.kind == DATABASE_RESOURCE_KIND
        )
        if len(database_refs) != 1 or len(artifact.resource_refs) != 1:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The Result Artifact has an invalid database binding.",
                status_code=409,
            )
        resource_ref = database_refs[0]
        resource_version = str(resource_ref.version or "")
        try:
            handle = self._store.resolve_artifact_database(
                resource_ref.id,
                resource_version,
            )
        except KeyError as exc:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The database source is unavailable.",
                status_code=404,
            ) from exc
        except ValueError as exc:
            raise _error(
                "SOURCE_CHANGED",
                "The database source generation has changed.",
                status_code=409,
            ) from exc
        parameters = dict(sql_payload.parameters)
        fingerprint = query_fingerprint(resource_ref, sql_payload.safe_sql, parameters)
        if (
            not sql_payload.safe_sql
            or sql_payload.query_fingerprint != fingerprint
            or str(artifact.payload.get("queryFingerprint") or "") != fingerprint
            or str(artifact.payload.get("datasourceGeneration") or "")
            != resource_version
            or sql_payload.dialect != handle.profile.provider
        ):
            raise _error(
                "SOURCE_CHANGED",
                "The Result Artifact query identity no longer matches its source.",
                status_code=409,
            )
        columns = [str(column) for column in artifact.payload.get("columns") or []]
        if not columns or len(columns) != len(set(columns)):
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The Result Artifact has no valid output schema.",
                status_code=409,
            )
        return _LiveSource(
            sql=sql_payload.safe_sql,
            parameters=parameters,
            dialect=sql_payload.dialect,
            columns=columns,
            database_id=resource_ref.id,
            resource_version=resource_version,
            query_fingerprint=fingerprint,
            handle=handle,
        )

    @staticmethod
    def _snapshot_view(
        stored: StoredResultPage,
        *,
        filters: tuple[DataFrameFilter, ...],
        sort: tuple[DataFrameSort, ...],
        search: str | None,
    ) -> list[dict[str, Any]]:
        return _apply_view(
            stored.rows,
            stored.columns,
            filters=filters,
            sort=sort,
            search=search,
        )

    @staticmethod
    def _sql_filters(
        filters: tuple[DataFrameFilter, ...],
    ) -> list[SqlBackedFilter]:
        return [
            SqlBackedFilter(
                column=item.field,
                operator=item.operator,
                value=item.value,
            )
            for item in filters
        ]

    @staticmethod
    def _sql_sorts(sort: tuple[DataFrameSort, ...]) -> list[SqlBackedSort]:
        return [
            SqlBackedSort(column=item.field, direction=item.direction)
            for item in sort
        ]

    def _execute_live(
        self,
        source: _LiveSource,
        sql: str,
    ) -> Any:
        try:
            return self._connection.execute_readonly(
                source.handle,
                sql,
                invocation_id=f"representation-{uuid4().hex}",
                parameters=source.parameters,
            )
        except Exception as exc:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The live SQL source could not be read.",
                status_code=503,
            ) from exc

    def rows(
        self,
        artifact: Artifact,
        context: ArtifactRepresentationContext,
        *,
        max_rows: int = 1_000,
    ) -> DataRepresentationRows:
        if artifact.type == SNAPSHOT_ARTIFACT_TYPE or artifact.schema_version == 1:
            stored = self._load_snapshot(artifact)
            return DataRepresentationRows(
                columns=stored.columns,
                rows=stored.rows[:max_rows],
                source_version=stored.resource_version,
                source_fingerprint=stored.query_fingerprint,
                source_truncated=stored.source_truncated or len(stored.rows) > max_rows,
                consistency="durable_snapshot",
            )
        source = self._live_source(artifact, context)
        try:
            query = build_sql_backed_page_sql(
                base_sql=source.sql,
                dialect=source.dialect,
                columns=source.columns,
                limit=max_rows + 1,
            )
        except SqlBackedViewError as exc:
            raise _error(
                "SOURCE_UNAVAILABLE",
                "The Result SQL source is no longer valid.",
                status_code=409,
            ) from exc
        result = self._execute_live(source, query.sql)
        return DataRepresentationRows(
            columns=source.columns,
            rows=result.rows[:max_rows],
            source_version=source.resource_version,
            source_fingerprint=source.query_fingerprint,
            source_truncated=result.truncated or len(result.rows) > max_rows,
            consistency="live_reexecution",
        )

    def _execute_snapshot(
        self,
        artifact: Artifact,
        request: ArtifactRepresentationRequest,
    ) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        stored = self._load_snapshot(artifact)
        if request.operation == "export.csv":
            export_request = DataFrameExportRequest.model_validate(request.parameters)
            rows = self._snapshot_view(
                stored,
                filters=export_request.filters,
                sort=export_request.sort,
                search=export_request.search,
            )
            return ArtifactRepresentationStream(
                chunks=CsvExportService.stream_csv(rows, stored.columns),
                media_type="text/csv",
                file_name="dbfox-snapshot.csv",
                metadata={
                    "row-count": str(len(rows)),
                    "source-truncated": str(stored.source_truncated).lower(),
                },
            )

        page_request = DataFramePageRequest.model_validate(request.parameters)
        started = time.perf_counter()
        rows = self._snapshot_view(
            stored,
            filters=page_request.filters,
            sort=page_request.sort,
            search=page_request.search,
        )
        offset = (page_request.page - 1) * page_request.page_size
        page_rows = rows[offset : offset + page_request.page_size]
        return ArtifactRepresentationResult(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            representation_version=1,
            operation="page",
            payload=self._page_payload(
                artifact,
                stored.columns,
                page_rows,
                page=page_request.page,
                page_size=page_request.page_size,
                row_count=len(rows),
                has_next_page=offset + len(page_rows) < len(rows),
                latency_ms=int((time.perf_counter() - started) * 1_000),
                source_truncated=stored.source_truncated,
            ),
            consistency="durable_snapshot",
            original_observed_at=(
                str(
                    artifact.payload.get("capturedAt")
                    or artifact.payload.get("executedAt")
                    or ""
                )
                or None
            ),
            read_at=datetime.now(UTC).isoformat(),
            read_id=f"read_{uuid4().hex}",
            source_version=stored.resource_version,
            source_fingerprint=stored.query_fingerprint,
            warnings=(
                "The snapshot was truncated when it was captured.",
            ) if stored.source_truncated else (),
            notices=("Loaded from an immutable Data snapshot.",),
        )

    @staticmethod
    def _page_payload(
        artifact: Artifact,
        columns: list[str],
        rows: list[dict[str, Any]],
        *,
        page: int,
        page_size: int,
        row_count: int | None,
        has_next_page: bool,
        latency_ms: int,
        source_truncated: bool,
    ) -> dict[str, Any]:
        fields = [
            DataFrameField(
                key=f"field_{index}",
                name=column,
                type=_field_type(artifact, column, [row.get(column) for row in rows]),
                nullable=True,
                values=[row.get(column) for row in rows],
            )
            for index, column in enumerate(columns)
        ]
        return DataFramePage(
            fields=fields,
            page=page,
            page_size=page_size,
            row_count=row_count,
            has_next_page=has_next_page,
            latency_ms=latency_ms,
            source_truncated=source_truncated,
        ).model_dump(mode="json")

    def _execute_live_request(
        self,
        artifact: Artifact,
        request: ArtifactRepresentationRequest,
        context: ArtifactRepresentationContext,
    ) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        source = self._live_source(artifact, context)
        if request.operation == "export.csv":
            export_request = DataFrameExportRequest.model_validate(request.parameters)
            try:
                query = build_sql_backed_page_sql(
                    base_sql=source.sql,
                    dialect=source.dialect,
                    columns=source.columns,
                    filters=self._sql_filters(export_request.filters),
                    sorts=self._sql_sorts(export_request.sort),
                    search=export_request.search,
                    searchable_columns=source.columns,
                )
            except SqlBackedViewError as exc:
                raise _error(
                    "INVALID_REQUEST",
                    "The DataFrame export request is invalid.",
                    status_code=422,
                ) from exc
            result = self._execute_live(source, query.sql)
            return ArtifactRepresentationStream(
                chunks=CsvExportService.stream_csv(result.rows, source.columns),
                media_type="text/csv",
                file_name="dbfox-result.csv",
                metadata={
                    "row-count": str(len(result.rows)),
                    "source-truncated": str(result.truncated).lower(),
                },
            )

        page_request = DataFramePageRequest.model_validate(request.parameters)
        offset = (page_request.page - 1) * page_request.page_size
        try:
            query = build_sql_backed_page_sql(
                base_sql=source.sql,
                dialect=source.dialect,
                columns=source.columns,
                filters=self._sql_filters(page_request.filters),
                sorts=self._sql_sorts(page_request.sort),
                search=page_request.search,
                searchable_columns=source.columns,
                limit=page_request.page_size + 1,
                offset=offset,
            )
            count_query = (
                build_sql_backed_count_sql(
                    base_sql=source.sql,
                    dialect=source.dialect,
                    columns=source.columns,
                    filters=self._sql_filters(page_request.filters),
                    search=page_request.search,
                    searchable_columns=source.columns,
                )
                if page_request.count_mode == "exact"
                else None
            )
        except SqlBackedViewError as exc:
            raise _error(
                "INVALID_REQUEST",
                "The DataFrame page request is invalid.",
                status_code=422,
            ) from exc
        result = self._execute_live(source, query.sql)
        page_rows = result.rows[: page_request.page_size]
        has_next_page = len(result.rows) > page_request.page_size
        row_count = None
        latency_ms = _execution_latency_ms(result)
        if count_query is not None:
            count_result = self._execute_live(source, count_query.sql)
            latency_ms += _execution_latency_ms(count_result)
            if count_result.rows:
                try:
                    row_count = int(count_result.rows[0].get("dbfox_count") or 0)
                except (TypeError, ValueError) as exc:
                    raise _error(
                        "PROVIDER_FAILURE",
                        "The database returned an invalid row count.",
                        status_code=503,
                    ) from exc
        return ArtifactRepresentationResult(
            representation_type=DATAFRAME_REPRESENTATION_TYPE,
            representation_version=1,
            operation="page",
            payload=self._page_payload(
                artifact,
                source.columns,
                page_rows,
                page=page_request.page,
                page_size=page_request.page_size,
                row_count=row_count,
                has_next_page=has_next_page,
                latency_ms=latency_ms,
                source_truncated=result.truncated,
            ),
            consistency="live_reexecution",
            original_observed_at=str(artifact.payload.get("executedAt") or "") or None,
            read_at=datetime.now(UTC).isoformat(),
            read_id=f"read_{uuid4().hex}",
            source_version=source.resource_version,
            source_fingerprint=source.query_fingerprint,
            warnings=(
                "The live response exceeded the bounded DataFrame read window.",
            ) if result.truncated else (),
            notices=("Re-executed the immutable SQL source against the current database.",),
        )

    def execute(
        self,
        artifact: Artifact,
        request: ArtifactRepresentationRequest,
        context: ArtifactRepresentationContext,
    ) -> ArtifactRepresentationResult | ArtifactRepresentationStream:
        descriptor = self.describe(artifact)
        if descriptor.operation(request.operation) is None:
            raise _error(
                "UNSUPPORTED_REPRESENTATION",
                f"DataFrame operation '{request.operation}' is unavailable.",
                status_code=409,
            )
        if artifact.type == SNAPSHOT_ARTIFACT_TYPE or artifact.schema_version == 1:
            return self._execute_snapshot(artifact, request)
        return self._execute_live_request(artifact, request, context)
