"""Pytest fixtures for dbfox_agent tests."""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

import pytest

from dlcs.dbfox_data.backend.store import DataStateStore
from engine.models import DEFAULT_PROJECT_ID
from engine.runtime_composition import set_active_runtime_snapshot
from engine.runtime_paths import private_runtime_dir
from verification.tests.system.conftest import (
    _make_datasource,
    datasource_template_file,
    db_session,
    metadata_template_file,
)
from scripts.prepare_dev_system_dlcs import prepare_dev_system_dlcs


@pytest.fixture(scope="session", autouse=True)
def system_capability_dlcs():
    """Exercise Agent contracts against the same signed System DLCs as the app."""

    package_dir, manifest = prepare_dev_system_dlcs()
    previous_dir = os.environ.get("DBFOX_SYSTEM_DLC_DIR")
    previous_manifest = os.environ.get("DBFOX_SYSTEM_DLC_MANIFEST")
    os.environ["DBFOX_SYSTEM_DLC_DIR"] = str(package_dir)
    os.environ["DBFOX_SYSTEM_DLC_MANIFEST"] = str(manifest)
    set_active_runtime_snapshot(None)
    try:
        yield
    finally:
        set_active_runtime_snapshot(None)
        if previous_dir is None:
            os.environ.pop("DBFOX_SYSTEM_DLC_DIR", None)
        else:
            os.environ["DBFOX_SYSTEM_DLC_DIR"] = previous_dir
        if previous_manifest is None:
            os.environ.pop("DBFOX_SYSTEM_DLC_MANIFEST", None)
        else:
            os.environ["DBFOX_SYSTEM_DLC_MANIFEST"] = previous_manifest


@pytest.fixture
def test_datasource(
    system_capability_dlcs,
    db_session,
    tmp_path,
    datasource_template_file,
):
    """Seed the same SQLite database in the real dbfox.data System DLC state."""

    datasource = _make_datasource(db_session, tmp_path, datasource_template_file)
    store = DataStateStore(private_runtime_dir("dlcs") / "data" / "dbfox.data")
    created = store.create_profile(
        project_id=DEFAULT_PROJECT_ID,
        name=f"agent-test-{uuid4().hex}",
        provider="sqlite",
        host=None,
        port=None,
        username=None,
        password_credential_ref=None,
        is_read_only=True,
        environment="test",
        ssh_enabled=False,
        ssh_host=None,
        ssh_port=None,
        ssh_username=None,
        ssh_password_credential_ref=None,
        ssh_pkey_path=None,
        ssh_key_passphrase_credential_ref=None,
        ssl_enabled=False,
        ssl_ca_path=None,
        ssl_cert_path=None,
        ssl_key_path=None,
        ssl_verify_identity=True,
        initial_database_name=str(datasource.database_name),
        initial_database_display_name="Agent test database",
    )
    generated_id = created.databases[0].id
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE database_resources SET id = ? WHERE id = ?",
            (str(datasource.id), generated_id),
        )
        connection.commit()
    return datasource

__all__ = [
    "datasource_template_file",
    "db_session",
    "metadata_template_file",
    "test_datasource",
    "system_capability_dlcs",
]
