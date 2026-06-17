# executor.py / datasource.py 模块拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `engine/sql/executor.py`（1011 行）和 `engine/datasource.py`（585 行）按职责边界拆分为更小的模块。纯重构，不改外部行为。

**Architecture:** 从 executor.py 提取 5 个新模块（pool_manager / row_serializer / safety_gate / dialect/*），从 datasource.py 提取 1 个新模块（tunnel.py）。原文件通过 re-export 保持所有现有 import 路径兼容。

**Tech Stack:** Python 3.12, SQLAlchemy, PyMySQL, psycopg2, sshtunnel, sqlglot

## Global Constraints

- 所有现有 `from engine.sql.executor import X` 和 `from engine.datasource import X` 调用点不修改
- 所有现有测试不改动（除 import 路径调整外）
- 每个 task 结束后运行对应测试套件，必须全绿
- 每个 task 独立提交

---

### Task 1: 提取 pool_manager.py

**Files:**
- Create: `engine/sql/pool_manager.py`
- Modify: `engine/sql/executor.py`

**Interfaces:**
- Produces: `get_postgres_pool(datasource_id, params) -> QueuePool`, `get_mysql_pool(datasource_id, params) -> QueuePool`, `_ping_mysql_connection(conn_proxy) -> Any`

- [ ] **Step 1: 创建 engine/sql/pool_manager.py**

从 executor.py 第 98-184 行提取 `get_postgres_pool`、`get_mysql_pool`、`_ping_mysql_connection`，并将 pool_registry import 提到文件顶部。

```python
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
```

- [ ] **Step 2: 修改 engine/sql/executor.py**

删除原 L98-184 的 `get_postgres_pool`、`get_mysql_pool`、`_ping_mysql_connection` 函数定义，以及 L100 的 inline import `from engine.sql.pool_registry import get_pool_registry`。

在文件顶部 import 区域添加：

```python
from engine.sql.pool_manager import get_mysql_pool, get_postgres_pool, _ping_mysql_connection
```

同时移除 executor.py 中不再需要的 `from typing import cast`（如果仅 pool_manager 使用的话）和 `import pymysql`（如果仅 pool_manager 使用的话）。检查：`pymysql` 在 mysql dialect executor 中也被引用，所以保留。`cast` 只在 pool 函数中使用，移除。

- [ ] **Step 3: 运行相关测试**

```bash
pytest engine/tests/test_executor.py -v --tb=short
```

- [ ] **Step 4: 验证导入兼容性**

```bash
python -c "from engine.sql.executor import get_postgres_pool, get_mysql_pool, _ping_mysql_connection; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add engine/sql/pool_manager.py engine/sql/executor.py
git commit -m "refactor: extract pool_manager.py from executor.py"
```

---

### Task 2: 提取 row_serializer.py

**Files:**
- Create: `engine/sql/row_serializer.py`
- Modify: `engine/sql/executor.py`

**Interfaces:**
- Produces: `_fetch_and_serialize(cursor, max_rows, *, row_mapper) -> tuple`, `_serialize_value(val) -> str | None`, `_process_rows(raw_rows, columns, ...) -> ProcessedRows`, `MAX_ROWS`, `MAX_COLUMNS`, `MAX_CELL_CHARS`, `MAX_RESPONSE_BYTES`, `QUERY_TIMEOUT_MS`, `ProcessedRows`

- [ ] **Step 1: 创建 engine/sql/row_serializer.py**

从 executor.py 提取 L38-75（常量 + ProcessedRows + _fetch_and_serialize）和 L187-230（_serialize_value + _process_rows）：

```python
from __future__ import annotations

import datetime
import decimal
import json
import time
from typing import Any

MAX_ROWS = 1000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 5000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_MS = 30_000

ProcessedRows = tuple[list[dict[str, Any]], list[str], bool, int]


def _fetch_and_serialize(cursor: Any, max_rows: int = MAX_ROWS, *, row_mapper: Any = None) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int]:
    """Common fetch/serialize logic shared by all database dialects."""
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    truncated = False
    response_bytes = 2
    fetch_ms = 0
    serialize_ms = 0

    if cursor.description:
        columns = [col[0] for col in cursor.description]

        t_fetch_start = time.perf_counter()
        raw_rows = cursor.fetchmany(max_rows)
        if row_mapper:
            raw_rows = [row_mapper(r) for r in raw_rows]
        fetch_ms = int((time.perf_counter() - t_fetch_start) * 1000)

        t_ser_start = time.perf_counter()
        rows, columns, truncated, response_bytes = _process_rows(raw_rows, columns)
        serialize_ms = int((time.perf_counter() - t_ser_start) * 1000)

    return rows, columns, truncated, response_bytes, fetch_ms, serialize_ms


def _serialize_value(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, decimal.Decimal):
        return str(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return "<binary>"
    return str(val)


def _process_rows(
    raw_rows: list[Any],
    columns: list[str],
    max_columns: int = MAX_COLUMNS,
    max_cell_chars: int = MAX_CELL_CHARS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> ProcessedRows:
    """Process raw cursor rows into a list of serialized dicts with limits applied."""
    if len(columns) > max_columns:
        columns = columns[:max_columns]

    rows = []
    response_bytes = 2  # JSON array brackets
    truncated = False

    for r in raw_rows:
        row_dict = {}
        for col in columns:
            val = r[col]
            if isinstance(val, str) and len(val) > max_cell_chars:
                val = val[:max_cell_chars] + "..."
            row_dict[col] = _serialize_value(val)

        row_bytes = len(json.dumps(row_dict, ensure_ascii=False, default=str).encode("utf-8")) + 1
        if response_bytes + row_bytes > max_response_bytes:
            truncated = True
            break

        response_bytes += row_bytes
        rows.append(row_dict)

    return rows, columns, truncated, response_bytes
```

- [ ] **Step 2: 修改 engine/sql/executor.py**

删除 L38-75（常量 + ProcessedRows + _fetch_and_serialize）和 L187-230（_serialize_value + _process_rows）。

在 import 区域添加：

```python
from engine.sql.row_serializer import (
    _fetch_and_serialize, _serialize_value, _process_rows,
    MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS, MAX_RESPONSE_BYTES,
    QUERY_TIMEOUT_MS, ProcessedRows,
)
```

从 executor.py 移除不再需要的 `import decimal`、`import datetime`（检查：datetime 在 _run_approved_query 中未使用，可安全移除）。

- [ ] **Step 3: 运行测试**

```bash
pytest engine/tests/test_executor.py -v --tb=short
```

- [ ] **Step 4: 验证导入兼容**

```bash
python -c "from engine.sql.executor import _serialize_value, _process_rows, MAX_ROWS; print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add engine/sql/row_serializer.py engine/sql/executor.py
git commit -m "refactor: extract row_serializer.py from executor.py"
```

---

### Task 3: 创建 dialect/ 包并提取 SQLite 执行器

**Files:**
- Create: `engine/sql/dialect/__init__.py`
- Create: `engine/sql/dialect/sqlite.py`
- Modify: `engine/sql/executor.py`

**Interfaces:**
- Produces: `_execute_on_sqlite_profiled(safe_sql, timeout_ms, execution_id, datasource_id, sqlite_path) -> tuple`, `_execute_on_sqlite(safe_sql, timeout_ms, execution_id, datasource_id, sqlite_path) -> tuple`

- [ ] **Step 1: 创建 engine/sql/dialect/__init__.py**

空文件：

```python
# dialect package
```

- [ ] **Step 2: 创建 engine/sql/dialect/sqlite.py**

从 executor.py L233-298 提取 `_execute_on_sqlite_profiled` 和 `_execute_on_sqlite`：

```python
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.row_serializer import (
    _fetch_and_serialize,
    QUERY_TIMEOUT_MS,
)

logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_sqlite_profiled(
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    sqlite_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on the SQLite database, returning timing breakdown."""
    db_path = sqlite_path
    if not db_path:
        raise ValueError("SQLite database path is required for query execution")
    
    t_conn_start = time.perf_counter()
    conn = sqlite3.connect(db_path)
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
    
    conn.row_factory = sqlite3.Row
    deadline = time.monotonic() + (timeout_ms / 1000)
    timed_out = False

    def abort_when_timed_out() -> int:
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1
        return 0

    try:
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.set_progress_handler(abort_when_timed_out, 1000)
        if execution_id:
            QUERY_REGISTRY.register_sqlite(execution_id, datasource_id, conn)
        cursor = conn.cursor()
        
        t_exec_start = time.perf_counter()
        try:
            cursor.execute(safe_sql)
        except sqlite3.OperationalError as exc:
            if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                raise SQLQueryCancelledError("SQL query cancelled by user") from exc
            if timed_out:
                raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
            raise
        execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

        rows, columns, truncated, response_bytes, fetch_ms, serialize_ms = _fetch_and_serialize(cursor)
            
        return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn.set_progress_handler(None, 0)
        conn.close()


def _execute_on_sqlite(
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
    sqlite_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_sqlite_profiled(
        safe_sql, timeout_ms, execution_id, datasource_id, sqlite_path
    )
    return rows, columns, truncated, response_bytes
```

- [ ] **Step 3: 修改 engine/sql/executor.py**

删除 L233-298（两个 SQLite 执行器函数）。

在 import 区域添加：

```python
from engine.sql.dialect.sqlite import _execute_on_sqlite, _execute_on_sqlite_profiled
```

从 executor.py 移除不再需要的 `import sqlite3`（检查：explain_sql 也使用 sqlite3，保留）。

- [ ] **Step 4: 运行测试**

```bash
pytest engine/tests/test_executor.py -v --tb=short -k "sqlite"
```

- [ ] **Step 5: 提交**

```bash
git add engine/sql/dialect/__init__.py engine/sql/dialect/sqlite.py engine/sql/executor.py
git commit -m "refactor: extract dialect/sqlite.py from executor.py"
```

---

### Task 4: 提取 dialect/postgres.py

**Files:**
- Create: `engine/sql/dialect/postgres.py`
- Modify: `engine/sql/executor.py`

**Interfaces:**
- Produces: `_execute_on_postgres_profiled(datasource_id, params, safe_sql, timeout_ms, execution_id) -> tuple`

- [ ] **Step 1: 创建 engine/sql/dialect/postgres.py**

从 executor.py L301-353 提取 `_execute_on_postgres_profiled`：

```python
from __future__ import annotations

import logging
import time
from typing import Any

from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.pool_manager import get_postgres_pool
from engine.sql.row_serializer import (
    _fetch_and_serialize,
    QUERY_TIMEOUT_MS,
)

logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_postgres_profiled(
    datasource_id: str,
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on a real PostgreSQL database, returning timing breakdown."""
    t_conn_start = time.perf_counter()
    pool = get_postgres_pool(datasource_id, params)
    conn_proxy: Any = pool.connect()
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
    
    try:
        raw_conn = conn_proxy.connection if hasattr(conn_proxy, "connection") else conn_proxy
        if execution_id:
            QUERY_REGISTRY.register_postgres(
                execution_id,
                datasource_id,
                raw_conn,
            )

        with conn_proxy.cursor() as cursor:
            try:
                cursor.execute(f"SET statement_timeout = {timeout_ms}")
            except Exception as exc:
                logger.warning("Failed to set Postgres statement timeout: %s", exc)

            t_exec_start = time.perf_counter()
            try:
                cursor.execute(safe_sql)
            except Exception as exc:
                if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                    raise SQLQueryCancelledError("SQL query cancelled by user") from exc
                
                pgcode = getattr(exc, "pgcode", None)
                if pgcode == "57014":
                    raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
                raise
            execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

            pg_columns = [col[0] for col in cursor.description] if cursor.description else []
            mapped_rows, columns_raw, truncated, response_bytes, fetch_ms, serialize_ms = _fetch_and_serialize(
                cursor, row_mapper=lambda r, _c=pg_columns: dict(zip(_c, r)) if _c else r,
            )

            return mapped_rows, columns_raw, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn_proxy.close()
```

- [ ] **Step 2: 修改 engine/sql/executor.py**

删除 L301-353（postgres 执行器）。

在 import 区域添加：

```python
from engine.sql.dialect.postgres import _execute_on_postgres_profiled
```

- [ ] **Step 3: 运行测试**

```bash
pytest engine/tests/test_executor.py -v --tb=short
```

- [ ] **Step 4: 提交**

```bash
git add engine/sql/dialect/postgres.py engine/sql/executor.py
git commit -m "refactor: extract dialect/postgres.py from executor.py"
```

---

### Task 5: 提取 dialect/mysql.py

**Files:**
- Create: `engine/sql/dialect/mysql.py`
- Modify: `engine/sql/executor.py`

**Interfaces:**
- Produces: `_execute_on_mysql_profiled(datasource_id, params, safe_sql, timeout_ms, execution_id) -> tuple`, `_execute_on_mysql(params, safe_sql, timeout_ms, execution_id, datasource_id) -> tuple`

- [ ] **Step 1: 创建 engine/sql/dialect/mysql.py**

从 executor.py L356-416 提取 `_execute_on_mysql_profiled` 和 `_execute_on_mysql`：

```python
from __future__ import annotations

import logging
import time
from typing import Any

import pymysql

from engine.errors import SQLQueryCancelledError
from engine.query_registry import QUERY_REGISTRY
from engine.sql.pool_manager import get_mysql_pool, _ping_mysql_connection
from engine.sql.row_serializer import (
    _fetch_and_serialize,
    QUERY_TIMEOUT_MS,
)

logger = logging.getLogger("dbfox.sql.executor")


def _execute_on_mysql_profiled(
    datasource_id: str,
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int, int, int]:
    """Execute a safe SQL query on a real MySQL database via PyMySQL, returning timing breakdown."""
    t_conn_start = time.perf_counter()
    pool = get_mysql_pool(datasource_id, params)
    conn_proxy: Any = pool.connect()
    connect_ms = int((time.perf_counter() - t_conn_start) * 1000)
    
    try:
        raw_conn = _ping_mysql_connection(conn_proxy)
        if execution_id:
            QUERY_REGISTRY.register_mysql(
                execution_id,
                datasource_id,
                params,
                int(raw_conn.thread_id()),
            )

        with conn_proxy.cursor() as cursor:
            try:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (timeout_ms,))
            except Exception as exc:
                logger.warning("Failed to set MySQL MAX_EXECUTION_TIME: %s", exc)

            t_exec_start = time.perf_counter()
            try:
                cursor.execute(safe_sql)
            except pymysql.err.OperationalError as exc:
                code = exc.args[0] if exc.args else None
                if execution_id and QUERY_REGISTRY.is_cancelled(execution_id):
                    raise SQLQueryCancelledError("SQL query cancelled by user") from exc
                if code in {1317, 3024}:
                    raise TimeoutError(f"Query timed out after {timeout_ms} ms") from exc
                raise
            execute_ms = int((time.perf_counter() - t_exec_start) * 1000)

            rows, columns, truncated, response_bytes, fetch_ms, serialize_ms = _fetch_and_serialize(cursor)
                
            return rows, columns, truncated, response_bytes, connect_ms, execute_ms, fetch_ms, serialize_ms
    finally:
        if execution_id:
            QUERY_REGISTRY.unregister(execution_id)
        conn_proxy.close()


def _execute_on_mysql(
    params: dict[str, Any],
    safe_sql: str,
    timeout_ms: int = QUERY_TIMEOUT_MS,
    execution_id: str | None = None,
    datasource_id: str = "",
) -> tuple[list[dict[str, Any]], list[str], bool, int]:
    rows, columns, truncated, response_bytes, _, _, _, _ = _execute_on_mysql_profiled(
        datasource_id, params, safe_sql, timeout_ms, execution_id
    )
    return rows, columns, truncated, response_bytes
```

- [ ] **Step 2: 修改 engine/sql/executor.py**

删除 L356-416（MySQL 执行器）。

在 import 区域添加：

```python
from engine.sql.dialect.mysql import _execute_on_mysql, _execute_on_mysql_profiled
```

从 executor.py 移除不再需要的 `import pymysql`（仅 dialect/mysql.py 使用了）。

- [ ] **Step 3: 运行测试**

```bash
pytest engine/tests/test_executor.py -v --tb=short
```

- [ ] **Step 4: 提交**

```bash
git add engine/sql/dialect/mysql.py engine/sql/executor.py
git commit -m "refactor: extract dialect/mysql.py from executor.py"
```

---

### Task 6: 提取 safety_gate.py

**Files:**
- Create: `engine/sql/safety_gate.py`
- Modify: `engine/sql/executor.py`

**Interfaces:**
- Produces: `guardrail_bypass_allowed() -> bool`, `validate_sql_schema(generated_sql, db, datasource_id) -> list[str]`
- Internal: `_resolve_execution_safety_decision()`, `_decision_checks_for_history()`, `_decision_checks_for_error()`, `_decision_block_message()`, `_is_projection_alias_reference()`

- [ ] **Step 1: 创建 engine/sql/safety_gate.py**

从 executor.py 提取 L79-96（guardrail_bypass_allowed）、L419-510（_resolve_execution_safety_decision）、L513-595（_decision_* 函数）、L931-1011（validate_sql_schema、_is_projection_alias_reference）。

**重要**：此文件内部函数（`_resolve_execution_safety_decision` 等）仍需要被 executor.py 的 `execute_query` 和 `explain_sql` 调用。公开导出 `guardrail_bypass_allowed` 和 `validate_sql_schema`（外部消费），以及所有 `_resolve_*` / `_decision_*` / `_is_projection_alias_reference`（executor.py 内部消费）。

```python
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import sqlglot
from sqlglot import exp
from sqlalchemy.orm import Session

from engine.errors import GuardrailValidationError
from engine.models import DataSource, SchemaTable
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate
from engine.query_registry import QUERY_REGISTRY

logger = logging.getLogger("dbfox.sql.executor")


def guardrail_bypass_allowed() -> bool:
    """Centralized check for guardrail bypass availability.
    
    Requires both DBFOX_TESTING=1 and DBFOX_ALLOW_GUARDRAIL_BYPASS=1.
    Always denied in frozen (packaged) builds.
    """
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        if os.environ.get("DBFOX_TESTING") == "1" or os.environ.get("DBFOX_ALLOW_GUARDRAIL_BYPASS") == "1":
            logger.critical(
                "Guardrail bypass env vars detected in frozen build — ignoring."
            )
        return False
    if os.environ.get("DBFOX_TESTING") != "1":
        return False
    if os.environ.get("DBFOX_ALLOW_GUARDRAIL_BYPASS") != "1":
        return False
    return True


# --- _resolve_execution_safety_decision (原 L419-510) ---
# （完整代码从 executor.py 移动，保持不变）


# --- _decision_checks_for_history (原 L513-549) ---
# --- _decision_checks_for_error (原 L552-560) ---
# --- _decision_block_message (原 L563-595) ---


def validate_sql_schema(generated_sql: str | exp.Expression, db: Session, datasource_id: str) -> list[str]:
    """Check generated SQL for hallucinated tables/columns against local schema cache."""
    # （完整代码从 executor.py L931-1000 移动，保持不变）


def _is_projection_alias_reference(col_node: exp.Column) -> bool:
    # （完整代码从 executor.py L1003-1011 移动，保持不变）
```

- [ ] **Step 2: 修改 engine/sql/executor.py**

删除以下行范围的代码：
- L79-96: `guardrail_bypass_allowed()`
- L419-595: `_resolve_execution_safety_decision`、`_decision_*` 函数
- L931-1011: `validate_sql_schema`、`_is_projection_alias_reference`

在 import 区域添加：

```python
from engine.sql.safety_gate import (
    guardrail_bypass_allowed,
    _resolve_execution_safety_decision,
    _decision_checks_for_history,
    _decision_checks_for_error,
    _decision_block_message,
    validate_sql_schema,
    _is_projection_alias_reference,
)
```

移除 executor.py 中不再需要的 `import os`（检查：仅 guardrail_bypass_allowed 使用了；safety_gate.py 保留）、`import sys`（同上）、`import sqlglot`（检查：仅 validate_sql_schema 使用了，保留给 safety_gate.py）。如果 executor.py 中无其他使用 `os`、`sys`、`sqlglot`，则移除。

- [ ] **Step 3: 运行测试**

```bash
pytest engine/tests/test_executor.py engine/tests/test_trust_gate.py -v --tb=short
```

- [ ] **Step 4: 提交**

```bash
git add engine/sql/safety_gate.py engine/sql/executor.py
git commit -m "refactor: extract safety_gate.py from executor.py"
```

---

### Task 7: executor.py 最终清理

**Files:**
- Modify: `engine/sql/executor.py`

**目标：** 经过 Task 1-6 的提取，executor.py 现在应只剩 `execute_query`、`explain_sql`、`_run_approved_query` 以及 re-export 行。清理冗余 import，确认文件行数 ~200。

- [ ] **Step 1: 清理 executor.py 中不再需要的顶层 import**

删除 Task 1-6 提取后不再需要的 import 语句（`os`、`sys`、`sqlglot`、`pymysql`、`decimal`、`datetime` 等——取决于是否有残留使用）。

保留的 import 应为：

```python
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from engine.datasource import (
    datasource_connection_dict,
    get_mysql_connection_params,
    get_postgres_connection_params,
)
from engine.errors import (
    GuardrailValidationError,
    SQLExecutionError,
    SQLQueryCancelledError,
    SQLQueryTimeoutError,
)
from engine.models import DataSource, QueryHistory
from engine.policy.redactor import DataRedactor
from engine.query_registry import QUERY_REGISTRY
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate

# Re-exports from extracted modules (backward compatibility)
from engine.sql.pool_manager import get_mysql_pool, get_postgres_pool, _ping_mysql_connection
from engine.sql.row_serializer import (
    _fetch_and_serialize, _serialize_value, _process_rows,
    MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS, MAX_RESPONSE_BYTES,
    QUERY_TIMEOUT_MS, ProcessedRows,
)
from engine.sql.dialect.sqlite import _execute_on_sqlite, _execute_on_sqlite_profiled
from engine.sql.dialect.postgres import _execute_on_postgres_profiled
from engine.sql.dialect.mysql import _execute_on_mysql, _execute_on_mysql_profiled
from engine.sql.safety_gate import (
    guardrail_bypass_allowed,
    _resolve_execution_safety_decision,
    _decision_checks_for_history,
    _decision_checks_for_error,
    _decision_block_message,
    validate_sql_schema,
    _is_projection_alias_reference,
)

logger = logging.getLogger("dbfox.sql.executor")

# --- _run_approved_query (原 L598-742) ---
# --- execute_query (原 L745-820) ---
# --- explain_sql (原 L823-928) ---
```

- [ ] **Step 2: 确认 executor.py 中 execute_query、explain_sql 等工作函数逻辑未变**

代码只删除、不修改任何函数体。确认 `_run_approved_query` 中的 `QUERY_TIMEOUT_MS` 和 `_execute_on_*_profiled` 引用通过 re-export 仍可解析。

- [ ] **Step 3: 运行全部相关测试**

```bash
pytest engine/tests/test_executor.py engine/tests/test_trust_gate.py engine/tests/test_agent_api.py -v --tb=short
```

- [ ] **Step 4: 验证全部外部 import 点兼容**

```bash
python -c "
from engine.sql.executor import execute_query, explain_sql, validate_sql_schema
from engine.sql.executor import get_postgres_pool, get_mysql_pool, _ping_mysql_connection
from engine.sql.executor import _serialize_value, _process_rows, MAX_ROWS
from engine.sql.executor import _execute_on_sqlite, _execute_on_mysql
from engine.sql.executor import guardrail_bypass_allowed
print('All imports OK')
"
```

- [ ] **Step 5: 提交**

```bash
git add engine/sql/executor.py
git commit -m "refactor: clean up executor.py after module extraction"
```

---

### Task 8: 提取 tunnel.py

**Files:**
- Create: `engine/tunnel.py`
- Modify: `engine/datasource.py`

**Interfaces:**
- Produces: `TUNNEL_MANAGER`, `close_active_tunnel(datasource_id)`, `close_all_tunnels()`, `get_or_create_tunnel_for_dict(ds_dict) -> SSHTunnelForwarder`, `open_temporary_tunnel(config) -> SSHTunnelForwarder`

- [ ] **Step 1: 创建 engine/tunnel.py**

从 datasource.py L1-222 提取所有 Tunnel 相关代码：

```python
from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path
from typing import Any

import pymysql
from sshtunnel import SSHTunnelForwarder

from engine.crypto import decrypt_password
from engine.errors import DataSourceConnectionError

logger = logging.getLogger("dbfox.tunnel")


class TunnelState:
    CONNECTED = "connected"
    STALE = "stale"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSED = "closed"


class TunnelInstance:
    datasource_id: str
    ds_dict: dict[str, Any]
    tunnel: SSHTunnelForwarder
    state: str
    error_message: str | None

    def __init__(self, datasource_id: str, ds_dict: dict[str, Any], tunnel: SSHTunnelForwarder) -> None:
        self.datasource_id = datasource_id
        self.ds_dict = ds_dict
        self.tunnel = tunnel
        self.state = TunnelState.CONNECTED
        self.error_message = None


# --- _create_physical_tunnel_forwarder (原 L40-78) ---
# --- open_temporary_tunnel (原 L81-83) ---
# --- TunnelManager (原 L86-205) ---


TUNNEL_MANAGER = TunnelManager()


def close_active_tunnel(datasource_id: str) -> None:
    """Close active SSH tunnel for a data source if it exists."""
    TUNNEL_MANAGER.close_tunnel(datasource_id)


def close_all_tunnels() -> None:
    """Close all active SSH tunnels on app shutdown."""
    TUNNEL_MANAGER.close_all()


def get_or_create_tunnel_for_dict(ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
    """Get or start an SSH tunnel with deep health probes and auto-reconnects."""
    return TUNNEL_MANAGER.get_or_reconnect(ds_dict)
```

**注意**：`_create_physical_tunnel_forwarder`、`open_temporary_tunnel`、`TunnelManager` 完整代码从 datasource.py 移动，逻辑一字不改。

- [ ] **Step 2: 修改 engine/datasource.py**

删除 L1-222（除 `_normalized_optional_path` 外所有 Tunnel 相关代码）。保留的 import 区域加入：

```python
from engine.tunnel import (
    TUNNEL_MANAGER,
    close_active_tunnel,
    close_all_tunnels,
    get_or_create_tunnel_for_dict,
    open_temporary_tunnel,
)
```

移除 datasource.py 中不再需要的 `import threading`、`import socket`、`from sshtunnel import SSHTunnelForwarder`（全部移到了 tunnel.py）。`pymysql` 保留（`get_mysql_connection_params` 仍需要）。

- [ ] **Step 3: 运行相关测试**

```bash
pytest engine/tests/test_datasource_safety.py engine/tests/test_datasource_ssl.py -v --tb=short
```

- [ ] **Step 4: 提交**

```bash
git add engine/tunnel.py engine/datasource.py
git commit -m "refactor: extract tunnel.py from datasource.py"
```

---

### Task 9: datasource.py 最终清理

**Files:**
- Modify: `engine/datasource.py`

**目标：** 经过 Task 8 提取，datasource.py 应只剩 connection params、SSL builders、test_connection、datasource_connection_dict。清理冗余 import，确认行数 ~355。

- [ ] **Step 1: 清理 datasource.py 中不再需要的 import**

删除 `import socket`、`import threading`、`from pathlib import Path`（如果仅 tunnel 使用）、`from sshtunnel import SSHTunnelForwarder`。

保留的 import：

```python
from __future__ import annotations

import logging
from typing import Any

import pymysql

from engine.crypto import decrypt_password
from engine.errors import DataSourceConnectionError
from engine.tunnel import (
    TUNNEL_MANAGER,
    close_active_tunnel,
    close_all_tunnels,
    get_or_create_tunnel_for_dict,
    open_temporary_tunnel,
)

logger = logging.getLogger("dbfox.tunnel")


# --- _normalized_optional_path (原 L225-229) ---
# --- _require_existing_sqlite_file (原 L232-239) ---
# --- build_mysql_ssl_params (原 L242-265) ---
# --- build_postgres_ssl_params (原 L268-290) ---
# --- get_mysql_connection_params (原 L293-317) ---
# --- get_postgres_connection_params (原 L320-339) ---
# --- test_connection (原 L342-554) ---
# --- datasource_connection_dict (原 L557-585) ---
```

- [ ] **Step 2: 验证外部 import 兼容**

```bash
python -c "
from engine.datasource import TUNNEL_MANAGER, close_active_tunnel, close_all_tunnels, get_or_create_tunnel_for_dict, open_temporary_tunnel
from engine.datasource import datasource_connection_dict, get_mysql_connection_params, get_postgres_connection_params
from engine.datasource import build_mysql_ssl_params, build_postgres_ssl_params, test_connection
print('All datasource imports OK')
"
```

- [ ] **Step 3: 运行全部数据源测试**

```bash
pytest engine/tests/test_datasource_safety.py engine/tests/test_datasource_ssl.py engine/tests/test_datasource_ssl_e2e.py -v --tb=short
```

- [ ] **Step 4: 提交**

```bash
git add engine/datasource.py
git commit -m "refactor: clean up datasource.py after tunnel extraction"
```

---

### Task 10: 全量回归测试

**Files:** 无新建/修改

- [ ] **Step 1: 运行 engine 全量测试**

```bash
pytest engine/tests/ -v --tb=short
```

- [ ] **Step 2: 确认所有测试通过，无 import 警告**

```bash
python -W all -c "
from engine.sql.executor import *
from engine.datasource import *
print('All imports clean')
"
```

- [ ] **Step 3: 验证 engine 可正常启动**

```bash
python -c "from engine.main import app; print('App created OK')"
```

- [ ] **Step 4: 提交（如有剩余变更）**

```bash
git status
# 如有未提交变更则 add + commit
```

---

## 文件变更总览

| 操作 | 文件 | 预计行数 |
|------|------|---------|
| CREATE | `engine/sql/pool_manager.py` | ~120 |
| CREATE | `engine/sql/row_serializer.py` | ~100 |
| CREATE | `engine/sql/safety_gate.py` | ~320 |
| CREATE | `engine/sql/dialect/__init__.py` | 1 |
| CREATE | `engine/sql/dialect/sqlite.py` | ~60 |
| CREATE | `engine/sql/dialect/postgres.py` | ~60 |
| CREATE | `engine/sql/dialect/mysql.py` | ~55 |
| CREATE | `engine/tunnel.py` | ~230 |
| MODIFY | `engine/sql/executor.py` | 1011 → ~200 |
| MODIFY | `engine/datasource.py` | 585 → ~355 |
