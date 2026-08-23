"""Database dialect value contracts owned by the Data capability."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


SqlDialect = Literal["mysql", "postgresql", "sqlite", "duckdb"]


def canonical_sql_dialect(value: str | None) -> SqlDialect:
    raw = (value or "mysql").strip().lower()
    if raw in {"postgres", "postgresql"}:
        return "postgresql"
    if raw == "sqlite":
        return "sqlite"
    if raw == "duckdb":
        return "duckdb"
    return "mysql"


class DatabaseDialectContext(BaseModel):
    resource_id: str
    dialect: SqlDialect

    @property
    def sqlglot_dialect(self) -> str:
        return "postgres" if self.dialect == "postgresql" else self.dialect
