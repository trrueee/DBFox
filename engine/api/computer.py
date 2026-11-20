"""Authenticated direct-user sharing, previews and emergency stop."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from sqlalchemy.orm import Session

from engine.attachments import require_session
from engine.computer.contracts import BrowserState, ComputerError, ComputerGrant, ShareInput, TargetOption
from engine.computer.runtime import ComputerRuntime
from engine.db import get_db

router = APIRouter()
TargetId = Annotated[str, Path(pattern=r"^computer_[0-9a-f]{32}$")]


def _runtime(request: Request) -> ComputerRuntime:
    runtime = getattr(request.app.state, "computer", None)
    if not isinstance(runtime, ComputerRuntime):
        raise HTTPException(status_code=409, detail={"code": "COMPUTER_UNAVAILABLE", "message": "电脑操作目前支持 Windows 11 桌面客户端。"})
    return runtime


def _error(exc: ComputerError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)})


@router.get("/computer/targets")
def list_computer_targets(request: Request) -> list[TargetOption]:
    try:
        return list(_runtime(request).inventory())
    except ComputerError as exc:
        raise _error(exc) from None


@router.get("/conversations/{conversation_id}/computer")
def list_computer_shares(conversation_id: str, request: Request, db: Session = Depends(get_db)) -> list[ComputerGrant]:
    require_session(db, conversation_id)
    return list(_runtime(request).store.list(conversation_id))


@router.post("/conversations/{conversation_id}/computer", status_code=201)
def share_computer_target(conversation_id: str, input: ShareInput, request: Request, db: Session = Depends(get_db)) -> ComputerGrant:
    require_session(db, conversation_id)
    try:
        return _runtime(request).share(conversation_id, input)
    except ComputerError as exc:
        raise _error(exc) from None


@router.get("/conversations/{conversation_id}/computer/{target_id}/preview", response_class=Response)
def preview_computer_target(conversation_id: str, target_id: TargetId, request: Request, db: Session = Depends(get_db)) -> Response:
    require_session(db, conversation_id)
    try:
        png, _title = _runtime(request).preview(conversation_id, target_id)
    except ComputerError as exc:
        raise _error(exc) from None
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/conversations/{conversation_id}/computer/{target_id}/browser")
def read_computer_browser(conversation_id: str, target_id: TargetId, request: Request, db: Session = Depends(get_db)) -> BrowserState:
    require_session(db, conversation_id)
    try:
        return _runtime(request).browser_state(conversation_id, target_id)
    except ComputerError as exc:
        raise _error(exc) from None


@router.post("/conversations/{conversation_id}/computer/{target_id}/stop", status_code=202)
def stop_computer_target(conversation_id: str, target_id: TargetId, request: Request, db: Session = Depends(get_db)) -> Response:
    require_session(db, conversation_id)
    try:
        _runtime(request).stop(conversation_id, target_id=target_id)
    except ComputerError as exc:
        raise _error(exc) from None
    return Response(status_code=202)


@router.delete("/conversations/{conversation_id}/computer/{target_id}", status_code=204)
def revoke_computer_target(conversation_id: str, target_id: TargetId, request: Request, db: Session = Depends(get_db)) -> Response:
    require_session(db, conversation_id)
    try:
        _runtime(request).stop(conversation_id, target_id=target_id, revoke=True)
    except ComputerError as exc:
        raise _error(exc) from None
    return Response(status_code=204)


@router.post("/computer/stop", status_code=202)
def stop_all_computer_targets(request: Request) -> Response:
    _runtime(request).stop(None)
    return Response(status_code=202)
