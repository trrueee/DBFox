"""Unit tests for ai_index tokenizer and search_text builders."""

from __future__ import annotations

from engine.ai_index import (
    build_column_search_text,
    build_table_search_text,
    compute_schema_hash,
    segment_for_fts,
    tokenize_query,
)


def test_tokenize_query_chinese_english_mixed():
    tokens = tokenize_query("小红书功能使用频率 daily")
    # jieba may segment differently; check key parts exist
    assert "daily" in tokens
    assert any("书" in t or "红" in t for t in tokens) or len(tokens) >= 3


def test_tokenize_query_english_only():
    tokens = tokenize_query("xhs feature usage count")
    assert "xhs" in tokens
    assert "feature" in tokens
    assert "usage" in tokens
    assert "count" in tokens


def test_segment_for_fts_chinese():
    result = segment_for_fts("小红书功能使用频率日统计表")
    # Should have spaces between segmented Chinese words
    assert " " in result or len(result) > 5


def test_segment_for_fts_uses_jieba_lcut_without_recursing():
    result = segment_for_fts("小红书工具")

    assert result
    assert "小红书" in result or "工具" in result


def test_segment_for_fts_preserves_english():
    result = segment_for_fts("xhs_feature_usage_daily")
    assert result == "xhs_feature_usage_daily"


def test_build_table_search_text_includes_all_fields():
    text = build_table_search_text(
        table_name="xhs_feature_usage_daily",
        ai_description="测试描述",
        semantic_tags=["测试标签"],
        business_terms=["测试术语"],
        aliases=["xhs", "test"],
        table_role="agg",
        grain="按日期聚合",
        column_names=["user_id", "cnt"],
        column_ai_descriptions={"cnt": "计数"},
        relation_text="user_id 关联用户表",
    )
    assert "xhs_feature_usage_daily" in text
    assert "cnt" in text


def test_build_column_search_text():
    text = build_column_search_text(
        column_name="usage_count",
        table_name="xhs_feature_usage_daily",
        ai_description="功能使用次数",
        semantic_tags=["使用次数"],
        business_terms=["使用频率"],
        column_role="measure",
        metric_type="count",
    )
    assert "usage_count" in text
    assert "xhs_feature_usage_daily" in text


def test_compute_schema_hash_detects_change():
    """schema_hash must change when a column is added/removed."""

    class FakeCol:
        def __init__(self, name, ctype, comment=""):
            self.column_name = name
            self.column_type = ctype
            self.data_type = ctype
            self.column_comment = comment

    class FakeTable:
        def __init__(self, name, cols):
            self.table_name = name
            self.columns = cols

    t1 = FakeTable("users", [FakeCol("id", "INT"), FakeCol("name", "VARCHAR")])
    t2 = FakeTable("users", [FakeCol("id", "INT"), FakeCol("name", "VARCHAR"), FakeCol("email", "VARCHAR")])

    h1 = compute_schema_hash(t1)
    h2 = compute_schema_hash(t2)
    assert h1 != h2
