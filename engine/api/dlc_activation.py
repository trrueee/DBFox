"""Runtime DLC activation projection endpoint for Frontend and Asset Host handoff."""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel

from engine.runtime_composition import get_active_runtime_snapshot

router = APIRouter(prefix="/dlcs", tags=["dlc_activation"])


class ActiveDlcItem(BaseModel):
    dlc_id: str
    package_version: str
    package_digest: str
    frontend_entrypoint: str | None = None


class DlcActivationProjectionResponse(BaseModel):
    snapshot_id: str
    active_dlcs: list[ActiveDlcItem]


@router.get(
    "/activation",
    response_model=DlcActivationProjectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active Runtime DLC projection and snapshot identity",
)
async def get_dlc_activation_projection() -> DlcActivationProjectionResponse:
    """Return the wire-safe activation projection derived from active runtime truth."""
    snapshot = get_active_runtime_snapshot()
    projection = snapshot.derive_r3_projection()
    return DlcActivationProjectionResponse(
        snapshot_id=projection.snapshot_id,
        active_dlcs=[
            ActiveDlcItem(
                dlc_id=item["dlc_id"],
                package_version=item["package_version"],
                package_digest=item["package_digest"],
                frontend_entrypoint=item.get("frontend_entrypoint"),
            )
            for item in projection.active_dlcs
        ],
    )
