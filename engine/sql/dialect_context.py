from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from engine.models import DataSource


SqlDialect = Literal["mysql", "postgresql", "sqlite"]


def canonical_sql_dialect(value: str | None) -> SqlDialect:
    raw = (value or "mysql").strip().lower()
    if raw in {"postgres", "postgresql"}:
        return "postgresql"
    if raw == "sqlite":
        return "sqlite"
    return "mysql"


class DialectContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    datasource_id: str
    dialect: SqlDialect
    schema_cache: Any | None = None

    @property
    def sqlglot_dialect(self) -> str:
        if self.dialect == "postgresql":
            return "postgres"
        return self.dialect

    @classmethod
    def from_datasource(cls, datasource: DataSource) -> "DialectContext":
        return cls(
            datasource_id=str(datasource.id),
            dialect=canonical_sql_dialect(str(datasource.db_type or "mysql")),
        )

    @classmethod
    def from_datasource_id(cls, db: Session, datasource_id: str) -> "DialectContext":
        datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
        if datasource is None:
            return cls(datasource_id=datasource_id, dialect="mysql")
        return cls.from_datasource(datasource)
