"""P2 publication contracts for ``DataSource.catalog_revision``."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from engine.ai_enrich import ai_enrich_catalog
from engine.environment.authoritative_inventory import AuthoritativeInventory
from engine.environment.inventory import SchemaInventory
from engine.environment.schema_catalog_sync import (
    SchemaCatalogSync,
    bump_catalog_revision,
    ensure_catalog,
)
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import DataSource, SchemaColumn, SchemaTable
from engine.tools.builtin.catalog import CatalogOverviewTool
from engine.tools.builtin.contracts import EmptyInput
from engine.tools.runtime.context import ToolRunContext


def _revision(db_session, datasource_id: str) -> int:
    return int(
        db_session.query(DataSource.catalog_revision)
        .filter(DataSource.id == datasource_id)
        .scalar()
    )


def _empty_inventory(datasource_id: str) -> AuthoritativeInventory:
    return AuthoritativeInventory.from_completed_inventory(
        SchemaInventory(datasource_id=datasource_id, dialect="sqlite")
    )


def test_initial_catalog_revision_is_zero(db_session, test_datasource) -> None:
    db_session.commit()
    assert _revision(db_session, test_datasource.id) == 0


def test_successful_publication_bumps_catalog_revision(
    db_session,
    test_datasource,
) -> None:
    result = ensure_catalog(db_session, test_datasource.id, ai_enrich=False)
    db_session.commit()

    assert result.catalog_revision == 1
    assert _revision(db_session, test_datasource.id) == 1


def test_failed_publication_does_not_bump_catalog_revision(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_catalog(db_session, test_datasource.id, ai_enrich=False)
    db_session.commit()
    revision = _revision(db_session, test_datasource.id)
    assert revision == 1

    def fail_search_rebuild(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected catalog rebuild failure")

    monkeypatch.setattr(
        "engine.environment.schema_catalog_sync.rebuild_search_docs",
        fail_search_rebuild,
    )
    with pytest.raises(RuntimeError, match="injected catalog rebuild failure"):
        SchemaCatalogSync().sync_authoritative(
            db_session,
            _empty_inventory(test_datasource.id),
        )

    assert _revision(db_session, test_datasource.id) == revision


def test_catalog_overview_freezes_execution_time_revision(
    db_session,
    test_datasource,
) -> None:
    result = ensure_catalog(db_session, test_datasource.id, ai_enrich=False)
    db_session.commit()
    revision = result.catalog_revision
    assert revision is not None

    context = ToolRunContext.for_invocation(
        request=SimpleNamespace(
            datasource_id=test_datasource.id,
            datasource_generation=test_datasource.connection_generation,
            session_id="session-revision",
            run_id="run-revision",
            execution_id="exec-revision",
        ),
        idempotency_key="catalog-revision-overview",
        raw_input={},
        resources={"database": db_session},
    )
    output = CatalogOverviewTool().run(EmptyInput(), context)
    facts = CatalogOverviewTool().project_observation(
        status="success",
        output=output.model_dump(mode="json"),
        artifacts=[],
    ).facts

    assert output.catalog_revision == revision
    assert facts["catalog_revision"] == revision


def test_ai_enrich_batch_bumps_catalog_revision(
    db_session,
    test_datasource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = SchemaTable(
        id="revision-table",
        data_source_id=test_datasource.id,
        table_schema="main",
        table_name="revision_orders",
        table_type="BASE TABLE",
    )
    db_session.add(table)
    db_session.add(
        SchemaColumn(
            id="revision-column",
            table_id="revision-table",
            column_name="id",
            data_type="integer",
            column_type="INTEGER",
            is_primary_key=True,
        )
    )
    db_session.commit()
    assert _revision(db_session, test_datasource.id) == 0

    def fake_enrich_tables_batch(tables_context: list[dict[str, Any]], **_kwargs: object) -> dict[str, Any]:
        return {
            "tables": [
                {
                    "name": item["name"],
                    "ai_description": "测试表",
                    "semantic_tags": ["测试"],
                    "business_terms": ["测试"],
                    "aliases": [],
                    "table_role": "dim",
                    "grain": "one row per id",
                    "subject_area": "other",
                    "ai_confidence": 0.9,
                    "columns": [],
                }
                for item in tables_context
            ]
        }

    monkeypatch.setattr("engine.ai_enrich.enrich_tables_batch", fake_enrich_tables_batch)

    result = ai_enrich_catalog(
        db_session,
        test_datasource.id,
        llm_config=object(),
    )

    assert result["ai_enriched"] is True
    assert result["enriched_count"] == 1
    assert _revision(db_session, test_datasource.id) == 1


def test_concurrent_atomic_bumps_are_monotonic(
    db_session,
    test_datasource,
) -> None:
    """Two SQL-level bumps cannot lose an increment when writes serialize."""

    engine = db_session.get_bind()
    SessionLocal = sessionmaker(bind=engine)
    first = SessionLocal()
    first.execute(text("BEGIN IMMEDIATE"))
    first_revision = bump_catalog_revision(first, test_datasource.id)

    outcome: dict[str, int] = {}

    def second_bump() -> None:
        session = SessionLocal()
        try:
            revision = bump_catalog_revision(session, test_datasource.id)
            session.commit()
            outcome["revision"] = revision
        finally:
            session.close()

    thread = threading.Thread(target=second_bump)
    thread.start()
    thread.join(timeout=0.25)
    assert thread.is_alive() or "revision" not in outcome

    first.commit()
    thread.join(timeout=10)
    assert not thread.is_alive()

    assert first_revision == 1
    assert outcome["revision"] == 2
    assert _revision(db_session, test_datasource.id) == 2
