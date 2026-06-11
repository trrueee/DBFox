from engine.schema_sync import sync_schema
from engine.semantic import SchemaContextBuilder, SchemaLinker, SemanticAliasResolver


def test_alias_resolver_maps_business_terms() -> None:
    resolver = SemanticAliasResolver()
    matches = resolver.resolve("按客户统计 GMV 和订单金额")

    targets = {match.target for match in matches}
    assert "orders.total_amount" in targets
    assert "users" in targets


def test_schema_linker_selects_alias_tables_and_columns(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    result = SchemaLinker(db_session).link(
        datasource_id=test_datasource.id,
        question="按客户统计 GMV 和订单金额",
    )

    selected_tables = result.selected_table_names()
    assert result.original_table_count == 20
    assert len(selected_tables) < result.original_table_count
    assert "orders" in selected_tables
    assert "users" in selected_tables
    assert "orders.total_amount" in result.selected_column_names()

    reasons = result.reason_payload()
    assert any(item["targetType"] == "column" and item.get("column") == "total_amount" for item in reasons)
    assert any("alias_column_match" in " ".join(item["reasons"]) for item in reasons)


def test_schema_context_builder_keeps_create_table_shape_and_keys(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = SchemaLinker(db_session).link(
        datasource_id=test_datasource.id,
        question="按客户统计 GMV",
    )

    context = SchemaContextBuilder(db_session).build(result)

    assert "CREATE TABLE orders" in context
    assert "total_amount" in context
    assert "PRIMARY KEY" in context
    assert "REFERENCES users(id)" in context
