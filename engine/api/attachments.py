"""Authenticated streaming upload of generic conversation snapshots."""
from __future__ import annotations

import asyncio
import hashlib
import re
from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from engine.attachments import AttachmentError, AttachmentService, AttachmentSummary, MAX_ATTACHMENT_BYTES, MAX_SESSION_ATTACHMENTS, MAX_SESSION_ATTACHMENT_BYTES, require_session
from pydantic import BaseModel
from engine.db import get_db
from engine.agent.repositories.write_transaction import begin_agent_write

router = APIRouter()


class AttachmentCapabilities(BaseModel):
    max_file_bytes: int
    max_session_files: int
    max_session_bytes: int


@router.get("/attachment-capabilities", response_model=AttachmentCapabilities)
def attachment_capabilities() -> AttachmentCapabilities:
    return AttachmentCapabilities(max_file_bytes=MAX_ATTACHMENT_BYTES, max_session_files=MAX_SESSION_ATTACHMENTS,
                                  max_session_bytes=MAX_SESSION_ATTACHMENT_BYTES)


def _failure(error: AttachmentError) -> HTTPException:
    return HTTPException(error.status, detail={"code": error.code, "message": str(error)})


@router.get("/conversations/{session_id}/attachments", response_model=list[AttachmentSummary])
def list_attachments(session_id: str, db: Session = Depends(get_db)) -> list[AttachmentSummary]:
    try:
        service = AttachmentService(db)
        return [service.summary(row) for row in service.listing(session_id, staged=True)]
    except AttachmentError as exc:
        raise _failure(exc) from None


@router.post("/conversations/{session_id}/attachments", response_model=AttachmentSummary, status_code=201)
async def upload_attachment(session_id: str, request: Request, db: Session = Depends(get_db)) -> AttachmentSummary:
    temporary = None
    try:
        require_session(db, session_id)
        db.rollback()
        name = unquote(request.headers.get("x-file-name", ""), errors="strict")
        key = request.headers.get("x-upload-key", "")
        media_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        if not name or len(name) > 255 or re.search(r"[\\/\x00-\x1f\x7f]", name) or len(media_type) > 255 or re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key) is None:
            raise AttachmentError("INVALID_ATTACHMENT_METADATA", "文件名或上传标识无效。")
        service = AttachmentService(db)
        temporary = service.root / ("upload_" + uuid4().hex + ".tmp")
        digest, size = hashlib.sha256(), 0
        async with asyncio.timeout(60):
            with temporary.open("xb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_ATTACHMENT_BYTES:
                        raise AttachmentError("ATTACHMENT_TOO_LARGE", "附件不能超过10 MiB。", 413)
                    digest.update(chunk)
                    output.write(chunk)
        if size == 0:
            raise AttachmentError("ATTACHMENT_EMPTY", "不能添加空文件。")
        begin_agent_write(db)
        row = service.publish(session_id, temporary=temporary, name=name, media_type=media_type, size=size, digest=digest.hexdigest(), key=key)
        db.commit()
        return service.summary(row)
    except AttachmentError as exc:
        db.rollback()
        raise _failure(exc) from None
    except (TimeoutError, UnicodeError):
        db.rollback()
        raise HTTPException(400, detail={"code": "ATTACHMENT_UPLOAD_FAILED", "message": "附件上传未完成，请重试。"}) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@router.delete("/conversations/{session_id}/attachments/{attachment_id}", status_code=204, response_model=None)
def remove_attachment(session_id: str, attachment_id: str, db: Session = Depends(get_db)) -> None:
    try:
        begin_agent_write(db)
        AttachmentService(db).remove_staged(session_id, attachment_id)
        db.commit()
    except AttachmentError as exc:
        db.rollback()
        raise _failure(exc) from None
