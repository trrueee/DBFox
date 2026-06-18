from __future__ import annotations

import pytest

from engine.agent.graph.state import _add_list


class TestAddListReducer:
    """Test suite for the append-only list reducer with __clear__ sentinel."""

    # ── standard append-only (no sentinel) ──────────────────────────────────

    def test_empty_left_appends_all_right(self):
        assert _add_list([], [{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]

    def test_non_empty_left_appends_right(self):
        assert _add_list([{"x": 0}], [{"a": 1}]) == [{"x": 0}, {"a": 1}]

    def test_empty_right_returns_left_unchanged(self):
        left = [{"x": 0}, {"y": 1}]
        assert _add_list(left, []) is left  # identity preserved when right empty

    def test_both_empty_returns_empty(self):
        assert _add_list([], []) == []

    # ── __clear__ sentinel ──────────────────────────────────────────────────

    def test_clear_sentinel_discards_left_and_returns_remainder(self):
        left = [{"old": 1}, {"old": 2}]
        right = [{"__clear__": True}, {"new": "a"}, {"new": "b"}]
        assert _add_list(left, right) == [{"new": "a"}, {"new": "b"}]

    def test_clear_sentinel_with_no_remaining_items_returns_empty(self):
        left = [{"old": 1}]
        right = [{"__clear__": True}]
        assert _add_list(left, right) == []

    def test_clear_sentinel_with_empty_left(self):
        left: list = []
        right = [{"__clear__": True}, {"fresh": 1}]
        assert _add_list(left, right) == [{"fresh": 1}]

    def test_clear_sentinel_falsy_value_does_not_trigger(self):
        """Only a truthy __clear__ value triggers the sentinel."""
        left = [{"old": 1}]
        right = [{"__clear__": False}, {"extra": 2}]
        assert _add_list(left, right) == [{"old": 1}, {"__clear__": False}, {"extra": 2}]

    def test_clear_sentinel_only_in_first_element(self):
        """__clear__ in a later position is treated as regular data."""
        left = [{"old": 1}]
        right = [{"regular": 1}, {"__clear__": True}, {"extra": 2}]
        assert _add_list(left, right) == [
            {"old": 1},
            {"regular": 1},
            {"__clear__": True},
            {"extra": 2},
        ]

    def test_clear_sentinel_with_non_dict_element(self):
        """If the first element is not a dict, no clear occurs."""
        left = [{"old": 1}]
        right = ["not_a_dict", {"extra": 2}]
        assert _add_list(left, right) == [{"old": 1}, "not_a_dict", {"extra": 2}]

    # ── integration-style: mimics real usage patterns ───────────────────────

    def test_init_fresh_state_like_service_usage(self):
        """Mimics the pattern used in engine.agent.app.service to init state."""
        # First transition: clear empty list + add initial artifacts
        result = _add_list([], [{"__clear__": True}, {"id": "a1", "type": "sql"}])
        assert result == [{"id": "a1", "type": "sql"}]

        # Subsequent transition: append without clear
        result = _add_list(result, [{"id": "a2", "type": "chart"}])
        assert result == [
            {"id": "a1", "type": "sql"},
            {"id": "a2", "type": "chart"},
        ]

        # New run starts: clear old artifacts + add new ones
        result = _add_list(result, [{"__clear__": True}, {"id": "b1", "type": "table"}])
        assert result == [{"id": "b1", "type": "table"}]

    def test_mixed_types_in_list(self):
        """Reducer should work regardless of element types."""
        left = [1, "two", 3.0]
        right = [{"__clear__": True}, "alpha", 42]
        assert _add_list(left, right) == ["alpha", 42]
