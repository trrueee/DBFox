from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from engine.datasource import get_mysql_connection_params, is_demo_db
from engine.errors import DataBoxError
from engine.models import BackupRecord, DataSource, DEFAULT_PROJECT_ID
from engine.runtime_paths import private_runtime_dir


class BackupError(DataBoxError):
    def __init__(self, message: str, code: str = "BACKUP_FAILED") -> None:
        super().__init__(message, code=code)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "backup"


def _datasource_connection_dict(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "host": ds.host,
        "port": ds.port,
        "username": ds.username,
        "database_name": ds.database_name,
        "password_ciphertext": ds.password_ciphertext,
        "password_nonce": ds.password_nonce,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    }


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
    params = get_mysql_connection_params(_datasource_connection_dict(ds))
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


def create_backup(db: Session, datasource_id: str, label: str | None = None) -> BackupRecord:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise BackupError("Data source not found.", code="DATASOURCE_NOT_FOUND")
    if is_demo_db(str(ds.host), str(ds.database_name)):
        raise BackupError(
            "Built-in mock demo datasource cannot be backed up with mysqldump. Start a local Docker MySQL environment first.",
            code="BACKUP_UNSUPPORTED_DATASOURCE",
        )

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
    try:
        _run_mysqldump(ds, output_path)
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise BackupError("Backup file was not created or is empty.")

        completed = datetime.now(UTC)
        setattr(record, "status", "success")
        setattr(record, "completed_at", completed)
        setattr(record, "duration_ms", int((time.monotonic() - start_time) * 1000))
        setattr(record, "file_size_bytes", output_path.stat().st_size)
        setattr(record, "checksum_sha256", _sha256_file(output_path))
        setattr(record, "error_message", None)
    except Exception as exc:
        completed = datetime.now(UTC)
        setattr(record, "status", "failed")
        setattr(record, "completed_at", completed)
        setattr(record, "duration_ms", int((time.monotonic() - start_time) * 1000))
        setattr(record, "error_message", str(exc))
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
        sample = path.read_text(encoding="utf-8", errors="ignore")[:4096].lower()
        if "create table" not in sample and "insert into" not in sample and "mysql dump" not in sample:
            warnings.append("Backup file does not look like a standard SQL dump.")

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
    params = get_mysql_connection_params(_datasource_connection_dict(ds))
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


def execute_restore(db: Session, backup_id: str) -> dict[str, Any]:
    record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
    if not record:
        raise BackupError("Backup record not found.", code="BACKUP_NOT_FOUND")

    ds = db.query(DataSource).filter(DataSource.id == record.datasource_id).first()
    if not ds:
        raise BackupError("Data source for this backup record not found.", code="DATASOURCE_NOT_FOUND")

    if ds.is_read_only:
        raise BackupError("Cannot restore to a read-only data source.", code="RESTORE_READONLY_ERROR")

    # Run pre-check first
    precheck = precheck_restore(record)
    if not precheck["ok"]:
        raise BackupError(f"Restore pre-check failed: {', '.join(precheck['errors'])}", code="RESTORE_PRECHECK_FAILED")

    # Perform restore
    sql_path = Path(precheck["filePath"])
    _run_mysql_restore(ds, sql_path)

    return {
        "success": True,
        "backup_id": backup_id,
        "datasource_id": ds.id,
        "database_name": ds.database_name,
        "message": f"Successfully restored database '{ds.database_name}' from backup file."
    }

