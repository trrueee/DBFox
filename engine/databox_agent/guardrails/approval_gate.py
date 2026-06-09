from __future__ import annotations

from typing import Any


def requires_human_approval(tool_name: str, args: dict[str, Any]) -> bool:
    """Return True if a tool execution definitely requires human confirmation."""
    # This is handled dynamically by PolicyGate checks.
    return False
