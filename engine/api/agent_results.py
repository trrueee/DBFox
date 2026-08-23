"""Artifact and table result-view endpoints."""

from __future__ import annotations

import logging
from typing import Any, Literal
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
from engine.agent.artifact_view import (
    ArtifactTableExportRequest,
    ArtifactTablePageRequest,
    ArtifactViewError,
    ArtifactViewFilter,
    ArtifactViewSort,
)
from engine.agent.repositories.artifact import ArtifactRepository
from engine.runtime_composition import get_active_runtime_snapshot
from engine.models import AgentArtifactRecord
from engine.security.audit import SecurityAuditService


logger = logging.getLogger("dbfox.api.agent.results")
router = APIRouter()


class ResultPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=500)
    sort: list[ArtifactViewSort] | None = Field(default=None, max_length=16)
    filters: list[ArtifactViewFilter] | None = Field(default=None, max_length=16)
    search: str | None = Field(default=None, max_length=512)
    countMode: Literal["none", "exact", "estimate"] = "none"


class ResultExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort: list[ArtifactViewSort] | None = Field(default=None, max_length=16)
    filters: list[ArtifactViewFilter] | None = Field(default=None, max_length=16)
    search: str | None = Field(default=None, max_length=512)


class ResultPageResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    page: int
    pageSize: int
    rowCount: int | None = None
    hasNextPage: bool
    latencyMs: int
    consistency: Literal["durable_snapshot", "live_reexecution", "live_query"]
    originalExecutedAt: str | None = None
    viewExecutedAt: str
    viewExecutionId: str
    resourceVersion: str | int
    sourceFingerprint: str
    warnings: list[str] | None = None
    notices: list[str] | None = None


class ChartPointResponse(BaseModel):
    label: str
    value: float


class ChartDataResponse(BaseModel):
    series: list[ChartPointResponse]
    sampleSize: int
    truncated: bool
    consistency: Literal["durable_snapshot", "live_reexecution"]
    originalExecutedAt: str | None = None
    viewExecutedAt: str
    viewExecutionId: str
    resourceVersion: str | int
    sourceFingerprint: str


def _result_filters(
    filters: list[ArtifactViewFilter] | None,
) -> list[ArtifactViewFilter]:
    return list(filters or [])


def _result_sorts(
    sorts: list[ArtifactViewSort] | None,
) -> list[ArtifactViewSort]:
    return list(sorts or [])


def _http_detail(_error: DBFoxError) -> dict[str, str]:
    return fixed_error_detail(FixedErrorCode.AGENT_REQUEST_ERROR)


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
        viewExecutedAt=result.read_at,
        viewExecutionId=result.read_id,
        resourceVersion=result.resource_version,
        sourceFingerprint=result.source_fingerprint,
        warnings=result.warnings,
        notices=result.notices,
    )


@router.post("/artifacts/{artifact_id}/page", response_model=ResultPageResponse)
def api_agent_result_page(
    artifact_id: str,
    request: ResultPageRequest,
    db: Session = Depends(get_db),
) -> ResultPageResponse:
    try:
        artifact_row = db.get(AgentArtifactRecord, artifact_id)
        if artifact_row is None:
            raise ArtifactViewError("Artifact was not found.", status_code=404)
        contribution = get_active_runtime_snapshot().get_artifact_table_view(
            str(artifact_row.type)
        )
        if contribution is None:
            raise ArtifactViewError(
                "Artifact type has no durable table-view provider.", status_code=409
            )
        artifact = ArtifactRepository(db).get(artifact_id)
        if artifact is None:
            raise ArtifactViewError("Artifact was not found.", status_code=404)
        result = contribution.provider.page(
            artifact,
            ArtifactTablePageRequest(
                filters=tuple(
                    ArtifactViewFilter.model_validate(item.model_dump())
                    for item in _result_filters(request.filters)
                ),
                sort=tuple(
                    ArtifactViewSort.model_validate(item.model_dump())
                    for item in _result_sorts(request.sort)
                ),
                search=request.search,
                page=request.page,
                page_size=request.pageSize,
                count_mode=request.countMode,
            ),
        )
    except ArtifactViewError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=fixed_error_detail(FixedErrorCode.RESULT_PAGE_ERROR),
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
        artifact_row = db.get(AgentArtifactRecord, artifact_id)
        if artifact_row is None:
            raise ArtifactViewError("Artifact was not found.", status_code=404)
        contribution = get_active_runtime_snapshot().get_artifact_chart_view(
            str(artifact_row.type)
        )
        if contribution is None:
            raise ArtifactViewError(
                "Artifact type has no durable chart-view provider.", status_code=409
            )
        artifacts = ArtifactRepository(db)
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            raise ArtifactViewError("Artifact was not found.", status_code=404)
        source_ids = tuple(
            relation.artifact_id
            for relation in artifact.relations
            if relation.relation.value == "derived_from"
        )
        if len(source_ids) != 1:
            raise ArtifactViewError(
                "Chart Artifact has no unambiguous durable source.", status_code=409
            )
        source = artifacts.get(source_ids[0])
        if source is None or source.session_id != artifact.session_id:
            raise ArtifactViewError(
                "Chart source Artifact is unavailable.", status_code=404
            )
        result = contribution.provider.data(artifact, source)
    except ArtifactViewError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=fixed_error_detail(FixedErrorCode.RESULT_PAGE_ERROR),
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
        viewExecutedAt=result.read_at,
        viewExecutionId=result.read_id,
        resourceVersion=result.resource_version,
        sourceFingerprint=result.source_fingerprint,
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
        artifact_row = db.get(AgentArtifactRecord, artifact_id)
        if artifact_row is None:
            raise ArtifactViewError("Artifact was not found.", status_code=404)
        contribution = get_active_runtime_snapshot().get_artifact_table_view(
            str(artifact_row.type)
        )
        if contribution is None:
            raise ArtifactViewError(
                "Artifact type has no durable table-view provider.", status_code=409
            )
        artifact = ArtifactRepository(db).get(artifact_id)
        if artifact is None:
            raise ArtifactViewError("Artifact was not found.", status_code=404)
        exported = contribution.provider.export_csv(
            artifact,
            ArtifactTableExportRequest(
                filters=tuple(
                    ArtifactViewFilter.model_validate(item.model_dump())
                    for item in _result_filters(request.filters)
                ),
                sort=tuple(
                    ArtifactViewSort.model_validate(item.model_dump())
                    for item in _result_sorts(request.sort)
                ),
                search=request.search,
            ),
        )
    except ArtifactViewError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail=fixed_error_detail(FixedErrorCode.RESULT_EXPORT_ERROR),
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
        exported.chunks,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="dbfox-result.csv"',
            "X-DBFox-Export-Row-Count": str(exported.row_count),
            "X-DBFox-Source-Truncated": str(exported.source_truncated).lower(),
        },
    )
