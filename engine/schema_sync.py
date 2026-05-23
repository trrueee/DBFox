import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from engine.crypto import decrypt_password
from engine.datasource import MOCK_TABLES_INFO, build_mysql_ssl_params, is_demo_db
from engine.models import DataSource, SchemaColumn, SchemaTable

SchemaSnapshot = tuple[list[SchemaTable], list[SchemaColumn], int]


def _build_demo_schema_snapshot(ds: DataSource, datasource_id: str) -> SchemaSnapshot:
    tables_to_insert: list[SchemaTable] = []
    columns_to_insert: list[SchemaColumn] = []
    table_name_to_id: dict[str, str] = {}
    column_name_to_id: dict[tuple[str, str], str] = {}

    for t_info in MOCK_TABLES_INFO:
        table_id = str(uuid.uuid4())
        table_name = str(t_info["table_name"])
        table_name_to_id[table_name] = table_id
        tables_to_insert.append(
            SchemaTable(
                id=table_id,
                data_source_id=datasource_id,
                table_schema=ds.database_name,
                table_name=table_name,
                table_comment=t_info["table_comment"],
                table_type=t_info["table_type"],
                row_count_estimate=t_info["row_count_estimate"],
                engine_name=t_info["engine_name"],
            )
        )

        columns_list = cast(list[dict[str, object]], t_info["columns"])
        for col in columns_list:
            column_name_to_id[(table_name, str(col["column_name"]))] = str(uuid.uuid4())

    for t_info in MOCK_TABLES_INFO:
        table_name = str(t_info["table_name"])
        table_id = table_name_to_id[table_name]
        demo_columns = cast(list[dict[str, object]], t_info["columns"])

        for i, col in enumerate(demo_columns):
            column_name = str(col["column_name"])
            column_id = column_name_to_id[(table_name, column_name)]
            foreign_table_id = None
            foreign_column_id = None

            if col.get("is_foreign_key"):
                foreign_table_name = str(col["foreign_table"])
                foreign_column_name = str(col["foreign_column"])
                foreign_table_id = table_name_to_id.get(foreign_table_name)
                foreign_column_id = column_name_to_id.get((foreign_table_name, foreign_column_name))

            columns_to_insert.append(
                SchemaColumn(
                    id=column_id,
                    table_id=table_id,
                    column_name=column_name,
                    data_type=col["data_type"],
                    column_type=col["column_type"],
                    is_nullable=col["is_nullable"],
                    column_default=None,
                    column_comment=col["column_comment"],
                    is_primary_key=col["is_primary_key"],
                    is_foreign_key=bool(col.get("is_foreign_key", 0)),
                    foreign_table_id=foreign_table_id,
                    foreign_column_id=foreign_column_id,
                    ordinal_position=i + 1,
                )
            )

    return tables_to_insert, columns_to_insert, len(tables_to_insert)


def _build_real_schema_snapshot(ds: DataSource, datasource_id: str) -> SchemaSnapshot:
    host = str(ds.host)
    port = int(ds.port)
    user = str(ds.username)
    database_name = str(ds.database_name)
    password = decrypt_password(str(ds.password_ciphertext), str(ds.password_nonce))

    if ds.ssh_enabled:
        from engine.datasource import get_or_create_tunnel_for_dict

        ds_dict = {
            "id": ds.id,
            "host": ds.host,
            "port": ds.port,
            "username": ds.username,
            "database_name": ds.database_name,
            "ssh_enabled": True,
            "ssh_host": ds.ssh_host,
            "ssh_port": ds.ssh_port,
            "ssh_username": ds.ssh_username,
            "ssh_password_ciphertext": ds.ssh_password_ciphertext,
            "ssh_password_nonce": ds.ssh_password_nonce,
            "ssh_pkey_path": ds.ssh_pkey_path,
            "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
            "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        }
        tunnel = get_or_create_tunnel_for_dict(ds_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    ssl_params = build_mysql_ssl_params(
        {
            "ssl_enabled": ds.ssl_enabled,
            "ssl_ca_path": ds.ssl_ca_path,
            "ssl_cert_path": ds.ssl_cert_path,
            "ssl_key_path": ds.ssl_key_path,
            "ssl_verify_identity": ds.ssl_verify_identity,
        }
    )

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
                
                table_id = table_name_to_id.get(t_name)
                if not table_id:
                    continue
                    
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
                    setattr(fk_column, "is_foreign_key", True)
                    setattr(fk_column, "foreign_table_id", ref_table_id)
                    setattr(fk_column, "foreign_column_id", ref_col_id)

        return tables_to_insert, columns_to_insert, len(tables_to_insert)
    finally:
        engine.dispose()


def _replace_schema_snapshot(
    db: Session,
    datasource_id: str,
    tables_to_insert: list[SchemaTable],
    columns_to_insert: list[SchemaColumn],
) -> None:
    table_ids = [
        row[0]
        for row in db.query(SchemaTable.id).filter(SchemaTable.data_source_id == datasource_id).all()
    ]
    if table_ids:
        db.query(SchemaColumn).filter(SchemaColumn.table_id.in_(table_ids)).delete(synchronize_session=False)
    db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).delete(synchronize_session=False)
    db.add_all(tables_to_insert)
    db.add_all(columns_to_insert)


def sync_schema(db: Session, datasource_id: str) -> dict[str, Any]:
    """
    Synchronize metadata into local SQLite without deleting the previous snapshot
    until the new snapshot has been gathered successfully.
    """
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    try:
        if is_demo_db(str(ds.host), str(ds.database_name)):
            tables_to_insert, columns_to_insert, tables_synced = _build_demo_schema_snapshot(ds, datasource_id)
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

        return {
            "ok": True,
            "tablesSynced": tables_synced,
            "message": "Schema synchronized successfully.",
        }

    except Exception as e:
        db.rollback()
        now = datetime.now(UTC)
        db.query(DataSource).filter(DataSource.id == datasource_id).update(
            {
                "last_sync_at": now,
                "last_sync_status": "failed",
                "last_sync_error": str(e),
            }
        )
        db.commit()
        raise ValueError(f"Schema sync failed: {str(e)}")


def build_er_diagram_data(db: Session, datasource_id: str) -> dict[str, Any]:
    """
    Constructs ER diagram node and link data based on synchronized tables & columns in SQLite
    for rendering with React Flow or simple visualizations.
    """
    tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()

    nodes = []
    edges = []

    table_id_to_name = {t.id: t.table_name for t in tables}

    for t in tables:
        fields = []
        for col in t.columns:
            fields.append(
                {
                    "name": col.column_name,
                    "type": col.column_type,
                    "is_pk": bool(col.is_primary_key),
                    "is_fk": bool(col.is_foreign_key),
                    "comment": col.column_comment,
                }
            )

            if col.is_foreign_key and col.foreign_table_id:
                target_table_name = table_id_to_name.get(col.foreign_table_id)
                target_col = db.query(SchemaColumn).filter(SchemaColumn.id == col.foreign_column_id).first()
                target_col_name = target_col.column_name if target_col else "id"

                if target_table_name:
                    edges.append(
                        {
                            "id": f"fk-{t.table_name}-{col.column_name}__to__{target_table_name}-{target_col_name}",
                            "source": t.table_name,
                            "sourceHandle": col.column_name,
                            "target": target_table_name,
                            "targetHandle": target_col_name,
                            "label": "FK",
                        }
                    )

        nodes.append(
            {
                "id": t.table_name,
                "label": t.table_name,
                "comment": t.table_comment or "",
                "fields": fields,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
    }
