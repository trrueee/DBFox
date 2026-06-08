"""Unit tests for the evaluation result comparator in run_agent_eval.py."""
import pytest
import sys
from pathlib import Path

# Add .agent_eval to path so we can import from run_agent_eval
_agent_eval = Path(__file__).resolve().parent.parent.parent / ".agent_eval"
sys.path.insert(0, str(_agent_eval))

from run_agent_eval import compare_results, clean_val


# ============================================================
# clean_val — numeric normalization
# ============================================================

def test_clean_val_none() -> None:
    assert clean_val(None) is None


def test_clean_val_int() -> None:
    assert clean_val(1) == "1"
    assert clean_val(0) == "0"
    assert clean_val(100) == "100"


def test_clean_val_float() -> None:
    assert clean_val(1.0) == "1"
    assert clean_val(1.5) == "1.5"
    assert clean_val(0.0) == "0"
    assert clean_val(3.1416) == "3.1416"


def test_clean_val_int_float_equivalent() -> None:
    """int(2) and float(2.0) must normalize to the same string."""
    assert clean_val(2) == clean_val(2.0)
    assert clean_val(0) == clean_val(0.0)


def test_clean_val_float_rounding() -> None:
    """Values within 4 decimal places should round equivalently."""
    assert clean_val(1.00001) == clean_val(1.0)  # round(1.00001, 4) == 1.0
    assert clean_val(3.14159) == "3.1416"  # round up


def test_clean_val_negative_zero() -> None:
    assert clean_val(-0.0) == "0"


def test_clean_val_string_passthrough() -> None:
    assert clean_val("hello") == "hello"
    assert clean_val("Dog") == "Dog"


def test_clean_val_bytes() -> None:
    assert clean_val(b"hello") == "hello"


# ============================================================
# compare_results — strict equality
# ============================================================

def test_strict_match_identical() -> None:
    match, reason = compare_results(
        [(1, "Dog"), (2, "Cat")],
        [(1, "Dog"), (2, "Cat")],
    )
    assert match is True
    assert "Strict" in reason or "Normalized" in reason or "Success" in reason


def test_both_empty() -> None:
    match, reason = compare_results([], [])
    assert match is True
    assert "empty" in reason.lower()


# ============================================================
# compare_results — row order normalization
# ============================================================

def test_row_order_normalized_when_no_order_by() -> None:
    """Row order should not matter when no ORDER BY."""
    match, reason = compare_results(
        [(1, "Dog"), (2, "Cat")],
        [(2, "Cat"), (1, "Dog")],
        has_order_by=False,
    )
    assert match is True


# ============================================================
# compare_results — ORDER BY strictness
# ============================================================

def test_order_by_strict_row_order_preserved() -> None:
    """When ORDER BY is present, rows must be in matching order."""
    gold = [(1, "Alice"), (2, "Bob")]
    agent = [(2, "Bob"), (1, "Alice")]  # reversed
    match, reason = compare_results(gold, agent, has_order_by=True)
    assert match is False, f"Expected False for wrong ORDER BY row order: {reason}"


def test_order_by_matching_rows_pass() -> None:
    """When ORDER BY is present and rows match, should pass."""
    gold = [(1, "Alice"), (2, "Bob")]
    agent = [(1, "Alice"), (2, "Bob")]
    match, reason = compare_results(gold, agent, has_order_by=True)
    assert match is True


# ============================================================
# compare_results — column order normalization
# ============================================================

def test_column_order_normalized() -> None:
    """Same multiset of values, different column order → match."""
    gold = [(1.5, "Dog"), (3.0, "Cat")]   # [avg, name]
    agent = [("Dog", 1.5), ("Cat", 3.0)]   # [name, avg]
    match, reason = compare_results(gold, agent)
    assert match is True


# ============================================================
# compare_results — numeric type normalization
# ============================================================

def test_numeric_int_float_equivalent() -> None:
    """int and float in different positions must still match."""
    gold = [(1, 2.0, "Dog")]
    agent = [("Dog", 1.0, 2)]
    match, reason = compare_results(gold, agent)
    assert match is True


# ============================================================
# compare_results — column count must match
# ============================================================

def test_extra_column_rejected() -> None:
    """Extra column in agent result must fail."""
    gold = [(1.5, "Dog")]
    agent = [("Dog", 1.5, "extra")]
    match, reason = compare_results(gold, agent)
    assert match is False
    assert "Column count" in reason


def test_missing_column_rejected() -> None:
    """Missing column in agent result must fail."""
    gold = [("Dog", 1.5, "extra")]
    agent = [("Dog", 1.5)]
    match, reason = compare_results(gold, agent)
    assert match is False
    assert "Column count" in reason


# ============================================================
# compare_results — row count must match
# ============================================================

def test_row_count_mismatch_rejected() -> None:
    """Different row count must fail even if values overlap."""
    gold = [(1.5, "Dog"), (3.0, "Cat")]
    agent = [(1.5, "Dog")]
    match, reason = compare_results(gold, agent)
    assert match is False
    assert "Row count" in reason


# ============================================================
# compare_results — different values must fail
# ============================================================

def test_different_values_rejected() -> None:
    """Same row count, same column count but different values → fail."""
    gold = [(1.5, "Dog"), (3.0, "Cat")]
    agent = [(5.0, "Fish"), (7.0, "Bird")]
    match, reason = compare_results(gold, agent)
    assert match is False


def test_partial_value_overlap_rejected() -> None:
    """One matching row + one different row → fail."""
    gold = [(1.5, "Dog"), (3.0, "Cat")]
    agent = [(1.5, "Dog"), (99.0, "Zebra")]
    match, reason = compare_results(gold, agent)
    assert match is False


# ============================================================
# compare_results — aggregate value mismatch
# ============================================================

def test_aggregate_value_mismatch_rejected() -> None:
    """Wrong aggregate values must fail."""
    gold = [(1.5, "Dog"), (3.0, "Cat")]  # avg age
    agent = [(10.5, "Dog"), (30.0, "Cat")]  # wrong avg
    match, reason = compare_results(gold, agent)
    assert match is False


# ============================================================
# compare_results — ORDER BY with column order differs
# ============================================================

def test_order_by_column_order_differs_still_ok() -> None:
    """ORDER BY with column reorder but same row values → still match."""
    gold = [(1, "Alice"), (2, "Bob")]
    agent = [("Alice", 1), ("Bob", 2)]
    match, reason = compare_results(gold, agent, has_order_by=True)
    assert match is True


# ============================================================
# compare_results — real-world Spider scenarios
# ============================================================

def test_spider_avg_max_groupby_column_order() -> None:
    """Simulates case 013/014: avg+max+pettype vs pettype+avg+max."""
    # Gold: SELECT avg(pet_age), max(pet_age), pettype FROM pets GROUP BY pettype
    gold = [(1.5, 2, "Dog"), (3.0, 3, "Cat")]
    # Agent: SELECT PetType, AVG(pet_age), MAX(pet_age) FROM pets GROUP BY PetType
    agent = [("Dog", 1.5, 2), ("Cat", 3.0, 3)]
    match, reason = compare_results(gold, agent)
    assert match is True


def test_spider_avg_groupby_column_order() -> None:
    """Simulates case 015/016: avg+pettype vs pettype+avg."""
    gold = [(1.5, "Dog"), (3.0, "Cat")]
    agent = [("Dog", 1.5), ("Cat", 3.0)]
    match, reason = compare_results(gold, agent)
    assert match is True


def test_spider_count_single_value() -> None:
    """Simulates count(*) queries — single value."""
    gold = [(10,)]  # COUNT(*)
    agent = [(10,)]  # COUNT(*) AS count
    match, reason = compare_results(gold, agent)
    assert match is True
