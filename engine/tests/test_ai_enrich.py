from __future__ import annotations

import uuid

import pytest

import engine.api.datasources.schema as schema_api
from engine.ai_index import enrich_tables_batch
from engine.ai_enrich import ai_enrich_catalog
from engine.environment.inventory import SchemaInventory
from engine.environment.schema_catalog_sync import SchemaCatalogSync
from engine.errors import DBFoxError
from engine.models import SchemaColumn, SchemaTable


SENTINEL = "provider-sentinel-not-a-redaction-pattern"


def test_ai_enrich_catalog_batches_tables_by_default(db_session, test_datasource, monkeypatch) -> None:
    batch_sizes: list[int] = []

    for i in range(12):
        table_id = str(uuid.uuid4())
        db_session.add(
            SchemaTable(
                id=table_id,
                data_source_id=test_datasource.id,
                table_schema="main",
                table_name=f"table_{i}",
                table_type="BASE TABLE",
            )
        )
        db_session.add(
            SchemaColumn(
                id=str(uuid.uuid4()),
                table_id=table_id,
                column_name="id",
                data_type="integer",
                column_type="INTEGER",
                is_nullable=False,
                is_primary_key=True,
            )
        )
    db_session.commit()

    def fake_enrich_tables_batch(tables_context, **kwargs):
        batch_sizes.append(len(tables_context))
        return {
            "tables": [
                {
                    "name": table["name"],
                    "ai_description": "测试表",
                    "semantic_tags": ["测试"],
                    "business_terms": ["测试"],
                    "aliases": [],
                    "table_role": "dim",
                    "grain": "one row per id",
                    "subject_area": "other",
                    "ai_confidence": 0.9,
                    "columns": [
                        {
                            "name": "id",
                            "ai_description": "主键",
                            "semantic_tags": ["主键"],
                            "business_terms": ["id"],
                            "aliases": [],
                            "column_role": "id",
                            "metric_type": None,
                            "ai_confidence": 0.9,
                        }
                    ],
                }
                for table in tables_context
            ]
        }

    monkeypatch.setattr("engine.ai_enrich.enrich_tables_batch", fake_enrich_tables_batch)

    result = ai_enrich_catalog(db_session, test_datasource.id, llm_config=object())

    assert result["ai_enriched"] is True
    assert result["enriched_count"] == 12
    assert batch_sizes
    assert max(batch_sizes) <= 8


def test_ai_enrich_does_not_use_environment_api_key(monkeypatch, db_session, test_datasource) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    table = SchemaTable(
        id=str(uuid.uuid4()),
        data_source_id=test_datasource.id,
        table_name="orders",
        table_schema="main",
        table_type="BASE TABLE",
        schema_hash="stale",
    )
    db_session.add(table)
    db_session.commit()

    result = ai_enrich_catalog(db_session, test_datasource.id)

    assert result["ai_enriched"] is False
    assert result["reason"] == "请先在设置中配置 LLM API Key。"


def test_enrich_retry_never_logs_or_rethrows_provider_error_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_provider(*_args, **_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr("engine.ai_index._call_llm", fail_provider)
    monkeypatch.setattr("engine.ai_index.time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError) as exc_info:
        enrich_tables_batch(
            [{"name": "orders"}],
            llm_config=object(),
            max_retries=1,
        )

    assert str(exc_info.value) == "LLM_ENRICH_FAILED"
    assert SENTINEL not in caplog.text


def test_catalog_enrichment_never_returns_or_logs_provider_error_text(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_session.add(
        SchemaTable(
            id=str(uuid.uuid4()),
            data_source_id=test_datasource.id,
            table_schema="main",
            table_name="orders",
            table_type="BASE TABLE",
            schema_hash="stale",
        )
    )
    db_session.commit()

    def fail_enrichment(*_args, **_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr("engine.ai_enrich.enrich_tables_batch", fail_enrichment)

    result = ai_enrich_catalog(db_session, test_datasource.id, llm_config=object())

    assert result["reason"] == "LLM_ENRICH_FAILED"
    assert result["errors"] == ["LLM_ENRICH_FAILED"]
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


def test_catalog_sync_records_a_fixed_enrichment_failure_for_config_errors(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_provider_config(*_args, **_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(
        "engine.llm.config.resolve_product_llm_config_from_credential",
        fail_provider_config,
    )

    result = SchemaCatalogSync().sync_inventory(
        db_session,
        test_datasource.id,
        SchemaInventory(datasource_id=test_datasource.id, dialect="sqlite"),
        ai_enrich=True,
        llm_credential_id="cred_llm_api_key_schema_sync_test",
    )

    assert result.ai_enrich_result == {
        "ai_enriched": False,
        "enriched_count": 0,
        "reason": "LLM_ENRICH_FAILED",
        "errors": ["LLM_ENRICH_FAILED"],
    }
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


def test_sync_api_replaces_unexpected_sync_error_with_a_fixed_public_message(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_sync(*_args, **_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(schema_api, "_sync_catalog", fail_sync)

    with pytest.raises(DBFoxError) as exc_info:
        schema_api.api_sync_schema(
            "ds-schema-sync-test",
            schema_api.SchemaSyncRequest(ai_enrich=True),
            db_session,
        )

    assert exc_info.value.code == "SYNC_FAILED"
    assert exc_info.value.message == "Schema synchronization failed."
    assert exc_info.value.__cause__ is None
    assert SENTINEL not in repr(exc_info.value)
    assert SENTINEL not in caplog.text


def test_schema_list_auto_sync_uses_the_fixed_public_failure_message(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_sync(*_args, **_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(schema_api, "load_schema_tables", lambda *_args: [])
    monkeypatch.setattr(schema_api, "_sync_catalog", fail_sync)

    with pytest.raises(DBFoxError) as exc_info:
        schema_api.api_list_tables("ds-schema-sync-test", db_session)

    assert exc_info.value.code == "SYNC_FAILED"
    assert exc_info.value.message == "Schema synchronization failed."
    assert exc_info.value.__cause__ is None
    assert SENTINEL not in repr(exc_info.value)
    assert SENTINEL not in caplog.text
