"""Dedicated SQLite test datasource payloads.

All engine integration tests should use in-memory / tmp SQLite fixtures
instead of mock MySQL demo hosts. Production code must never import this module.
"""
from __future__ import annotations

from typing import Any


def sqlite_datasource_create_payload(
    database_path: str,
    *,
    name: str = "test_sqlite",
    username: str = "test",
    project_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "db_type": "sqlite",
        "host": "localhost",
        "port": 0,
        "database_name": database_path,
        "username": username,
        **extra,
    }
    if project_id is not None:
        payload["project_id"] = project_id
    return payload


def sqlite_connection_test_payload(database_path: str) -> dict[str, Any]:
    return {
        "db_type": "sqlite",
        "host": "localhost",
        "port": 0,
        "database_name": database_path,
        "username": "test",
        "password": "test",
    }
