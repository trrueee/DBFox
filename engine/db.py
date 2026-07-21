# -*- coding: utf-8 -*-
"""
DBFox 数据库连接与迁移管理模块 (Database Connection & Migration Manager)
------------------------------------------------------------------------
这个模块负责：
1. 配置和初始化 DBFox 本地 SQLite 元数据库。
2. 建立与配置 SQLAlchemy ORM 引擎与会话工厂。
3. 实现连接获取的生成器函数（供 FastAPI 依赖注入使用）。
4. 在服务启动时，安全地执行数据库版本控制与结构平滑迁移（兼容老版本的手写 SQL 迁移并过渡到 Alembic 管理）。
"""

import contextvars
import logging
import os
import sys
import threading
import traceback
from pathlib import Path

logger = logging.getLogger("dbfox.db")

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from alembic.config import Config

from engine.app.safe_errors import diagnostic_fingerprint
from engine.runtime_paths import PROJECT_DIR, private_runtime_dir, private_runtime_root

# 1. 动态持久化路径解析
# 环境变量 DBFOX_DATABASE_URL 允许 eval farm 隔离每个 worker 的 SQLite DB
_env_db_url = os.environ.get("DBFOX_DATABASE_URL", "")
if _env_db_url:
    DATABASE_URL = _env_db_url
else:
    # Source and packaged modes deliberately share the same private runtime
    # layout.  A repository checkout is never a metadata-data directory.
    DB_PATH = private_runtime_dir("data") / "dbfox_local.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"

# Keep the resolved metadata path available for lifecycle reset and isolated tests.
if "DB_PATH" not in dir():
    DB_PATH = Path(DATABASE_URL.replace("sqlite:///", ""))

# This is the exact pre-Foundation source-mode location.  It is retired only
# after a successful reset of the new private runtime; no arbitrary URL is
# used as a deletion target.
LEGACY_SOURCE_METADATA_PATH = PROJECT_DIR / "dbfox_local.db"
LEGACY_SOURCE_RUNTIME_ROOT = LEGACY_SOURCE_METADATA_PATH.parent

# Connection pool safety defaults. They intentionally mirror the retryable error
# semantics used by Agent tool execution: stale connections should be detected
# before use, long-lived pooled connections should be recycled, and pool waits
# should fail fast enough for the Agent loop to classify and retry.
DB_POOL_SIZE = int(os.environ.get("DBFOX_DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.environ.get("DBFOX_DB_MAX_OVERFLOW", "20"))
DB_POOL_RECYCLE_SECONDS = int(os.environ.get("DBFOX_DB_POOL_RECYCLE_SECONDS", "1800"))
DB_POOL_TIMEOUT_SECONDS = int(os.environ.get("DBFOX_DB_POOL_TIMEOUT_SECONDS", "30"))
DB_SQLITE_TIMEOUT_SECONDS = float(os.environ.get("DBFOX_SQLITE_TIMEOUT_SECONDS", "30"))


def _agent_write_trace_path(timestamp: str) -> Path:
    """Keep opt-in write diagnostics inside the private runtime boundary."""
    return private_runtime_dir("diagnostics") / f"db_write_trace_{timestamp}.jsonl"


def _trace_error_diagnostic(exc: BaseException) -> dict[str, str]:
    """Represent a database error without persisting its potentially sensitive text."""
    return {
        "error_type": type(exc).__name__,
        "error_fingerprint": diagnostic_fingerprint(exc),
    }

def configure_sqlite_pragmas(database_url: str | None = None) -> None:
    """Apply WAL / busy_timeout / synchronous PRAGMAs for SQLite databases.

    Safe to call multiple times; no-op for non-SQLite URLs.
    Must be called before Alembic inspection in the metadata initializer.
    """
    import sqlite3 as _sqlite3
    url = database_url or DATABASE_URL
    if not url.startswith("sqlite:///"):
        return
    db_path = Path(url.replace("sqlite:///", ""))
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(DB_SQLITE_TIMEOUT_SECONDS * 1000)}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA secure_delete=ON")
    finally:
        conn.close()


def build_metadata_engine(database_url: str) -> Engine:
    """Build an engine for DBFox metadata, including SQLite safety PRAGMAs.

    Alembic and runtime code must use the same connection contract.  SQLite
    enforces foreign keys per connection, so the listener belongs on each
    engine instance rather than only on the module-global runtime engine.
    """
    engine_kwargs: dict[str, object] = {
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_pre_ping": True,
        "pool_recycle": DB_POOL_RECYCLE_SECONDS,
        "pool_timeout": DB_POOL_TIMEOUT_SECONDS,
    }
    if database_url.startswith("sqlite:"):
        engine_kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": DB_SQLITE_TIMEOUT_SECONDS,
        }

    metadata_engine = create_engine(database_url, **engine_kwargs)
    if metadata_engine.dialect.name == "sqlite":
        from sqlalchemy import event as _sa_event

        @_sa_event.listens_for(metadata_engine, "connect")
        def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute(f"PRAGMA busy_timeout={int(DB_SQLITE_TIMEOUT_SECONDS * 1000)}")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA secure_delete=ON")
            finally:
                cursor.close()

    return metadata_engine


engine: Engine = build_metadata_engine(DATABASE_URL)

# ---------------------------------------------------------------------------
# DB write tracing (for diagnosing concurrent eval SQLite lock issues)
# Set AGENT_DB_WRITE_TRACE=true to log all INSERT/UPDATE/DELETE to JSONL
# ---------------------------------------------------------------------------
current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_run_id", default="")
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_id", default="")

if os.environ.get("AGENT_DB_WRITE_TRACE", "").lower() == "true":
    _trace_file = None
    _trace_lock = threading.Lock()
    import sys as _sys
    print("DB_WRITE_TRACE: tracing enabled", file=_sys.stderr, flush=True)

    def _open_trace():
        global _trace_file
        if _trace_file is None:
            import time as _t_time
            _ts = _t_time.strftime("%Y%m%d_%H%M%S")
            _trace_file = open(str(_agent_write_trace_path(_ts)), "a", encoding="utf-8")

    from sqlalchemy import event as _ev3
    @_ev3.listens_for(engine, "before_cursor_execute")
    def _trace_before(conn, cursor, statement, parameters, context, executemany):
        stmt_type = statement.strip().upper().split()[0] if statement.strip() else "?"
        if stmt_type in ("INSERT", "UPDATE", "DELETE"):
            _open_trace()
            import json as _json
            # Extract table name
            table = "?"
            for word in statement.strip().upper().split():
                if word == "INTO" or word == "FROM":
                    continue
                if word not in ("INSERT", "UPDATE", "DELETE", "OR", "ROLLBACK", "SET", "VALUES", "WHERE", "AND", "INTO"):
                    table = word.lower().rstrip("(")
                    break
            stacks = []
            for frame in traceback.extract_stack(limit=12)[:-2]:
                stacks.append(f"{frame.filename.split(chr(92))[-1]}:{frame.lineno} {frame.name}")
            rec = {
                "type": stmt_type, "table": table, "thread": threading.current_thread().name,
                "run_id": current_run_id.get(), "session_id": current_session_id.get(),
                "stack": stacks[-6:],
            }
            with _trace_lock:
                _trace_file.write(_json.dumps(rec, default=str) + "\n")
                _trace_file.flush()

    @_ev3.listens_for(engine, "handle_error")
    def _trace_error(context):
        exc = context.original_exception
        if exc and "database is locked" in str(exc).lower():
            _open_trace()
            import json as _json
            rec = {
                "type": "ERROR", "table": "?",
                "thread": threading.current_thread().name,
                "run_id": current_run_id.get(), "session_id": current_session_id.get(),
            }
            rec.update(_trace_error_diagnostic(exc))
            with _trace_lock:
                _trace_file.write(_json.dumps(rec, default=str) + "\n")
                _trace_file.flush()

# 创建本地数据库会话工厂 (Session Factory)
# autocommit=False: 开启事务管理，所有写操作必须显式调用 commit() 才会保存，防止数据写一半出错导致脏数据。
# autoflush=False: 关闭自动刷新，提升性能，避免频繁往数据库发送临时数据。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建声明式 ORM 模型基类 (Declarative Base)
# 项目中所有的实体模型类（如 User, DataSource, BackupRecord 等）都必须继承自这个 Base 基类，
# 这样 SQLAlchemy 才能识别并将它们映射到实际的数据库表中。
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话连接 (Database Session Generator)
    
    FastAPI 极其经典的依赖注入管道方法：
    Python ：
      - `Generator[Session, None, None]`：类型注解，表示这是一个生成器，产生（yield）Session 对象，不接收输入，也没有最终返回值。
      - `yield` 关键字：在此处会暂停执行，将创建好的 `db` 会话交给 FastAPI 具体的 API 接口使用。
      - `finally` 块：无论接口执行成功还是中途抛出任何崩溃异常，FastAPI 结束请求时都会再次回到这里，
        执行 `db.close()`，确保连接绝对被关闭释放，从而彻底杜绝了数据库连接泄露（Connection Leak）的致命隐患！
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_alembic_config(database_url: str) -> "Config":
    """Build an explicit Alembic configuration for one metadata URL."""
    from alembic.config import Config

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        ini_path = bundle_root / "alembic.ini"
        script_location = bundle_root / "engine" / "migrations"
    else:
        ini_path = PROJECT_DIR / "alembic.ini"
        script_location = PROJECT_DIR / "engine" / "migrations"
    if not ini_path.is_file() or not script_location.is_dir():
        raise RuntimeError("DBFOX_METADATA_ALEMBIC_CONFIGURATION_MISSING")

    config = Config(str(ini_path))
    config.set_main_option("script_location", str(script_location))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_alembic_upgrade(database_url: str) -> None:
    """Run the sole schema authority for a metadata database."""
    from alembic import command

    configure_sqlite_pragmas(database_url)
    # Release the process-global runtime pool before Alembic takes its SQLite
    # mutex/snapshot lock.  Alembic owns recovery, not this caller.
    if database_url == DATABASE_URL:
        engine.dispose()
    command.upgrade(build_alembic_config(database_url), "head")


def verify_metadata_database(database_url: str) -> None:
    """Verify the migrated revision, FTS contract, and SQLite FK integrity."""
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    config = build_alembic_config(database_url)
    expected_revision = ScriptDirectory.from_config(config).get_current_head()
    metadata_engine = build_metadata_engine(database_url)
    try:
        with metadata_engine.connect() as connection:
            actual_revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
            if actual_revision != expected_revision:
                raise RuntimeError("DBFOX_METADATA_REVISION_MISMATCH")

            if connection.dialect.name == "sqlite":
                objects = {
                    str(row[0])
                    for row in connection.execute(
                        text("SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')")
                    )
                }
                required_objects = {
                    "schema_search_fts",
                    "query_history_fts",
                    "query_history_search_docs_ai",
                    "query_history_search_docs_ad",
                    "query_history_search_docs_au",
                }
                if not required_objects.issubset(objects):
                    raise RuntimeError("DBFOX_METADATA_FTS_CONTRACT_MISSING")
                if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("DBFOX_METADATA_FOREIGN_KEY_VIOLATION")
    finally:
        metadata_engine.dispose()


def initialize_metadata_database() -> None:
    """Initialize the private metadata runtime through Alembic and reset only.

    There is deliberately no ORM ``create_all``, table-name inference, schema
    stamp, or ad-hoc recovery path here.  Migrations own schema evolution;
    the versioned reset owns destructive retirement of legacy runtime state.
    """
    run_alembic_upgrade(DATABASE_URL)
    verify_metadata_database(DATABASE_URL)

    from engine.security.runtime_reset import (
        reset_legacy_runtime_state,
        retire_legacy_project_runtime_dir,
        retire_legacy_source_runtime,
    )

    runtime_root = private_runtime_root()
    reset_legacy_runtime_state(DATABASE_URL, runtime_root)
    verify_metadata_database(DATABASE_URL)

    # A prior source-mode release stored metadata/checkpoints in the repository
    # root.  After the new private runtime is healthy, retire exactly that
    # known artifact family and nothing inferred from a database record.
    if not _env_db_url and LEGACY_SOURCE_METADATA_PATH != DB_PATH:
        retire_legacy_source_runtime(LEGACY_SOURCE_RUNTIME_ROOT)
        retire_legacy_project_runtime_dir(runtime_root)
