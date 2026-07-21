"""SQLite-safe write transaction boundary for the Agent aggregate."""

from __future__ import annotations

from sqlalchemy.orm import Session


def begin_agent_write(session: Session) -> None:
    """Acquire the metadata writer before reading mutable Agent state.

    PostgreSQL-style ``SELECT FOR UPDATE`` is ignored by SQLite. DBFox is a
    local-first application, so the correct SQLite primitive is one short
    ``BEGIN IMMEDIATE`` transaction: it serializes writers while WAL continues
    to serve readers. The call is idempotent inside an already active physical
    transaction and remains a no-op for databases with real row locks.
    """

    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        return

    connection = session.connection()
    driver_connection = connection.connection.driver_connection
    if bool(getattr(driver_connection, "in_transaction", False)):
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")
