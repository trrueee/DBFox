"""R5.2 cutover contracts for legacy Core GitHub durable data."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text

from engine.db import build_alembic_config, build_metadata_engine
from engine.github.migration import (
    GithubBindingRecord,
    GithubDataMigrationError,
    TransitionalGithubBindingStore,
    github_dlc_data_path,
    migrate_legacy_github_data,
)
from engine.github.repository import list_github_bindings
from engine.models import GithubRepositoryBinding, Project


def _legacy_binding(*, binding_id: str = "legacy-binding") -> GithubRepositoryBinding:
    return GithubRepositoryBinding(
        id=binding_id,
        project_id="legacy-project",
        owner="astral-sh",
        repository="uv",
        ref_name="main",
        resolved_revision="a" * 40,
        default_branch="main",
        description="legacy durable binding",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        updated_at=datetime(2026, 1, 2, 3, 4, 6),
    )


def _seed_legacy_binding(db_session, *, binding_id: str = "legacy-binding") -> None:
    db_session.add(Project(id="legacy-project", name="Legacy project"))
    db_session.commit()
    db_session.add(_legacy_binding(binding_id=binding_id))
    db_session.commit()


def test_cutover_is_idempotent_and_runtime_never_falls_back_to_core(db_session) -> None:
    _seed_legacy_binding(db_session)
    data_path = github_dlc_data_path(db_session.get_bind())

    first = migrate_legacy_github_data(db_session, data_path=data_path)
    second = migrate_legacy_github_data(db_session, data_path=data_path)

    assert first.source_row_count == 1
    assert first.target_changed is True
    assert second.source_fingerprint == first.source_fingerprint
    assert second.target_changed is False

    # Simulate a stale/older Core writer after cutover.  The compatibility
    # runtime reads only DLC state and therefore does not observe this change.
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

    restarted_store = TransitionalGithubBindingStore(data_path)
    restarted_binding = restarted_store.get_binding("legacy-binding")
    assert restarted_binding is not None
    assert restarted_binding.resolved_revision == "a" * 40
    assert (
        list_github_bindings(db_session, "legacy-project")[0].resolved_revision
        == "a" * 40
    )


def test_failed_target_copy_preserves_legacy_rows(db_session, tmp_path: Path) -> None:
    _seed_legacy_binding(db_session)
    data_path = tmp_path / "dlc-data"
    store = TransitionalGithubBindingStore(data_path)
    store.create_binding(
        GithubBindingRecord(
            id="legacy-binding",
            project_id="legacy-project",
            owner="conflict",
            repository="conflict",
            ref_name="main",
            resolved_revision="c" * 40,
            default_branch="main",
            description=None,
            created_at=datetime(2026, 1, 2, 3, 4, 5),
            updated_at=datetime(2026, 1, 2, 3, 4, 6),
        )
    )

    with pytest.raises(GithubDataMigrationError, match="conflicting non-migration"):
        migrate_legacy_github_data(db_session, data_path=data_path)

    legacy = db_session.get(GithubRepositoryBinding, "legacy-binding")
    assert legacy is not None
    assert legacy.owner == "astral-sh"
    assert legacy.resolved_revision == "a" * 40
    target = store.get_binding("legacy-binding")
    assert target is not None
    assert target.owner == "conflict"


def test_retry_after_post_commit_validation_failure_is_safe(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_legacy_binding(db_session)
    data_path = tmp_path / "dlc-data"
    original_validate = TransitionalGithubBindingStore.validate_legacy_rows

    def fail_validation(self, rows):  # type: ignore[no-untyped-def]
        raise GithubDataMigrationError("injected validation failure")

    monkeypatch.setattr(
        TransitionalGithubBindingStore, "validate_legacy_rows", fail_validation
    )
    with pytest.raises(GithubDataMigrationError, match="injected"):
        migrate_legacy_github_data(db_session, data_path=data_path)

    # The target transaction committed, while the source remains untouched.
    assert (
        TransitionalGithubBindingStore(data_path).get_binding("legacy-binding")
        is not None
    )
    assert db_session.get(GithubRepositoryBinding, "legacy-binding") is not None

    monkeypatch.setattr(
        TransitionalGithubBindingStore,
        "validate_legacy_rows",
        original_validate,
    )
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
        assert (
            source.execute(
                "SELECT COUNT(*) FROM github_repository_bindings"
            ).fetchone()[0]
            == 1
        )
        assert source.execute("SELECT version_num FROM alembic_version").fetchone()[
            0
        ] == ("d5e6f7a8b9c1")
    target_path = tmp_path / "dlcs" / "data" / "dbfox.github" / "state.sqlite3"
    with sqlite3.connect(target_path) as target:
        assert (
            target.execute(
                "SELECT resolved_revision FROM repository_bindings WHERE id = 'legacy-binding'"
            ).fetchone()[0]
            == "a" * 40
        )

    # A completed revision does not replay or mutate the historical source.
    command.upgrade(config, "head")
    with sqlite3.connect(target_path) as target:
        assert (
            target.execute("SELECT COUNT(*) FROM repository_bindings").fetchone()[0]
            == 1
        )
