"""Compatibility facade for the fixed public-error catalog.

Public error helpers intentionally accept catalog enum members only.  They do
not accept exception instances, arbitrary strings, or dynamically supplied
codes, so exception text cannot be reintroduced at an HTTP or persistence
boundary through this module.
"""
from __future__ import annotations

from engine.app.safe_errors import FixedErrorCode, fixed_error_detail, fixed_error_message


class PublicErrorService:
    def public_message(self, code: FixedErrorCode) -> str:
        return fixed_error_message(code)

    def public_error(self, code: FixedErrorCode) -> dict[str, str]:
        return fixed_error_detail(code)


public_error_service = PublicErrorService()


def public_message(code: FixedErrorCode) -> str:
    return public_error_service.public_message(code)


def public_error(code: FixedErrorCode) -> dict[str, str]:
    return public_error_service.public_error(code)
