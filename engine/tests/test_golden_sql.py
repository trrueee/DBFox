"""Golden SQL test suite — V1.1 必测：30 条测试，结构命中率 ≥ 70%

Evaluates structural correctness of generated SQL:
- Correct tables referenced
- Correct columns referenced (at least partial match)
- Correct query type (SELECT, aggregation, JOIN, etc.)

These tests validate the offline heuristic demo_sql matcher against the
e-commerce demo database schema.
"""
import re

import pytest
from engine.sql.generator import search_demo_sql


# ---------------------------------------------------------------------------
# 30 Golden SQL Test Cases
# ---------------------------------------------------------------------------
# Each entry: (question, expected_tables, expected_columns, expected_has_aggregation, expected_has_join)
GOLDEN_TESTS = [
    # 1. Simple SELECT from single table
    ("查询所有用户", {"users"}, {"id", "username", "email"}, False, False),
    # 2. COUNT aggregation
    ("统计用户数", {"users"}, set(), True, False),
    # 3. Simple product query
    ("商品列表", {"products"}, {"name", "price"}, False, False),
    # 4. Stock filter
    ("库存少于10的商品", {"products"}, {"name", "stock"}, False, False),
    # 5. Out of stock
    ("缺货商品", {"products"}, {"name", "stock"}, False, False),
    # 6. Most expensive
    ("最贵的商品", {"products"}, {"name", "price"}, False, False),
    # 7. All orders
    ("所有订单", {"orders"}, {"id", "total_amount", "status"}, False, False),
    # 8. Total sales
    ("订单总额", {"orders"}, {"total_amount"}, True, False),
    # 9. Order count
    ("订单数量", {"orders"}, set(), True, False),
    # 10. Orders by status
    ("订单状态统计", {"orders"}, {"status"}, True, False),
    # 11. Recent orders (JOIN + ORDER BY)
    ("最近的订单", {"orders", "users"}, {"id", "username", "total_amount"}, False, True),
    # 12. Cancelled orders
    ("已取消订单", {"orders"}, {"status"}, False, False),
    # 13. Best selling products (JOIN + aggregation)
    ("销售最好的商品", {"order_items", "products"}, {"name"}, True, True),
    # 14. Top 5 sales
    ("销量前五", {"order_items", "products"}, {"name"}, True, True),
    # 15. Revenue ranking
    ("最高销售额", {"order_items", "products"}, {"name"}, True, True),
    # 16. Payment by channel
    ("支付渠道统计", {"payments"}, {"payment_method"}, True, False),
    # 17. Payment status
    ("支付状态统计", {"payments"}, {"status"}, True, False),
    # 18. Refunds
    ("退款记录", {"payments"}, {"status"}, False, False),
    # 19. Low rating reviews (JOIN)
    ("低评分评价", {"reviews", "products", "users"}, {"rating", "comment"}, False, True),
    # 20. Product ratings
    ("商品评分", {"reviews", "products"}, {"name"}, True, True),
    # 21. Cart items (JOIN)
    ("购物车加购", {"cart", "users", "products"}, {"username", "quantity"}, False, True),
    # 22. Supplier list
    ("供应商列表", {"suppliers"}, {"name", "contact", "phone"}, False, False),
    # 23. Shipping status
    ("物流状态统计", {"shipping", "orders"}, {"tracking_number", "carrier", "status"}, False, True),
    # 24. Delivered orders
    ("已妥投订单", {"shipping", "orders", "users"}, {"carrier", "tracking_number"}, False, True),
    # 25. System settings
    ("系统配置", {"system_settings"}, {"key", "value"}, False, False),
    # 26. Recommendations (JOIN)
    ("商品推荐", {"recommendations", "users", "products"}, {"username", "score"}, False, True),
    # 27. Inventory logs (JOIN)
    ("库存变更记录", {"inventory_logs", "products"}, {"change_amount", "reason"}, False, True),
    # 28. Category stats (JOIN + aggregation)
    ("商品分类", {"categories", "products"}, {"name"}, True, True),
    # 29. User addresses (JOIN)
    ("用户地址", {"user_addresses", "users"}, {"consignee", "province", "city"}, False, True),
    # 30. Order totals by payment method
    ("订单的支付方式统计", {"orders"}, {"payment_method"}, True, False),
]


def extract_tables(sql: str) -> set[str]:
    """Extract table names mentioned in a SQL statement."""
    tables = set()
    # Match FROM and JOIN patterns
    for match in re.finditer(
        r'(?:FROM|JOIN)\s+(\w+)',
        sql,
        re.IGNORECASE,
    ):
        tables.add(match.group(1).lower())
    return tables


def has_select_star(sql: str) -> bool:
    """Check if SQL uses SELECT *."""
    return bool(re.search(r'SELECT\s+\*', sql, re.IGNORECASE))


def extract_columns(sql: str) -> set[str]:
    """Extract column names from a SQL SELECT clause."""
    columns = set()
    select_match = re.search(
        r'SELECT\s+(.*?)\s+FROM',
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not select_match:
        return columns

    select_clause = select_match.group(1)
    for part in select_clause.split(","):
        part = part.strip()
        # Handle function calls: "SUM(column) AS alias" → extract "column"
        func_match = re.match(r'(\w+)\((\w+(?:\.\w+)?)\)', part)
        if func_match:
            col_ref = func_match.group(2)
            if "." in col_ref:
                col_ref = col_ref.split(".")[-1]
            columns.add(col_ref.lower())
            continue
        # Handle table.column references with possible aliases
        dot_match = re.match(r'(?:\w+\.)?(\w+)', part)
        if dot_match:
            col = dot_match.group(1).lower()
            if col != "*" and col not in ("as",):
                columns.add(col)

    return columns


def has_aggregation(sql: str) -> bool:
    """Check if SQL contains aggregation functions."""
    agg_functions = ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "GROUP BY"]
    sql_upper = sql.upper()
    return any(fn in sql_upper for fn in agg_functions)


def has_join(sql: str) -> bool:
    """Check if SQL contains JOIN clauses."""
    return bool(re.search(r'\bJOIN\b', sql, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Golden Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question,expected_tables,expected_columns,expected_agg,expected_join", GOLDEN_TESTS)
def test_golden_sql_structure(
    question: str,
    expected_tables: set[str],
    expected_columns: set[str],
    expected_agg: bool,
    expected_join: bool,
) -> None:
    """Validate that generated SQL hits the right tables and has the right structure."""
    sql = search_demo_sql(question)
    assert sql, f"No SQL generated for: '{question}'"
    assert "SELECT" in sql.upper(), f"Generated SQL is not a SELECT: {sql}"

    tables = extract_tables(sql)
    columns = extract_columns(sql)
    is_agg = has_aggregation(sql)
    is_join = has_join(sql)

    # Check table coverage: generated SQL should reference at least the expected tables
    missing_tables = expected_tables - tables
    assert not missing_tables, (
        f"Question: '{question}'\n"
        f"Generated SQL: {sql}\n"
        f"Missing expected tables: {missing_tables}"
    )

    # Check column coverage (skip for SELECT * since columns are implicit)
    if expected_columns and not has_select_star(sql):
        column_hits = expected_columns & columns
        hit_rate = len(column_hits) / len(expected_columns) if expected_columns else 1.0
        assert hit_rate >= 0.5, (
            f"Question: '{question}'\n"
            f"Generated SQL: {sql}\n"
            f"Column hit rate: {hit_rate:.0%} (hits: {column_hits}, expected: {expected_columns})"
        )

    # Check aggregation
    if expected_agg:
        assert is_agg, (
            f"Question: '{question}'\n"
            f"Generated SQL: {sql}\n"
            f"Expected aggregation but none found."
        )

    # Check joins
    if expected_join:
        assert is_join, (
            f"Question: '{question}'\n"
            f"Generated SQL: {sql}\n"
            f"Expected JOIN but none found."
        )


def test_golden_sql_overall_accuracy() -> None:
    """Report overall structural accuracy across all 30 test cases."""
    table_hits = 0
    total_with_tables = 0
    failures = []

    for question, expected_tables, expected_columns, expected_agg, expected_join in GOLDEN_TESTS:
        sql = search_demo_sql(question)
        tables = extract_tables(sql)
        columns = extract_columns(sql)
        is_agg = has_aggregation(sql)
        is_join = has_join(sql)

        missing = expected_tables - tables
        if not missing:
            table_hits += 1

        col_ok = True
        if expected_columns:
            hits = expected_columns & columns
            col_ok = len(hits) / len(expected_columns) >= 0.5 if expected_columns else True

        agg_ok = not expected_agg or is_agg
        join_ok = not expected_join or is_join

        if missing or not col_ok or not agg_ok or not join_ok:
            failures.append({
                "question": question,
                "sql": sql,
                "missing_tables": missing,
                "col_ok": col_ok,
                "agg_ok": agg_ok,
                "join_ok": join_ok,
            })

        total_with_tables += 1

    table_accuracy = table_hits / total_with_tables if total_with_tables else 0
    structural_pass = total_with_tables - len(failures)
    structural_rate = structural_pass / total_with_tables if total_with_tables else 0

    print(f"\nGolden SQL Accuracy Report:")
    print(f"  Table accuracy: {table_accuracy:.0%} ({table_hits}/{total_with_tables})")
    print(f"  Structural pass rate: {structural_rate:.0%} ({structural_pass}/{total_with_tables})")
    if failures:
        print(f"  Failures ({len(failures)}):")
        for f_item in failures:
            print(f"    - '{f_item['question']}' → {f_item['sql'][:80]}")

    # V1.1 acceptance criteria: ≥70% structural accuracy
    assert structural_rate >= 0.70, (
        f"Golden SQL structural accuracy {structural_rate:.0%} below 70% threshold.\n"
        f"Failures: {failures}"
    )
