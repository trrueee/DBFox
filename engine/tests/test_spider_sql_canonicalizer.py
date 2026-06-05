from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_eval_module(module_name: str, filename: str):
    path = Path(__file__).resolve().parents[2] / ".agent_eval" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _canonicalizer_module():
    return _load_eval_module("spider_sql_canonicalizer", "spider_sql_canonicalizer.py")


def _runner_module():
    return _load_eval_module("run_agent_eval", "run_agent_eval.py")


def _one_line(sql: str) -> str:
    return " ".join(sql.split())


def test_canonicalizer_does_not_rewrite_string_literals() -> None:
    canonicalizer = _canonicalizer_module()

    sql = "SELECT * FROM Friend WHERE name = 'Friend'"
    double_quoted_sql = 'SELECT * FROM Friend WHERE name = "Friend"'

    assert (
        _one_line(
            canonicalizer.canonicalize_gold_sql_for_mysql(
                sql,
                db_id="school",
                table_names=["friend"],
            )
        )
        == "SELECT * FROM friend WHERE name = 'Friend'"
    )
    assert (
        _one_line(
            canonicalizer.canonicalize_gold_sql_for_mysql(
                double_quoted_sql,
                db_id="school",
                table_names=["friend"],
            )
        )
        == 'SELECT * FROM friend WHERE name = "Friend"'
    )


def test_canonicalizer_rewrites_from_join_alias_tables() -> None:
    canonicalizer = _canonicalizer_module()

    sql = "SELECT T1.ID FROM Friend AS T1 JOIN Highschooler AS T2 ON T1.ID = T2.ID"

    assert (
        _one_line(
            canonicalizer.canonicalize_gold_sql_for_mysql(
                sql,
                db_id="school",
                table_names=["friend", "highschooler"],
            )
        )
        == "SELECT T1.ID FROM friend AS T1 JOIN highschooler AS T2 ON T1.ID = T2.ID"
    )


def test_canonicalizer_rewrites_subquery_tables() -> None:
    canonicalizer = _canonicalizer_module()

    sql = "SELECT id FROM Friend WHERE id IN (SELECT id FROM Likes)"

    assert (
        _one_line(
            canonicalizer.canonicalize_gold_sql_for_mysql(
                sql,
                db_id="school",
                table_names=["friend", "likes"],
            )
        )
        == "SELECT id FROM friend WHERE id IN (SELECT id FROM likes)"
    )


def test_runner_executes_canonical_gold_sql(monkeypatch) -> None:
    runner = _runner_module()
    executed_sql: list[str] = []

    monkeypatch.setattr(
        runner,
        "fetch_mysql_tables",
        lambda *_args, **_kwargs: (["friend"], None),
    )

    def fake_execute_mysql_query(*args):
        executed_sql.append(args[-1])
        return [("ok",)], ["status"], None

    monkeypatch.setattr(runner, "execute_mysql_query", fake_execute_mysql_query)

    result = runner.execute_gold_sql_for_case(
        mysql_host="127.0.0.1",
        mysql_port=3307,
        mysql_user="root",
        mysql_password="root",
        mysql_db="spider_school",
        db_id="school",
        gold_sql="SELECT * FROM Friend",
    )

    assert executed_sql == ["SELECT * FROM friend"]
    assert result["gold_sql_original"] == "SELECT * FROM Friend"
    assert result["gold_sql_canonical"] == "SELECT * FROM friend"
    assert result["gold_sql_was_canonicalized"] is True
    assert result["gold_error"] is None
