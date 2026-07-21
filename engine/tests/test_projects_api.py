from __future__ import annotations

import uuid

from sqlalchemy import event

from engine.api.projects import api_list_projects
from engine.models import DataSource, Project


def _datasource(project_id: str | None, name: str) -> DataSource:
    return DataSource(
        id=str(uuid.uuid4()),
        project_id=project_id,
        name=name,
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name=":memory:",
        username="",
        connection_generation=1,
        status="active",
    )


def test_list_projects_counts_datasources_with_grouped_sql(db_session) -> None:
    project_a = Project(id=str(uuid.uuid4()), name="Project A", status="active")
    project_b = Project(id=str(uuid.uuid4()), name="Project B", status="active")
    inactive = Project(id=str(uuid.uuid4()), name="Inactive", status="archived")
    db_session.add_all([project_a, project_b, inactive])
    db_session.add_all([
        _datasource(project_a.id, "a1"),
        _datasource(project_a.id, "a2"),
        _datasource(project_b.id, "b1"),
        _datasource(None, "orphan"),
        _datasource(inactive.id, "inactive"),
    ])
    db_session.commit()

    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(db_session.bind, "before_cursor_execute", capture_sql)
    try:
        result = api_list_projects(db_session)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture_sql)

    by_id = {item["id"]: item for item in result}
    assert by_id[project_a.id]["datasource_count"] == 2
    assert by_id[project_b.id]["datasource_count"] == 1
    assert inactive.id not in by_id

    datasource_selects = [
        statement
        for statement in statements
        if statement.startswith("select") and " from data_sources" in statement
    ]
    assert datasource_selects == [
        statement
        for statement in datasource_selects
        if "count(" in statement and " group by " in statement
    ]
