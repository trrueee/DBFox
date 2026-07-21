"""Persistent confirmation tokens for destructive operations.

Confirmation state is metadata, not process-local cache.  The owning API
request supplies the SQLAlchemy session so creation and one-time consumption
use the same Alembic-managed database contract as the operation it protects.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sys
import time
from typing import Any

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from engine.errors import DBFoxError
from engine.models import ConfirmationToken


logger = logging.getLogger("dbfox.security.confirmation")

_INVALID_TOKEN_MESSAGE = "确认令牌无效或已过期，请重新发起操作。"
_EXPIRED_TOKEN_MESSAGE = "确认令牌已过期，请重新发起操作。"
_ACTION_MISMATCH_MESSAGE = "二次确认操作类型不匹配，安全拒绝执行。"
_DATASOURCE_MISMATCH_MESSAGE = "二次确认数据源不匹配，安全拒绝执行。"
_DETAILS_MISMATCH_MESSAGE = "二次确认参数不匹配，操作可能已被篡改，安全拒绝执行。"


def confirmation_bypass_enabled() -> bool:
    """Allow confirmation bypass only in an explicit non-frozen test process."""
    return (
        os.environ.get("DBFOX_BYPASS_CONFIRMATION") == "1"
        and os.environ.get("DBFOX_TESTING") == "1"
        and not getattr(sys, "frozen", False)
    )


def sha256_hash(text: str) -> str:
    """Return a SHA-256 digest for callers that need a non-plaintext binding."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ConfirmationPersistenceError(DBFoxError):
    """Fail closed when durable confirmation state cannot be changed."""

    def __init__(self) -> None:
        super().__init__("确认令牌服务暂不可用，请稍后重试。", "CONFIRMATION_UNAVAILABLE")


def _canonical_details_json(details: dict[str, Any]) -> str:
    """Serialize the complete confirmation context into a stable comparison key."""
    if not isinstance(details, dict) or any(not isinstance(key, str) for key in details):
        raise ValueError("Confirmation details must be a mapping with string keys.")
    try:
        return json.dumps(
            details,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Confirmation details must be JSON serializable.") from exc


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Confirmation {field_name} must not be empty.")
    return normalized


class ConfirmationManager:
    """Create and atomically consume durable confirmation tokens.

    This class deliberately owns no cache, connection, or runtime-path state.
    A matching ``DELETE`` is the consume operation: only one concurrent request
    can delete the token with its complete expected context.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds

    def create_confirmation(
        self,
        *,
        db: Session,
        datasource_id: str,
        action: str,
        details: dict[str, Any],
        expected_confirm_text: str,
    ) -> str:
        """Persist a confirmation token before returning it to the client.

        There is intentionally no memory-only fallback.  If the metadata write
        fails, the protected operation cannot advance to its confirmation step.
        """
        now = time.time()
        token = secrets.token_urlsafe(32)
        record = ConfirmationToken(
            token=token,
            expires_at=now + self._ttl,
            datasource_id=_required_text(datasource_id, "datasource id"),
            action=_required_text(action, "action"),
            details_json=_canonical_details_json(details),
            expected_confirm_text=_required_text(expected_confirm_text, "text"),
        )

        try:
            db.execute(
                delete(ConfirmationToken).where(ConfirmationToken.expires_at <= now)
            )
            db.add(record)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.warning("Confirmation token persistence failed (%s)", type(exc).__name__)
            raise ConfirmationPersistenceError() from exc

        return token

    def validate_and_consume(
        self,
        *,
        db: Session,
        token: str,
        confirm_text: str,
        expected_action: str,
        expected_datasource_id: str,
        expected_details: dict[str, Any],
    ) -> tuple[bool, str]:
        """Validate and consume a token with a single context-bound delete.

        The successful path is atomic even when multiple API workers race on
        the same token.  Failed attempts retain the token so an operator can
        correct a typo; all operation identity fields remain bound in the SQL
        predicate and cannot be changed by a retry.
        """
        if not token:
            return False, _INVALID_TOKEN_MESSAGE

        now = time.time()
        expected_action = _required_text(expected_action, "action")
        expected_datasource_id = _required_text(expected_datasource_id, "datasource id")
        expected_details_json = _canonical_details_json(expected_details)
        # An empty operator response is a normal validation failure, not a
        # programming error.  Keep it in the predicate so it cannot consume a
        # token issued for a non-empty datasource name.
        normalized_confirm_text = str(confirm_text).strip()

        try:
            result = db.execute(
                delete(ConfirmationToken).where(
                    ConfirmationToken.token == token,
                    ConfirmationToken.expires_at > now,
                    ConfirmationToken.action == expected_action,
                    ConfirmationToken.datasource_id == expected_datasource_id,
                    ConfirmationToken.details_json == expected_details_json,
                    ConfirmationToken.expected_confirm_text == normalized_confirm_text,
                )
            )
            if getattr(result, "rowcount", None) == 1:
                db.commit()
                return True, ""
            db.rollback()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.warning("Confirmation token consumption failed (%s)", type(exc).__name__)
            raise ConfirmationPersistenceError() from exc

        # A failed delete has not consumed anything.  The diagnostic below is
        # derived from the durable row only; it never permits an operation.
        try:
            record = db.get(ConfirmationToken, token)
            if record is None:
                return False, _INVALID_TOKEN_MESSAGE
            if record.expires_at <= now:
                db.delete(record)
                db.commit()
                return False, _EXPIRED_TOKEN_MESSAGE
            if record.action != expected_action:
                return False, _ACTION_MISMATCH_MESSAGE
            if record.datasource_id != expected_datasource_id:
                return False, _DATASOURCE_MISMATCH_MESSAGE
            if record.details_json != expected_details_json:
                return False, _DETAILS_MISMATCH_MESSAGE
            if record.expected_confirm_text != normalized_confirm_text:
                return (
                    False,
                    f"二次确认文本不匹配！请输入数据源名称 '{record.expected_confirm_text}' 进行确认。",
                )
            # A concurrent successful delete can make the row disappear before
            # the context lookup.  Any other unexpected mismatch is denied.
            return False, _INVALID_TOKEN_MESSAGE
        except SQLAlchemyError as exc:
            db.rollback()
            logger.warning("Confirmation token lookup failed (%s)", type(exc).__name__)
            raise ConfirmationPersistenceError() from exc


confirmation_manager = ConfirmationManager()
