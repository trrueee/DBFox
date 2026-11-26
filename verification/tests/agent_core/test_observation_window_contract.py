"""Completion must be able to observe the Run's complete tool budget."""

from __future__ import annotations

from engine.agent.context import MAX_OBSERVATIONS
from engine.agent.run import RunLimits


def test_model_observation_window_covers_the_tool_budget() -> None:
    assert MAX_OBSERVATIONS >= RunLimits().max_tool_invocations
