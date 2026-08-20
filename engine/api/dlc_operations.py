"""Generic typed operation endpoint for Runtime DLC management RPCs."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError

from engine.dlc.api import DlcOperationContext
from engine.runtime_composition import get_active_runtime_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dlcs", tags=["dlc_operations"])


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
    """Execute a typed DLC operation."""
    snapshot = get_active_runtime_snapshot()
    op_contrib = snapshot.get_operation(dlc_id, operation_name)
    if op_contrib is None:
        # Check if DLC is active
        is_dlc_active = any(d.dlc_id == dlc_id for d in snapshot.active_dlcs)
        if not is_dlc_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "DLC_NOT_ACTIVE",
                    "message": f"DLC '{dlc_id}' is not currently active.",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "OPERATION_NOT_FOUND",
                "message": f"Operation '{operation_name}' not found for DLC '{dlc_id}'.",
            },
        )

    spec = op_contrib.spec

    # Parse JSON body
    try:
        body_bytes = await request.body()
        raw_input = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_JSON",
                "message": f"Failed to parse request JSON: {exc}",
            },
        ) from exc

    # Validate input model
    try:
        input_data = spec.input_model.model_validate(raw_input)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_OPERATION_INPUT",
                "message": "Operation input validation failed.",
                "errors": exc.errors(),
            },
        ) from exc

    # Build execution context
    ctx = DlcOperationContext(
        dlc_id=dlc_id,
        operation_name=operation_name,
        caller_info={"client": request.client.host if request.client else None},
    )

    # Execute handler
    try:
        try:
            # Try 2-arg handler (input, ctx)
            result = spec.handler(input_data, ctx)  # type: ignore[call-arg]
        except TypeError:
            # Fall back to 1-arg handler (input)
            result = spec.handler(input_data)  # type: ignore[call-arg]
    except Exception as exc:
        logger.error(
            f"Operation '{operation_name}' for DLC '{dlc_id}' failed: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "OPERATION_EXECUTION_FAILED",
                "message": f"Operation execution failed: {type(exc).__name__}",
            },
        ) from exc

    # Validate output model
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
                "error_code": "INVALID_OPERATION_OUTPUT",
                "message": "Operation handler returned output that does not match its output model.",
            },
        ) from exc

    # Check max output bytes
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
