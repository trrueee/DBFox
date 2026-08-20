"""Generic typed operation endpoint for Runtime DLC management RPCs."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from engine.db import SessionLocal
from engine.dlc.api import DlcOperationContext
from engine.models import Project
from engine.runtime_composition import get_active_runtime_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dlcs", tags=["dlc_operations"])

MAX_DLC_OPERATION_INPUT_BYTES = 10 * 1024 * 1024  # 10 MiB


@router.post(
    "/{dlc_id}/operations/{operation_name}",
    status_code=status.HTTP_200_OK,
    summary="Invoke a registered DLC management operation",
)
async def invoke_dlc_operation(
    dlc_id: str,
    operation_name: str,
    request: Request,
) -> Any:
    """Execute a typed DLC operation with input/output bounds and single-call semantics."""
    snapshot = get_active_runtime_snapshot()
    op_contrib = snapshot.get_operation(dlc_id, operation_name)
    if op_contrib is None:
        # Check if DLC is active
        is_dlc_active = any(d.dlc_id == dlc_id for d in snapshot.active_dlcs)
        if not is_dlc_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "DLC_NOT_ACTIVE",
                    "message": f"DLC '{dlc_id}' is not currently active.",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "OPERATION_NOT_FOUND",
                "message": f"Operation '{operation_name}' not found for DLC '{dlc_id}'.",
            },
        )

    spec = op_contrib.spec

    # 1. Enforce input size bound before buffering
    content_length_header = request.headers.get("content-length")
    if content_length_header:
        try:
            content_length = int(content_length_header)
            if content_length > MAX_DLC_OPERATION_INPUT_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={
                        "code": "INPUT_SIZE_EXCEEDED",
                        "message": f"Request body size ({content_length} bytes) exceeds limit of {MAX_DLC_OPERATION_INPUT_BYTES} bytes.",
                    },
                )
        except ValueError:
            pass

    body_chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_DLC_OPERATION_INPUT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "INPUT_SIZE_EXCEEDED",
                    "message": f"Request body size exceeds limit of {MAX_DLC_OPERATION_INPUT_BYTES} bytes.",
                },
            )
        body_chunks.append(chunk)
    body_bytes = b"".join(body_chunks)

    # 2. Parse JSON body
    try:
        raw_input = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_JSON",
                "message": f"Failed to parse request JSON: {exc}",
            },
        ) from exc

    # 3. Validate input model
    try:
        input_data = spec.input_model.model_validate(raw_input)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_OPERATION_INPUT",
                "message": "Operation input validation failed.",
                "errors": exc.errors(),
            },
        ) from exc

    # 4. Validate scope authority
    project_id: str | None = None
    if spec.scope == "project":
        project_id = request.query_params.get("project_id") or request.headers.get("x-project-id")
        if not project_id and isinstance(raw_input, dict):
            project_id = raw_input.get("project_id")
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "MISSING_PROJECT_ID",
                    "message": f"Operation '{operation_name}' is project-scoped and requires a valid project_id.",
                },
            )
        with SessionLocal() as db:
            project_row = db.get(Project, project_id)
            if project_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "PROJECT_NOT_FOUND",
                        "message": f"Project '{project_id}' does not exist.",
                    },
                )

    # 5. Build execution context
    ctx = DlcOperationContext(
        dlc_id=dlc_id,
        operation_name=operation_name,
        project_id=project_id,
    )

    # 6. Execute handler exactly once in threadpool (non-blocking)
    try:
        result = await run_in_threadpool(spec.handler, input_data, ctx)
    except Exception as exc:
        logger.error(
            f"Operation '{operation_name}' for DLC '{dlc_id}' failed: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "OPERATION_EXECUTION_FAILED",
                "message": f"Operation execution failed: {type(exc).__name__}",
            },
        ) from exc

    # 7. Validate output model
    try:
        if isinstance(result, spec.output_model):
            validated_output = result
        else:
            validated_output = spec.output_model.model_validate(result)
        output_dict = validated_output.model_dump(mode="json")
    except Exception as exc:
        logger.error(
            f"Operation '{operation_name}' for DLC '{dlc_id}' produced invalid output: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INVALID_OPERATION_OUTPUT",
                "message": "Operation handler returned output that does not match its output model.",
            },
        ) from exc


    # 8. Check max output bytes
    output_json_bytes = json.dumps(output_dict).encode("utf-8")
    if len(output_json_bytes) > spec.max_output_bytes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "OUTPUT_SIZE_EXCEEDED",
                "message": f"Operation output size ({len(output_json_bytes)} bytes) exceeds limit of {spec.max_output_bytes} bytes",
            },
        )

    return Response(
        content=output_json_bytes,
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )
