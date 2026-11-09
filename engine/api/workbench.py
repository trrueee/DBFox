"""Local HTTP boundary for applying a single live Dock request."""

from fastapi import APIRouter, HTTPException, Request, Response

from engine.workbench_presentations import WorkbenchPresentation, WorkbenchPresentationReceipt

router = APIRouter()


@router.post("/conversations/{conversation_id}/workbench-presentations/{invocation_id}/claim")
def claim_workbench_presentation(
    conversation_id: str, invocation_id: str, request: Request,
) -> WorkbenchPresentation | None:
    broker = getattr(request.app.state, "workbench_presentations", None)
    return broker.claim(conversation_id, invocation_id) if broker is not None else None


@router.post("/conversations/{conversation_id}/workbench-presentations/{invocation_id}/receipt", status_code=204)
def acknowledge_workbench_presentation(
    conversation_id: str, invocation_id: str, payload: WorkbenchPresentationReceipt, request: Request,
) -> Response:
    broker = getattr(request.app.state, "workbench_presentations", None)
    if broker is None or not broker.acknowledge(conversation_id, invocation_id, payload):
        raise HTTPException(status_code=404, detail={
            "code": "WORKBENCH_PRESENTATION_UNAVAILABLE",
            "message": "The Workbench presentation request is no longer available.",
        })
    return Response(status_code=204)
