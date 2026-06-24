from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import PermissionProbe, PermissionReport
from .mysql import MySQLPermissionProbe
from .postgres import PostgresPermissionProbe
from .sqlite import SQLitePermissionProbe

__all__ = [
    "MySQLPermissionProbe",
    "PermissionProbe",
    "PermissionReport",
    "PostgresPermissionProbe",
    "SQLitePermissionProbe",
    "permission_probe_for_dialect",
]


def permission_probe_for_dialect(dialect: str, **kwargs: Any) -> PermissionProbe:
    normalized = dialect.strip().lower()
    if normalized in {"postgres", "postgresql"}:
        return PostgresPermissionProbe()
    if normalized == "mysql":
        return MySQLPermissionProbe()
    if normalized == "sqlite":
        database_path = kwargs.get("database_path")
        if database_path is None:
            raise ValueError("SQLite permission probe requires database_path.")
        return SQLitePermissionProbe(
            database_path=Path(database_path),
            connection_readonly=kwargs.get("connection_readonly"),
        )
    raise ValueError(f"Unsupported permission probe dialect: {dialect}")
