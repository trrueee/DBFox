"""Artifact and table result-view endpoints."""

from __future__ import annotations

import logging
from typing import Any, Final, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import DataSource
from engine.security.audit import SecurityAuditService
from engine.sql.execution.streaming_executor import export_max_rows_from_env
from engine.sql.result_view.models import (
    ResultExportQuery as ServiceResultExportQuery,
    ResultFilter as ServiceResultFilter,
    ResultPageQuery as ServiceResultPageQuery,
    ResultSort as ServiceResultSort,
    ResultSourceRef,
    ResultViewError,
    TableExportQuery as ServiceTableExportQuery,
    TablePageQuery as ServiceTablePageQuery,
    TableSourceRef,
)
from engine.sql.result_view.service import ResultViewService


logger = logging.getLogger("dbfox.api.agent.results")
router = APIRouter()


class ResultPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ServiceResultSort] | None = Field(default=None, max_length=16)
    filters: list[ServiceResultFilter] | None = Field(default=None, max_length=16)
    search: str | None = Field(default=None, max_length=512)
    countMode: Literal["none", "exact", "estimate"] = "none"


class TableResultPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasourceId: str = Field(min_length=1, max_length=256)
    tableId: str | None = Field(default=None, min_length=1, max_length=256)
    tableName: str = Field(min_length=1, max_length=256)
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ServiceResultSort] | None = Field(default=None, max_length=16)
    filters: list[ServiceResultFilter] | None = Field(default=None, max_length=16)
    search: str | None = Field(default=None, max_length=512)
    countMode: Literal["none", "exact", "estimate"] = "none"


class TableResultExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasourceId: str = Field(min_length=1, max_length=256)
    tableId: str | None = Field(default=None, min_length=1, max_length=256)
    tableName: str = Field(min_length=1, max_length=256)
    sort: list[ServiceResultSort] | None = Field(default=None, max_length=16)
    filters: list[ServiceResultFilter] | None = Field(default=None, max_length=16)
    search: str | None = Field(default=None, max_length=512)


class ResultExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort: list[ServiceResultSort] | None = Field(default=None, max_length=16)
    filters: list[ServiceResultFilter] | None = Field(default=None, max_length=16)
    search: str | None = Field(default=None, max_length=512)


class ResultPageResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    pageSize: int
    rowCount: int | None = None
    hasNextPage: bool
    latencyMs: int
    consistency: Literal["live_reexecution", "live_query"]
    originalExecutedAt: str | None = None
    viewExecutedAt: str
    viewExecutionId: str
    datasourceGeneration: int
    queryFingerprint: str
    warnings: list[str] | None = None
    notices: list[str] | None = None


class ChartPointResponse(BaseModel):
    label: str
    value: float


class ChartDataResponse(BaseModel):
    series: list[ChartPointResponse]
    sampleSize: int
    truncated: bool
    consistency: Literal["live_reexecution"]
    originalExecutedAt: str | None = None
    viewExecutedAt: str
    viewExecutionId: str
    datasourceGeneration: int
    queryFingerprint: str


def _result_source_ref(artifact_id: str) -> ResultSourceRef:
    return ResultSourceRef(artifact_id=artifact_id)


def _table_source_ref(
    request: TableResultPageRequest | TableResultExportRequest,
) -> TableSourceRef:
    return TableSourceRef(
        datasource_id=request.datasourceId,
        table_id=request.tableId,
        table_name=request.tableName,
    )


def _result_filters(
    filters: list[ServiceResultFilter] | None,
) -> list[ServiceResultFilter]:
    return list(filters or [])


def _result_sorts(
    sorts: list[ServiceResultSort] | None,
) -> list[ServiceResultSort]:
    return list(sorts or [])


_RESULT_VIEW_ERROR_CODES: Final[dict[str, FixedErrorCode]] = {
    code.value: code
    for code in (
        FixedErrorCode.SOURCE_ARTIFACT_NOT_FOUND,
        FixedErrorCode.SOURCE_ARTIFACT_UNSUPPORTED,
        FixedErrorCode.SOURCE_SQL_MISSING,
        FixedErrorCode.SOURCE_SQL_MISMATCH,
        FixedErrorCode.SOURCE_SQL_VALIDATION_FAILED,
        FixedErrorCode.SOURCE_DATASOURCE_CHANGED,
        FixedErrorCode.TABLE_SOURCE_NOT_FOUND,
        FixedErrorCode.TABLE_COLUMNS_NOT_FOUND,
        FixedErrorCode.DERIVED_SQL_VALIDATION_FAILED,
        FixedErrorCode.DERIVED_SQL_BUILD_FAILED,
        FixedErrorCode.COUNT_SQL_BUILD_FAILED,
        FixedErrorCode.FILTER_COLUMN_NOT_ALLOWED,
        FixedErrorCode.SORT_COLUMN_NOT_ALLOWED,
        FixedErrorCode.FILTER_OPERATOR_NOT_ALLOWED,
    )
}


def _http_detail(_error: DBFoxError) -> dict[str, str]:
    return fixed_error_detail(FixedErrorCode.AGENT_REQUEST_ERROR)


def _result_view_http_error(
    error: ResultViewError,
    *,
    code: FixedErrorCode,
) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail=fixed_error_detail(_RESULT_VIEW_ERROR_CODES.get(error.code, code)),
    )


def _page_response(result: Any) -> ResultPageResponse:
    return ResultPageResponse(
        columns=result.columns,
        rows=result.rows,
        page=result.page,
        pageSize=result.page_size,
        rowCount=result.row_count,
        hasNextPage=result.has_next_page,
        latencyMs=result.latency_ms,
        consistency=result.consistency,
        originalExecutedAt=result.original_executed_at,
        viewExecutedAt=result.view_executed_at,
        viewExecutionId=result.view_execution_id,
        datasourceGeneration=result.datasource_generation,
        queryFingerprint=result.query_fingerprint,
        warnings=result.warnings,
        notices=result.notices,
    )


def _require_datasource(db: Session, datasource_id: str) -> None:
    if db.get(DataSource, datasource_id) is None:
        raise HTTPException(
            status_code=404,
            detail=fixed_error_detail(FixedErrorCode.DATASOURCE_NOT_FOUND),
        )


@router.post("/artifacts/{artifact_id}/page", response_model=ResultPageResponse)
def api_agent_result_page(
    artifact_id: str,
    request: ResultPageRequest,
    db: Session = Depends(get_db),
) -> ResultPageResponse:
    try:
        result = ResultViewService(db).page(
            ServiceResultPageQuery(
                source=_result_source_ref(artifact_id),
                filters=_result_filters(request.filters),
                sort=_result_sorts(request.sort),
                search=request.search,
                page=request.page,
                page_size=request.pageSize,
                count_mode=request.countMode,
            )
        )
    except ResultViewError as error:
        raise _result_view_http_error(
            error,
            code=FixedErrorCode.RESULT_PAGE_ERROR,
        ) from None
    except DBFoxError as error:
        raise HTTPException(status_code=400, detail=_http_detail(error))
    except Exception as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_RESULT_PAGE,
            exc=error,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.RESULT_PAGE_ERROR),
        ) from None
    return _page_response(result)


@router.post("/artifacts/{artifact_id}/chart-data", response_model=ChartDataResponse)
def api_agent_chart_data(
    artifact_id: str,
    db: Session = Depends(get_db),
) -> ChartDataResponse:
    try:
        result = ResultViewService(db).chart_data(artifact_id)
    except ResultViewError as error:
        raise _result_view_http_error(
            error,
            code=FixedErrorCode.RESULT_PAGE_ERROR,
        ) from None
    except DBFoxError as error:
        raise HTTPException(status_code=400, detail=_http_detail(error))
    except Exception as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_RESULT_PAGE,
            exc=error,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.RESULT_PAGE_ERROR),
        ) from None
    return ChartDataResponse(
        series=[ChartPointResponse.model_validate(point) for point in result.series],
        sampleSize=result.sample_size,
        truncated=result.truncated,
        consistency=result.consistency,
        originalExecutedAt=result.original_executed_at,
        viewExecutedAt=result.view_executed_at,
        viewExecutionId=result.view_execution_id,
        datasourceGeneration=result.datasource_generation,
        queryFingerprint=result.query_fingerprint,
    )


@router.post("/agent/results/table/page", response_model=ResultPageResponse)
def api_agent_table_result_page(
    request: TableResultPageRequest,
    db: Session = Depends(get_db),
) -> ResultPageResponse:
    _require_datasource(db, request.datasourceId)
    try:
        result = ResultViewService(db).page_table(
            ServiceTablePageQuery(
                source=_table_source_ref(request),
                filters=_result_filters(request.filters),
                sort=_result_sorts(request.sort),
                search=request.search,
                page=request.page,
                page_size=request.pageSize,
                count_mode=request.countMode,
            )
        )
    except ResultViewError as error:
        raise _result_view_http_error(
            error,
            code=FixedErrorCode.TABLE_RESULT_PAGE_ERROR,
        ) from None
    except DBFoxError as error:
        raise HTTPException(status_code=400, detail=_http_detail(error))
    except Exception as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_TABLE_RESULT_PAGE,
            exc=error,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.TABLE_RESULT_PAGE_ERROR),
        ) from None
    return _page_response(result)


@router.post(
    "/agent/results/table/export",
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
            "description": "CSV export",
        }
    },
)
def api_agent_table_result_export(
    request: TableResultExportRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _require_datasource(db, request.datasourceId)
    try:
        stream, _columns = ResultViewService(db).export_table_csv_stream(
            ServiceTableExportQuery(
                source=_table_source_ref(request),
                filters=_result_filters(request.filters),
                sort=_result_sorts(request.sort),
                search=request.search,
            )
        )
    except ResultViewError as error:
        raise _result_view_http_error(
            error,
            code=FixedErrorCode.TABLE_RESULT_EXPORT_ERROR,
        ) from None
    except DBFoxError as error:
        raise HTTPException(status_code=400, detail=_http_detail(error))
    except Exception as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_TABLE_RESULT_EXPORT,
            exc=error,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.TABLE_RESULT_EXPORT_ERROR),
        ) from None
    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="dbfox-table.csv"',
            "X-DBFox-Export-Max-Rows": str(export_max_rows_from_env()),
        },
    )


@router.post(
    "/artifacts/{artifact_id}/export",
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
            "description": "CSV export",
        }
    },
)
def api_agent_result_export(
    artifact_id: str,
    request: ResultExportRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        stream, _columns = ResultViewService(db).export_csv_stream(
            ServiceResultExportQuery(
                source=_result_source_ref(artifact_id),
                filters=_result_filters(request.filters),
                sort=_result_sorts(request.sort),
                search=request.search,
            )
        )
    except ResultViewError as error:
        raise _result_view_http_error(
            error,
            code=FixedErrorCode.RESULT_EXPORT_ERROR,
        ) from None
    except DBFoxError as error:
        raise HTTPException(status_code=400, detail=_http_detail(error))
    except Exception as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_RESULT_EXPORT,
            exc=error,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.RESULT_EXPORT_ERROR),
        ) from None

    SecurityAuditService(db).record(
        action="artifact.result.export",
        outcome="requested",
        resource_type="agent_artifact",
        resource_id=artifact_id,
        correlation_id=f"export:{artifact_id}:{uuid4().hex}",
        details={"format": "csv"},
    )
    db.commit()
    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="dbfox-result.csv"',
            "X-DBFox-Export-Max-Rows": str(export_max_rows_from_env()),
        },
    )
