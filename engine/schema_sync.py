"""
.. deprecated::
    This module is superseded by ``engine.environment.schema_catalog_sync``
    which uses an upsert strategy and is the single source of truth for all
    schema sync operations as of 2026-06-20 (MVP simplification).

    Kept for the ``build_er_diagram_data()`` helper and for backward
    compatibility.  New code should call ``ensure_catalog()`` instead.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from engine.crypto import decrypt_password
from engine.datasource import (
    build_mysql_ssl_params,
    build_postgres_ssl_params,
    datasource_connection_dict,
)
from engine.models import DataSource, SchemaColumn, SchemaTable

logger = logging.getLogger("dbfox.schema_sync")

SchemaSnapshot = tuple[list[SchemaTable], list[SchemaColumn], int]


def _build_real_schema_snapshot(ds: DataSource, datasource_id: str) -> SchemaSnapshot:
    host = str(ds.host)
    port = int(ds.port)
    user = str(ds.username)
    database_name = str(ds.database_name)
    password = decrypt_password(str(ds.password_ciphertext), str(ds.password_nonce))

    if ds.ssh_enabled:
        from engine.datasource import get_or_create_tunnel_for_dict

        ds_dict = datasource_connection_dict(ds)
        tunnel = get_or_create_tunnel_for_dict(ds_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    ssl_params = build_mysql_ssl_params(datasource_connection_dict(ds))

    dsn = URL.create(
        drivername="mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database_name,
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(dsn, connect_args={"connect_timeout": 5, **ssl_params})

    try:
        from sqlalchemy import text
        tables_to_insert: list[SchemaTable] = []
        columns_to_insert: list[SchemaColumn] = []
        
        table_name_to_id: dict[str, str] = {}
        column_name_to_id: dict[tuple[str, str], str] = {}
        column_objects: dict[tuple[str, str], SchemaColumn] = {}

        with engine.connect() as conn:
            # 1. Batch read tables and views from information_schema
            tables_query = text("""
                SELECT 
                    table_name, 
                    table_comment, 
                    table_type, 
                    engine as engine_name,
                    table_rows as row_count_estimate
                FROM information_schema.tables
                WHERE table_schema = :db_name
            """)
            tables_rows = conn.execute(tables_query, {"db_name": database_name}).fetchall()
            
            for row in tables_rows:
                t_name = str(row[0])
                t_comment = row[1]
                t_type = str(row[2])
                e_name = row[3]
                r_count = row[4] if row[4] is not None else 0
                
                table_id = str(uuid.uuid4())
                table_name_to_id[t_name] = table_id
                
                tables_to_insert.append(
                    SchemaTable(
                        id=table_id,
                        data_source_id=datasource_id,
                        table_schema=database_name,
                        table_name=t_name,
                        table_comment=t_comment,
                        table_type=t_type,
                        row_count_estimate=r_count,
                        engine_name=e_name,
                    )
                )

            # 2. Batch read columns from information_schema
            columns_query = text("""
                SELECT 
                    table_name, 
                    column_name, 
                    data_type, 
                    column_type, 
                    is_nullable, 
                    column_default, 
                    column_comment, 
                    column_key, 
                    ordinal_position
                FROM information_schema.columns
                WHERE table_schema = :db_name
                ORDER BY table_name, ordinal_position
            """)
            columns_rows = conn.execute(columns_query, {"db_name": database_name}).fetchall()

            for row in columns_rows:
                t_name = str(row[0])
                c_name = str(row[1])
                d_type = str(row[2])
                c_type = str(row[3])
                nullable_str = str(row[4]).upper()
                c_default = row[5]
                c_comment = row[6]
                c_key = str(row[7]).upper()
                ord_pos = row[8]
                
                t_id = table_name_to_id.get(t_name)
                if not t_id:
                    continue
                table_id = t_id
                    
                col_id = str(uuid.uuid4())
                column_name_to_id[(t_name, c_name)] = col_id
                
                column = SchemaColumn(
                    id=col_id,
                    table_id=table_id,
                    column_name=c_name,
                    data_type=d_type.lower(),
                    column_type=c_type,
                    is_nullable=(nullable_str == "YES"),
                    column_default=str(c_default) if c_default is not None else None,
                    column_comment=c_comment,
                    is_primary_key=(c_key == "PRI"),
                    is_foreign_key=False,
                    ordinal_position=ord_pos,
                )
                column_objects[(t_name, c_name)] = column
                columns_to_insert.append(column)

            # 3. Batch read foreign keys (key_column_usage) from information_schema
            fkeys_query = text("""
                SELECT 
                    table_name, 
                    column_name, 
                    referenced_table_name, 
                    referenced_column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = :db_name 
                  AND referenced_table_name IS NOT NULL
            """)
            fkeys_rows = conn.execute(fkeys_query, {"db_name": database_name}).fetchall()

            for row in fkeys_rows:
                t_name = str(row[0])
                c_name = str(row[1])
                ref_t_name = str(row[2])
                ref_c_name = str(row[3])
                
                fk_column = column_objects.get((t_name, c_name))
                ref_table_id = table_name_to_id.get(ref_t_name)
                ref_col_id = column_name_to_id.get((ref_t_name, ref_c_name))

                if fk_column and ref_table_id and ref_col_id:
                    fk_column.is_foreign_key = True  # type: ignore[assignment]
                    fk_column.foreign_table_id = ref_table_id  # type: ignore[assignment]
                    fk_column.foreign_column_id = ref_col_id  # type: ignore[assignment]

        return tables_to_insert, columns_to_insert, len(tables_to_insert)
    finally:
        engine.dispose()


def _build_inspector_snapshot(
    engine: Any, datasource_id: str, *, schema: str | None = None
) -> SchemaSnapshot:
    """Build a SchemaSnapshot using SQLAlchemy's inspector API.

    Shared by SQLite and PostgreSQL schema sync paths.  MySQL uses a
    separate raw-SQL path because it queries ``information_schema``
    directly for extra metadata (row counts, engine, table comments).
    """
    tables_to_insert: list[SchemaTable] = []
    columns_to_insert: list[SchemaColumn] = []
    table_name_to_id: dict[str, str] = {}
    column_name_to_id: dict[tuple[str, str], str] = {}
    column_objects: dict[tuple[str, str], SchemaColumn] = {}

    inspector = inspect(engine)
    resolved_schema = schema or "main"

    table_names = inspector.get_table_names(schema=schema) if schema else inspector.get_table_names()
    view_names = inspector.get_view_names(schema=schema) if schema else inspector.get_view_names()

    for t_name in table_names + view_names:
        table_id = str(uuid.uuid4())
        table_name_to_id[t_name] = table_id
        t_type = "VIEW" if t_name in view_names else "BASE TABLE"
        tables_to_insert.append(
            SchemaTable(
                id=table_id,
                data_source_id=datasource_id,
                table_schema=resolved_schema,
                table_name=t_name,
                table_comment=None,
                table_type=t_type,
                row_count_estimate=0,
                engine_name=None,
            )
        )

    for t_name in table_names + view_names:
        table_id = table_name_to_id[t_name]
        cols = inspector.get_columns(t_name, schema=schema) if schema else inspector.get_columns(t_name)
        pk_constraint = inspector.get_pk_constraint(t_name, schema=schema) if schema else inspector.get_pk_constraint(t_name)
        pk_cols = pk_constraint.get("constrained_columns", []) or []

        for i, col in enumerate(cols):
            c_name = col["name"]
            col_id = str(uuid.uuid4())
            column_name_to_id[(t_name, c_name)] = col_id
            column = SchemaColumn(
                id=col_id,
                table_id=table_id,
                column_name=c_name,
                data_type=str(col["type"]).lower(),
                column_type=str(col["type"]),
                is_nullable=col.get("nullable", True),
                column_default=str(col.get("default")) if col.get("default") is not None else None,
                column_comment=col.get("comment"),
                is_primary_key=(c_name in pk_cols),
                is_foreign_key=False,
                ordinal_position=i + 1,
            )
            column_objects[(t_name, c_name)] = column
            columns_to_insert.append(column)

    for t_name in table_names:
        fkeys = inspector.get_foreign_keys(t_name, schema=schema) if schema else inspector.get_foreign_keys(t_name)
        for fk in fkeys:
            constrained_cols = fk.get("constrained_columns", [])
            referred_table = fk.get("referred_table")
            referred_cols = fk.get("referred_columns", [])
            if not referred_table or not constrained_cols or not referred_cols:
                continue
            ref_table_id = table_name_to_id.get(referred_table)
            if not ref_table_id:
                continue
            for c_col, r_col in zip(constrained_cols, referred_cols):
                fk_column = column_objects.get((t_name, c_col))
                ref_col_id = column_name_to_id.get((referred_table, r_col))
                if fk_column and ref_col_id:
                    fk_column.is_foreign_key = True  # type: ignore[assignment]
                    fk_column.foreign_table_id = ref_table_id  # type: ignore[assignment]
                    fk_column.foreign_column_id = ref_col_id  # type: ignore[assignment]

    return tables_to_insert, columns_to_insert, len(tables_to_insert)


def _build_sqlite_schema_snapshot(ds: DataSource, datasource_id: str) -> SchemaSnapshot:
    engine = create_engine(f"sqlite:///{str(ds.database_name)}")
    try:
        return _build_inspector_snapshot(engine, datasource_id)
    finally:
        engine.dispose()


def _build_postgresql_schema_snapshot(ds: DataSource, datasource_id: str) -> SchemaSnapshot:
    host = str(ds.host)
    port = int(ds.port)
    user = str(ds.username)
    database_name = str(ds.database_name)
    password = decrypt_password(str(ds.password_ciphertext), str(ds.password_nonce))

    if ds.ssh_enabled:
        from engine.datasource import get_or_create_tunnel_for_dict
        ds_dict = datasource_connection_dict(ds)
        tunnel = get_or_create_tunnel_for_dict(ds_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    ssl_params = build_postgres_ssl_params(datasource_connection_dict(ds))
    dsn = URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database_name,
    )
    engine = create_engine(dsn, connect_args={"connect_timeout": 5, **ssl_params})
    try:
        inspector = inspect(engine)
        schema = inspector.default_schema_name or "public"
        return _build_inspector_snapshot(engine, datasource_id, schema=schema)
    finally:
        engine.dispose()


# AI metadata fields that should survive schema sync so manual edits
# (主题域 / AI描述 / 置信度 / 语义标签 / 业务术语) are not lost.
_TABLE_AI_FIELDS = [
    "ai_description", "semantic_tags", "business_terms", "aliases",
    "table_role", "grain", "subject_area", "ai_confidence", "ai_enriched_at",
    "schema_hash",  # preserve so tables without structural changes skip re-enrichment
]
_COLUMN_AI_FIELDS = [
    "ai_description", "semantic_tags", "business_terms", "aliases",
    "column_role", "metric_type", "is_pii", "ai_confidence", "ai_enriched_at",
]


def _snapshot_ai_metadata(
    db: Session, datasource_id: str,
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    """Read existing AI metadata before the old rows are deleted."""
    old_tables = (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .all()
    )
    table_ai: dict[str, dict[str, Any]] = {}
    column_ai: dict[tuple[str, str], dict[str, Any]] = {}

    for t in old_tables:
        t_name = str(t.table_name)
        saved: dict[str, Any] = {}
        for field in _TABLE_AI_FIELDS:
            val = getattr(t, field, None)
            if val is not None:
                saved[field] = val
        if saved:
            table_ai[t_name] = saved

        for col in t.columns or []:
            c_name = str(col.column_name)
            csaved: dict[str, Any] = {}
            for field in _COLUMN_AI_FIELDS:
                val = getattr(col, field, None)
                if val is not None:
                    csaved[field] = val
            if csaved:
                column_ai[(t_name, c_name)] = csaved

    return table_ai, column_ai


def _restore_ai_metadata(
    tables_to_insert: list[SchemaTable],
    columns_to_insert: list[SchemaColumn],
    table_ai: dict[str, dict[str, Any]],
    column_ai: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Copy preserved AI metadata onto the fresh snapshot rows."""
    for t in tables_to_insert:
        t_name = str(t.table_name)
        saved = table_ai.get(t_name, {})
        for field, val in saved.items():
            setattr(t, field, val)

    table_name_by_id: dict[str, str] = {}
    for t in tables_to_insert:
        table_name_by_id[str(t.id)] = str(t.table_name)

    for col in columns_to_insert:
        t_name = table_name_by_id.get(str(col.table_id))
        if not t_name:
            continue
        c_name = str(col.column_name)
        csaved = column_ai.get((t_name, c_name), {})
        for field, val in csaved.items():
            setattr(col, field, val)


def _replace_schema_snapshot(
    db: Session,
    datasource_id: str,
    tables_to_insert: list[SchemaTable],
    columns_to_insert: list[SchemaColumn],
) -> None:
    # Preserve user-edited AI metadata before deleting old rows
    table_ai, column_ai = _snapshot_ai_metadata(db, datasource_id)

    table_ids = [
        row[0]
        for row in db.query(SchemaTable.id).filter(SchemaTable.data_source_id == datasource_id).all()
    ]
    if table_ids:
        db.query(SchemaColumn).filter(SchemaColumn.table_id.in_(table_ids)).delete(synchronize_session=False)
    db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).delete(synchronize_session=False)
    db.add_all(tables_to_insert)
    db.add_all(columns_to_insert)
    db.flush()  # assign IDs so FK relationships are resolved

    _restore_ai_metadata(tables_to_insert, columns_to_insert, table_ai, column_ai)


def _ai_enrich_warning(enrich_result: dict[str, Any]) -> str | None:
    if enrich_result.get("ai_enriched") is not False:
        return None
    reason = str(enrich_result.get("reason") or "").strip()
    if not reason or reason == "no structural changes":
        return None
    return f"AI 语义打分未完成：{reason}"


def sync_schema(
    db: Session,
    datasource_id: str,
    *,
    ai_enrich: bool = True,
    ai_api_key: str | None = None,
    ai_api_base: str | None = None,
    ai_model_name: str | None = None,
) -> dict[str, Any]:
    """
    Synchronize metadata into local SQLite without deleting the previous snapshot
    until the new snapshot has been gathered successfully.
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    try:
        if ds.db_type == "sqlite":
            tables_to_insert, columns_to_insert, tables_synced = _build_sqlite_schema_snapshot(ds, datasource_id)
        elif ds.db_type == "postgresql":
            tables_to_insert, columns_to_insert, tables_synced = _build_postgresql_schema_snapshot(ds, datasource_id)
        else:
            tables_to_insert, columns_to_insert, tables_synced = _build_real_schema_snapshot(ds, datasource_id)

        _replace_schema_snapshot(db, datasource_id, tables_to_insert, columns_to_insert)
        now = datetime.now(UTC)
        db.query(DataSource).filter(DataSource.id == datasource_id).update(
            {
                "last_sync_at": now,
                "last_sync_status": "success",
                "last_sync_error": None,
            }
        )
        db.commit()

        enrich_result: dict[str, Any] | None = None
        warnings: list[str] = []
        if ai_enrich:
            # Early check: skip AI enrichment when no LLM API key is available.
            # Mirrors agent.api._check_llm_credentials — key comes from frontend
            # request body (configured in Settings UI), OPENAI_API_KEY as fallback.
            _resolved_key = (ai_api_key or os.getenv("OPENAI_API_KEY", "")).strip()
            if not _resolved_key:
                logger.info("AI enrich skipped for datasource %s: no LLM API key configured", datasource_id)
                enrich_result = {
                    "ai_enriched": False,
                    "enriched_count": 0,
                    "reason": "请先在设置中配置 LLM API Key。",
                }
            else:
                from engine.ai_enrich import ai_enrich_catalog
                try:
                    enrich_result = ai_enrich_catalog(
                        db,
                        datasource_id,
                        api_key=ai_api_key,
                        api_base=ai_api_base,
                        model_name=ai_model_name,
                    )
                except Exception as exc:
                    db.rollback()
                    logger.exception("AI enrich failed for datasource %s: %s", datasource_id, exc)
                    enrich_result = {
                        "ai_enriched": False,
                        "enriched_count": 0,
                        "reason": str(exc),
                    }
            logger.info("AI enrich: %s", enrich_result)
            warning = _ai_enrich_warning(enrich_result)
            if warning:
                warnings.append(warning)

        response: dict[str, Any] = {
            "ok": True,
            "tablesSynced": tables_synced,
            "message": "Schema synchronized successfully.",
        }
        if enrich_result is not None:
            response["aiEnrich"] = enrich_result
        if warnings:
            response["warnings"] = warnings
        return response

    except Exception as e:
        db.rollback()
        now = datetime.now(UTC)
        from engine.policy.error_sanitizer import sanitize_error_message
        db.query(DataSource).filter(DataSource.id == datasource_id).update(
            {
                "last_sync_at": now,
                "last_sync_status": "failed",
                "last_sync_error": sanitize_error_message(str(e)),
            }
        )
        db.commit()
        raise ValueError(f"Schema sync failed: {sanitize_error_message(str(e))}")


def _guess_module_tag(table_name: str) -> str | None:
    return None


def _resolve_inferred_target(col_name: str, table_names: set[str]) -> str | None:
    """Try to match a column name like 'user_id' to an existing table like 'users'."""
    if not col_name.endswith("_id"):
        return None
    base = col_name[:-3]
    candidates = [
        base,
        base + "s",
        base + "es",
        base.rstrip("s") if base.endswith("s") else None,
    ]
    for candidate in candidates:
        if candidate and candidate in table_names:
            return candidate
    return None


def build_er_diagram_data(db: Session, datasource_id: str) -> dict[str, Any]:
    """
    Constructs ER diagram node and link data based on synchronized tables & columns in SQLite.

    Returns nodes with module_tag and edges with edge_type ("real" | "inferred").
    Inferred edges are guessed from column names ending in _id that match a known table.
    """
    tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()

    nodes = []
    edges = []

    table_id_to_name = {str(t.id): str(t.table_name) for t in tables}
    table_name_set = {str(t.table_name) for t in tables}

    # Track which (source, target) pairs already have real FK edges to avoid duplicates
    real_fk_pairs: set[tuple[str, str]] = set()

    for t in tables:
        table_name = str(t.table_name)
        fields = []
        fk_source_cols: list[str] = []

        for col in t.columns:
            column_name = str(col.column_name)
            fields.append(
                {
                    "name": column_name,
                    "type": str(col.column_type or ""),
                    "is_pk": bool(col.is_primary_key),
                    "is_fk": bool(col.is_foreign_key),
                    "comment": str(col.column_comment or ""),
                }
            )

            if col.is_foreign_key and col.foreign_table_id:
                target_table_name = table_id_to_name.get(str(col.foreign_table_id))
                target_col = db.query(SchemaColumn).filter(SchemaColumn.id == col.foreign_column_id).first()
                target_col_name = str(target_col.column_name) if target_col else "id"

                if target_table_name:
                    real_fk_pairs.add((table_name, target_table_name))
                    fk_source_cols.append(column_name)
                    edges.append(
                        {
                            "id": f"fk-{table_name}-{column_name}__to__{target_table_name}-{target_col_name}",
                            "source": table_name,
                            "sourceHandle": column_name,
                            "target": target_table_name,
                            "targetHandle": target_col_name,
                            "label": "FK",
                            "edge_type": "real",
                        }
                    )

        # Inferred FK edges: columns ending in _id, not already real FK, matching a known table
        for col in t.columns:
            column_name = str(col.column_name)
            if col.is_foreign_key and col.foreign_table_id:
                continue  # already handled as real FK
            if not column_name.endswith("_id"):
                continue

            target_table_name = _resolve_inferred_target(column_name, table_name_set)
            if not target_table_name or target_table_name == table_name:
                continue
            if (table_name, target_table_name) in real_fk_pairs:
                continue

            target_table = next((x for x in tables if str(x.table_name) == target_table_name), None)
            target_pk_col = "id"
            if target_table:
                # Prefer an actual PK column name
                for tc in target_table.columns:
                    if tc.is_primary_key:
                        target_pk_col = str(tc.column_name)
                        break

            edge_id = f"inf-{table_name}-{column_name}__to__{target_table_name}-{target_pk_col}"
            if any(e["id"] == edge_id for e in edges):
                continue

            edges.append(
                {
                    "id": edge_id,
                    "source": table_name,
                    "sourceHandle": column_name,
                    "target": target_table_name,
                    "targetHandle": target_pk_col,
                    "label": "推断",
                    "edge_type": "inferred",
                }
            )

        nodes.append(
            {
                "id": table_name,
                "label": table_name,
                "comment": t.table_comment or "",
                "module_tag": _guess_module_tag(table_name),
                "fields": fields,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
    }
