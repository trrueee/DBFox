from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from engine.models import SchemaSearchDoc, SchemaSearchEmbedding, utcnow


DEFAULT_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-v4"
DEFAULT_EMBEDDING_DIMENSION = 1024
DEFAULT_EMBEDDING_BATCH_SIZE = 10

API_KEY_ENV_ORDER = (
    "DBFOX_EMBEDDING_API_KEY",
    "DASHSCOPE_API_KEY",
    "OPENAI_API_KEY",
    "QWEN_API_KEY",
)
BASE_URL_ENV_ORDER = (
    "DBFOX_EMBEDDING_BASE_URL",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
)


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    dimension: int
    batch_size: int
    api_key: str | None
    base_url: str


@dataclass(frozen=True)
class EmbeddingBuildResult:
    total_docs: int
    built_count: int
    stale_count: int
    embedding_build_time_ms: float
    model: str
    dimension: int


def resolve_embedding_config(
    *,
    model: str | None = None,
    dimension: int | None = None,
    batch_size: int | None = None,
) -> EmbeddingConfig:
    resolved_model = model or os.getenv("DBFOX_EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL
    resolved_dimension = dimension or _env_int("DBFOX_EMBEDDING_DIMENSION", DEFAULT_EMBEDDING_DIMENSION)
    resolved_batch_size = batch_size or _env_int("DBFOX_EMBEDDING_BATCH_SIZE", DEFAULT_EMBEDDING_BATCH_SIZE)
    resolved_batch_size = max(1, min(DEFAULT_EMBEDDING_BATCH_SIZE, resolved_batch_size))
    return EmbeddingConfig(
        model=resolved_model,
        dimension=resolved_dimension,
        batch_size=resolved_batch_size,
        api_key=_first_env_value(API_KEY_ENV_ORDER),
        base_url=_first_env_value(BASE_URL_ENV_ORDER) or DEFAULT_EMBEDDING_BASE_URL,
    )


def embed_texts(
    texts: Sequence[str],
    *,
    model: str | None = None,
    dimension: int | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    config = resolve_embedding_config(model=model, dimension=dimension)
    resolved_key = api_key or config.api_key
    if not resolved_key:
        raise RuntimeError("Embedding API key is not configured.")

    from openai import OpenAI

    client = OpenAI(api_key=resolved_key, base_url=base_url or config.base_url)
    response = client.embeddings.create(
        model=model or config.model,
        input=list(texts),
        dimensions=dimension or config.dimension,
        encoding_format="float",
    )
    return [[float(value) for value in item.embedding] for item in response.data]


def ensure_schema_embeddings(
    db: Session,
    datasource_id: str,
    *,
    model: str | None = None,
    dimension: int | None = None,
    batch_size: int | None = None,
) -> EmbeddingBuildResult:
    config = resolve_embedding_config(model=model, dimension=dimension, batch_size=batch_size)
    start = time.perf_counter()

    docs = (
        db.query(SchemaSearchDoc)
        .filter(SchemaSearchDoc.datasource_id == datasource_id)
        .order_by(SchemaSearchDoc.entity_type, SchemaSearchDoc.table_name, SchemaSearchDoc.column_name)
        .all()
    )
    existing_rows = (
        db.query(SchemaSearchEmbedding)
        .filter(
            SchemaSearchEmbedding.datasource_id == datasource_id,
            SchemaSearchEmbedding.embedding_model == config.model,
            SchemaSearchEmbedding.embedding_dimension == config.dimension,
        )
        .all()
    )
    existing_by_key = {
        _embedding_key(row.entity_type, row.entity_id): row
        for row in existing_rows
    }

    docs_by_key = {_embedding_key(doc.entity_type, doc.entity_id): doc for doc in docs}
    for key, row in list(existing_by_key.items()):
        if key not in docs_by_key:
            db.delete(row)
            existing_by_key.pop(key, None)

    stale_or_missing: list[SchemaSearchDoc] = []
    stale_count = 0
    for doc in docs:
        key = _embedding_key(doc.entity_type, doc.entity_id)
        current_hash = search_text_hash(doc.search_text or "")
        existing = existing_by_key.get(key)
        if existing is None:
            stale_or_missing.append(doc)
            continue
        if existing.search_text_hash != current_hash:
            stale_count += 1
            stale_or_missing.append(doc)

    built_count = 0
    for batch in _batched(stale_or_missing, config.batch_size):
        vectors = embed_texts(
            [doc.search_text or "" for doc in batch],
            model=config.model,
            dimension=config.dimension,
            api_key=config.api_key,
            base_url=config.base_url,
        )
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding provider returned an unexpected vector count.")
        for doc, vector in zip(batch, vectors, strict=True):
            key = _embedding_key(doc.entity_type, doc.entity_id)
            row = existing_by_key.get(key)
            if row is None:
                row = SchemaSearchEmbedding(
                    datasource_id=datasource_id,
                    entity_type=doc.entity_type,
                    entity_id=doc.entity_id,
                    embedding_model=config.model,
                    embedding_dimension=config.dimension,
                    search_text_hash=search_text_hash(doc.search_text or ""),
                    embedding_blob=pack_embedding(vector),
                    embedding_json=json.dumps([float(value) for value in vector], ensure_ascii=True),
                    synced_at=utcnow(),
                )
                db.add(row)
                existing_by_key[key] = row
            else:
                row.search_text_hash = search_text_hash(doc.search_text or "")
                row.embedding_blob = pack_embedding(vector)
                row.embedding_json = json.dumps([float(value) for value in vector], ensure_ascii=True)
                row.synced_at = utcnow()
            built_count += 1

    db.commit()
    return EmbeddingBuildResult(
        total_docs=len(docs),
        built_count=built_count,
        stale_count=stale_count,
        embedding_build_time_ms=round((time.perf_counter() - start) * 1000, 3),
        model=config.model,
        dimension=config.dimension,
    )


def vector_search_results(
    db: Session,
    datasource_id: str,
    query: str,
    limit: int,
    *,
    model: str | None = None,
    dimension: int | None = None,
    batch_size: int | None = None,
) -> tuple[list[dict[str, Any]], EmbeddingBuildResult]:
    config = resolve_embedding_config(model=model, dimension=dimension, batch_size=batch_size)
    build = ensure_schema_embeddings(
        db,
        datasource_id,
        model=config.model,
        dimension=config.dimension,
        batch_size=config.batch_size,
    )
    query_vector = embed_texts(
        [query],
        model=config.model,
        dimension=config.dimension,
        api_key=config.api_key,
        base_url=config.base_url,
    )[0]

    rows = (
        db.query(SchemaSearchDoc, SchemaSearchEmbedding)
        .join(
            SchemaSearchEmbedding,
            (SchemaSearchEmbedding.datasource_id == SchemaSearchDoc.datasource_id)
            & (SchemaSearchEmbedding.entity_type == SchemaSearchDoc.entity_type)
            & (SchemaSearchEmbedding.entity_id == SchemaSearchDoc.entity_id),
        )
        .filter(
            SchemaSearchDoc.datasource_id == datasource_id,
            SchemaSearchEmbedding.embedding_model == config.model,
            SchemaSearchEmbedding.embedding_dimension == config.dimension,
        )
        .all()
    )

    scored: list[dict[str, Any]] = []
    for doc, embedding in rows:
        if embedding.search_text_hash != search_text_hash(doc.search_text or ""):
            continue
        vector = unpack_embedding(embedding.embedding_blob)
        score = cosine_similarity(query_vector, vector)
        item = _doc_to_vector_result(doc, score)
        scored.append(item)

    scored.sort(key=lambda item: (-float(item["score"]), item["type"], item["name"]))
    for index, item in enumerate(scored[:limit], start=1):
        item["vector_rank"] = index
    return scored[:limit], build


def search_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack_embedding(vector: Sequence[float]) -> bytes:
    values = [float(value) for value in vector]
    return struct.pack(f"<{len(values)}f", *values)


def unpack_embedding(blob: bytes) -> list[float]:
    if not blob:
        return []
    count = len(blob) // 4
    return [float(value) for value in struct.unpack(f"<{count}f", blob)]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    dot = sum(float(left[i]) * float(right[i]) for i in range(length))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left[:length]))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right[:length]))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _doc_to_vector_result(doc: SchemaSearchDoc, score: float) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": doc.entity_type,
        "name": doc.name,
        "table_name": doc.table_name,
        "score": round(float(score), 6),
        "reasons": ["vector_cosine_similarity"],
        "matched_fields": ["search_text"],
        "matched_by": ["vector"],
        "reason": f"vector cosine score {score:.4f}",
    }
    if doc.entity_type == "table":
        item["ai_description"] = doc.ai_description or ""
        item["table_role"] = doc.table_role or ""
        try:
            item["semantic_tags"] = json.loads(doc.semantic_tags or "[]")
        except (json.JSONDecodeError, TypeError):
            item["semantic_tags"] = []
    if doc.entity_type == "column":
        item["column_name"] = doc.column_name or ""
        item["column_role"] = doc.column_role or ""
        item["metric_type"] = doc.metric_type or ""
    return item


def _batched(items: Sequence[SchemaSearchDoc], size: int) -> list[list[SchemaSearchDoc]]:
    return [list(items[index:index + size]) for index in range(0, len(items), size)]


def _embedding_key(entity_type: str, entity_id: str) -> tuple[str, str]:
    return (str(entity_type), str(entity_id))


def _first_env_value(names: Sequence[str]) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default
