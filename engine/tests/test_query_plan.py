from unittest.mock import MagicMock

from engine.models import SchemaColumn, SchemaTable
from engine.schema_sync import sync_schema
from engine.semantic import QueryDimension, QueryMetric, QueryPlan, QueryPlanBuilder


def test_query_plan_daily_order_count(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    plan = QueryPlanBuilder(db_session).build(
        datasource_id=test_datasource.id,
        question="统计每天订单量",
        mode="offline",
    )

    assert "orders" in plan.tables
    assert any("COUNT" in (metric.expression or "") for metric in plan.metrics)
    assert any(
        "order" in (dimension.name or "").lower()
        for dimension in plan.dimensions
    )
    assert plan.warnings == []


def test_query_plan_top_selling_products(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)

    plan = QueryPlanBuilder(db_session).build(
        datasource_id=test_datasource.id,
        question="销量最高的商品",
        mode="offline",
    )

    assert plan.intent == "rank_products_by_sales_volume"
    assert "products" in plan.tables
    assert any("quantity" in (metric.source_column or "") for metric in plan.metrics)
    assert any(dimension.column == "products.name" for dimension in plan.dimensions)
    assert any("products" in (join.condition or "") for join in plan.joins)


def test_query_plan_offline_uses_schema_matching_without_domain_templates(db_session, test_datasource) -> None:
    students = SchemaTable(
        data_source_id=test_datasource.id,
        table_schema="main",
        table_name="students",
        table_comment="Learners enrolled in courses",
    )
    courses = SchemaTable(
        data_source_id=test_datasource.id,
        table_schema="main",
        table_name="courses",
        table_comment="Course catalog",
    )
    db_session.add_all([students, courses])
    db_session.flush()
    db_session.add_all(
        [
            SchemaColumn(table_id=students.id, column_name="id", data_type="int", is_primary_key=True),
            SchemaColumn(table_id=students.id, column_name="country", data_type="varchar"),
            SchemaColumn(table_id=students.id, column_name="age", data_type="int"),
            SchemaColumn(table_id=courses.id, column_name="id", data_type="int", is_primary_key=True),
            SchemaColumn(table_id=courses.id, column_name="title", data_type="varchar"),
        ]
    )
    db_session.commit()

    plan = QueryPlanBuilder(db_session).build(
        datasource_id=test_datasource.id,
        question="count students by country",
        mode="offline",
    )

    assert plan.intent == "schema_matched_aggregate"
    assert plan.tables == ["students"]
    assert any(metric.expression == "COUNT(*)" and metric.source_column == "students.id" for metric in plan.metrics)
    assert any(dimension.column == "students.country" for dimension in plan.dimensions)
    assert plan.warnings == []


def test_query_plan_validation_collects_missing_schema_warnings(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    plan = QueryPlan(
        intent="bad_plan",
        tables=["ghost_table", "orders"],
        metrics=[QueryMetric(name="bad_metric", expression="SUM(orders.fake_amount)", source_column="orders.fake_amount")],
        dimensions=[QueryDimension(name="ghost_dim", column="ghost_table.created_at", transform="DATE")],
        limit=100,
    )

    validated = QueryPlanBuilder(db_session).validate(test_datasource.id, plan)

    assert any("ghost_table" in warning for warning in validated.warnings)
    assert any("orders.fake_amount" in warning for warning in validated.warnings)


def test_query_plan_validation_checks_unqualified_columns_in_table_scope(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    plan = QueryPlan(
        intent="bad_unqualified_column",
        tables=["orders"],
        metrics=[QueryMetric(name="bad_metric", expression="COUNT(*)", source_column="not_a_real_column")],
        limit=100,
    )

    validated = QueryPlanBuilder(db_session).validate(test_datasource.id, plan)

    assert any("not_a_real_column" in warning for warning in validated.warnings)


def test_query_plan_online_json_is_validated(db_session, test_datasource, monkeypatch) -> None:
    sync_schema(db_session, test_datasource.id)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"intent":"llm_plan","tables":["orders"],'
                        '"metrics":[{"name":"bad","expression":"SUM(orders.nope)",'
                        '"source_column":"orders.nope"}],'
                        '"dimensions":[],"filters":[],"joins":[],"order_by":null,"limit":50}'
                    )
                }
            }
        ]
    }
    monkeypatch.setattr("engine.semantic.query_plan.httpx.post", lambda *args, **kwargs: mock_resp)

    plan = QueryPlanBuilder(db_session).build(
        datasource_id=test_datasource.id,
        question="bad online plan",
        schema_context="CREATE TABLE orders (...);",
        llm_config={"api_key": "sk-test", "api_base": "https://test/v1", "model": "gpt-test"},
        mode="online",
    )

    assert plan.mode == "online"
    assert plan.intent == "llm_plan"
    assert any("orders.nope" in warning for warning in plan.warnings)
