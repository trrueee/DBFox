from __future__ import annotations

from typing import Any

from engine.policy.error_sanitizer import sanitize_error_message


class PublicErrorService:
    def public_message(self, exc_or_message: Exception | str) -> str:
        return sanitize_error_message(str(exc_or_message))

    def public_error(self, code: str, exc_or_message: Exception | str) -> dict[str, Any]:
        return {
            "code": code,
            "message": self.public_message(exc_or_message),
        }


public_error_service = PublicErrorService()


def public_message(exc_or_message: Exception | str) -> str:
    return public_error_service.public_message(exc_or_message)


def public_error(code: str, exc_or_message: Exception | str) -> dict[str, Any]:
    return public_error_service.public_error(code, exc_or_message)
