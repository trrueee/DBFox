from __future__ import annotations

import pytest

from engine.sql.bound_parameters import render_dbapi_sql
from engine.sql.builder import build_select


@pytest.mark.parametrize(
    ("dialect", "placeholder"),
    [
        ("mysql", "%(dbfox_p0)s"),
        ("postgresql", "%(dbfox_p0)s"),
        ("sqlite", ":dbfox_p0"),
        ("duckdb", "$dbfox_p0"),
    ],
)
def test_internal_filter_value_is_bound_not_concatenated(
    dialect: str, placeholder: str
) -> None:
    attack = "x' OR 1=1 --"
    sql, parameters = build_select(
        table="users",
        columns=["id"],
        where={"column": "name", "op": "=", "value": attack},
        order=None,
        limit=10,
        dialect=dialect,
    )

    assert attack not in sql
    rendered, bound = render_dbapi_sql(sql, dialect, parameters)
    assert attack not in rendered
    assert placeholder in rendered
    assert bound == {"dbfox_p0": attack}


def test_qualified_catalog_table_keeps_filter_value_bound() -> None:
    attack = "x' OR 1=1 --"
    sql, parameters = build_select(
        table="users",
        table_schema="creatorhub",
        columns=["id"],
        where={"column": "name", "op": "=", "value": attack},
        order=None,
        limit=10,
        dialect="mysql",
        catalog_validated_identifiers=True,
    )

    assert "FROM `creatorhub`.`users`" in sql
    assert attack not in sql
    rendered, bound = render_dbapi_sql(sql, "mysql", parameters)
    assert attack not in rendered
    assert "FROM `creatorhub`.`users`" in rendered
    assert '"creatorhub"."users"' not in rendered
    assert "%(dbfox_p0)s" in rendered
    assert bound == {"dbfox_p0": attack}


def test_placeholder_parameter_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="do not match"):
        render_dbapi_sql(
            "SELECT * FROM users WHERE id = :dbfox_p0",
            "sqlite",
            {"dbfox_p1": 1},
        )


def test_external_placeholder_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="internal named parameters"):
        render_dbapi_sql(
            "SELECT * FROM users WHERE id = :user_supplied",
            "sqlite",
            {"user_supplied": 1},
        )
