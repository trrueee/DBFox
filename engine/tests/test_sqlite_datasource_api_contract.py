from __future__ import annotations

import sqlite3

from engine.models import DataSource


def test_sqlite_datasource_can_omit_network_only_fields(
    client,
    db_session,
    tmp_path,
) -> None:
    source_path = tmp_path / "source.sqlite"
    with sqlite3.connect(source_path) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")

    response = client.post(
        "/api/v1/datasources",
        json={
            "name": "SQLite without network coordinates",
            "db_type": "sqlite",
            "database_name": str(source_path),
            "is_read_only": True,
            "env": "test",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["host"] is None
    assert payload["port"] is None
    assert payload["username"] is None
    datasource = db_session.get(DataSource, payload["id"])
    assert datasource is not None
    assert datasource.host is None
    assert datasource.port is None
    assert datasource.username is None
