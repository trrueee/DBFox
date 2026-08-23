from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text

from engine.migrations.workspace_dlc_state import migrate_legacy_workspace_data
from engine.models import Project


def test_workspace_import_is_replay_safe_and_clears_core_fact_after_validation(
    db_session,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = Project(
        id="workspace-project",
        name="Workspace Project",
    )
    db_session.add(project)
    db_session.commit()
    # Reconstruct the historical Core schema at the migration boundary. The
    # current Project model deliberately has no workspace field.
    db_session.execute(text("ALTER TABLE projects ADD COLUMN workspace_root VARCHAR"))
    db_session.execute(
        text("UPDATE projects SET workspace_root = :root WHERE id = :project_id"),
        {"root": str(workspace), "project_id": project.id},
    )
    db_session.commit()
    target = tmp_path / "dlcs" / "data" / "dbfox.workspace"

    result = migrate_legacy_workspace_data(db_session, data_path=target)
    db_session.commit()
    assert result.source_row_count == 1
    assert db_session.execute(
        text("SELECT workspace_root FROM projects WHERE id = :project_id"),
        {"project_id": project.id},
    ).scalar_one() is None

    with sqlite3.connect(target / "state.sqlite3") as connection:
        row = connection.execute(
            "SELECT id, project_id, root_path, root_digest FROM workspace_bindings"
        ).fetchone()
    assert row is not None
    assert row[0] == row[1] == "workspace-project"
    assert Path(row[2]) == workspace.resolve()
    assert len(row[3]) == 16

    replay = migrate_legacy_workspace_data(db_session, data_path=target)
    db_session.commit()
    assert replay.source_row_count == 0
    with sqlite3.connect(target / "state.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM workspace_bindings").fetchone()[0] == 1
