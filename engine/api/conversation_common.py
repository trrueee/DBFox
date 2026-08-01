from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request


def coordinator(request: Request) -> Any:
    value = getattr(request.app.state, "agent_coordinator", None)
    if value is None or not bool(getattr(value, "available", False)):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AGENT_UNAVAILABLE",
                "message": "智能分析暂时不可用，请稍后重试。",
            },
        )
    return value


def required_iso(value: datetime | None, field: str) -> str:
    if value is None:
        raise RuntimeError(f"Persisted conversation is missing {field}")
    return value.isoformat()
