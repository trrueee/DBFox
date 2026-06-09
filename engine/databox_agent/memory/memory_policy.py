"""Memory safety policy — what can and cannot be automatically stored."""
from __future__ import annotations

from typing import Any

# Types that are safe to auto-store
AUTO_STORE_TYPES = frozenset({
    "user_preference",       # user explicitly stated
    "successful_trajectory", # system-generated from completed runs
    "failure_learning",      # errors and fixes
})

# Types that require review when agent_inferred
REVIEW_WHEN_INFERRED_TYPES = frozenset({
    "schema_alias",
    "metric_definition",
    "project_rule",
    "join_path",
})

# Content patterns that must NEVER be stored in long-term memory
FORBIDDEN_CONTENT_PATTERNS = [
    "password",
    "api_key",
    "token",
    "secret",
    "credit_card",
    "ssn",
    "身份证",
    "手机号",
    "银行卡",
    "密码",
]


def is_safe_for_long_term(record_type: str, source: str, content: dict[str, Any]) -> bool:
    """Check whether a candidate memory is safe to store."""
    # Check content for forbidden patterns
    content_str = str(content).lower()
    for pattern in FORBIDDEN_CONTENT_PATTERNS:
        if pattern.lower() in content_str:
            return False

    # agent_inferred + low-confidence metric/schema → pending_review
    if source == "agent_inferred" and record_type in REVIEW_WHEN_INFERRED_TYPES:
        return False  # caller should set pending_review

    return True


def default_status(record_type: str, source: str, confidence: float) -> str:
    """Return the default status for a new memory record."""
    if source == "user_explicit":
        return "active"
    if source == "agent_inferred":
        if record_type in REVIEW_WHEN_INFERRED_TYPES and confidence < 0.8:
            return "pending_review"
        return "active"
    if source == "trajectory_eval":
        return "active"
    return "active"
