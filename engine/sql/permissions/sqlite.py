from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import (
    PermissionProbe,
    PermissionReport,
    WRITE_PRIVILEGE_WARNING,
    bool_from_db_value,
    managed_cursor,
)


class SQLitePermissionProbe(PermissionProbe):
    def __init__(self, database_path: Path | str, connection_readonly: bool | None = None) -> None:
        self.database_path = Path(database_path)
        self.connection_readonly = connection_readonly

    def probe(self, conn: Any) -> PermissionReport:
        connection_readonly = self.connection_readonly
        if connection_readonly is None:
            connection_readonly = self._probe_query_only(conn)

        file_writable = os.access(self.database_path, os.W_OK)
        readonly = connection_readonly or not file_writable
        writable_privileges = [] if readonly else ["SQLITE_FILE_WRITE"]
        warnings = [WRITE_PRIVILEGE_WARNING] if writable_privileges else []
        if connection_readonly and file_writable:
            warnings.append("提示：SQLite 当前连接为只读，但数据库文件在文件系统上仍可写。")

        return PermissionReport(
            readonly=readonly,
            writable_privileges=writable_privileges,
            warnings=warnings,
            evidence={
                "probe": "sqlite_connection_and_file",
                "connection_readonly": connection_readonly,
                "file_writable": file_writable,
                "database_path": str(self.database_path),
            },
        )

    def _probe_query_only(self, conn: Any) -> bool:
        with managed_cursor(conn) as cursor:
            cursor.execute("PRAGMA query_only")
            row = cursor.fetchone()
        return bool_from_db_value(row[0]) if row else False
