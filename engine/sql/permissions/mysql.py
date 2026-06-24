from __future__ import annotations

import re
from typing import Any

from .base import PermissionProbe, PermissionReport, WRITE_PRIVILEGE_WARNING, managed_cursor


MYSQL_WRITE_PRIVILEGES = (
    "ALL PRIVILEGES",
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "DROP",
    "ALTER",
    "TRIGGER",
)


class MySQLPermissionProbe(PermissionProbe):
    def probe(self, conn: Any) -> PermissionReport:
        try:
            with managed_cursor(conn) as cursor:
                cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
                grants = [_grant_text(row) for row in cursor.fetchall()]
        except Exception as exc:
            return PermissionReport(
                readonly=False,
                writable_privileges=["UNKNOWN"],
                warnings=[WRITE_PRIVILEGE_WARNING],
                evidence={
                    "probe": "mysql_show_grants",
                    "error": str(exc),
                },
            )

        writable_privileges = _extract_writable_privileges(grants)
        warnings = [WRITE_PRIVILEGE_WARNING] if writable_privileges else []
        return PermissionReport(
            readonly=not writable_privileges,
            writable_privileges=writable_privileges,
            warnings=warnings,
            evidence={
                "probe": "mysql_show_grants",
                "grants": grants,
            },
        )


def _grant_text(row: Any) -> str:
    if isinstance(row, dict):
        return str(next(iter(row.values()), ""))
    if isinstance(row, (list, tuple)):
        return str(row[0]) if row else ""
    return str(row)


def _extract_writable_privileges(grants: list[str]) -> list[str]:
    found: list[str] = []
    for grant in grants:
        grant_upper = grant.upper()
        for privilege in MYSQL_WRITE_PRIVILEGES:
            if privilege == "ALL PRIVILEGES":
                matched = privilege in grant_upper
            else:
                matched = re.search(rf"\b{re.escape(privilege)}\b", grant_upper) is not None
            if matched and privilege not in found:
                found.append(privilege)
    return found
