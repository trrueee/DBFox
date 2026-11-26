"""Conservative per-model context windows for prompt budgeting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelLimits:
    context_window: int
    max_output_tokens: int

    def prompt_limit(self, definition_cap: int) -> int:
        """Leave room for the largest response the model may emit."""

        available = self.context_window - self.max_output_tokens
        return min(definition_cap, max(0, available))


# A model name absent from this table keeps the explicit definition cap: an
# unknown modern model may have a smaller window, but inventing one here would
# silently truncate a capable endpoint or a test/bench that set its own budget.
_EXACT: dict[str, ModelLimits] = {
    "gpt-4o": ModelLimits(128_000, 16_384),
    "gpt-4o-mini": ModelLimits(128_000, 16_384),
    "gpt-4.1": ModelLimits(1_047_576, 32_768),
    "gpt-4.1-mini": ModelLimits(1_047_576, 32_768),
    "deepseek-chat": ModelLimits(64_000, 8_192),
    "deepseek-reasoner": ModelLimits(64_000, 8_192),
    "qwen-plus": ModelLimits(131_072, 8_192),
    "qwen-max": ModelLimits(32_768, 8_192),
    "moonshot-v1-8k": ModelLimits(8_192, 2_048),
    "moonshot-v1-32k": ModelLimits(32_768, 4_096),
    "glm-4-plus": ModelLimits(128_000, 4_096),
}

_PREFIXES: tuple[tuple[str, ModelLimits], ...] = (
    ("gpt-5", ModelLimits(400_000, 128_000)),
    ("claude", ModelLimits(200_000, 8_192)),
    ("gemini", ModelLimits(1_048_576, 8_192)),
    ("grok", ModelLimits(131_072, 8_192)),
    ("qwen3", ModelLimits(131_072, 8_192)),
    ("deepseek", ModelLimits(64_000, 8_192)),
    ("moonshot", ModelLimits(131_072, 8_192)),
    ("glm", ModelLimits(128_000, 4_096)),
)


def resolve_model_limits(model_name: str | None) -> ModelLimits | None:
    """Resolve a documented window, or ``None`` when the definition cap decides."""

    name = (model_name or "").strip().lower()
    if not name:
        return None
    exact = _EXACT.get(name)
    if exact is not None:
        return exact
    for prefix, limits in _PREFIXES:
        if name.startswith(prefix):
            return limits
    return None
