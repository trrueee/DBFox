"""Data authority must survive source changes and concurrent restore cutover."""
from contextlib import contextmanager
import inspect
import sqlite3
import time

import pytest

from dlcs.dbfox_data.backend.connection import DataConnectionBoundary
from dlcs.dbfox_data.backend.store import DataStateStore
from dlcs.dbfox_data.backend.workbench import DataCatalogWorkbench
from dlcs.dbfox_data.backend import backup as backup_module
from dbfox_dlc_api import ToolInputError


@pytest.fixture
def sources(tmp_path):
    paths = [tmp_path / name for name in ("A.sqlite", "B.sqlite", "C.sqlite")]
    for index, path in enumerate(paths):
        with sqlite3.connect(path) as connection:
            connection.execute(f"CREATE TABLE source_{index}(n INTEGER)")
    store = DataStateStore(tmp_path / "data")
    values = {name: None for name in inspect.signature(store.create_profile).parameters}
    values.update(project_id="project", name="synthetic", provider="sqlite", is_read_only=True,
                  environment="dev", ssh_enabled=False, ssl_enabled=False, ssl_verify_identity=True,
                  initial_database_name=str(paths[0]))
    created = store.create_profile(**values)
    database = created.databases[0]
    return store, database, paths


def test_source_change_invalidates_catalog_and_late_reflection(sources):
    store, database, paths = sources
    workbench = DataCatalogWorkbench(store, DataConnectionBoundary(lambda *_: None))
    old = store.resolve_project_database("project", database.id)
    workbench.refresh(old, invocation_id="first")
    store.update_database(project_id="project", database_id=database.id, expected_generation=1,
                          database_name=str(paths[1]), display_name="B")
    current = store.resolve_project_database("project", database.id)
    assert workbench.overview(current).catalog_status == "uninitialized"
    assert store.list_catalog_tables(database.id, after=None, limit=20, name_filter=None)[0] == []
    with pytest.raises(ValueError, match="version|generation"):
        workbench.refresh(old, invocation_id="late")
    workbench.refresh(current, invocation_id="current")
    tables, _ = store.list_catalog_tables(database.id, after=None, limit=20, name_filter=None)
    assert [table["table_name"] for table in tables] == ["source_1"]


def test_restore_cannot_overwrite_a_newer_binding(sources, monkeypatch):
    store, database, paths = sources
    handle = store.resolve_project_database("project", database.id)
    backup = store.create_backup_record(project_id="project", database_resource_id=database.id,
                                       resource_version=handle.scope_version,
                                       source_database_name=str(paths[0]), label=None, file_name="synthetic")
    store.complete_backup_record(backup.record.id, file_size_bytes=1, checksum_sha256="0" * 64)
    original_connect = store._connect
    changed = False

    class InterleavedConnection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, parameters=()):
            nonlocal changed
            if "UPDATE database_resources" in sql and "catalog_revision = 0" in sql and not changed:
                changed = True
                store.update_database(project_id="project", database_id=database.id, expected_generation=1,
                                      database_name=str(paths[1]), display_name="B")
            return self.connection.execute(sql, parameters)

    @contextmanager
    def connect():
        with original_connect() as connection:
            yield InterleavedConnection(connection)

    monkeypatch.setattr(store, "_connect", connect)
    with pytest.raises(ValueError, match="version changed"):
        store.commit_sqlite_restore(project_id="project", backup_id=backup.record.id,
                                    database_resource_id=database.id,
                                    expected_resource_version=handle.scope_version,
                                    source_database_name=str(paths[0]), target_database_name=str(paths[2]),
                                    validated_table_count=1)
    assert changed
    current = store.resolve_project_database("project", database.id)
    assert current.database.database_name == str(paths[1])
    assert current.scope_version == "1:2"
    with original_connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM restore_operations").fetchone()[0] == 0


def test_profile_change_invalidates_every_owned_catalog(sources):
    store, database, _ = sources
    workbench = DataCatalogWorkbench(store, DataConnectionBoundary(lambda *_: None))
    old = store.resolve_project_database("project", database.id)
    workbench.refresh(old, invocation_id="first")
    profile = old.profile.model_dump()
    values = {name: profile.get(name) for name in inspect.signature(store.update_profile).parameters}
    values.update(profile_id=old.profile.id, expected_generation=1, name="updated")
    store.update_profile(**values)
    current = store.resolve_project_database("project", database.id)
    assert current.scope_version == "2:1"
    assert workbench.overview(current).catalog_status == "uninitialized"
    with pytest.raises(ValueError, match="version"):
        workbench.refresh(old, invocation_id="late-profile")


def test_v4_catalog_is_untrusted_until_fenced_refresh(sources):
    store, database, _ = sources
    workbench = DataCatalogWorkbench(store, DataConnectionBoundary(lambda *_: None))
    handle = store.resolve_project_database("project", database.id)
    workbench.refresh(handle, invocation_id="before-upgrade")
    with store._connect() as connection, connection:
        connection.execute("ALTER TABLE database_resources DROP COLUMN catalog_source_version")
        connection.execute("PRAGMA user_version = 4")
    reopened = DataStateStore(store.database_path.parent)
    assert reopened.catalog_state(database.id)["refreshed_at"] is None
    assert reopened.list_catalog_tables(database.id, after=None, limit=20, name_filter=None)[0] == []
    DataCatalogWorkbench(reopened, DataConnectionBoundary(lambda *_: None)).refresh(handle, invocation_id="after-upgrade")
    assert reopened.catalog_state(database.id)["table_count"] == 1


def test_duplicate_result_columns_are_rejected_before_serialization(sources):
    store, database, _ = sources
    handle = store.resolve_project_database("project", database.id)
    with pytest.raises(ToolInputError, match="unique|alias"):
        DataConnectionBoundary(lambda *_: None).execute_readonly(
            handle, "SELECT 1 AS x, 2 AS x FROM source_0", invocation_id="duplicate")
    with sqlite3.connect(handle.database.database_name) as connection:
        connection.execute("INSERT INTO source_0 VALUES (0)")
    result = DataConnectionBoundary(lambda *_: None).execute_readonly(
        handle, "SELECT 1 AS x, 2 AS X FROM source_0", invocation_id="distinct-case-aliases")
    assert result.rows == [{"x": "1", "X": "2"}]


def test_busy_backup_has_deadline_and_cleans_staging(sources, monkeypatch):
    store, database, paths = sources
    monkeypatch.setattr(backup_module, "BACKUP_TIMEOUT_SECONDS", 0.15, raising=False)
    service = backup_module.DataBackupService(store, store.database_path.parent)
    locked = sqlite3.connect(paths[0])
    locked.execute("BEGIN EXCLUSIVE")
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            service.create(project_id="project", database_id=database.id, label=None)
    finally:
        locked.rollback()
        locked.close()
    assert time.monotonic() - started < 2
    assert not list(service._backup_root.iterdir())
    assert store.list_backups("project", database.id)[0].status == "failed"
