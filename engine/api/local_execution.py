"""Conversation-scoped reads and direct user stop for the Host Dock."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session

from engine.agent.resource_refs import RequestedResourceRef
from engine.attachments import AttachmentError, require_session
from engine.db import get_db
from engine.local_execution.broker import LocalExecutionBroker
from engine.local_execution.contracts import ExecutionScope, JobPage, JobView, WORKSPACE_KIND
from engine.runtime_composition import authorize_conversation_resources

router = APIRouter(prefix="/conversations/{conversation_id}/execution-jobs")
JobId = Annotated[str, Path(pattern=r"^job_[0-9a-f]{32}$")]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={
        "code": "EXECUTION_JOB_UNAVAILABLE", "message": "当前会话或项目绑定下没有可用的执行记录。",
    })


def _context(conversation_id: str, request: Request, db: Session) -> tuple[LocalExecutionBroker, ExecutionScope]:
    broker = getattr(request.app.state, "local_execution", None)
    if broker is None:
        raise HTTPException(status_code=409, detail={
            "code": "LOCAL_EXECUTION_UNAVAILABLE", "message": "当前客户端没有启用本机执行环境。",
        })
    try:
        conversation = require_session(db, conversation_id)
        (ref,) = authorize_conversation_resources(db, conversation_id, [
            RequestedResourceRef(kind=WORKSPACE_KIND, id=str(conversation.project_id or "")),
        ])
    except (AttachmentError, ValueError, KeyError):
        raise _not_found() from None
    return broker, ExecutionScope(conversation_id, ref)


@router.get("")
def list_execution_jobs(
    conversation_id: str, request: Request, db: Session = Depends(get_db),
) -> list[JobView]:
    broker, scope = _context(conversation_id, request, db)
    try:
        return broker.list_jobs(scope)
    except (ValueError, KeyError, OSError):
        raise _not_found() from None


@router.get("/{job_id}")
def read_execution_job(
    conversation_id: str, job_id: JobId, request: Request,
    after: int = Query(default=0, ge=0, le=2**53 - 1),
    limit: int = Query(default=16, ge=1, le=16),
    tail: bool = False,
    db: Session = Depends(get_db),
) -> JobPage:
    broker, scope = _context(conversation_id, request, db)
    try:
        return broker.page(scope, job_id, after, limit, tail=tail)
    except (ValueError, KeyError, OSError):
        raise _not_found() from None


@router.post("/{job_id}/stop", status_code=202)
def stop_execution_job(
    conversation_id: str, job_id: JobId, request: Request, db: Session = Depends(get_db),
) -> Response:
    broker, scope = _context(conversation_id, request, db)
    try:
        broker.stop(scope, job_id)
    except (ValueError, KeyError, OSError):
        raise _not_found() from None
    return Response(status_code=202)
