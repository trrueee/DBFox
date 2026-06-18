from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from engine.datasource import datasource_connection_dict, get_mysql_connection_params

logger = logging.getLogger("dbfox.backup")
from engine.errors import DBFoxError
from engine.models import BackupRecord, DataSource, DEFAULT_PROJECT_ID
from engine.runtime_paths import private_runtime_dir


class BackupError(DBFoxError):
    def __init__(self, message: str, code: str = "BACKUP_FAILED") -> None:
        super().__init__(message, code=code)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "backup"


def _backup_path(ds: DataSource, backup_id: str) -> Path:
    project_id = str(ds.project_id or DEFAULT_PROJECT_ID)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{_safe_filename(str(ds.database_name))}_{backup_id[:8]}.sql"
    return private_runtime_dir("backups") / _safe_filename(project_id) / _safe_filename(str(ds.id)) / filename


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_mysqldump(ds: DataSource, output_path: Path) -> None:
    params = get_mysql_connection_params(datasource_connection_dict(ds))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "mysqldump",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--default-character-set=utf8mb4",
        f"--host={params['host']}",
        f"--port={int(params['port'])}",
        f"--user={params['user']}",
        f"--result-file={str(output_path)}",
        str(params["database"]),
    ]

    if params.get("ssl_ca"):
        cmd.append(f"--ssl-ca={params['ssl_ca']}")
    if params.get("ssl_cert"):
        cmd.append(f"--ssl-cert={params['ssl_cert']}")
    if params.get("ssl_key"):
        cmd.append(f"--ssl-key={params['ssl_key']}")

    env = os.environ.copy()
    env["MYSQL_PWD"] = str(params["password"])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300, env=env)
    except FileNotFoundError as exc:
        raise BackupError("mysqldump was not found. Please install MySQL client tools and ensure mysqldump is in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise BackupError(f"mysqldump failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError("mysqldump timed out after 300 seconds.", code="BACKUP_TIMEOUT") from exc


def _pymysql_simple_sql_export(ds: DataSource, output_path: Path) -> None:
    import pymysql
    params = get_mysql_connection_params(datasource_connection_dict(ds))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = pymysql.connect(
        host=params["host"],
        port=int(params["port"]),
        user=params["user"],
        password=str(params["password"]),
        database=str(params["database"]),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor
    )
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("-- DBFox Simple SQL Export (Pure-Python)\n")
            f.write("-- Warning: This simple export is only suited for simple table structures and data backups.\n")
            f.write("-- Stored procedures, triggers, views, or complex physical properties are not supported.\n")
            f.write(f"-- Dump Date: {datetime.now(UTC).isoformat()}\n")
            f.write(f"-- Database: {params['database']}\n\n")
            f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")
            
            with conn.cursor() as cursor:
                # 1. Fetch tables
                cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    f.write(f"-- Table structure for table `{table}`\n")
                    f.write(f"DROP TABLE IF EXISTS `{table}`;\n")
                    cursor.execute(f"SHOW CREATE TABLE `{table}`")
                    create_table_sql = cursor.fetchone()[1]  # type: ignore[index]
                    f.write(f"{create_table_sql};\n\n")
                    
                    # 2. Fetch rows
                    f.write(f"-- Dumping data for table `{table}`\n")
                    cursor.execute(f"SELECT * FROM `{table}`")
                    columns = [desc[0] for desc in cursor.description]
                    
                    rows = cursor.fetchall()
                    if rows:
                        for row in rows:
                            values = []
                            for val in row:
                                if val is None:
                                     values.append("NULL")
                                elif isinstance(val, (int, float)):
                                     values.append(str(val))
                                else:
                                     escaped_val = str(val).replace("\\", "\\\\").replace("'", "\\'")
                                     values.append(f"'{escaped_val}'")
                            
                            col_str = ", ".join([f"`{c}`" for c in columns])
                            val_str = ", ".join(values)
                            f.write(f"INSERT INTO `{table}` ({col_str}) VALUES ({val_str});\n")
                        f.write("\n")
                
                # 3. Fetch views
                cursor.execute("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
                views = [row[0] for row in cursor.fetchall()]
                for view in views:
                    f.write(f"-- View structure for view `{view}`\n")
                    f.write(f"DROP VIEW IF EXISTS `{view}`;\n")
                    cursor.execute(f"SHOW CREATE VIEW `{view}`")
                    create_view_sql = cursor.fetchone()[1]  # type: ignore[index]
                    f.write(f"{create_view_sql};\n\n")
            
            f.write("SET FOREIGN_KEY_CHECKS=1;\n")
    finally:
        conn.close()


def _pymysql_simple_sql_import(ds: DataSource, sql_file_path: Path) -> None:
    import pymysql
    params = get_mysql_connection_params(datasource_connection_dict(ds))
    
    conn = pymysql.connect(
        host=params["host"],
        port=int(params["port"]),
        user=params["user"],
        password=str(params["password"]),
        database=str(params["database"]),
        charset="utf8mb4",
        autocommit=True
    )
    
    try:
        with conn.cursor() as cursor:
            sql_content = sql_file_path.read_text(encoding="utf-8", errors="ignore")
            statements = []
            current_statement = []
            
            for line in sql_content.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("--") or stripped.startswith("/*"):
                    continue
                current_statement.append(line)
                if stripped.endswith(";"):
                    statements.append("\n".join(current_statement))
                    current_statement = []
                    
            if current_statement:
                stmt = "\n".join(current_statement).strip()
                if stmt:
                    statements.append(stmt)
                    
            for stmt in statements:
                stmt_stripped = stmt.strip()
                if stmt_stripped:
                    cursor.execute(stmt_stripped)
    finally:
        conn.close()


def create_backup(db: Session, datasource_id: str, label: str | None = None, allow_fallback: bool = True) -> BackupRecord:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise BackupError("Data source not found.", code="DATASOURCE_NOT_FOUND")


    backup_id = str(uuid.uuid4())
    started = datetime.now(UTC)
    output_path = _backup_path(ds, backup_id)
    record = BackupRecord(
        id=backup_id,
        project_id=str(ds.project_id or DEFAULT_PROJECT_ID),
        datasource_id=datasource_id,
        environment_id=ds.environment_id,
        label=(label or "").strip() or None,
        backup_type="mysqldump",
        status="running",
        file_path=str(output_path),
        started_at=started,
        created_at=started,
    )
    db.add(record)
    db.flush()

    start_time = time.monotonic()
    backup_mode = "mysqldump"
    try:
        try:
            _run_mysqldump(ds, output_path)
        except BackupError as exc:
            if "not found" in str(exc).lower():
                if not allow_fallback:
                    raise BackupError(
                        "mysqldump was not found. System is in Strict Mode (allow_fallback=False). "
                        "Please install MySQL client tools and ensure mysqldump is in your system PATH "
                        "to perform a production-grade full logical backup.",
                        code="MYSQLDUMP_NOT_FOUND"
                    ) from exc
                logger.warning(
                    "Warning: pure-Python simple SQL export is being used as fallback. "
                    "This export only supports simple table structures and row data, and DOES NOT support "
                    "triggers, stored procedures, views, or large binary objects. Please install official "
                    "mysql-client tools for production-grade physical backups."
                )
                _pymysql_simple_sql_export(ds, output_path)
                backup_mode = "simple_sql_export"
            else:
                raise

        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise BackupError("Backup file was not created or is empty.")

        completed = datetime.now(UTC)
        record.status = "success"
        record.backup_type = backup_mode
        record.completed_at = completed
        record.duration_ms = int((time.monotonic() - start_time) * 1000)
        record.file_size_bytes = output_path.stat().st_size
        record.checksum_sha256 = _sha256_file(output_path)
        record.error_message = None
    except Exception as exc:
        completed = datetime.now(UTC)
        record.status = "failed"
        record.completed_at = completed
        record.duration_ms = int((time.monotonic() - start_time) * 1000)
        record.error_message = str(exc)[:2000]
        db.commit()  # independent commit so API rollback does not erase the audit trail
        raise

    return record


def precheck_restore(record: BackupRecord) -> dict[str, Any]:
    warnings: list[str] = []
    path_value = str(record.file_path or "")
    if not path_value:
        return {"ok": False, "warnings": warnings, "errors": ["Backup record has no file path."]}

    path = Path(path_value)
    errors: list[str] = []
    if not path.exists():
        errors.append("Backup file does not exist.")
    elif not path.is_file():
        errors.append("Backup path is not a file.")
    else:
        size = path.stat().st_size
        if size <= 0:
            errors.append("Backup file is empty.")
        if path.suffix.lower() != ".sql":
            warnings.append("Backup file does not use .sql extension.")
        
        # Calculate current checksum and compare for anti-tamper security validation
        try:
            current_checksum = _sha256_file(path)
            if current_checksum != record.checksum_sha256:
                errors.append(f"Backup file has been modified or tampered with! Original checksum: {record.checksum_sha256}, current checksum: {current_checksum}")
        except Exception as e:
            errors.append(f"Failed to calculate backup file checksum: {e}")

        try:
            sample = path.read_text(encoding="utf-8", errors="ignore")[:4096].lower()
            if "create table" not in sample and "insert into" not in sample and "mysql dump" not in sample and "simple sql export" not in sample and "fallback database dump" not in sample:
                warnings.append("Backup file does not look like a standard SQL dump.")
        except Exception:
            pass

    if str(record.status) != "success":
        warnings.append("Backup record status is not success.")

    return {
        "ok": not errors,
        "warnings": warnings,
        "errors": errors,
        "filePath": path_value,
        "fileSizeBytes": path.stat().st_size if path.exists() and path.is_file() else 0,
        "checksumSha256": record.checksum_sha256,
    }


def _run_mysql_restore(ds: DataSource, sql_file_path: Path) -> None:
    params = get_mysql_connection_params(datasource_connection_dict(ds))
    cmd = [
        "mysql",
        f"--host={params['host']}",
        f"--port={int(params['port'])}",
        f"--user={params['user']}",
        "--default-character-set=utf8mb4",
        str(params["database"]),
    ]

    if params.get("ssl_ca"):
        cmd.append(f"--ssl-ca={params['ssl_ca']}")
    if params.get("ssl_cert"):
        cmd.append(f"--ssl-cert={params['ssl_cert']}")
    if params.get("ssl_key"):
        cmd.append(f"--ssl-key={params['ssl_key']}")

    env = os.environ.copy()
    env["MYSQL_PWD"] = str(params["password"])

    try:
        with open(sql_file_path, "r", encoding="utf-8", errors="ignore") as f:
            subprocess.run(cmd, stdin=f, capture_output=True, text=True, check=True, timeout=300, env=env)
    except FileNotFoundError as exc:
        raise BackupError("mysql client command was not found. Please install MySQL client tools and ensure mysql is in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise BackupError(f"mysql restore failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError("mysql restore timed out after 300 seconds.", code="RESTORE_TIMEOUT") from exc


def execute_restore(db: Session, backup_id: str, allow_fallback: bool = True) -> dict[str, Any]:
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise BackupError("Backup record not found.", code="BACKUP_NOT_FOUND")

    ds = db.query(DataSource).filter(DataSource.id == record.datasource_id).first()
    if not ds:
        raise BackupError("Data source for this backup record not found.", code="DATASOURCE_NOT_FOUND")

    if ds.is_read_only:
        raise BackupError("Cannot restore to a read-only data source.", code="RESTORE_READONLY_ERROR")

    # Perform Dry-Run precheck (which includes SHA-256 anti-tamper confirmation)
    precheck = precheck_restore(record)
    if not precheck["ok"]:
        raise BackupError(f"Restore pre-check failed: {', '.join(precheck['errors'])}", code="RESTORE_PRECHECK_FAILED")

    sql_path = Path(precheck["filePath"])

    # Safety confirmation: Prevent environment tier mismatch
    if record.environment_id and record.environment_id != ds.environment_id:
        raise BackupError(
            f"Environment mismatch: Cannot restore a backup from environment '{record.environment_id}' to different target environment '{ds.environment_id or 'unknown'}'.",
            code="RESTORE_ENV_MISMATCH"
        )

    try:
        _run_mysql_restore(ds, sql_path)
    except BackupError as exc:
        if "not found" in str(exc).lower():
            if not allow_fallback:
                raise BackupError(
                    "mysql client command was not found. System is in Strict Mode (allow_fallback=False). "
                    "Please install MySQL client tools and ensure mysql is in PATH.",
                    code="MYSQL_CLIENT_NOT_FOUND"
                ) from exc
            logger.warning("mysql command not found, falling back to pure-Python simple SQL execution.")
            _pymysql_simple_sql_import(ds, sql_path)
        else:
            raise

    return {
        "success": True,
        "backup_id": backup_id,
        "datasource_id": ds.id,
        "database_name": ds.database_name,
        "message": f"Successfully restored database '{ds.database_name}' from backup file."
    }


