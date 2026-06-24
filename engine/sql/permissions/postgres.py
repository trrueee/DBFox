from __future__ import annotations

from typing import Any

from .base import (
    PermissionProbe,
    PermissionReport,
    WRITE_PRIVILEGE_WARNING,
    bool_from_db_value,
    managed_cursor,
)


POSTGRES_TABLE_PRIVILEGE_SQL = """
    SELECT
        table_schema,
        table_name,
        has_table_privilege(format('%I.%I', table_schema, table_name), 'INSERT') AS can_insert,
        has_table_privilege(format('%I.%I', table_schema, table_name), 'UPDATE') AS can_update,
        has_table_privilege(format('%I.%I', table_schema, table_name), 'DELETE') AS can_delete
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND table_type IN ('BASE TABLE', 'FOREIGN TABLE')
    ORDER BY table_schema, table_name
"""


class PostgresPermissionProbe(PermissionProbe):
    def probe(self, conn: Any) -> PermissionReport:
        with managed_cursor(conn) as cursor:
            cursor.execute(POSTGRES_TABLE_PRIVILEGE_SQL)
            rows = list(cursor.fetchall())

        writable_privileges: list[str] = []
        for row in rows:
            schema, table, can_insert, can_update, can_delete = _postgres_row(row)
            table_ref = f"{schema}.{table}"
            if bool_from_db_value(can_insert):
                writable_privileges.append(f"{table_ref}:INSERT")
            if bool_from_db_value(can_update):
                writable_privileges.append(f"{table_ref}:UPDATE")
            if bool_from_db_value(can_delete):
                writable_privileges.append(f"{table_ref}:DELETE")

        warnings = [WRITE_PRIVILEGE_WARNING] if writable_privileges else []
        return PermissionReport(
            readonly=not writable_privileges,
            writable_privileges=writable_privileges,
            warnings=warnings,
            evidence={
                "probe": "postgres_table_privileges",
                "checked_tables": len(rows),
            },
        )


def _postgres_row(row: Any) -> tuple[str, str, Any, Any, Any]:
    if isinstance(row, dict):
        return (
            str(row["table_schema"]),
            str(row["table_name"]),
            row["can_insert"],
            row["can_update"],
            row["can_delete"],
        )
    return str(row[0]), str(row[1]), row[2], row[3], row[4]
