from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Iterator

from pydantic import BaseModel, Field


class PermissionReport(BaseModel):
    readonly: bool
    writable_privileges: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PermissionProbe(ABC):
    @abstractmethod
    def probe(self, conn: Any) -> PermissionReport:
        raise NotImplementedError


WRITE_PRIVILEGE_WARNING = "提示：当前数据库账号包含写入权限，建议在生产环境使用只读账号以保安全。"


@contextmanager
def managed_cursor(conn: Any) -> Iterator[Any]:
    cursor_or_context = conn.cursor()
    if hasattr(cursor_or_context, "__enter__") and hasattr(cursor_or_context, "__exit__"):
        with cursor_or_context as cursor:
            yield cursor
        return

    try:
        yield cursor_or_context
    finally:
        close = getattr(cursor_or_context, "close", None)
        if callable(close):
            close()


def bool_from_db_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "t", "true", "on", "yes"}
