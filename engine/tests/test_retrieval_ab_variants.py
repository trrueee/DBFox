from __future__ import annotations

import pytest

from engine.evaluation.retrieval_ab.metrics import RetrievalHit
from engine.evaluation.retrieval_ab.variants import (
    SUPPORTED_VARIANTS,
    fuse_rrf,
    normalize_variant_names,
)


def test_normalize_variant_names_preserves_order_and_rejects_unknown() -> None:
    assert normalize_variant_names("keyword, vector,hybrid") == ("keyword", "vector", "hybrid")
    assert normalize_variant_names(("hybrid", "keyword")) == ("hybrid", "keyword")
    assert SUPPORTED_VARIANTS == ("keyword", "vector", "hybrid")

    with pytest.raises(ValueError, match="Unsupported retrieval variant"):
        normalize_variant_names("keyword,graph")


def test_rrf_fusion_deduplicates_by_table_and_column_with_rank_metadata() -> None:
    keyword = (
        RetrievalHit(type="table", table_name="singer", score=12.0, matched_fields=("table_name",)),
        RetrievalHit(type="column", table_name="concert", column_name="year", score=8.0),
        RetrievalHit(type="table", table_name="stadium", score=4.0),
    )
    vector = (
        RetrievalHit(type="table", table_name="concert", score=10.0),
        RetrievalHit(type="table", table_name="singer", score=9.0, matched_fields=("ai_description",)),
        RetrievalHit(type="column", table_name="concert", column_name="year", score=7.0),
    )

    fused = fuse_rrf(keyword, vector, limit=3, k=60)

    assert tuple(hit.key for hit in fused) == (
        ("table", "singer", None),
        ("column", "concert", "year"),
        ("table", "concert", None),
    )
    singer = fused[0]
    assert singer.keyword_rank == 1
    assert singer.vector_rank == 2
    assert singer.matched_by == ("keyword", "vector")
    assert singer.matched_fields == ("ai_description", "table_name")
    assert "keyword rank 1" in str(singer.reason)
    assert "vector rank 2" in str(singer.reason)


def test_rrf_fusion_keeps_single_source_hits_explainable() -> None:
    fused = fuse_rrf(
        keyword_results=(RetrievalHit(type="table", table_name="orders", score=3.0),),
        vector_results=(),
        limit=10,
    )

    assert len(fused) == 1
    assert fused[0].table_name == "orders"
    assert fused[0].matched_by == ("keyword",)
    assert fused[0].keyword_rank == 1
    assert fused[0].vector_rank is None
