from __future__ import annotations

from engine.evaluation.spider.sql_prediction_extractor import extract_final_sql


class _FakeResponse:
    def __init__(self, sql: str | None = None):
        self.sql = sql


class TestExtractFinalSql:
    def test_prefers_execute_readonly_safe_sql(self) -> None:
        events = [
            {"step": {"tool_name": "sql.execute_readonly", "output": {"safe_sql": "SELECT * FROM t LIMIT 10"}}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT * FROM t LIMIT 10"

    def test_falls_back_to_validate(self) -> None:
        events = [
            {"step": {"tool_name": "sql.validate", "safe_sql": "SELECT a FROM t"}},
            {"step": {"tool_name": "sql.validate", "safe_sql": "SELECT b FROM t"}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT b FROM t"

    def test_falls_back_to_response_sql(self) -> None:
        events: list[dict] = []
        sql = extract_final_sql(_FakeResponse(sql="SELECT x"), events)
        assert sql == "SELECT x"

    def test_falls_back_to_model_sql_draft(self) -> None:
        events = [
            {"step": {"tool_name": "model.sql_draft", "output": {"sql": "SELECT gen FROM t"}}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT gen FROM t"

    def test_returns_none_when_no_sql_found(self) -> None:
        assert extract_final_sql(_FakeResponse(), []) is None

    def test_empty_string_not_returned(self) -> None:
        events = [{"step": {"tool_name": "sql.validate", "safe_sql": ""}}]
        assert extract_final_sql(_FakeResponse(), events) is None

    def test_execute_readonly_output_dict_safe_sql(self) -> None:
        events = [{"step": {"tool_name": "sql.execute_readonly", "output": {"safe_sql": "SELECT out FROM t"}}}]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT out FROM t"

    def test_ignores_retired_db_query_events(self) -> None:
        events = [{"step": {"tool_name": "db.query", "output": {"safe_sql": "SELECT old FROM t"}}}]
        assert extract_final_sql(_FakeResponse(), events) is None

    def test_tool_name_match(self) -> None:
        events = [{"step": {"tool_name": "model.sql_draft", "output": {"sql": "SELECT gen FROM t"}}}]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT gen FROM t"

    def test_does_not_return_list(self) -> None:
        events = [
            {"step": {"tool_name": "model.sql_draft", "sql": "SELECT 1"}},
            {"step": {"tool_name": "model.sql_draft", "sql": "SELECT 2"}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert isinstance(sql, str)
