from __future__ import annotations

import re

from sqlglot import exp
from sqlglot.lineage import lineage
from sqlglot.schema import MappingSchema
from sqlalchemy.orm import Session

from engine.models import SchemaColumn, SchemaTable, SemanticAlias
from dlcs.dbfox_data.backend.sensitivity import (
    SAFE_PATTERN_SET,
    SENSITIVE_FALLBACK,
    SENSITIVE_PATTERN_STRINGS,
)

def _bootstrap_sensitivity(db: Session, datasource_id: str) -> None:
    """Write built-in sensitivity patterns into the database."""
    for pat in SENSITIVE_PATTERN_STRINGS:
        db.add(SemanticAlias(
            data_source_id=datasource_id,
            alias=pat,
            target_type="sensitive",
            target="*",
            description="Bootstrapped default",
        ))
    try:
        db.commit()
    except Exception:
        db.rollback()

def load_sensitivity(db: Session, datasource_id: str) -> re.Pattern:
    """Return a compiled regex of sensitive column patterns.

    Reads from SemanticAlias rows with target_type='sensitive'.
    Falls back to the built-in default set.
    """
    rows = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type == "sensitive",
        )
        .all()
    )
    if not rows:
        _bootstrap_sensitivity(db, datasource_id)
        rows = (
            db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type == "sensitive",
            )
            .all()
        )

    patterns: list[str] = []
    for r in rows:
        alias = str(r.alias)
        # Escape administrator-provided patterns to prevent ReDoS.
        # Bootstrapped defaults (word-boundary anchored alternations) are
        # known-safe and used verbatim.
        if alias in SAFE_PATTERN_SET:
            patterns.append(alias)
        else:
            patterns.append(re.escape(alias))
    pii_column_names = (
        db.query(SchemaColumn.column_name)
        .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
        .filter(
            SchemaTable.data_source_id == datasource_id,
            SchemaColumn.is_pii.is_(True),
        )
        .all()
    )
    patterns.extend(
        rf"\b{re.escape(str(column_name))}\b"
        for (column_name,) in pii_column_names
        if str(column_name).strip()
    )
    if not patterns:
        return SENSITIVE_FALLBACK
    return re.compile("|".join(patterns), re.IGNORECASE)


def projection_sensitivity_mask(
    db: Session,
    datasource_id: str,
    sql: str,
    dialect: str,
    sensitivity: re.Pattern,
) -> tuple[bool, ...] | None:
    """Return one sensitivity flag per output projection.

    SQL output names are caller-controlled aliases, so result-key matching alone
    cannot enforce the datasource sensitivity policy.  SQLGlot lineage resolves
    each output projection back to catalog columns, including aliases, expressions,
    CTEs, and stars.  ``None`` means lineage could not prove a safe mapping and the
    caller must fail closed for every returned column.
    """

    read_dialect = "postgres" if dialect == "postgresql" else dialect
    try:
        catalog_rows = (
            db.query(
                SchemaTable.table_schema,
                SchemaTable.table_name,
                SchemaColumn.column_name,
                SchemaColumn.data_type,
            )
            .join(SchemaColumn, SchemaColumn.table_id == SchemaTable.id)
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        )
        if not catalog_rows:
            return None
        catalog: dict[tuple[str, str], dict[str, str]] = {}
        for table_schema, table_name, column_name, data_type in catalog_rows:
            normalized_table = str(table_name or "").strip()
            normalized_column = str(column_name or "").strip()
            if not normalized_table or not normalized_column:
                continue
            key = (str(table_schema or "").strip(), normalized_table)
            catalog.setdefault(key, {})[normalized_column] = str(data_type or "UNKNOWN")

        schema = MappingSchema(dialect=read_dialect)
        for (table_schema, table_name), columns in catalog.items():
            table_expression = exp.Table(
                this=exp.to_identifier(table_name),
                db=(exp.to_identifier(table_schema) if table_schema else None),
            )
            schema.add_table(
                table_expression,
                columns,
                dialect=read_dialect,
                match_depth=False,
            )

        output_lineage = lineage(
            None,
            sql,
            schema=schema,
            dialect=read_dialect,
        )
        flags: list[bool] = []
        for node in output_lineage.values():
            sensitive = False
            for upstream in node.walk():
                if isinstance(upstream.expression, exp.Placeholder):
                    # An unresolved source column cannot be declared non-sensitive.
                    sensitive = True
                    break
                if not isinstance(upstream.expression, exp.Table):
                    continue
                source_column = str(upstream.name).rsplit(".", 1)[-1]
                if sensitivity.search(source_column):
                    sensitive = True
                    break
            flags.append(sensitive)
        return tuple(flags)
    except Exception:
        return None
