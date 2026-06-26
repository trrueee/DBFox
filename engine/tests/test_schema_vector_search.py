from __future__ import annotations

import json
import os
from collections.abc import Sequence

import pytest

from engine.models import SchemaSearchDoc
from engine.tools.db.search import db_search


def _add_doc(
    db_session,
    *,
    datasource_id: str,
    entity_type: str,
    entity_id: str,
    table_name: str,
    search_text: str,
    column_name: str | None = None,
) -> SchemaSearchDoc:
    doc = SchemaSearchDoc(
        datasource_id=datasource_id,
        entity_type=entity_type,
        entity_id=entity_id,
        table_name=table_name,
        column_name=column_name,
        name=column_name or table_name,
        search_text=search_text,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_vector_search_builds_schema_embeddings_and_ranks_by_cosine(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    _add_doc(
        db_session,
        datasource_id=test_datasource.id,
        entity_type="table",
        entity_id="orders-doc",
        table_name="orders",
        search_text="orders revenue payment amount",
    )
    _add_doc(
        db_session,
        datasource_id=test_datasource.id,
        entity_type="table",
        entity_id="customers-doc",
        table_name="customers",
        search_text="customers profile email",
    )

    def fake_embed_texts(texts: Sequence[str], **_kwargs) -> list[list[float]]:
        vectors = {
            "orders revenue payment amount": [1.0, 0.0, 0.0],
            "customers profile email": [0.0, 1.0, 0.0],
            "revenue": [1.0, 0.0, 0.0],
        }
        return [vectors[str(text)] for text in texts]

    monkeypatch.setattr("engine.tools.db.embedding.embed_texts", fake_embed_texts)
    monkeypatch.setenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "vector")

    result = db_search(db_session, test_datasource.id, "revenue", 5)

    assert result["engine"] == "vector"
    assert result["vector_available"] is True
    assert result["embedding_build_time_ms"] >= 0
    assert result["results"][0]["table_name"] == "orders"
    assert result["results"][0]["matched_by"] == ["vector"]
    assert result["results"][0]["vector_rank"] == 1


def test_vector_embedding_rebuilds_only_stale_schema_docs(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    doc = _add_doc(
        db_session,
        datasource_id=test_datasource.id,
        entity_type="table",
        entity_id="orders-doc",
        table_name="orders",
        search_text="orders amount",
    )
    calls: list[list[str]] = []

    def fake_embed_texts(texts: Sequence[str], **_kwargs) -> list[list[float]]:
        batch = [str(text) for text in texts]
        calls.append(batch)
        return [[float(len(text)), 1.0] for text in batch]

    monkeypatch.setattr("engine.tools.db.embedding.embed_texts", fake_embed_texts)
    from engine.tools.db.embedding import ensure_schema_embeddings
    from engine.models import SchemaSearchEmbedding

    first = ensure_schema_embeddings(db_session, test_datasource.id, model="fake", dimension=2)
    second = ensure_schema_embeddings(db_session, test_datasource.id, model="fake", dimension=2)
    doc.search_text = "orders gross merchandise value"
    db_session.commit()
    third = ensure_schema_embeddings(db_session, test_datasource.id, model="fake", dimension=2)

    stored = db_session.query(SchemaSearchEmbedding).filter_by(entity_id="orders-doc").one()
    assert first.built_count == 1
    assert second.built_count == 0
    assert third.built_count == 1
    assert calls == [["orders amount"], ["orders gross merchandise value"]]
    assert json.loads(stored.embedding_json) == [30.0, 1.0]


def test_vector_embedding_batches_requests_at_configured_size(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    for index in range(11):
        _add_doc(
            db_session,
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id=f"doc-{index}",
            table_name=f"table_{index}",
            search_text=f"table {index}",
        )
    batch_sizes: list[int] = []

    def fake_embed_texts(texts: Sequence[str], **_kwargs) -> list[list[float]]:
        batch_sizes.append(len(texts))
        return [[float(index), 0.0] for index, _text in enumerate(texts)]

    monkeypatch.setattr("engine.tools.db.embedding.embed_texts", fake_embed_texts)
    from engine.tools.db.embedding import ensure_schema_embeddings

    result = ensure_schema_embeddings(db_session, test_datasource.id, model="fake", dimension=2, batch_size=10)

    assert result.built_count == 11
    assert batch_sizes == [10, 1]


def test_vector_mode_returns_structured_unavailable_response_without_secret(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    _add_doc(
        db_session,
        datasource_id=test_datasource.id,
        entity_type="table",
        entity_id="orders-doc",
        table_name="orders",
        search_text="orders amount",
    )
    secret = "test-secret-that-must-not-leak"
    monkeypatch.setenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "vector")
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    def fail_embed_texts(_texts: Sequence[str], **_kwargs) -> list[list[float]]:
        raise RuntimeError(f"provider rejected key {secret}")

    monkeypatch.setattr("engine.tools.db.embedding.embed_texts", fail_embed_texts)

    result = db_search(db_session, test_datasource.id, "orders", 5)

    assert result["engine"] == "vector_unavailable"
    assert result["vector_available"] is False
    assert result["results"] == []
    assert secret not in result["error"]
    assert "provider rejected key" not in result["error"]


def test_hybrid_search_fuses_keyword_and_vector_results_with_rrf(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    _add_doc(
        db_session,
        datasource_id=test_datasource.id,
        entity_type="table",
        entity_id="orders-doc",
        table_name="orders",
        search_text="orders amount revenue",
    )
    _add_doc(
        db_session,
        datasource_id=test_datasource.id,
        entity_type="table",
        entity_id="payments-doc",
        table_name="payments",
        search_text="payments transaction settlement",
    )

    def fake_embed_texts(texts: Sequence[str], **_kwargs) -> list[list[float]]:
        vectors = {
            "orders amount revenue": [0.6, 0.4],
            "payments transaction settlement": [1.0, 0.0],
            "revenue": [1.0, 0.0],
        }
        return [vectors[str(text)] for text in texts]

    monkeypatch.setattr("engine.tools.db.embedding.embed_texts", fake_embed_texts)
    monkeypatch.setenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "hybrid")
    monkeypatch.setenv("DBFOX_RETRIEVAL_KEYWORD_TOP_K", "5")
    monkeypatch.setenv("DBFOX_RETRIEVAL_VECTOR_TOP_K", "5")

    result = db_search(db_session, test_datasource.id, "revenue", 5)

    assert result["engine"] == "hybrid"
    assert result["vector_available"] is True
    assert result["results"][0]["table_name"] == "orders"
    assert result["results"][0]["matched_by"] == ["keyword", "vector"]
    assert result["results"][0]["keyword_rank"] == 1
    assert result["results"][0]["vector_rank"] == 2
    assert "keyword rank 1" in result["results"][0]["reason"]
