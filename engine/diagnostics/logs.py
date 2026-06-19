from __future__ import annotations

import logging
import os
import platform
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

from engine.runtime_paths import PROJECT_DIR, private_runtime_file

LOG_FILE_NAME = "dbfox-engine.log"
DEFAULT_MAX_LINES = 300
MAX_MAX_LINES = 1000
MAX_READ_BYTES = 256 * 1024
_DIAGNOSTIC_HANDLER_MARKER = "_dbfox_diagnostic_log_handler"

_ASSIGNMENT_RE = re.compile(
    r"(?i)([\"']?\b(?:api[_-]?key|admin[_-]?api[_-]?key|openai[_-]?api[_-]?key|"
    r"aliyun[_-]?api[_-]?key|password|passwd|pwd|secret|token|cookie|"
    r"connection[_-]?string|dsn)\b[\"']?\s*[:=]\s*)([\"']?)([^\"'\s,;}\]]+)([\"']?)"
)
_AUTHORIZATION_RE = re.compile(r"(?i)\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)")
_URL_PASSWORD_RE = re.compile(r"(://[^:/@\s]+:)([^@/\s]+)(@)")


def diagnostic_log_file() -> Path:
    return private_runtime_file("logs", LOG_FILE_NAME)


def diagnostic_log_paths() -> list[tuple[str, Path]]:
    runtime_logs = PROJECT_DIR / "artifacts" / "runtime-logs"
    return [
        ("engine", diagnostic_log_file()),
        ("engine-stdout", runtime_logs / "engine.out.log"),
        ("engine-stderr", runtime_logs / "engine.err.log"),
        ("frontend-stdout", runtime_logs / "frontend.out.log"),
        ("frontend-stderr", runtime_logs / "frontend.err.log"),
    ]


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text

    redacted = _URL_PASSWORD_RE.sub(r"\1[REDACTED]\3", text)
    redacted = _AUTHORIZATION_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2) or ''}[REDACTED]",
        redacted,
    )
    redacted = _ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}",
        redacted,
    )
    return redacted


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


def configure_diagnostic_logging(level: int = logging.INFO) -> Path:
    log_path = diagnostic_log_file()
    logger = logging.getLogger("dbfox")
    logger.setLevel(level)

    for handler in logger.handlers:
        if getattr(handler, _DIAGNOSTIC_HANDLER_MARKER, False):
            return log_path

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    setattr(handler, _DIAGNOSTIC_HANDLER_MARKER, True)
    handler.setLevel(level)
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(handler)
    return log_path


def read_log_source(name: str, path: Path, max_lines: int = DEFAULT_MAX_LINES) -> dict[str, object]:
    max_lines = _bounded_max_lines(max_lines)
    if not path.exists():
        return {
            "name": name,
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "modified_at": None,
            "content": "",
        }

    stat = path.stat()
    content = redact_sensitive_text(_tail_text(path, max_lines=max_lines))
    return {
        "name": name,
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "content": content,
    }


def collect_diagnostic_logs(
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    sources: Iterable[tuple[str, Path]] | None = None,
) -> dict[str, object]:
    max_lines = _bounded_max_lines(max_lines)
    selected_sources = list(sources) if sources is not None else diagnostic_log_paths()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "redacted": True,
            "max_lines_per_source": max_lines,
            "omitted": [
                "database passwords",
                "API keys",
                "local engine tokens",
                "cookies and authorization headers",
                "large query result data",
            ],
        },
        "environment": {
            "app": "DBFox",
            "pid": os.getpid(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "sources": [
            read_log_source(name, path, max_lines=max_lines)
            for name, path in selected_sources
        ],
    }


def _bounded_max_lines(max_lines: int) -> int:
    return max(1, min(int(max_lines), MAX_MAX_LINES))


def _tail_text(path: Path, *, max_lines: int) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > MAX_READ_BYTES:
            handle.seek(-MAX_READ_BYTES, os.SEEK_END)
            handle.readline()
        data = handle.read()

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])
