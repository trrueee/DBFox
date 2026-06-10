from __future__ import annotations


def check_sql_safety(sql: str) -> bool:
    """Return True if the SQL query only contains SELECT commands without DML/DDL."""
    if not sql:
        return False
    lower_sql = sql.lower()
    for forbidden in ("drop ", "delete ", "insert ", "update ", "alter ", "truncate "):
        if forbidden in lower_sql:
            return False
    return True
