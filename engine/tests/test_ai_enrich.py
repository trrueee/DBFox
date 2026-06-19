from __future__ import annotations

import uuid

from engine.ai_enrich import ai_enrich_catalog
from engine.models import SchemaColumn, SchemaTable


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

    result = ai_enrich_catalog(db_session, test_datasource.id)

    assert result["ai_enriched"] is True
    assert result["enriched_count"] == 12
    assert batch_sizes
    assert max(batch_sizes) <= 8
