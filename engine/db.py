import sys
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from typing import Generator

# Dynamic persistent path resolution for packaged production vs local workspace development
is_frozen = getattr(sys, "frozen", False)
if is_frozen:
    from engine.runtime_paths import private_runtime_dir
    DB_PATH = private_runtime_dir("data") / "databox_local.db"
else:
    DB_PATH = Path(__file__).resolve().parent.parent / "databox_local.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from engine import models  # noqa: F811
    import shutil
    import time
    from sqlalchemy import text

    # 1. Secure Local Database Backup before any migrations run
    backup_path = None
    if DB_PATH.exists():
        timestamp = int(time.time())
        backup_name = f"{DB_PATH.name}.bak_{timestamp}"
        backup_path = DB_PATH.with_name(backup_name)
        try:
            shutil.copy2(DB_PATH, backup_path)
            # Prune ancient backups, keeping only the 5 most recent ones
            backups = sorted(DB_PATH.parent.glob(f"{DB_PATH.name}.bak_*"))
            if len(backups) > 5:
                for old_bak in backups[:-5]:
                    try:
                        old_bak.unlink()
                    except Exception:
                        pass
        except Exception as e:
            print(f"Migration Warning: Could not back up SQLite metadatabase before alteration: {e}")
            backup_path = None

    try:
        # Create core tables if they do not exist
        Base.metadata.create_all(bind=engine)

        # 2. Initialize Migration Version Ledger Table
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at DATETIME NOT NULL
                )
            """))

        # Helper to safely verify column existence in SQLite tables
        def has_column(conn: Connection, table: str, col: str) -> bool:
            res = conn.execute(text(f"PRAGMA table_info({table})"))
            return any(row[1] == col for row in res.fetchall())

        # Define sequential incremental migration versions
        def migration_v1(conn: Connection) -> None:
            # Version 1: SSH Connection Tunnel Parameters
            cols = {
                "ssh_enabled": "INTEGER NOT NULL DEFAULT 0",
                "ssh_host": "VARCHAR",
                "ssh_port": "INTEGER NOT NULL DEFAULT 22",
                "ssh_username": "VARCHAR",
                "ssh_password_ciphertext": "VARCHAR",
                "ssh_password_nonce": "VARCHAR",
                "ssh_pkey_path": "VARCHAR",
                "ssh_pkey_passphrase_ciphertext": "VARCHAR",
                "ssh_pkey_passphrase_nonce": "VARCHAR",
            }
            for col_name, col_type in cols.items():
                if not has_column(conn, "data_sources", col_name):
                    conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {col_name} {col_type}"))

        def migration_v2(conn: Connection) -> None:
            # Version 2: Multi-Environment (env) & Read Only connection protections
            cols = {
                "is_read_only": "INTEGER NOT NULL DEFAULT 0",
                "env": "VARCHAR NOT NULL DEFAULT 'dev'",
            }
            for col_name, col_type in cols.items():
                if not has_column(conn, "data_sources", col_name):
                    conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {col_name} {col_type}"))

        def migration_v3(conn: Connection) -> None:
            # Version 3: Trace and audit LLM prompt generation logs by data_source_id
            if not has_column(conn, "llm_logs", "data_source_id"):
                conn.execute(text("ALTER TABLE llm_logs ADD COLUMN data_source_id VARCHAR"))

        def migration_v4(conn: Connection) -> None:
            # Version 4: MySQL TLS/SSL connection verification settings
            cols = {
                "ssl_enabled": "INTEGER NOT NULL DEFAULT 0",
                "ssl_ca_path": "VARCHAR",
                "ssl_cert_path": "VARCHAR",
                "ssl_key_path": "VARCHAR",
                "ssl_verify_identity": "INTEGER NOT NULL DEFAULT 1",
            }
            for col_name, col_type in cols.items():
                if not has_column(conn, "data_sources", col_name):
                    conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {col_name} {col_type}"))

        def migration_v5(conn: Connection) -> None:
            # Version 5: Prompt versioning & schema validation audit logs
            cols = {
                "prompt_version": "VARCHAR",
                "prompt_template_hash": "VARCHAR",
                "model_temperature": "FLOAT",
                "max_tokens": "INTEGER",
                "schema_validation_warnings": "TEXT",
            }
            for col_name, col_type in cols.items():
                if not has_column(conn, "llm_logs", col_name):
                    conn.execute(text(f"ALTER TABLE llm_logs ADD COLUMN {col_name} {col_type}"))

        def migration_v6(conn: Connection) -> None:
            # Version 6: Query performance latency profiling breakdown
            cols = {
                "connect_ms": "INTEGER",
                "guardrail_ms": "INTEGER",
                "execute_ms": "INTEGER",
                "fetch_ms": "INTEGER",
                "serialize_ms": "INTEGER",
            }
            for col_name, col_type in cols.items():
                if not has_column(conn, "query_history", col_name):
                    conn.execute(text(f"ALTER TABLE query_history ADD COLUMN {col_name} {col_type}"))

        migrations = {
            1: migration_v1,
            2: migration_v2,
            3: migration_v3,
            4: migration_v4,
            5: migration_v5,
            6: migration_v6,
        }

        # Apply outstanding migrations sequentially within a transaction block
        with engine.begin() as conn:
            res = conn.execute(text("SELECT version FROM schema_migrations"))
            applied_versions = {row[0] for row in res.fetchall()}

            for version in sorted(migrations.keys()):
                if version not in applied_versions:
                    print(f"Applying SQLite schema migration v{version}...")
                    migrations[version](conn)
                    conn.execute(
                        text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, datetime('now'))"),
                        {"v": version}
                    )
                    print(f"SQLite schema migration v{version} applied successfully.")

    except Exception as exc:
        print(f"❌ METASTORE SCHEMA MIGRATION FAILURE: {exc}")
        if backup_path and backup_path.exists():
            print(f"🔄 Rolling back: Disposing engine connections and restoring SQLite database from '{backup_path.name}'...")
            try:
                engine.dispose()
                shutil.copy2(backup_path, DB_PATH)
                print("🔄 SQLite metadatabase successfully restored to pre-migration snapshot.")
            except Exception as restore_err:
                print(f"🚨 CRITICAL ERROR: Restoring metastore from backup failed: {restore_err}")
        raise exc
