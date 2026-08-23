"""Historical migration contracts for retired Core GitHub durable data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from engine.db import build_alembic_config, build_metadata_engine
from engine.migrations.github_dlc_state import (
    GithubDataMigrationError,
    GithubLegacyImportTarget,
    github_dlc_data_path,
    migrate_legacy_github_data,
)


def _seed_legacy_binding(db_session, *, binding_id: str = "legacy-binding") -> None:
    db_session.execute(
        text(
            """
            INSERT INTO projects (id, name, status, created_at, updated_at)
            VALUES ('legacy-project', 'Legacy project', 'active',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    db_session.execute(
        text(
            """
            INSERT INTO github_repository_bindings (
                id, project_id, owner, repository, ref_name,
                resolved_revision, default_branch, description,
                created_at, updated_at
            ) VALUES (
                :binding_id, 'legacy-project', 'astral-sh', 'uv', 'main',
                :revision, 'main', 'legacy durable binding',
                '2026-01-02T03:04:05', '2026-01-02T03:04:06'
            )
            """
        ),
        {"binding_id": binding_id, "revision": "a" * 40},
    )
    db_session.commit()


def _target_row(data_path: Path, binding_id: str = "legacy-binding") -> sqlite3.Row | None:
    with sqlite3.connect(data_path / "state.sqlite3") as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM repository_bindings WHERE id = ?", (binding_id,)
        ).fetchone()


def _seed_target_conflict(data_path: Path) -> None:
    target = GithubLegacyImportTarget(data_path)
    with sqlite3.connect(target.database_path) as connection:
        connection.execute(
            """
            INSERT INTO repository_bindings (
                id, project_id, owner, repository, ref_name,
                resolved_revision, default_branch, description,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-binding",
                "legacy-project",
                "conflict",
                "conflict",
                "main",
                "c" * 40,
                "main",
                None,
                "2026-01-02T03:04:05",
                "2026-01-02T03:04:06",
            ),
        )


def test_historical_import_is_idempotent_and_target_is_independent(db_session) -> None:
    _seed_legacy_binding(db_session)
    data_path = github_dlc_data_path(db_session.get_bind())

    first = migrate_legacy_github_data(db_session, data_path=data_path)
    second = migrate_legacy_github_data(db_session, data_path=data_path)

    assert first.source_row_count == 1
    assert first.target_changed is True
    assert second.source_fingerprint == first.source_fingerprint
    assert second.target_changed is False

    db_session.execute(
        text(
            """
            UPDATE github_repository_bindings
               SET resolved_revision = :revision
             WHERE id = 'legacy-binding'
            """
        ),
        {"revision": "b" * 40},
    )
    db_session.commit()

    target = _target_row(data_path)
    assert target is not None
    assert target["resolved_revision"] == "a" * 40


def test_failed_target_copy_preserves_legacy_rows(db_session, tmp_path: Path) -> None:
    _seed_legacy_binding(db_session)
    data_path = tmp_path / "dlc-data"
    _seed_target_conflict(data_path)

    with pytest.raises(GithubDataMigrationError, match="conflicting non-migration"):
        migrate_legacy_github_data(db_session, data_path=data_path)

    source = db_session.execute(
        text(
            "SELECT owner, resolved_revision FROM github_repository_bindings "
            "WHERE id = 'legacy-binding'"
        )
    ).mappings().one()
    assert source["owner"] == "astral-sh"
    assert source["resolved_revision"] == "a" * 40
    target = _target_row(data_path)
    assert target is not None
    assert target["owner"] == "conflict"


def test_retry_after_post_commit_validation_failure_is_safe(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_legacy_binding(db_session)
    data_path = tmp_path / "dlc-data"
    original_validate = GithubLegacyImportTarget.validate

    def fail_validation(self, rows):  # type: ignore[no-untyped-def]
        raise GithubDataMigrationError("injected validation failure")

    monkeypatch.setattr(GithubLegacyImportTarget, "validate", fail_validation)
    with pytest.raises(GithubDataMigrationError, match="injected"):
        migrate_legacy_github_data(db_session, data_path=data_path)

    assert _target_row(data_path) is not None
    assert db_session.execute(
        text(
            "SELECT COUNT(*) FROM github_repository_bindings "
            "WHERE id = 'legacy-binding'"
        )
    ).scalar_one() == 1

    monkeypatch.setattr(GithubLegacyImportTarget, "validate", original_validate)
    retried = migrate_legacy_github_data(db_session, data_path=data_path)
    assert retried.target_changed is False


def test_alembic_revision_commits_dlc_data_before_recording_head(
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "metadata.db"
    database_url = f"sqlite:///{metadata_path.as_posix()}"
    config = build_alembic_config(database_url)
    command.upgrade(config, "c5d6e7f8a9b0")

    metadata_engine = build_metadata_engine(database_url)
    try:
        with metadata_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO projects (id, name, status, created_at, updated_at)
                    VALUES ('legacy-project', 'Legacy project', 'active',
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO github_repository_bindings (
                        id, project_id, owner, repository, ref_name,
                        resolved_revision, default_branch, description,
                        created_at, updated_at
                    ) VALUES (
                        'legacy-binding', 'legacy-project', 'astral-sh', 'uv', 'main',
                        :revision, 'main', 'legacy durable binding',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"revision": "a" * 40},
            )
    finally:
        metadata_engine.dispose()

    command.upgrade(config, "head")

    with sqlite3.connect(metadata_path) as source:
        assert source.execute(
            "SELECT COUNT(*) FROM github_repository_bindings"
        ).fetchone()[0] == 1
        assert source.execute("SELECT version_num FROM alembic_version").fetchone()[
            0
        ] == ("d1e2f3a4b5c7")
    target_path = tmp_path / "dlcs" / "data" / "dbfox.github" / "state.sqlite3"
    with sqlite3.connect(target_path) as target:
        assert target.execute(
            "SELECT resolved_revision FROM repository_bindings "
            "WHERE id = 'legacy-binding'"
        ).fetchone()[0] == "a" * 40

    command.upgrade(config, "head")
    with sqlite3.connect(target_path) as target:
        assert target.execute(
            "SELECT COUNT(*) FROM repository_bindings"
        ).fetchone()[0] == 1
