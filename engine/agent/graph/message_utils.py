from __future__ import annotations

from typing import Any


def message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "")
    return str(getattr(message, "role", None) or getattr(message, "type", None) or "")


def message_content_text(message: Any) -> str:
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("text")
        ]
        return " ".join(parts).strip()
    return str(content or "").strip()


def first_user_text(messages: list[Any]) -> str:
    for message in messages:
        if message_role(message) in {"user", "human"}:
            return message_content_text(message)
    if not messages:
        return ""
    return message_content_text(messages[0])


def is_ai_message(message: Any) -> bool:
    if isinstance(message, dict):
        return message_role(message) in {"assistant", "ai"}
    return message_role(message) in {"assistant", "ai"} or message.__class__.__name__ == "AIMessage"


def message_tool_calls(message: Any) -> list[Any]:
    if isinstance(message, dict):
        return list(message.get("tool_calls") or [])
    return list(getattr(message, "tool_calls", None) or [])
