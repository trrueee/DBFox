from __future__ import annotations

import os
import re
import stat
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from sqlalchemy import update
from sqlalchemy.orm import Session

from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.lifecycle import get_datasource_resource_lifecycle
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.datasource import datasource_connection_dict
from engine.errors import BackupSourceMismatchError
from engine.models import BackupRecord, DataSource, DEFAULT_PROJECT_ID, RestoreOperation
from engine.backup_paths import (
    BackupError,
    absolute_lexical_path as _absolute_lexical_path,
    backup_operation_error as _backup_operation_error,
    backup_path as _backup_path,
    backup_relative_path as _backup_relative_path,
    backup_root as _backup_root,
    existing_owned_backup_path as _existing_owned_backup_path,
    _is_link_or_reparse,
    new_owned_backup_path as _new_owned_backup_path,
    open_existing_regular_file as _open_existing_regular_file,
    parse_backup_relative_path as _parse_backup_relative_path,
    regular_file_size as _regular_file_size,
    remove_regular_file_if_owned as _remove_regular_file_if_owned,
    require_private_directory as _require_private_directory,
    safe_backup_record_path,
    sha256_file as _sha256_file,
)


_MYSQL_CLIENT_DIR_ENV: Final = "DBFOX_MYSQL_CLIENT_DIR"
_NATIVE_CLIENT_TIMEOUT_SECONDS: Final = 300
_LOCALE: Final = "C"


def _restore_operation_error() -> BackupError:
    return BackupError(
        fixed_error_message(FixedErrorCode.RESTORE_OPERATION_FAILED),
        code=FixedErrorCode.RESTORE_OPERATION_FAILED.value,
    )


def _restore_version_conflict() -> BackupError:
    return BackupError(
        fixed_error_message(FixedErrorCode.RESTORE_VERSION_CONFLICT),
        code=FixedErrorCode.RESTORE_VERSION_CONFLICT.value,
    )


def _native_client_error() -> BackupError:
    return BackupError(
        fixed_error_message(FixedErrorCode.BACKUP_CLIENT_NOT_FOUND),
        code=FixedErrorCode.BACKUP_CLIENT_NOT_FOUND.value,
    )


def _native_client_path(client_name: str) -> Path:
    configured_dir = os.environ.get(_MYSQL_CLIENT_DIR_ENV, "").strip()
    if not configured_dir:
        raise _native_client_error()
    try:
        raw_directory = Path(configured_dir).expanduser()
    except (TypeError, ValueError) as exc:
        raise _native_client_error() from exc
    if not raw_directory.is_absolute():
        raise _native_client_error()
    try:
        client_directory = _require_private_directory(raw_directory)
    except BackupError as exc:
        raise _native_client_error() from exc

    filename = f"{client_name}.exe" if os.name == "nt" else client_name
    executable = client_directory / filename
    try:
        executable_stat = executable.lstat()
    except OSError as exc:
        raise _native_client_error() from exc
    if _is_link_or_reparse(executable_stat) or not stat.S_ISREG(executable_stat.st_mode):
        raise _native_client_error()
    if os.name != "nt" and not os.access(executable, os.X_OK):
        raise _native_client_error()
    return executable


def _native_client_environment(executable: Path, mysql_password: str) -> dict[str, str]:
    return {
        "MYSQL_PWD": mysql_password,
        "PATH": str(executable.parent),
        "LC_ALL": _LOCALE,
        "LANG": _LOCALE,
    }


def _validated_output_path(output_path: Path) -> Path:
    root = _backup_root()
    absolute = _absolute_lexical_path(output_path)
    try:
        raw_relative = absolute.relative_to(root)
    except ValueError as exc:
        raise _backup_operation_error() from exc
    relative = _parse_backup_relative_path(raw_relative.as_posix())
    if relative is None:
        raise _backup_operation_error()
    return _new_owned_backup_path(relative)


def _open_staging_file(output_path: Path) -> tuple[Path, Any]:
    staging_path = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.partial")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(staging_path, flags, 0o600)
    except OSError as exc:
        raise _backup_operation_error() from exc
    return staging_path, os.fdopen(descriptor, "wb")


def _run_mysqldump(ds: DataSource, output_path: Path) -> None:
    """Create a native dump through a configured absolute client executable."""
    output_path = _validated_output_path(output_path)
    profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
    factory = ConnectionFactory()
    staging_path: Path | None = None
    try:
        executable = _native_client_path("mysqldump")
        with factory.mysql_client_scope(profile, purpose=ConnectionPurpose.BACKUP) as client:
            command = [
                str(executable),
                "--single-transaction",
                "--routines",
                "--triggers",
                "--events",
                "--protocol=TCP",
                "--default-character-set=utf8mb4",
                f"--host={client.host}",
                f"--port={client.port}",
                f"--user={client.username}",
            ]
            for option, value in client.ssl_options.items():
                command.append(f"--{option.replace('_', '-')}={value}")
            command.extend(("--", client.database))

            staging_path, handle = _open_staging_file(output_path)
            with handle:
                subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=handle,
                    stderr=subprocess.DEVNULL,
                    text=False,
                    check=True,
                    timeout=_NATIVE_CLIENT_TIMEOUT_SECONDS,
                    env=_native_client_environment(executable, client.environment()["MYSQL_PWD"]),
                    cwd=str(output_path.parent),
                    close_fds=True,
                )
                handle.flush()
                os.fsync(handle.fileno())

        if _regular_file_size(staging_path) <= 0:
            raise _backup_operation_error()
        os.replace(staging_path, output_path)
        staging_path = None
    except BackupError:
        raise
    except FileNotFoundError:
        raise _native_client_error() from None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise _backup_operation_error() from None
    finally:
        if staging_path is not None:
            _remove_regular_file_if_owned(staging_path)


def _isolated_database_name(backup_id: str) -> str:
    compact_id = re.sub(r"[^a-fA-F0-9]", "", backup_id)[:16].lower()
    return f"dbfox_restore_{compact_id}_{uuid.uuid4().hex[:12]}"


def _quote_mysql_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]{1,64}", value):
        raise _restore_operation_error()
    return f"`{value}`"


def _isolated_profile(profile: ConnectionProfile, database_name: str) -> ConnectionProfile:
    """Use the same vault references without registering staging resources as managed."""

    return replace(
        profile,
        datasource_id=None,
        database_name=database_name,
        is_managed=False,
        connection_generation=None,
    )


def _create_isolated_database(
    factory: ConnectionFactory,
    profile: ConnectionProfile,
    database_name: str,
) -> None:
    statement = (
        f"CREATE DATABASE {_quote_mysql_identifier(database_name)} "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.RESTORE,
        read_only=False,
        pooled=False,
    ) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(statement)
            connection.commit()
        finally:
            cursor.close()


def _drop_isolated_database(
    factory: ConnectionFactory,
    profile: ConnectionProfile,
    database_name: str,
) -> None:
    statement = f"DROP DATABASE IF EXISTS {_quote_mysql_identifier(database_name)}"
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.RESTORE,
        read_only=False,
        pooled=False,
    ) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(statement)
            connection.commit()
        finally:
            cursor.close()


def _run_mysql_restore(
    factory: ConnectionFactory,
    profile: ConnectionProfile,
    backup_path: Path,
) -> None:
    executable = _native_client_path("mysql")
    descriptor = _open_existing_regular_file(backup_path, os.O_RDONLY)
    try:
        with factory.mysql_client_scope(profile, purpose=ConnectionPurpose.RESTORE) as client:
            command = [
                str(executable),
                "--binary-mode",
                "--protocol=TCP",
                "--default-character-set=utf8mb4",
                f"--host={client.host}",
                f"--port={client.port}",
                f"--user={client.username}",
                f"--database={client.database}",
            ]
            for option, value in client.ssl_options.items():
                command.append(f"--{option.replace('_', '-')}={value}")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                subprocess.run(
                    command,
                    stdin=handle,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=False,
                    check=True,
                    timeout=_NATIVE_CLIENT_TIMEOUT_SECONDS,
                    env=_native_client_environment(executable, client.environment()["MYSQL_PWD"]),
                    cwd=str(backup_path.parent),
                    close_fds=True,
                )
    except BackupError:
        raise
    except FileNotFoundError:
        raise _native_client_error() from None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise _restore_operation_error() from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _validate_isolated_database(
    factory: ConnectionFactory,
    profile: ConnectionProfile,
) -> int:
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.RESTORE,
        read_only=True,
        pooled=False,
    ) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) AS table_count FROM information_schema.tables "
                "WHERE table_schema = %s",
                (profile.database_name,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    if isinstance(row, dict):
        value = row.get("table_count")
    elif isinstance(row, (tuple, list)) and row:
        value = row[0]
    else:
        raise _restore_operation_error()
    try:
        table_count = int(str(value))
    except (TypeError, ValueError) as exc:
        raise _restore_operation_error() from exc
    if table_count < 0:
        raise _restore_operation_error()
    return table_count


def create_backup(db: Session, datasource_id: str, label: str | None = None) -> BackupRecord:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise BackupError("Data source not found.", code="DATASOURCE_NOT_FOUND")

    source_profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
    if source_profile.connection_generation is None:
        raise _backup_operation_error()

    backup_id = str(uuid.uuid4())
    relative_path = _backup_relative_path(ds, backup_id)
    output_path = _backup_path(ds, backup_id)
    started = datetime.now(UTC)
    record = BackupRecord(
        id=backup_id,
        project_id=str(ds.project_id or DEFAULT_PROJECT_ID),
        datasource_id=datasource_id,
        environment_id=ds.environment_id,
        label=(label or "").strip() or None,
        backup_type="mysqldump",
        status="running",
        file_path=relative_path.as_posix(),
        source_connection_generation=source_profile.connection_generation,
        source_profile_fingerprint=source_profile.profile_fingerprint,
        source_database_name=source_profile.database_name,
        started_at=started,
        created_at=started,
    )
    db.add(record)
    db.flush()

    start_time = time.monotonic()
    try:
        _run_mysqldump(ds, output_path)
        _existing_owned_backup_path(relative_path)
        file_size = _regular_file_size(output_path)
        if file_size <= 0:
            raise _backup_operation_error()

        completed = datetime.now(UTC)
        setattr(record, "status", "success")
        setattr(record, "completed_at", completed)
        setattr(record, "duration_ms", int((time.monotonic() - start_time) * 1000))
        setattr(record, "file_size_bytes", file_size)
        setattr(record, "checksum_sha256", _sha256_file(output_path))
        setattr(record, "error_message", None)
    except Exception:
        _remove_regular_file_if_owned(output_path)
        completed = datetime.now(UTC)
        setattr(record, "status", "failed")
        setattr(record, "file_path", None)
        setattr(record, "completed_at", completed)
        setattr(record, "duration_ms", int((time.monotonic() - start_time) * 1000))
        setattr(record, "error_message", fixed_error_message(FixedErrorCode.BACKUP_OPERATION_FAILED))
        db.commit()  # Preserve the failed audit record independently of API rollback.
        raise

    return record


def precheck_restore(record: BackupRecord) -> dict[str, Any]:
    """Validate a stored native backup artifact before isolated restore."""
    warnings: list[str] = []
    errors: list[str] = []
    safe_path = safe_backup_record_path(record.file_path)
    file_size = 0

    if str(record.backup_type) != "mysqldump":
        errors.append("Backup record is not a native mysqldump backup.")
    if safe_path is None:
        errors.append("Backup record does not reference a managed backup artifact.")
    else:
        relative = _parse_backup_relative_path(safe_path)
        assert relative is not None
        try:
            path = _existing_owned_backup_path(relative)
            file_size = _regular_file_size(path)
            if file_size <= 0:
                errors.append("Backup file is empty.")
            if not record.checksum_sha256 or _sha256_file(path) != record.checksum_sha256:
                errors.append("Backup integrity verification failed.")
        except BackupError:
            errors.append("Managed backup artifact is unavailable.")

    if str(record.status) != "success":
        warnings.append("Backup record status is not success.")
    restore_available = not errors and str(record.status) == "success"
    return {
        "ok": not errors,
        "warnings": warnings,
        "errors": errors,
        "filePath": safe_path,
        "fileSizeBytes": file_size,
        "checksumSha256": record.checksum_sha256,
        "restoreAvailable": restore_available,
    }


def execute_restore(
    db: Session,
    backup_id: str,
    *,
    expected_datasource_generation: int,
    connection_factory: ConnectionFactory | None = None,
) -> RestoreOperation:
    """Restore into an isolated database, validate it, then CAS-cut over metadata."""

    record = db.get(BackupRecord, backup_id)
    if record is None:
        raise BackupError("Backup not found.", code="BACKUP_NOT_FOUND")
    if not precheck_restore(record)["restoreAvailable"]:
        raise _restore_operation_error()
    datasource = db.get(DataSource, record.datasource_id)
    if datasource is None:
        raise BackupError("Data source not found.", code="DATASOURCE_NOT_FOUND")
    if str(datasource.db_type).lower() != "mysql":
        raise _restore_operation_error()
    if int(datasource.connection_generation) != expected_datasource_generation:
        raise _restore_version_conflict()

    current_profile = ConnectionProfile.from_mapping(datasource_connection_dict(datasource))
    if (
        record.source_connection_generation is None
        or int(record.source_connection_generation) != expected_datasource_generation
        or not record.source_profile_fingerprint
        or record.source_profile_fingerprint != current_profile.profile_fingerprint
        or not record.source_database_name
        or record.source_database_name != current_profile.database_name
    ):
        raise BackupSourceMismatchError()

    relative = _parse_backup_relative_path(record.file_path)
    if relative is None:
        raise _restore_operation_error()
    backup_path = _existing_owned_backup_path(relative)
    if not record.checksum_sha256 or _sha256_file(backup_path) != record.checksum_sha256:
        raise _restore_operation_error()

    factory = connection_factory or ConnectionFactory()
    previous_profile = current_profile
    target_database = _isolated_database_name(str(record.id))
    target_profile = _isolated_profile(previous_profile, target_database)
    operation = RestoreOperation(
        id=str(uuid.uuid4()),
        backup_id=str(record.id),
        datasource_id=str(datasource.id),
        status="running",
        source_database_name=str(record.source_database_name),
        target_database_name=target_database,
        expected_generation=expected_datasource_generation,
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(operation)
    db.commit()

    isolated_created = False
    cutover_committed = False
    try:
        _create_isolated_database(factory, previous_profile, target_database)
        isolated_created = True
        _run_mysql_restore(factory, target_profile, backup_path)
        table_count = _validate_isolated_database(factory, target_profile)

        db.expire_all()
        updated = db.execute(
            update(DataSource)
            .where(
                DataSource.id == datasource.id,
                DataSource.connection_generation == expected_datasource_generation,
            )
            .values(
                database_name=target_database,
                connection_generation=expected_datasource_generation + 1,
            )
        )
        if int(getattr(updated, "rowcount", 0) or 0) != 1:
            raise _restore_version_conflict()
        persisted_operation = db.get(RestoreOperation, operation.id)
        if persisted_operation is None:
            raise _restore_operation_error()
        persisted_operation_row: Any = persisted_operation
        persisted_operation_row.status = "success"
        persisted_operation_row.committed_generation = expected_datasource_generation + 1
        persisted_operation_row.validated_table_count = table_count
        persisted_operation_row.completed_at = datetime.now(UTC)
        persisted_operation_row.error_code = None
        db.commit()
        cutover_committed = True

        current_datasource = db.get(DataSource, datasource.id, populate_existing=True)
        if current_datasource is None:
            raise _restore_operation_error()
        current_profile = ConnectionProfile.from_mapping(
            datasource_connection_dict(current_datasource)
        )
        get_datasource_resource_lifecycle().replace(previous_profile, current_profile)
        db.refresh(persisted_operation)
        return persisted_operation
    except Exception as exc:
        db.rollback()
        if isolated_created and not cutover_committed:
            try:
                _drop_isolated_database(factory, previous_profile, target_database)
            except Exception:
                pass
        persisted_operation = db.get(RestoreOperation, operation.id)
        if persisted_operation is not None and not cutover_committed:
            persisted_operation_row = persisted_operation
            persisted_operation_row.status = "failed"
            persisted_operation_row.error_code = (
                exc.code if isinstance(exc, BackupError) else FixedErrorCode.RESTORE_OPERATION_FAILED.value
            )
            persisted_operation_row.completed_at = datetime.now(UTC)
            db.commit()
        if isinstance(exc, BackupError):
            raise
        raise _restore_operation_error() from exc
