"""Catalog-backed SQL schema validation for sql_validate."""

from __future__ import annotations

import pytest

from dlcs.dbfox_data.backend.sql.safety_contracts import DatabaseSafetyScope
from dlcs.dbfox_data.backend.sql.schema_validation import CatalogSchemaValidator
from dlcs.dbfox_data.backend.sql.trust_gate import TrustGate


def _scope() -> DatabaseSafetyScope:
    return DatabaseSafetyScope(
        resource_id="database-1",
        exists=True,
        dialect="sqlite",
        environment="dev",
    )


def test_known_table_passes_without_warnings() -> None:
    seen: list[frozenset[str]] = []

    def lookup(names: frozenset[str]) -> set[str]:
        seen.append(names)
        return set(names)

    warnings = CatalogSchemaValidator(dialect="sqlite", lookup=lookup)(
        "SELECT id FROM users LIMIT 5"
    )

    assert warnings == []
    assert seen == [frozenset({"users"})]


def test_unknown_table_produces_a_public_warning() -> None:
    warnings = CatalogSchemaValidator(
        dialect="sqlite", lookup=lambda names: set(names) - {"missing"}
    )("SELECT id FROM missing LIMIT 5")

    assert warnings == ["表 missing 不在当前 Catalog 中；请刷新 Catalog 或核对名称。"]


def test_cte_names_are_not_treated_as_catalog_tables() -> None:
    seen: list[frozenset[str]] = []

    def lookup(names: frozenset[str]) -> set[str]:
        seen.append(names)
        return set(names)

    warnings = CatalogSchemaValidator(dialect="sqlite", lookup=lookup)(
        "WITH recent AS (SELECT id FROM users) SELECT id FROM recent LIMIT 5"
    )

    assert warnings == []
    assert seen == [frozenset({"users"})]


def test_qualified_table_name_is_checked_as_written() -> None:
    seen: list[frozenset[str]] = []

    def lookup(names: frozenset[str]) -> set[str]:
        seen.append(names)
        return set(names)

    warnings = CatalogSchemaValidator(dialect="sqlite", lookup=lookup)(
        "SELECT id FROM public.orders LIMIT 5"
    )

    assert warnings == []
    assert seen == [frozenset({"public.orders"})]


def test_qualified_table_inside_a_same_named_cte_is_still_checked() -> None:
    warnings = CatalogSchemaValidator(
        dialect="postgres", lookup=lambda _names: set(),
    )("WITH orders AS (SELECT id FROM archive.orders) SELECT id FROM orders")
    assert len(warnings) == 1
    assert "archive.orders" in warnings[0]


def test_postgres_catalog_preserves_quoted_names_and_folds_unquoted_names() -> None:
    warnings = CatalogSchemaValidator(
        dialect="postgres", lookup=lambda names: set(names) & {"Sales.Orders", "public.orders"},
    )('SELECT q.id FROM "Sales"."Orders" q JOIN PUBLIC.ORDERS p ON q.id = p.id')
    assert warnings == []


def test_unready_catalog_skips_schema_warnings() -> None:
    warnings = CatalogSchemaValidator(
        dialect="sqlite", lookup=lambda _names: None
    )("SELECT id FROM any_table LIMIT 5")

    assert warnings == []


def test_unparseable_sql_defers_to_the_guardrail() -> None:
    warnings = CatalogSchemaValidator(
        dialect="sqlite", lookup=lambda _names: set()
    )("SELECT FROM WHERE")

    assert warnings == []


def test_trust_gate_marks_unknown_table_as_a_warning_but_allows_execution() -> None:
    gate = TrustGate(
        CatalogSchemaValidator(
            dialect="sqlite", lookup=lambda names: set(names) - {"missing"}
        )
    )

    result = gate.evaluate(_scope(), "SELECT id FROM missing LIMIT 5")

    assert result["canExecute"] is True
    assert result["riskLevel"] == "warning"
    assert any("missing" in warning for warning in result["schemaWarnings"])


@pytest.mark.parametrize(("sql", "expected_advice"), [
    ("SELECT SUM(a.value), SUM(b.quantity * b.price) FROM invoices a JOIN lines b ON a.id = b.invoice_id", True),
    ("SELECT AVG(a.value), COUNT(b.id) FROM invoices a JOIN lines b ON a.id = b.invoice_id", True),
    ("SELECT (SELECT SUM(a.value) FROM invoices a), (SELECT SUM(b.price) FROM lines b)", False),
    ("SELECT SUM(b.price), COUNT(b.id) FROM invoices a JOIN lines b ON a.id = b.invoice_id", False),
])
def test_cross_source_aggregate_advice_is_independent_of_sql_safety(sql, expected_advice) -> None:
    gate = TrustGate(CatalogSchemaValidator(dialect="sqlite", lookup=lambda names: set(names)))

    result = gate.evaluate(_scope(), sql)

    assert any(message.startswith("JOIN aggregation grain") for message in result["messages"]) == expected_advice
    assert result["canExecute"] is True
    assert result["riskLevel"] == "safe"
    assert result["requiresConfirmation"] is False
