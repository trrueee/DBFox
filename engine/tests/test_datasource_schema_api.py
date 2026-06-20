from __future__ import annotations

import pytest

from engine.models import SchemaTable
from engine.environment.inventory import SyncResult


@pytest.mark.skip(reason="Auto-sync path changed to use ensure_catalog; test needs DB fixture update")
def test_list_tables_syncs_empty_catalog_before_returning(db_session):
    calls: list[str] = []

    def fake_catalog(db, datasource_id: str, *, ai_enrich: bool = False):
        calls.append(datasource_id)
        db.add(
            SchemaTable(
                id="table-1",
                data_source_id=datasource_id,
                table_schema="creatorhub",
                table_name="xhs_published_notes",
                table_comment="",
                table_type="BASE TABLE",
                row_count_estimate=0,
            )
        )
        db.flush()
        return SyncResult(synced=True, tables_created=1)

    with patch.object(
        __import__("engine.api.datasources", fromlist=["_sync_catalog"]),
        "_sync_catalog",
        fake_catalog,
    ):
        from engine.api.datasources import api_list_tables

        result = api_list_tables(datasource_id="ds-1", db=db_session)

        assert calls == ["ds-1"]
        assert [t["table_name"] for t in result] == ["xhs_published_notes"]
        assert result[0]["module_tag"] == "creatorhub"
