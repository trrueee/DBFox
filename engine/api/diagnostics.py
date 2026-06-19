from __future__ import annotations

from fastapi import APIRouter, Query

from engine.diagnostics.logs import (
    DEFAULT_MAX_LINES,
    collect_diagnostic_logs,
    diagnostic_log_paths,
)

router = APIRouter()


@router.get("/diagnostics/logs")
def get_diagnostic_logs(
    max_lines: int = Query(DEFAULT_MAX_LINES, ge=1, le=1000),
) -> dict[str, object]:
    return collect_diagnostic_logs(
        max_lines=max_lines,
        sources=diagnostic_log_paths(),
    )
