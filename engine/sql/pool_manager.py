from __future__ import annotations

import logging
from typing import Any, cast

import pymysql
from sqlalchemy.pool import QueuePool

from engine.sql.pool_registry import get_pool_registry

logger = logging.getLogger("dbfox.sql.executor")


def get_postgres_pool(datasource_id: str, params: dict[str, Any]) -> QueuePool:
    """Creates or retrieves a connection pool for the datasource with requested timeout properties."""
    pool_params = params.copy()
    # Normalise pool key so that SSL / SSH changes produce a new pool
    pool_key = (
        datasource_id,
        pool_params.get("host"),
        pool_params.get("port"),
        pool_params.get("user"),
        pool_params.get("database"),
        pool_params.get("sslmode", ""),
        pool_params.get("sslrootcert", ""),
        pool_params.get("sslcert", ""),
        pool_params.get("sslkey", ""),
    )

    registry = get_pool_registry()
    if registry.has(pool_key):
        return cast(QueuePool, registry.get_or_create(pool_key, lambda: None))

    def creator() -> Any:
        import psycopg2
        connect_kwargs: dict[str, Any] = {
            "host": pool_params.get("host"),
            "port": pool_params.get("port"),
            "user": pool_params.get("user"),
            "password": pool_params.get("password"),
            "database": pool_params.get("database"),
            "connect_timeout": 5,
        }
        for ssl_key in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
            val = pool_params.get(ssl_key)
            if val:
                connect_kwargs[ssl_key] = val
        return psycopg2.connect(**connect_kwargs)

    return registry.get_or_create(
        pool_key, cast(Any, creator), pool_size=5, max_overflow=10, recycle=1800,
    )


def get_mysql_pool(datasource_id: str, params: dict[str, Any]) -> QueuePool:
    """Creates or retrieves a connection pool for the datasource with requested timeout properties."""
    pool_params = params.copy()
    pool_params["connect_timeout"] = 5
    pool_params["read_timeout"] = 30
    pool_params["write_timeout"] = 30

    pool_key = (
        datasource_id,
        pool_params.get("host"),
        pool_params.get("port"),
        pool_params.get("user"),
        pool_params.get("database"),
        pool_params.get("ssl_ca"),
        pool_params.get("ssl_cert")
    )

    registry = get_pool_registry()
    if registry.has(pool_key):
        return cast(QueuePool, registry.get_or_create(pool_key, lambda: None))

    def creator() -> pymysql.Connection:
        return pymysql.connect(**pool_params)

    return registry.get_or_create(
        pool_key, cast(Any, creator), pool_size=5, max_overflow=10, recycle=1800,
    )


def _ping_mysql_connection(conn_proxy: Any) -> Any:
    """Validate a raw PyMySQL connection checked out from QueuePool."""
    raw_conn: Any = getattr(conn_proxy, "dbapi_connection", None) or getattr(conn_proxy, "connection", None) or conn_proxy
    try:
        raw_conn.ping(reconnect=True)
    except TypeError:
        raw_conn.ping(True)
    return raw_conn
