from __future__ import annotations

from engine.models import SchemaTable


def test_list_tables_syncs_empty_catalog_before_returning(db_session, monkeypatch):
    from engine.api import datasources as datasource_api

    calls: list[str] = []

    def fake_sync_schema(db, datasource_id: str):
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
        db.commit()
        return {"synced": True}

    monkeypatch.setattr(datasource_api, "sync_schema", fake_sync_schema)

    result = datasource_api.api_list_tables(datasource_id="ds-1", db=db_session)

    assert calls == ["ds-1"]
    assert [table["table_name"] for table in result] == ["xhs_published_notes"]
    assert result[0]["module_tag"] == "creatorhub"
