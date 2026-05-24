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
    import sys
    from pathlib import Path
    from sqlalchemy import text
    from sqlalchemy.engine import Connection
    from alembic.config import Config
    from alembic import command

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
        # Resolve Alembic Paths dynamically for frozen and non-frozen contexts
        is_frozen = getattr(sys, "frozen", False)
        if is_frozen:
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                ini_path = Path(meipass) / "alembic.ini"
                script_location = Path(meipass) / "engine" / "migrations"
            else:
                exec_dir = Path(sys.executable).parent
                ini_path = exec_dir / "alembic.ini"
                script_location = exec_dir / "engine" / "migrations"
        else:
            ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
            script_location = Path(__file__).resolve().parent / "migrations"

        # Create Alembic Configuration and override directories/URLs dynamically
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("script_location", str(script_location))
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        # Check existing schema state for legacy transitions
        has_legacy = False
        has_alembic = False
        with engine.begin() as conn:
            res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"))
            has_legacy = res.fetchone() is not None

            res_alembic = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"))
            has_alembic = res_alembic.fetchone() is not None

        # Case 1: Legacy hand-rolled metastore ledger exists and needs transition
        if has_legacy and not has_alembic:
            print("Detected legacy metastore schema ledger. Running fallback migrations to v10...")

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

            def migration_v7(conn: Connection) -> None:
                # Version 7: Project workspace ownership for lifecycle assets
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS projects (
                        id VARCHAR PRIMARY KEY,
                        name VARCHAR NOT NULL,
                        description TEXT,
                        status VARCHAR NOT NULL DEFAULT 'active',
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_projects_status
                    ON projects (status)
                """))
                conn.execute(text("""
                    INSERT OR IGNORE INTO projects (
                        id,
                        name,
                        description,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'default-project',
                        'Default Workspace',
                        'Auto-created workspace for existing DataBox assets.',
                        'active',
                        datetime('now'),
                        datetime('now')
                    )
                """))

                if not has_column(conn, "data_sources", "project_id"):
                    conn.execute(text("ALTER TABLE data_sources ADD COLUMN project_id VARCHAR"))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_data_sources_project_id
                        ON data_sources (project_id)
                    """))

                conn.execute(text("""
                    UPDATE data_sources
                    SET project_id = 'default-project'
                    WHERE project_id IS NULL OR project_id = ''
                """))

            def migration_v8(conn: Connection) -> None:
                # Version 8: Project-scoped local database environments
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS database_environments (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        name VARCHAR NOT NULL,
                        runtime VARCHAR NOT NULL DEFAULT 'docker',
                        engine_type VARCHAR NOT NULL DEFAULT 'mysql',
                        engine_version VARCHAR NOT NULL DEFAULT '8.0',
                        image VARCHAR NOT NULL DEFAULT 'mysql:8.0',
                        container_name VARCHAR NOT NULL,
                        host VARCHAR NOT NULL DEFAULT '127.0.0.1',
                        port INTEGER NOT NULL,
                        database_name VARCHAR NOT NULL,
                        username VARCHAR NOT NULL,
                        password_ciphertext VARCHAR NOT NULL,
                        password_nonce VARCHAR NOT NULL,
                        datasource_id VARCHAR,
                        status VARCHAR NOT NULL DEFAULT 'created',
                        last_health_status VARCHAR,
                        last_health_at DATETIME,
                        last_error TEXT,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_database_environments_project
                    ON database_environments (project_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_database_environments_status
                    ON database_environments (status)
                """))
                if not has_column(conn, "data_sources", "environment_id"):
                    conn.execute(text("ALTER TABLE data_sources ADD COLUMN environment_id VARCHAR"))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_data_sources_environment_id
                        ON data_sources (environment_id)
                    """))

            def migration_v9(conn: Connection) -> None:
                # Version 9: Project-scoped datasource backup records
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS backup_records (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        datasource_id VARCHAR NOT NULL,
                        environment_id VARCHAR,
                        label VARCHAR,
                        backup_type VARCHAR NOT NULL DEFAULT 'mysqldump',
                        status VARCHAR NOT NULL DEFAULT 'running',
                        file_path TEXT,
                        file_size_bytes INTEGER,
                        checksum_sha256 VARCHAR,
                        started_at DATETIME NOT NULL,
                        completed_at DATETIME,
                        duration_ms INTEGER,
                        error_message TEXT,
                        created_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_backup_records_project
                    ON backup_records (project_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_backup_records_datasource
                    ON backup_records (datasource_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_backup_records_created
                    ON backup_records (created_at)
                """))

            def migration_v10(conn: Connection) -> None:
                # Version 10: Table design drafts persistence
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS table_design_drafts (
                        id VARCHAR PRIMARY KEY,
                        project_id VARCHAR NOT NULL,
                        table_name VARCHAR NOT NULL,
                        table_comment VARCHAR,
                        columns_json TEXT NOT NULL,
                        indexes_json TEXT NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_table_design_drafts_project
                    ON table_design_drafts (project_id)
                """))

            migrations = {
                1: migration_v1,
                2: migration_v2,
                3: migration_v3,
                4: migration_v4,
                5: migration_v5,
                6: migration_v6,
                7: migration_v7,
                8: migration_v8,
                9: migration_v9,
                10: migration_v10,
            }

            # Apply legacy migrations sequentially
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

            # Database schema is now fully compatible with the v10 (baseline) schema.
            # We stamp the database with the Alembic baseline setup revision ID '99b4fdab0781'
            print("Stamping database with Alembic baseline revision '99b4fdab0781'...")
            command.stamp(alembic_cfg, "99b4fdab0781")

            # Drop the old ledger table
            print("Dropping legacy schema_migrations ledger table...")
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE schema_migrations"))

            print("Successfully transitioned legacy database to Alembic management!")

        # Case 2: Run Alembic migrations upgrade to the latest head
        print("Executing Alembic migrations upgrade to latest head...")
        command.upgrade(alembic_cfg, "head")
        print("Metastore schema initialized successfully via Alembic.")

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
