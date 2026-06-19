import uuid
from typing import Any

from engine.environment.schema_introspector import SchemaIntrospector
from engine.models import DataSource


def test_decrypt_datasource_password_does_not_query_sqlalchemy_bind(db_session):
    ds = DataSource(
        id=str(uuid.uuid4()),
        name="mysql probe",
        db_type="mysql",
        host="127.0.0.1",
        port=3306,
        database_name="creatorhub",
        username="root",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    password = SchemaIntrospector()._decrypt_datasource_password(db_session, ds.id)

    assert password == ""


class _FakeCursor:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.rows: list[tuple[Any, ...]] = []
        self.description: list[tuple[str]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        query = " ".join(sql.lower().split())
        self.description = []

        if "information_schema.tables" in query:
            if self.dialect == "postgres":
                self.rows = [("public", "orders", "BASE TABLE", "orders table", 42)]
            else:
                self.rows = [("main", "orders", "BASE TABLE", "orders table")]
            return

        if "information_schema.columns" in query:
            if self.dialect == "postgres":
                self.rows = [
                    ("id", "integer", "integer", "NO", None, True, False, "id comment"),
                    ("customer_id", "integer", "integer", "YES", None, False, True, "cust comment"),
                ]
            else:
                self.rows = [
                    ("id", "integer", "integer", "NO", None, True, False),
                    ("customer_id", "integer", "integer", "YES", None, False, True),
                ]
            return

        if "table_constraints" in query and "primary key" in query:
            self.rows = [("id",)]
            return

        if "key_column_usage" in query:
            self.rows = [("customer_id", "customers", "id")]
            return

        if "select count(*)" in query:
            self.rows = [(2,)]
            return

        if "select * from" in query:
            self.description = [("id",), ("customer_id",)]
            self.rows = [(1, 10), (2, 11)]
            return

        self.rows = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None


class _FakeConnection:
    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.dialect)

    def close(self) -> None:
        self.closed = True


def _add_datasource(db_session, db_type: str) -> DataSource:
    ds = DataSource(
        id=str(uuid.uuid4()),
        name=f"{db_type} probe",
        db_type=db_type,
        host="127.0.0.1",
        port=5432 if db_type == "postgres" else 0,
        database_name="analytics",
        username="dbfox",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()
    return ds


def test_postgres_introspection_returns_tables_columns_fks_and_samples(db_session, monkeypatch):
    ds = _add_datasource(db_session, "postgres")
    fake_conn = _FakeConnection("postgres")
    introspector = SchemaIntrospector()
    monkeypatch.setattr(
        introspector,
        "_connect_postgres",
        lambda db, resolved, tunnel=None: fake_conn,
        raising=False,
    )

    inventory = introspector.inspect(db_session, ds.id)

    assert fake_conn.closed is True
    assert inventory.dialect == "postgres"
    assert inventory.database_name == "analytics"
    assert inventory.table_count == 1
    assert inventory.column_count == 2
    table = inventory.tables[0]
    assert table.table_schema == "public"
    assert table.table_name == "orders"
    assert table.table_type == "table"
    assert table.comment == "orders table"
    assert table.row_count_estimate == 42
    assert table.columns[0].column_name == "id"
    assert table.columns[0].is_primary_key is True
    assert table.columns[1].is_foreign_key is True
    assert table.foreign_keys[0].column_name == "customer_id"
    assert table.foreign_keys[0].referenced_table == "customers"
    assert table.sample_rows == [{"id": 1, "customer_id": 10}, {"id": 2, "customer_id": 11}]


def test_duckdb_introspection_returns_tables_columns_fks_and_samples(db_session, monkeypatch):
    ds = _add_datasource(db_session, "duckdb")
    fake_conn = _FakeConnection("duckdb")
    introspector = SchemaIntrospector()
    monkeypatch.setattr(
        introspector,
        "_connect_duckdb",
        lambda resolved: fake_conn,
        raising=False,
    )

    inventory = introspector.inspect(db_session, ds.id)

    assert fake_conn.closed is True
    assert inventory.dialect == "duckdb"
    assert inventory.database_name == "analytics"
    assert inventory.table_count == 1
    assert inventory.column_count == 2
    table = inventory.tables[0]
    assert table.table_schema == "main"
    assert table.table_name == "orders"
    assert table.row_count_estimate == 2
    assert table.columns[0].is_primary_key is True
    assert table.columns[1].is_foreign_key is True
    assert table.foreign_keys[0].referenced_column == "id"
    assert table.sample_rows == [{"id": 1, "customer_id": 10}, {"id": 2, "customer_id": 11}]
