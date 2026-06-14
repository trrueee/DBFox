from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from engine.crypto import decrypt_password
from engine.datasource import build_postgres_ssl_params, get_or_create_tunnel_for_dict
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.schema_sync import _replace_schema_snapshot, sync_schema as _legacy_sync_schema


def sync_schema(db: Session, datasource_id: str) -> dict[str, Any]:
    """Safer schema sync entry point used by the API.

    - SQLite: refuses missing files so sync cannot create an empty database.
    - PostgreSQL: carries datasource SSL settings into the SQLAlchemy/psycopg2 connection.
    - MySQL: delegates to the existing sync implementation.
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    if ds.db_type == "sqlite":
        path = Path(str(ds.database_name or "")).expanduser()
        if not path.is_file():
            raise ValueError(f"SQLite database file does not exist: {path}")
        return _legacy_sync_schema(db, datasource_id)

    if ds.db_type != "postgresql":
        return _legacy_sync_schema(db, datasource_id)

    try:
        tables_to_insert, columns_to_insert, tables_synced = _build_postgresql_schema_snapshot(ds, datasource_id)
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
        return {
            "ok": True,
            "tablesSynced": tables_synced,
            "message": "Schema synchronized successfully.",
        }
    except Exception as exc:
        db.rollback()
        now = datetime.now(UTC)
        db.query(DataSource).filter(DataSource.id == datasource_id).update(
            {
                "last_sync_at": now,
                "last_sync_status": "failed",
                "last_sync_error": str(exc),
            }
        )
        db.commit()
        raise ValueError(f"Schema sync failed: {str(exc)}") from exc


def _build_postgresql_schema_snapshot(
    ds: DataSource,
    datasource_id: str,
) -> tuple[list[SchemaTable], list[SchemaColumn], int]:
    host = str(ds.host)
    port = int(ds.port)
    user = str(ds.username)
    database_name = str(ds.database_name)
    password = decrypt_password(str(ds.password_ciphertext), str(ds.password_nonce))

    if ds.ssh_enabled:
        ds_dict = _ds_connection_dict(ds)
        tunnel = get_or_create_tunnel_for_dict(ds_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    ssl_params = build_postgres_ssl_params(_ds_connection_dict(ds))
    engine = create_engine(
        "postgresql+psycopg2://",
        connect_args={
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database_name,
            "connect_timeout": 5,
            **ssl_params,
        },
    )

    try:
        tables_to_insert: list[SchemaTable] = []
        columns_to_insert: list[SchemaColumn] = []
        table_name_to_id: dict[str, str] = {}
        column_name_to_id: dict[tuple[str, str], str] = {}
        column_objects: dict[tuple[str, str], SchemaColumn] = {}

        inspector = inspect(engine)
        schema = inspector.default_schema_name or "public"
        table_names = inspector.get_table_names(schema=schema)
        view_names = inspector.get_view_names(schema=schema)

        for table_name in table_names + view_names:
            table_id = str(uuid.uuid4())
            table_name_to_id[table_name] = table_id
            tables_to_insert.append(
                SchemaTable(
                    id=table_id,
                    data_source_id=datasource_id,
                    table_schema=schema,
                    table_name=table_name,
                    table_comment=None,
                    table_type="VIEW" if table_name in view_names else "BASE TABLE",
                    row_count_estimate=0,
                    engine_name=None,
                )
            )

        for table_name in table_names + view_names:
            table_id = table_name_to_id[table_name]
            columns = inspector.get_columns(table_name, schema=schema)
            pk_constraint = inspector.get_pk_constraint(table_name, schema=schema)
            pk_columns = pk_constraint.get("constrained_columns", []) or []

            for index, column_info in enumerate(columns):
                column_name = str(column_info["name"])
                column_id = str(uuid.uuid4())
                column_name_to_id[(table_name, column_name)] = column_id
                column = SchemaColumn(
                    id=column_id,
                    table_id=table_id,
                    column_name=column_name,
                    data_type=str(column_info["type"]).lower(),
                    column_type=str(column_info["type"]),
                    is_nullable=bool(column_info.get("nullable", True)),
                    column_default=(
                        str(column_info.get("default"))
                        if column_info.get("default") is not None
                        else None
                    ),
                    column_comment=column_info.get("comment"),
                    is_primary_key=column_name in pk_columns,
                    is_foreign_key=False,
                    ordinal_position=index + 1,
                )
                column_objects[(table_name, column_name)] = column
                columns_to_insert.append(column)

        for table_name in table_names:
            for fk in inspector.get_foreign_keys(table_name, schema=schema):
                constrained_cols = fk.get("constrained_columns", []) or []
                referred_table = fk.get("referred_table")
                referred_cols = fk.get("referred_columns", []) or []
                if not referred_table or not constrained_cols or not referred_cols:
                    continue

                ref_table_id = table_name_to_id.get(str(referred_table))
                if not ref_table_id:
                    continue

                for source_col, referred_col in zip(constrained_cols, referred_cols):
                    fk_column = column_objects.get((table_name, str(source_col)))
                    ref_col_id = column_name_to_id.get((str(referred_table), str(referred_col)))
                    if fk_column and ref_col_id:
                        fk_column.is_foreign_key = True  # type: ignore[assignment]
                        fk_column.foreign_table_id = ref_table_id  # type: ignore[assignment]
                        fk_column.foreign_column_id = ref_col_id  # type: ignore[assignment]

        return tables_to_insert, columns_to_insert, len(tables_to_insert)
    finally:
        engine.dispose()


def _ds_connection_dict(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "host": ds.host,
        "port": ds.port,
        "username": ds.username,
        "database_name": ds.database_name,
        "password_ciphertext": ds.password_ciphertext,
        "password_nonce": ds.password_nonce,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    }
