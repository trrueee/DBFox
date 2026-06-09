from __future__ import annotations

from engine.evaluation.spider.sql_prediction_extractor import extract_final_sql


class _FakeResponse:
    def __init__(self, sql: str | None = None):
        self.sql = sql


class TestExtractFinalSql:
    def test_prefers_validated_safe_sql(self) -> None:
        events = [
            {"step": {"name": "generate_sql_candidate", "sql": "SELECT * FROM t"}},
            {"step": {"name": "validate_sql", "safe_sql": "SELECT * FROM t LIMIT 10"}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT * FROM t LIMIT 10"

    def test_last_validate_wins(self) -> None:
        events = [
            {"step": {"name": "validate_sql", "safe_sql": "SELECT a FROM t"}},
            {"step": {"name": "validate_sql", "safe_sql": "SELECT b FROM t"}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT b FROM t"

    def test_falls_back_to_response_sql(self) -> None:
        events: list[dict] = []
        sql = extract_final_sql(_FakeResponse(sql="SELECT x"), events)
        assert sql == "SELECT x"

    def test_falls_back_to_generated_sql(self) -> None:
        events = [
            {"step": {"name": "generate_sql_candidate", "sql": "SELECT gen FROM t"}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT gen FROM t"

    def test_returns_none_when_no_sql_found(self) -> None:
        assert extract_final_sql(_FakeResponse(), []) is None

    def test_empty_string_not_returned(self) -> None:
        events = [{"step": {"name": "validate_sql", "safe_sql": ""}}]
        assert extract_final_sql(_FakeResponse(), events) is None

    def test_output_dict_safe_sql(self) -> None:
        events = [{"step": {"name": "validate_sql", "output": {"safe_sql": "SELECT out FROM t"}}}]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT out FROM t"

    def test_tool_name_match(self) -> None:
        events = [{"step": {"tool_name": "sql.generate", "output": {"sql": "SELECT gen FROM t"}}}]
        sql = extract_final_sql(_FakeResponse(), events)
        assert sql == "SELECT gen FROM t"

    def test_does_not_return_list(self) -> None:
        events = [
            {"step": {"name": "generate_sql_candidate", "sql": "SELECT 1"}},
            {"step": {"name": "generate_sql_candidate", "sql": "SELECT 2"}},
        ]
        sql = extract_final_sql(_FakeResponse(), events)
        assert isinstance(sql, str)
