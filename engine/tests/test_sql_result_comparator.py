from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from engine.evaluation.spider.sql_result_comparator import (
    SqlComparisonResult,
    SqlExecutionResult,
    compare_sqlite_execution,
    execute_sqlite_query,
    normalize_rows,
    normalize_value,
)


def _make_db(path: Path, ddl: str):
    conn = sqlite3.connect(str(path))
    conn.executescript(ddl)
    conn.commit()
    conn.close()


class TestExecuteSqliteQuery:
    def test_success(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = Path(f.name)
        try:
            _make_db(db, "CREATE TABLE t (id INT); INSERT INTO t VALUES (1);")
            result = execute_sqlite_query(db, "SELECT * FROM t")
            assert result.success
            assert result.rows == [(1,)]
        finally:
            db.unlink()

    def test_failure(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = Path(f.name)
        try:
            _make_db(db, "CREATE TABLE t (id INT);")
            result = execute_sqlite_query(db, "SELECT bad_column FROM t")
            assert not result.success
            assert result.error is not None
        finally:
            db.unlink()


class TestNormalize:
    def test_null(self) -> None:
        assert normalize_value(None) is None

    def test_float_rounding(self) -> None:
        assert normalize_value(3.1415926535) == 3.141593

    def test_nan(self) -> None:
        import math
        assert normalize_value(float("nan")) == "NaN"

    def test_string_to_number(self) -> None:
        assert normalize_value("3.14") == 3.14

    def test_string_stays_string(self) -> None:
        assert normalize_value("hello") == "hello"

    def test_normalize_rows_order_insensitive(self) -> None:
        rows = [(2, "b"), (1, "a")]
        result = normalize_rows(rows, order_sensitive=False)
        assert result == [(1, "a"), (2, "b")]

    def test_normalize_rows_order_sensitive(self) -> None:
        rows = [(2, "b"), (1, "a")]
        result = normalize_rows(rows, order_sensitive=True)
        assert result == [(2, "b"), (1, "a")]


class TestCompareSqliteExecution:
    def _new_db(self) -> Path:
        db = Path(tempfile.mktemp(suffix=".sqlite"))
        _make_db(db, """
            CREATE TABLE students (id INT, name TEXT);
            INSERT INTO students VALUES (1, 'Alice'), (2, 'Bob');
        """)
        return db

    def test_same_sql_match(self) -> None:
        db = self._new_db()
        try:
            result = compare_sqlite_execution(db, "SELECT * FROM students", "SELECT * FROM students")
            assert result.execution_match
        finally:
            db.unlink()

    def test_different_order_no_order_by_match(self) -> None:
        # Direct test: normalize_rows with order_sensitive=False sorts both,
        # so rows in different input order still match.
        rows_a = [(2, "b"), (1, "a")]
        rows_b = [(1, "a"), (2, "b")]
        assert normalize_rows(rows_a, order_sensitive=False) == normalize_rows(rows_b, order_sensitive=False)

    def test_order_sensitive_with_order_by(self) -> None:
        db = self._new_db()
        try:
            # Same rows, different ORDER BY → different row order → no match.
            result = compare_sqlite_execution(db, "SELECT * FROM students ORDER BY id", "SELECT * FROM students ORDER BY name DESC")
            assert not result.execution_match
        finally:
            db.unlink()

    def test_predicted_execution_failure(self) -> None:
        db = self._new_db()
        try:
            result = compare_sqlite_execution(db, "SELECT * FROM students", "SELECT bad FROM students")
            assert not result.predicted_success
            assert not result.execution_match
            assert result.predicted_error is not None
        finally:
            db.unlink()

    def test_gold_execution_failure(self) -> None:
        db = self._new_db()
        try:
            result = compare_sqlite_execution(db, "SELECT bad FROM students", "SELECT * FROM students")
            assert not result.gold_success
            assert not result.execution_match
            assert result.gold_error is not None
        finally:
            db.unlink()

    def test_row_counts_preserved(self) -> None:
        db = self._new_db()
        try:
            result = compare_sqlite_execution(db, "SELECT * FROM students", "SELECT * FROM students")
            assert result.gold_rows_count == 2
            assert result.predicted_rows_count == 2
        finally:
            db.unlink()

    def test_tiny_fixture_comparator(self) -> None:
        db_path = Path("engine/tests/fixtures/spider_tiny/database/tiny_school/tiny_school.sqlite")
        if not db_path.exists():
            pytest.skip("Spider tiny fixture DB not found")
        result = compare_sqlite_execution(
            db_path,
            "SELECT COUNT(*) FROM students",
            "SELECT COUNT(*) FROM students",
        )
        assert result.execution_match
        assert result.gold_rows_count == 1
        assert result.predicted_rows_count == 1

        result2 = compare_sqlite_execution(
            db_path,
            "SELECT AVG(score) FROM courses",
            "SELECT AVG(score) FROM courses",
        )
        assert result2.execution_match
