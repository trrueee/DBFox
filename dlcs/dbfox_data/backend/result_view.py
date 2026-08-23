"""Workbench table reader for immutable Data-owned result payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import cmp_to_key
import time
from typing import Any
from uuid import uuid4

from dbfox_dlc_api import (
    Artifact,
    ArtifactChartData,
    ArtifactCsvStream,
    ArtifactTableExportRequest,
    ArtifactTablePage,
    ArtifactTablePageRequest,
    ArtifactViewError,
    ArtifactViewFilter,
    ArtifactViewSort,
)

from .artifact_contracts import RESULT_VIEW_ARTIFACT_TYPE
from .artifact_contracts import CHART_ARTIFACT_TYPE
from .chart_suggestion import build_chart_series
from .resource_kind import DATABASE_RESOURCE_KIND
from .sql.execution.csv_export import CsvExportService
from .store import DataStateStore, StoredResultPage


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


def _matches_filter(value: Any, spec: ArtifactViewFilter) -> bool:
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
    filters: tuple[ArtifactViewFilter, ...],
    sort: tuple[ArtifactViewSort, ...],
    search: str | None,
) -> list[dict[str, Any]]:
    allowed = set(columns)
    requested_columns = {
        item.column for item in (*filters, *sort)
    }
    unknown = sorted(requested_columns - allowed)
    if unknown:
        raise ArtifactViewError(
            f"Result view references unavailable columns: {', '.join(unknown)}"
        )
    search_text = str(search or "").strip().casefold()
    viewed = [
        row
        for row in rows
        if all(_matches_filter(row.get(spec.column), spec) for spec in filters)
        and (
            not search_text
            or any(search_text in _text(row.get(column)).casefold() for column in columns)
        )
    ]
    if sort:
        def compare_rows(left: dict[str, Any], right: dict[str, Any]) -> int:
            for spec in sort:
                result = _compare(left.get(spec.column), right.get(spec.column))
                if result:
                    return -result if spec.direction == "desc" else result
            return 0

        viewed.sort(key=cmp_to_key(compare_rows))
    return viewed


class DataResultTableView:
    """Reads the bounded immutable row set captured by Data query execution."""

    def __init__(self, store: DataStateStore) -> None:
        self._store = store

    def _load(self, artifact: Artifact) -> StoredResultPage:
        if artifact.type != RESULT_VIEW_ARTIFACT_TYPE or not artifact.payload_ref:
            raise ArtifactViewError(
                "This Artifact has no durable Data result payload.", status_code=409
            )
        database_refs = tuple(
            ref for ref in artifact.resource_refs if ref.kind == DATABASE_RESOURCE_KIND
        )
        if len(database_refs) != 1 or len(artifact.resource_refs) != 1:
            raise ArtifactViewError(
                "The Result Artifact has an invalid database binding.", status_code=409
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
            raise ArtifactViewError(
                "The durable Data result payload is unavailable.", status_code=404
            ) from exc
        database_ref = database_refs[0]
        if (
            stored.database_resource_id != database_ref.id
            or stored.resource_version != str(database_ref.version or "")
            or stored.query_fingerprint
            != str(artifact.payload.get("queryFingerprint") or "")
        ):
            raise ArtifactViewError(
                "The Result Artifact does not match its durable payload.",
                status_code=409,
            )
        return stored

    @staticmethod
    def _view(
        stored: StoredResultPage,
        *,
        filters: tuple[ArtifactViewFilter, ...],
        sort: tuple[ArtifactViewSort, ...],
        search: str | None,
    ) -> list[dict[str, Any]]:
        return _apply_view(
            stored.rows,
            stored.columns,
            filters=filters,
            sort=sort,
            search=search,
        )

    def page(
        self,
        artifact: Artifact,
        request: ArtifactTablePageRequest,
    ) -> ArtifactTablePage:
        started = time.perf_counter()
        stored = self._load(artifact)
        rows = self._view(
            stored,
            filters=request.filters,
            sort=request.sort,
            search=request.search,
        )
        offset = (request.page - 1) * request.page_size
        page_rows = rows[offset : offset + request.page_size]
        warnings = []
        if stored.source_truncated:
            warnings.append(
                "The source query exceeded the durable result boundary; this view contains only stored rows."
            )
        return ArtifactTablePage(
            columns=stored.columns,
            rows=page_rows,
            page=request.page,
            page_size=request.page_size,
            row_count=len(rows),
            has_next_page=offset + len(page_rows) < len(rows),
            latency_ms=int((time.perf_counter() - started) * 1_000),
            original_executed_at=str(artifact.payload.get("executedAt") or "") or None,
            read_at=datetime.now(UTC).isoformat(),
            read_id=f"read_{uuid4().hex}",
            resource_version=stored.resource_version,
            source_fingerprint=stored.query_fingerprint,
            warnings=warnings,
            notices=["Loaded from the durable Data result store without SQL reexecution."],
        )

    def export_csv(
        self,
        artifact: Artifact,
        request: ArtifactTableExportRequest,
    ) -> ArtifactCsvStream:
        stored = self._load(artifact)
        rows = self._view(
            stored,
            filters=request.filters,
            sort=request.sort,
            search=request.search,
        )
        return ArtifactCsvStream(
            chunks=CsvExportService.stream_csv(rows, stored.columns),
            row_count=len(rows),
            source_truncated=stored.source_truncated,
        )


class DataChartView:
    """Build transient chart points from the exact durable source Result."""

    def __init__(self, table_view: DataResultTableView) -> None:
        self._table_view = table_view

    def data(
        self,
        artifact: Artifact,
        source_artifact: Artifact,
    ) -> ArtifactChartData:
        if artifact.type != CHART_ARTIFACT_TYPE:
            raise ArtifactViewError("Artifact is not a Data chart.", status_code=409)
        if (
            str(artifact.payload.get("sourceResultArtifactId") or "")
            != source_artifact.id
            or artifact.resource_refs != source_artifact.resource_refs
        ):
            raise ArtifactViewError(
                "The chart does not match its durable source Result.", status_code=409
            )
        stored = self._table_view._load(source_artifact)
        x_column = str(artifact.payload.get("x") or "").strip()
        y_value = artifact.payload.get("y")
        y_column = (
            str(y_value[0]).strip()
            if isinstance(y_value, list) and y_value
            else ""
        )
        if (
            not x_column
            or not y_column
            or x_column not in stored.columns
            or y_column not in stored.columns
        ):
            raise ArtifactViewError(
                "The chart field mapping is unavailable in its source Result.",
                status_code=409,
            )
        return ArtifactChartData(
            series=build_chart_series(
                stored.rows,
                x_column,
                y_column,
                aggregation=str(artifact.payload.get("aggregation") or "none"),
            ),
            sample_size=stored.row_count,
            truncated=stored.source_truncated,
            original_executed_at=(
                str(source_artifact.payload.get("executedAt") or "") or None
            ),
            read_at=datetime.now(UTC).isoformat(),
            read_id=f"read_{uuid4().hex}",
            resource_version=stored.resource_version,
            source_fingerprint=stored.query_fingerprint,
        )
