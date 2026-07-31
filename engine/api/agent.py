"""Agent-adjacent SQL Console and result-service endpoints."""

from __future__ import annotations

import logging
import time as _time
from typing import Any, Final, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from engine.agent.artifact import Artifact
from engine.agent.console import ConsoleExecutionRequest, ConsoleRunService
from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.db import get_db
from engine.errors import DBFoxError
from engine.llm.config import resolve_product_llm_config_from_credential
from engine.llm.providers.openai import create_openai_responses_client
from engine.models import DataSource
from engine.sql.execution.streaming_executor import export_max_rows_from_env
from engine.sql.result_view.models import (
    ResultExportQuery as ServiceResultExportQuery,
    ResultFilter as ServiceResultFilter,
    ResultPageQuery as ServiceResultPageQuery,
    ResultSort as ServiceResultSort,
    ResultSourceRef,
    TableExportQuery as ServiceTableExportQuery,
    TablePageQuery as ServiceTablePageQuery,
    TableSourceRef,
    ResultViewError,
)
from engine.sql.result_view.service import ResultViewService

logger = logging.getLogger("dbfox.api.agent")
router = APIRouter()


class LlmTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_credential_id: str = Field(min_length=1, max_length=256)
    api_base: str = Field(min_length=1, max_length=2_048)
    model_name: str = Field(min_length=1, max_length=256)


class LlmTestResponse(BaseModel):
    ok: bool
    model: str
    api_base: str
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# LLM connection test — POST /agent/llm/test
# ---------------------------------------------------------------------------

@router.post("/agent/llm/test", response_model=LlmTestResponse)
def api_llm_test(req: LlmTestRequest) -> LlmTestResponse:
    """Test the exact Responses capability required by the Agent runtime.

    This endpoint resolves an opaque credential through the local OS vault and
    validates that it can reach the target LLM service.
    """
    t0 = _time.monotonic()
    try:
        config = resolve_product_llm_config_from_credential(
            llm_credential_id=req.llm_credential_id,
            api_base=req.api_base,
            model_name=req.model_name,
        )
        client = create_openai_responses_client(
            api_key=config.api_key,
            api_base=config.api_base,
            timeout=10.0,
        )
        client.responses.create(
            model=config.model_name,
            input="ping",
            max_output_tokens=16,
            store=False,
        )
        latency_ms = int((_time.monotonic() - t0) * 1000)
        return LlmTestResponse(
            ok=True,
            model=config.model_name,
            api_base=config.api_base,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.UNEXPECTED,
            exc=exc,
        )
        return LlmTestResponse(
            ok=False,
            model=req.model_name,
            api_base=req.api_base,
            latency_ms=latency_ms,
            error_code="LLM_CONNECTION_FAILED",
            error_message="模型连接测试未通过，请检查服务地址、凭据和模型名称。",
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _http_detail(_exc: DBFoxError) -> dict[str, str]:
    """Return a fixed detail for untrusted typed runtime errors."""
    return fixed_error_detail(FixedErrorCode.AGENT_REQUEST_ERROR)


# ---------------------------------------------------------------------------
# Agent run — GET routes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Agent run — POST routes (non-streaming)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Agent run — SSE streaming routes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SQL Console — artifact-backed execution
# ---------------------------------------------------------------------------

class ConsoleExecuteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    datasourceId: str = Field(min_length=1, max_length=128)
    sql: str = Field(min_length=1, max_length=200_000)
    question: str | None = Field(default=None, max_length=20_000)
    sessionId: str | None = Field(default=None, min_length=1, max_length=128)
    executionId: str | None = Field(default=None, min_length=1, max_length=128)


class ConsoleExecuteResponse(BaseModel):
    runId: str
    sessionId: str
    sqlArtifactId: str
    safetyArtifactId: str | None = None
    resultArtifactId: str | None = None
    artifacts: list[Artifact]
    warnings: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


@router.post("/agent/console/execute", response_model=ConsoleExecuteResponse)
def api_agent_console_execute(req: ConsoleExecuteRequest, db: Session = Depends(get_db)) -> ConsoleExecuteResponse:
    try:
        result = ConsoleRunService(db).execute(
            ConsoleExecutionRequest(
                datasource_id=req.datasourceId,
                sql=req.sql,
                question=req.question or "SQL Console",
                session_id=req.sessionId,
                execution_id=req.executionId,
            )
        )
        return ConsoleExecuteResponse(
            runId=result.run_id,
            sessionId=result.session_id,
            sqlArtifactId=result.sql_artifact_id,
            safetyArtifactId=result.safety_artifact_id,
            resultArtifactId=result.result_artifact_id,
            artifacts=list(result.artifacts),
            warnings=list(result.warnings),
            notices=list(result.notices),
        )
    except DBFoxError as exc:
        db.rollback()
        if exc.code == "DATASOURCE_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail=fixed_error_detail(FixedErrorCode.DATASOURCE_NOT_FOUND),
            )
        if exc.code == "SQL_EMPTY":
            raise HTTPException(
                status_code=400,
                detail=fixed_error_detail(FixedErrorCode.SQL_EMPTY),
            )
        raise HTTPException(status_code=400, detail=_http_detail(exc))
    except Exception as exc:
        db.rollback()
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_SQL_CONSOLE_EXECUTION,
            exc=exc,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.CONSOLE_EXECUTION_ERROR),
        ) from None

# ---------------------------------------------------------------------------
# Agent Result Pagination API
# ---------------------------------------------------------------------------

class ResultSort(BaseModel):
    column: str
    direction: Literal["asc", "desc"]

class ResultFilter(BaseModel):
    column: str
    operator: str
    value: Any

class ResultPageRequest(BaseModel):
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None
    countMode: Literal["none", "exact", "estimate"] = "none"

class TableResultPageRequest(BaseModel):
    datasourceId: str
    tableId: str | None = None
    tableName: str
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None
    countMode: Literal["none", "exact", "estimate"] = "none"

class TableResultExportRequest(BaseModel):
    datasourceId: str
    tableId: str | None = None
    tableName: str
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None

class ResultExportRequest(BaseModel):
    sort: list[ResultSort] | None = None
    filters: list[ResultFilter] | None = None
    search: str | None = None

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


def _table_source_ref(req: TableResultPageRequest | TableResultExportRequest) -> TableSourceRef:
    return TableSourceRef(
        datasource_id=req.datasourceId,
        table_id=req.tableId,
        table_name=req.tableName,
    )


def _result_filters(filters: list[ResultFilter] | None) -> list[ServiceResultFilter]:
    return [ServiceResultFilter.model_validate(item.model_dump()) for item in (filters or [])]


def _result_sorts(sorts: list[ResultSort] | None) -> list[ServiceResultSort]:
    return [ServiceResultSort.model_validate(item.model_dump()) for item in (sorts or [])]


_RESULT_VIEW_ERROR_CODES: Final[dict[str, FixedErrorCode]] = {
    FixedErrorCode.SOURCE_ARTIFACT_NOT_FOUND.value: FixedErrorCode.SOURCE_ARTIFACT_NOT_FOUND,
    FixedErrorCode.SOURCE_ARTIFACT_UNSUPPORTED.value: FixedErrorCode.SOURCE_ARTIFACT_UNSUPPORTED,
    FixedErrorCode.SOURCE_SQL_MISSING.value: FixedErrorCode.SOURCE_SQL_MISSING,
    FixedErrorCode.SOURCE_SQL_MISMATCH.value: FixedErrorCode.SOURCE_SQL_MISMATCH,
    FixedErrorCode.SOURCE_SQL_VALIDATION_FAILED.value: FixedErrorCode.SOURCE_SQL_VALIDATION_FAILED,
    FixedErrorCode.SOURCE_DATASOURCE_CHANGED.value: FixedErrorCode.SOURCE_DATASOURCE_CHANGED,
    FixedErrorCode.TABLE_SOURCE_NOT_FOUND.value: FixedErrorCode.TABLE_SOURCE_NOT_FOUND,
    FixedErrorCode.TABLE_COLUMNS_NOT_FOUND.value: FixedErrorCode.TABLE_COLUMNS_NOT_FOUND,
    FixedErrorCode.DERIVED_SQL_VALIDATION_FAILED.value: FixedErrorCode.DERIVED_SQL_VALIDATION_FAILED,
    FixedErrorCode.DERIVED_SQL_BUILD_FAILED.value: FixedErrorCode.DERIVED_SQL_BUILD_FAILED,
    FixedErrorCode.COUNT_SQL_BUILD_FAILED.value: FixedErrorCode.COUNT_SQL_BUILD_FAILED,
    FixedErrorCode.FILTER_COLUMN_NOT_ALLOWED.value: FixedErrorCode.FILTER_COLUMN_NOT_ALLOWED,
    FixedErrorCode.SORT_COLUMN_NOT_ALLOWED.value: FixedErrorCode.SORT_COLUMN_NOT_ALLOWED,
    FixedErrorCode.FILTER_OPERATOR_NOT_ALLOWED.value: FixedErrorCode.FILTER_OPERATOR_NOT_ALLOWED,
}


def _result_view_http_error(
    exc: ResultViewError,
    *,
    code: FixedErrorCode,
) -> HTTPException:
    """Map result-view failures to the endpoint's static error catalog entry."""
    safe_code = _RESULT_VIEW_ERROR_CODES.get(exc.code, code)
    return HTTPException(
        status_code=exc.status_code,
        detail=fixed_error_detail(safe_code),
    )

@router.post("/artifacts/{artifact_id}/page", response_model=ResultPageResponse)
def api_agent_result_page(
    artifact_id: str, req: ResultPageRequest, db: Session = Depends(get_db)
) -> ResultPageResponse:
    try:
        result = ResultViewService(db).page(
            ServiceResultPageQuery(
                source=_result_source_ref(artifact_id),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
                page=req.page,
                page_size=req.pageSize,
                count_mode=req.countMode,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e, code=FixedErrorCode.RESULT_PAGE_ERROR) from None
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_RESULT_PAGE,
            exc=e,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.RESULT_PAGE_ERROR),
        ) from None

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


@router.post("/artifacts/{artifact_id}/chart-data", response_model=ChartDataResponse)
def api_agent_chart_data(
    artifact_id: str, db: Session = Depends(get_db)
) -> ChartDataResponse:
    try:
        result = ResultViewService(db).chart_data(artifact_id)
    except ResultViewError as e:
        raise _result_view_http_error(e, code=FixedErrorCode.RESULT_PAGE_ERROR) from None
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_RESULT_PAGE,
            exc=e,
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
def api_agent_table_result_page(req: TableResultPageRequest, db: Session = Depends(get_db)) -> ResultPageResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(
            status_code=404,
            detail=fixed_error_detail(FixedErrorCode.DATASOURCE_NOT_FOUND),
        )

    try:
        result = ResultViewService(db).page_table(
            ServiceTablePageQuery(
                source=_table_source_ref(req),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
                page=req.page,
                page_size=req.pageSize,
                count_mode=req.countMode,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e, code=FixedErrorCode.TABLE_RESULT_PAGE_ERROR) from None
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_TABLE_RESULT_PAGE,
            exc=e,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.TABLE_RESULT_PAGE_ERROR),
        ) from None

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


@router.post(
    "/agent/results/table/export",
    responses={
        200: {
            "content": {
                "text/csv": {
                    "schema": {"type": "string", "format": "binary"},
                },
            },
            "description": "CSV export",
        },
    },
)
def api_agent_table_result_export(req: TableResultExportRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    from engine.models import DataSource

    ds = db.query(DataSource).filter(DataSource.id == req.datasourceId).first()
    if not ds:
        raise HTTPException(
            status_code=404,
            detail=fixed_error_detail(FixedErrorCode.DATASOURCE_NOT_FOUND),
        )

    try:
        stream, _columns = ResultViewService(db).export_table_csv_stream(
            ServiceTableExportQuery(
                source=_table_source_ref(req),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e, code=FixedErrorCode.TABLE_RESULT_EXPORT_ERROR) from None
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_TABLE_RESULT_EXPORT,
            exc=e,
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
            "content": {
                "text/csv": {
                    "schema": {"type": "string", "format": "binary"},
                },
            },
            "description": "CSV export",
        },
    },
)
def api_agent_result_export(
    artifact_id: str, req: ResultExportRequest, db: Session = Depends(get_db)
) -> StreamingResponse:
    try:
        stream, _columns = ResultViewService(db).export_csv_stream(
            ServiceResultExportQuery(
                source=_result_source_ref(artifact_id),
                filters=_result_filters(req.filters),
                sort=_result_sorts(req.sort),
                search=req.search,
            )
        )
    except ResultViewError as e:
        raise _result_view_http_error(e, code=FixedErrorCode.RESULT_EXPORT_ERROR) from None
    except DBFoxError as e:
        raise HTTPException(status_code=400, detail=_http_detail(e))
    except Exception as e:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.AGENT_RESULT_EXPORT,
            exc=e,
        )
        raise HTTPException(
            status_code=500,
            detail=fixed_error_detail(FixedErrorCode.RESULT_EXPORT_ERROR),
        ) from None

    from engine.security.audit import SecurityAuditService
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
