from engine.tools.safe_preview import db_preview


def test_db_preview_rejects_raw_where_fragment() -> None:
    result = db_preview(None, {"table": "orders", "where": "1=1 UNION SELECT password FROM users"})  # type: ignore[arg-type]

    assert result.status == "failed"
    assert "WHERE" in str(result.error)


def test_db_preview_rejects_raw_order_fragment() -> None:
    result = db_preview(None, {"table": "orders", "order_by": "id DESC; SELECT password FROM users"})  # type: ignore[arg-type]

    assert result.status == "failed"
    assert "ORDER BY" in str(result.error)
