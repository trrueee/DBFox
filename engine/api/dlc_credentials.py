"""Permission-scoped credential enrollment for active Runtime DLCs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from engine.api.credentials import enroll_credentials
from engine.db import get_db
from engine.runtime_composition import get_active_runtime_snapshot
from engine.schemas.credentials import (
    CredentialEnrollmentBatchRequest,
    CredentialEnrollmentBatchResponse,
)


router = APIRouter(prefix="/dlcs", tags=["dlc_credentials"])


@router.post(
    "/{dlc_id}/credentials/batch",
    response_model=CredentialEnrollmentBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_dlc_credentials(
    dlc_id: str,
    request: CredentialEnrollmentBatchRequest,
    db: Session = Depends(get_db),
) -> CredentialEnrollmentBatchResponse:
    active = next(
        (
            item
            for item in get_active_runtime_snapshot().active_dlcs
            if item.dlc_id == dlc_id
        ),
        None,
    )
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DLC_NOT_ACTIVE",
                "message": f"DLC '{dlc_id}' is not currently active.",
            },
        )
    allowed = set(active.permissions)
    denied = sorted(
        {
            item.kind.value
            for item in request.credentials
            if f"credentials:{item.kind.value}" not in allowed
        }
    )
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "DLC_CREDENTIAL_PERMISSION_DENIED",
                "message": "DLC did not declare permission for the requested credential kind.",
            },
        )
    return enroll_credentials(request, db=db)
