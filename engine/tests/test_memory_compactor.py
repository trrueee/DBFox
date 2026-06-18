"""Boundary-condition tests for memory_compactor — covers off-by-one risks noted in the architecture audit."""

import pytest
from engine.memory.memory_compactor import (
    MemoryCompactionConfig,
    compact_messages,
    compact_schema_context,
    compact_execution_result,
    DEFAULT_CONFIG,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

class _FakeToolMsg:
    def __init__(self, idx: int):
        self.idx = idx
    def __repr__(self):
        return f"Tool({self.idx})"

class _FakeMsg:
    def __init__(self, idx: int):
        self.idx = idx
    def __repr__(self):
        return f"Msg({self.idx})"


# ── compact_messages boundary tests ────────────────────────────────────────────

def test_empty_messages():
    assert compact_messages([]) == []


def test_single_message():
    msg = _FakeMsg(1)
    assert compact_messages([msg]) == [msg]


def test_exactly_at_max_messages():
    cfg = MemoryCompactionConfig(max_messages=3, max_tool_messages=2)
    msgs = [_FakeMsg(1), _FakeMsg(2), _FakeMsg(3)]
    result = compact_messages(msgs, cfg)
    assert len(result) == 3
    assert result == msgs  # no trimming needed


def test_one_over_max_messages():
    cfg = MemoryCompactionConfig(max_messages=3, max_tool_messages=2)
    msgs = [_FakeMsg(1), _FakeMsg(2), _FakeMsg(3), _FakeMsg(4)]
    result = compact_messages(msgs, cfg)
    assert len(result) <= 3


def test_max_tool_messages_zero():
    """max_tool_messages=0 must keep zero tool messages (not all via list[-0:])."""
    cfg = MemoryCompactionConfig(max_messages=3, max_tool_messages=0)
    msgs = [_FakeMsg(1), _FakeToolMsg(1), _FakeMsg(2), _FakeToolMsg(2)]
    result = compact_messages(msgs, cfg)
    tool_count = sum(1 for m in result if isinstance(m, _FakeToolMsg))
    assert tool_count == 0, f"max_tool_messages=0 should keep 0 tools, got {tool_count}"


def test_max_tool_messages_one():
    cfg = MemoryCompactionConfig(max_messages=3, max_tool_messages=1)
    msgs = [_FakeToolMsg(1), _FakeToolMsg(2), _FakeToolMsg(3), _FakeMsg(1)]
    result = compact_messages(msgs, cfg)
    tool_count = sum(1 for m in result if isinstance(m, _FakeToolMsg))
    assert tool_count == 1


def test_max_tool_messages_keeps_newest():
    """When trimming tool messages, keep the most recent ones."""
    cfg = MemoryCompactionConfig(max_messages=3, max_tool_messages=2)
    msgs = [_FakeToolMsg(1), _FakeToolMsg(2), _FakeToolMsg(3), _FakeToolMsg(4)]
    result = compact_messages(msgs, cfg)
    tools = [m for m in result if isinstance(m, _FakeToolMsg)]
    assert len(tools) == 2, f"expected 2 tools, got {len(tools)}: {tools}"
    assert tools[0].idx == 3
    assert tools[1].idx == 4


def test_no_tool_messages():
    cfg = MemoryCompactionConfig(max_messages=2, max_tool_messages=5)
    msgs = [_FakeMsg(1), _FakeMsg(2), _FakeMsg(3)]
    result = compact_messages(msgs, cfg)
    assert len(result) == 2


def test_large_overrun():
    cfg = MemoryCompactionConfig(max_messages=5, max_tool_messages=2)
    msgs = [_FakeMsg(i) for i in range(15)]
    result = compact_messages(msgs, cfg)
    assert len(result) == 5


def test_all_tool_messages():
    cfg = MemoryCompactionConfig(max_messages=5, max_tool_messages=3)
    msgs = [_FakeToolMsg(i) for i in range(10)]
    result = compact_messages(msgs, cfg)
    tools = [m for m in result if isinstance(m, _FakeToolMsg)]
    assert len(tools) == 3
    # Newest three: indices 7, 8, 9
    assert tools[0].idx == 7
    assert tools[-1].idx == 9


# ── compact_schema_context boundary tests ──────────────────────────────────────

def test_schema_within_budget():
    assert compact_schema_context("short") == "short"


def test_schema_exact_at_budget():
    cfg = MemoryCompactionConfig(max_schema_chars=10)
    assert compact_schema_context("1234567890", cfg) == "1234567890"


def test_schema_one_over_budget():
    cfg = MemoryCompactionConfig(max_schema_chars=10)
    result = compact_schema_context("1234567890ABC", cfg)
    assert "... (schema truncated)" in result
    assert result.startswith("1234567890")


# ── compact_execution_result boundary tests ────────────────────────────────────

def test_execution_none():
    assert compact_execution_result(None) is None


def test_execution_exact_sample_rows():
    cfg = MemoryCompactionConfig(max_execution_sample_rows=3)
    result = compact_execution_result({"rows": [1, 2, 3]}, cfg)
    assert result is not None
    assert result["rows"] == [1, 2, 3]
    assert "_truncated" not in result


def test_execution_one_over_sample():
    cfg = MemoryCompactionConfig(max_execution_sample_rows=3)
    result = compact_execution_result({"rows": [1, 2, 3, 4]}, cfg)
    assert result is not None
    assert len(result["rows"]) == 3
    assert result["rows"] == [1, 2, 3]
    assert result["_truncated"] is True
    assert result["_original_row_count"] == 4


def test_execution_zero_sample_rows():
    cfg = MemoryCompactionConfig(max_execution_sample_rows=0)
    result = compact_execution_result({"rows": [1, 2]}, cfg)
    assert result is not None
    assert result["rows"] == []
    assert result["_truncated"] is True


def test_default_config_values():
    """Sanity-check that the default config values are reasonable."""
    assert DEFAULT_CONFIG.max_messages > 0
    assert DEFAULT_CONFIG.max_tool_messages > 0
    assert DEFAULT_CONFIG.max_schema_chars > 0
    assert DEFAULT_CONFIG.max_execution_sample_rows > 0
    assert DEFAULT_CONFIG.summarize_after_messages > DEFAULT_CONFIG.max_messages
