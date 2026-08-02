"""RFC 9457 Problem Details responses for the local HTTP boundary."""

from __future__ import annotations

from http import HTTPStatus
import re
import secrets
from typing import Any, Mapping, Sequence

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Scope


PROBLEM_MEDIA_TYPE = "application/problem+json"
REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")


def new_request_id() -> str:
    """Return a non-identifying request correlation ID."""
    return secrets.token_hex(16)


def request_id_from_scope(scope: Scope) -> str:
    state = scope.setdefault("state", {})
    request_id = state.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        request_id = new_request_id()
        state["request_id"] = request_id
    return request_id


def _public_code(code: str) -> str:
    normalized = code.strip().upper()
    return normalized if _SAFE_CODE.fullmatch(normalized) else "REQUEST_FAILED"


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Request Failed"


def problem_document(
    *,
    status: int,
    code: str,
    detail: str,
    instance: str,
    request_id: str,
    checks: Sequence[Mapping[str, Any]] | None = None,
    errors: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the stable wire representation without embedding request data."""
    public_code = _public_code(code)
    document: dict[str, Any] = {
        "type": f"urn:dbfox:problem:{public_code.lower().replace('_', '-')}",
        "title": _title(status),
        "status": status,
        "detail": detail,
        "instance": instance,
        "code": public_code,
        "request_id": request_id,
    }
    if checks:
        document["checks"] = list(checks)
    if errors:
        document["errors"] = list(errors)
    return document


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    detail: str,
    checks: Sequence[Mapping[str, Any]] | None = None,
    errors: Sequence[Mapping[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_from_scope(request.scope)
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status,
        content=problem_document(
            status=status,
            code=code,
            detail=detail,
            instance=request.url.path,
            request_id=request_id,
            checks=checks,
            errors=errors,
        ),
        headers=response_headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def problem_response_for_scope(
    scope: Scope,
    *,
    status: int,
    code: str,
    detail: str,
) -> JSONResponse:
    request_id = request_id_from_scope(scope)
    return JSONResponse(
        status_code=status,
        content=problem_document(
            status=status,
            code=code,
            detail=detail,
            instance=str(scope.get("path") or "/"),
            request_id=request_id,
        ),
        headers={REQUEST_ID_HEADER: request_id},
        media_type=PROBLEM_MEDIA_TYPE,
    )
