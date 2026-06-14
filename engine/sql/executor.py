from __future__ import annotations

import datetime
import decimal
import json
import logging
import os
import sqlite3
import time
import uuid
from typing import Any

import pymysql
import sqlglot
from sqlglot import exp
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from engine.datasource import get_mysql_connection_params, get_postgres_connection_params
from engine.errors import (
    GuardrailValidationError,
    SQLExecutionError,
    SQLQueryCancelledError,
    SQLQueryTimeoutError,
)
from engine.models import DataSource, QueryHistory, SchemaTable
from engine.policy.redactor import DataRedactor
from engine.query_registry import QUERY_REGISTRY
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate

logger = logging.getLogger("databox.sql.executor")

MAX_ROWS = 1000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 5000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_MS = 30_000

ProcessedRows = tuple[list[dict[str, Any]], list[str], bool, int]

# Dynamic registry of pools mapped by database cache keys to support auto-updating of ports/credentials
_MYSQL_POOLS: dict[tuple[Any, ...], QueuePool] = {}
_POSTGRES_POOLS: dict[tuple[Any, ...], QueuePool] = {}


def get_postgres_pool(datasource_id: str, params: dict[str, Any]) -> QueuePool:
    """Create or retrieve a PostgreSQL connection pool for these exact connection settings."""
    pool_params = params.copy()
    pool_key = (
        datasource_id,
        pool_params.get("host"),
        pool_params.get("port"),
        pool_params.get("user"),
        pool_params.get("database"),
        pool_params.get("sslmode"),
        pool_params.get("sslrootcert"),
        pool_params.get("sslcert"),
        pool_params.get("sslkey"),
    )
    if pool_key not in _POSTGRES_POOLS:
        def creator() -> Any:
            import psycopg2
            return psycopg2.connect(**pool_params, connect_timeout=5)
        from typing import cast
        _POSTGRES_POOLS[pool_key] = QueuePool(
            cast(Any, creator),
            pool_size=5,
            max_overflow=10,
            recycle=1800,
        )
    return _POSTGRES_POOLS[pool_key]


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
    
    if pool_key not in _MYSQL_POOLS:
        def creator() -> pymysql.Connection:
            return pymysql.connect(**pool_params)
            
        from typing import cast
        _MYSQL_POOLS[pool_key] = QueuePool(
            cast(Any, creator),
            pool_size=5,
            max_overflow=10,
            recycle=1800,
        )
    return _MYSQL_POOLS[pool_key]


# Rest of file preserved by GitHub update is not supported here.
