"""Per-model context windows bound the prompt before the definition cap."""

from __future__ import annotations

import pytest

from engine.llm.model_capabilities import ModelLimits, resolve_model_limits


@pytest.mark.parametrize(
    ("model_name", "expected_window", "expected_output"),
    [
        ("gpt-4o-mini", 128_000, 16_384),
        ("gpt-4.1", 1_047_576, 32_768),
        ("deepseek-chat", 64_000, 8_192),
        ("moonshot-v1-8k", 8_192, 2_048),
        ("claude-sonnet-4.6", 200_000, 8_192),
        ("gemini-2.5-pro", 1_048_576, 8_192),
        ("unknown-model", None, None),
        (None, None, None),
    ],
)
def test_resolve_model_limits(
    model_name: str | None, expected_window: int | None, expected_output: int | None
) -> None:
    limits = resolve_model_limits(model_name)

    if expected_window is None:
        assert limits is None
        return
    assert limits is not None
    assert limits.context_window == expected_window
    assert limits.max_output_tokens == expected_output


def test_definition_cap_wins_for_large_windows() -> None:
    assert resolve_model_limits("gpt-4o-mini").prompt_limit(65_536) == 65_536


def test_small_windows_reduce_the_prompt_budget() -> None:
    assert resolve_model_limits("deepseek-chat").prompt_limit(65_536) == 55_808
    assert resolve_model_limits("moonshot-v1-8k").prompt_limit(65_536) == 6_144


def test_prompt_limit_respects_small_context_windows_and_explicit_caps() -> None:
    limits = ModelLimits(context_window=5_000, max_output_tokens=4_000)

    assert limits.prompt_limit(65_536) == 1_000
    assert ModelLimits(context_window=128_000, max_output_tokens=4_000).prompt_limit(1_024) == 1_024
