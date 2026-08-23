from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine.migrations.data_dlc_state import migrate_legacy_data_sources
from engine.models import DataSource, Project


def test_data_import_preserves_database_resource_ids_and_is_replay_safe(
    db_session,
    tmp_path: Path,
) -> None:
    project = Project(id="data-project", name="Data Project")
    first = DataSource(
        id="database-billing",
        project_id=project.id,
        name="Billing",
        db_type="mysql",
        host="db.internal",
        port=3306,
        database_name="billing",
        username="analyst",
        password_credential_id="credential:billing",
        connection_generation=4,
        catalog_revision=9,
        is_read_only=True,
        env="prod",
    )
    second = DataSource(
        id="database-analytics",
        project_id=project.id,
        name="Analytics",
        db_type="postgresql",
        host="analytics.internal",
        port=5432,
        database_name="analytics",
        connection_generation=2,
    )
    db_session.add_all([project, first, second])
    db_session.commit()
    target = tmp_path / "dlcs" / "data" / "dbfox.data"

    result = migrate_legacy_data_sources(db_session, data_path=target)
    assert result.source_row_count == 2
    assert result.imported_profile_count == 2
    assert result.imported_database_count == 2
    with sqlite3.connect(target / "state.sqlite3") as connection:
        resources = connection.execute(
            "SELECT id, database_name, display_name, catalog_revision FROM database_resources ORDER BY id"
        ).fetchall()
        profiles = connection.execute(
            "SELECT name, provider, host, connection_generation, password_credential_ref "
            "FROM connection_profiles ORDER BY name"
        ).fetchall()
    assert resources == [
        ("database-analytics", "analytics", "Analytics", 0),
        ("database-billing", "billing", "Billing", 9),
    ]
    assert profiles == [
        ("Analytics", "postgresql", "analytics.internal", 2, None),
        ("Billing", "mysql", "db.internal", 4, "credential:billing"),
    ]

    replay = migrate_legacy_data_sources(db_session, data_path=target)
    assert replay.source_row_count == 2
    assert replay.imported_profile_count == 0
    assert replay.imported_database_count == 0


def test_data_import_rejects_conflicting_target_state(db_session, tmp_path: Path) -> None:
    project = Project(id="conflict-project", name="Conflict Project")
    datasource = DataSource(
        id="database-conflict",
        project_id=project.id,
        name="Original",
        db_type="sqlite",
        database_name="C:/data/original.db",
    )
    db_session.add_all([project, datasource])
    db_session.commit()
    target = tmp_path / "dlcs" / "data" / "dbfox.data"
    migrate_legacy_data_sources(db_session, data_path=target)
    with sqlite3.connect(target / "state.sqlite3") as connection:
        connection.execute(
            "UPDATE database_resources SET display_name = 'Tampered' WHERE id = 'database-conflict'"
        )
        connection.commit()
    with pytest.raises(RuntimeError, match="Conflicting staged"):
        migrate_legacy_data_sources(db_session, data_path=target)
