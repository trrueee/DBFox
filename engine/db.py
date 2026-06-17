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
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from typing import Generator

# 1. 动态持久化路径解析
# 环境变量 DBFOX_DATABASE_URL 允许 eval farm 隔离每个 worker 的 SQLite DB
_env_db_url = os.environ.get("DBFOX_DATABASE_URL", "")
if _env_db_url:
    DATABASE_URL = _env_db_url
else:
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        from engine.runtime_paths import private_runtime_dir
        DB_PATH = private_runtime_dir("data") / "dbfox_local.db"
    else:
        DB_PATH = Path(__file__).resolve().parent.parent / "dbfox_local.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"

# Ensure DB_PATH is available for backward compat (checkpointer imports it)
if "DB_PATH" not in dir():
    DB_PATH = Path(DATABASE_URL.replace("sqlite:///", ""))

# Connection pool safety defaults. They intentionally mirror the retryable error
# semantics used by Agent tool execution: stale connections should be detected
# before use, long-lived pooled connections should be recycled, and pool waits
# should fail fast enough for the graph to route/retry instead of hanging.
DB_POOL_SIZE = int(os.environ.get("DBFOX_DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.environ.get("DBFOX_DB_MAX_OVERFLOW", "20"))
DB_POOL_RECYCLE_SECONDS = int(os.environ.get("DBFOX_DB_POOL_RECYCLE_SECONDS", "1800"))
DB_POOL_TIMEOUT_SECONDS = int(os.environ.get("DBFOX_DB_POOL_TIMEOUT_SECONDS", "30"))
DB_SQLITE_TIMEOUT_SECONDS = float(os.environ.get("DBFOX_SQLITE_TIMEOUT_SECONDS", "30"))

def configure_sqlite_pragmas(database_url: str | None = None) -> None:
    """Apply WAL / busy_timeout / synchronous PRAGMAs for SQLite databases.

    Safe to call multiple times; no-op for non-SQLite URLs.
    Must be called before Alembic inspection in init_db().
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
    finally:
        conn.close()


engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": DB_SQLITE_TIMEOUT_SECONDS,
    },
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=DB_POOL_RECYCLE_SECONDS,
    pool_timeout=DB_POOL_TIMEOUT_SECONDS,
)

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
            from pathlib import Path as _Path
            _dir = _Path(__file__).resolve().parent.parent / ".agent_eval" / "outputs"
            _dir.mkdir(parents=True, exist_ok=True)
            import time as _t_time
            _ts = _t_time.strftime("%Y%m%d_%H%M%S")
            _trace_file = open(str(_dir / f"db_write_trace_{_ts}.jsonl"), "a", encoding="utf-8")

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
                "type": "ERROR", "error": str(exc)[:200], "table": "?",
                "thread": threading.current_thread().name,
                "run_id": current_run_id.get(), "session_id": current_session_id.get(),
            }
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


def _ensure_fts5(conn) -> None:
    """Create FTS5 virtual table if it doesn't exist."""
    from sqlalchemy import text as sa_text
    from sqlalchemy.exc import OperationalError
    from engine.models import FTS5_DDL
    try:
        conn.execute(sa_text("SELECT 1 FROM schema_search_fts LIMIT 0"))
    except OperationalError as e:
        if "no such table" in str(e).lower():
            conn.execute(sa_text(FTS5_DDL))
            conn.commit()
        else:
            raise
    except Exception:
        raise


def init_db() -> None:
    """
    数据库初始化与版本自动迁移迁移引擎
    
    在 main.py 的 lifespan 启动勾子中调用。
    它负责：
    1. 物理备份：修改表结构前，完整复制一份 `dbfox_local.db` 备用，防止迁移失败导致数据库损毁。
    2. 兼容清理：若检测到极早期开发时手写的 `schema_migrations` 老旧迁移记录，则自动执行 v1~v10 的 SQL 平滑迁移。
    3. 移交 Alembic：利用 stamp 标记为 baseline，完成对主流数据库迁移工具 Alembic 的平滑过渡。
    4. 执行 Alembic：自动升级（upgrade head）到当前代码对应的最新表结构。
    5. 容灾恢复：若发生任何无法恢复的异常，自动丢弃当前连接，从备份文件瞬间还原，保证系统稳定性。
    """
    from engine import models  # 必须在这里导入模型，确保所有映射关系已在 SQLAlchemy 中完成注册
    import shutil
    import time
    import sys
    from pathlib import Path
    from sqlalchemy import text
    from sqlalchemy.engine import Connection
    from alembic.config import Config
    from alembic import command

    # 1. 物理安全备份机制 (Secure Database Backup)
    backup_path = None
    if DB_PATH.exists():
        timestamp = int(time.time())
        backup_name = f"{DB_PATH.name}.bak_{timestamp}"
        backup_path = DB_PATH.with_name(backup_name)
        try:
            # 完整物理复制数据库文件
            shutil.copy2(DB_PATH, backup_path)
            
            # 回收历史备份：只保留最近 5 次的备份文件，多余的老旧备份自动清理删除，避免撑爆磁盘
            backups = sorted(DB_PATH.parent.glob(f"{DB_PATH.name}.bak_*"))
            if len(backups) > 5:
                for old_bak in backups[:-5]:
                    try:
                        old_bak.unlink()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("迁移警告：升级前未能成功备份元数据库文件: %s", e)
            backup_path = None

    # 0. Ensure SQLite PRAGMAs are configured before any Alembic work
    configure_sqlite_pragmas(DATABASE_URL)

    try:
        # 2. 动态计算 Alembic 配置文件及其脚本的绝对路径
        is_frozen = getattr(sys, "frozen", False)
        if is_frozen:
            # 打包运行环境下，Alembic 配置文件和脚本会被释放在临时解压目录（_MEIPASS）中
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                ini_path = Path(meipass) / "alembic.ini"
                script_location = Path(meipass) / "engine" / "migrations"
            else:
                exec_dir = Path(sys.executable).parent
                ini_path = exec_dir / "alembic.ini"
                script_location = exec_dir / "engine" / "migrations"
        else:
            # 源码运行环境下，路径位于开发工作区中
            ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
            script_location = Path(__file__).resolve().parent / "migrations"

        if not ini_path.exists():
            logger.warning("Alembic配置文件不存在: %s", ini_path)
            return

        # 强制关闭所有连接，避免 Windows 下文件锁导致的迁移失败
        try:
            engine.dispose()
        except Exception:
            pass

        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("script_location", str(script_location))
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        # If DB does not exist, create and stamp to head after creating tables.
        # For existing DB, ensure version table and upgrade.
        with engine.begin() as conn:
            inspector = None
            try:
                from sqlalchemy import inspect
                inspector = inspect(conn)
                tables = inspector.get_table_names()
                logger.debug("Alembic migration: found %d existing tables", len(tables))
            except Exception as inspect_err:
                logger.warning("Alembic migration: inspect failed: %s", inspect_err)
                tables = []
            if not tables:
                logger.info("Alembic migration: no tables found, creating schema and stamping head")
                Base.metadata.create_all(bind=conn)
                _ensure_fts5(conn)
                command.stamp(alembic_cfg, "head")
            else:
                logger.info("Alembic migration: upgrading to head")
                command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error("数据库初始化失败: %s", e)
        if backup_path is not None and backup_path.exists():
            try:
                engine.dispose()
                import shutil
                shutil.copy2(backup_path, DB_PATH)
                logger.info("已从备份恢复数据库")
            except Exception as restore_err:
                logger.error("恢复备份失败: %s", restore_err)
