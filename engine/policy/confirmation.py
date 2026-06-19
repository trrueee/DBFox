import uuid
import time
import logging
import os
import sys
import json
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("dbfox.security.confirmation")

def confirmation_bypass_enabled() -> bool:
    """
    Checks if confirmation bypass is allowed.
    Only permitted in a local testing environment, never in production/frozen desktop applications.
    """
    return (
        os.environ.get("DBFOX_BYPASS_CONFIRMATION") == "1"
        and os.environ.get("DBFOX_TESTING") == "1"
        and not getattr(sys, "frozen", False)
    )

def sha256_hash(text: str) -> str:
    """Compute sha256 of text to safely bind it to a confirmation without leaking raw values in metastore/logs."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

class ConfirmationManager:
    """Dangerous-operation confirmation token manager.

    Tokens are persisted to the local SQLite database so that pending
    confirmations survive engine restarts (the desktop app may restart
    between the "create confirmation" and "validate" steps).
    """

    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._db_path: Path | None = None
        self._db_loaded = False
        # In-memory cache mirrors the DB for fast lookups under the lock.
        # Keyed by token → (expires_at, data_dict).
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_db_path(self) -> Path:
        """Return the engine DB path, creating the tokens table on first call.

        Does NOT acquire ``self._lock`` — safe to call from any context.
        """
        if self._db_path is not None:
            return self._db_path
        from engine.db import DB_PATH
        self._db_path = Path(DB_PATH)
        self._init_table()
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._get_db_path()))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db_loaded(self) -> None:
        """Restore unexpired tokens from DB into the cache (one-shot).

        Must be called OUTSIDE ``self._lock`` to avoid deadlock (the
        lock is not reentrant, and DB operations acquire the lock).
        """
        if self._db_loaded:
            return
        self._load_existing()
        self._db_loaded = True

    def _init_table(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS confirmation_tokens (
                        token TEXT PRIMARY KEY,
                        expires_at REAL NOT NULL,
                        datasource_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        expected_confirm_text TEXT NOT NULL DEFAULT ''
                    )
                """)
                conn.commit()
        except Exception:
            logger.exception("Failed to initialize confirmation_tokens table")

    def _load_existing(self) -> None:
        """Restore unexpired tokens from DB into the in-memory cache on startup."""
        now = time.time()
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT token, expires_at, datasource_id, action, details_json, expected_confirm_text "
                    "FROM confirmation_tokens WHERE expires_at > ?",
                    (now,),
                ).fetchall()
        except Exception:
            logger.exception("Failed to load existing confirmation tokens — operating memory-only")
            return

        with self._lock:
            restored = 0
            for row in rows:
                token = row["token"]
                if token in self._cache:
                    continue
                try:
                    details = json.loads(row["details_json"])
                except (json.JSONDecodeError, TypeError):
                    details = {}
                self._cache[token] = (
                    row["expires_at"],
                    {
                        "datasource_id": row["datasource_id"],
                        "action": row["action"],
                        "details": details,
                        "expected_confirm_text": row["expected_confirm_text"],
                    },
                )
                restored += 1
        if restored:
            logger.info("Restored %d unexpired confirmation token(s) from database", restored)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_confirmation(
        self, datasource_id: str, action: str,
        details: dict[str, Any], expected_confirm_text: str,
    ) -> str:
        self._ensure_db_loaded()
        with self._lock:
            now = time.time()
            self._cleanup(now)

            token = str(uuid.uuid4())
            expires_at = now + self._ttl
            data = {
                "datasource_id": str(datasource_id),
                "action": action,
                "details": details,
                "expected_confirm_text": expected_confirm_text,
            }

            # Persist to DB
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO confirmation_tokens"
                        " (token, expires_at, datasource_id, action, details_json, expected_confirm_text)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            token, expires_at, str(datasource_id),
                            action, json.dumps(details, ensure_ascii=False),
                            expected_confirm_text,
                        ),
                    )
                    conn.commit()
            except Exception:
                logger.exception("Failed to persist confirmation token — operating memory-only")

            # Cache in memory
            self._cache[token] = (expires_at, data)

            logger.info(
                "Created confirmation token %s... for action %s on datasource %s",
                token[:8], action, datasource_id,
            )
            return token

    def validate_and_consume(
        self,
        token: str,
        confirm_text: str,
        *,
        expected_action: str,
        expected_datasource_id: str,
        expected_details: dict[str, Any],
    ) -> tuple[bool, str]:
        """Validates and consumes a confirmation token with strict
        context-matching to prevent tampering or token reuse.

        Returns (is_valid, error_message).
        """
        self._ensure_db_loaded()
        with self._lock:
            now = time.time()
            self._cleanup(now)

            if not token or token not in self._cache:
                return False, "确认令牌无效或已过期，请重新发起操作。"

            expire_at, data = self._cache[token]
            # Consume token immediately (one-time use) — from both cache and DB
            del self._cache[token]
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM confirmation_tokens WHERE token = ?", (token,))
                    conn.commit()
            except Exception:
                logger.exception("Failed to delete consumed confirmation token from DB")

            if now > expire_at:
                return False, "确认令牌已过期，请重新发起操作。"

            # 1. Action Check
            if data["action"] != expected_action:
                return False, "二次确认操作类型不匹配，安全拒绝执行。"

            # 2. Datasource Check
            if str(data["datasource_id"]) != str(expected_datasource_id):
                return False, "二次确认数据源不匹配，安全拒绝执行。"

            # 3. Parameter / Details Check
            for k, expected_val in expected_details.items():
                actual_val = data["details"].get(k)
                if str(actual_val) != str(expected_val):
                    return False, f"二次确认参数 '{k}' 不匹配，操作可能已被篡改，安全拒绝执行。"

            # 4. Confirmation Text Check
            expected_text = data["expected_confirm_text"].strip()
            if confirm_text.strip() != expected_text:
                return False, f"二次确认文本不匹配！请输入数据源名称 '{expected_text}' 进行确认。"

            logger.info(
                "Successfully consumed confirmation token %s... for action %s",
                token[:8], data["action"],
            )
            return True, ""

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def _cleanup(self, now: float) -> None:
        """Remove expired tokens from the in-memory cache.

        DB cleanup is deferred to startup (_load_existing naturally skips
        expired rows).  Periodic deep-clean runs on create_confirmation.
        """
        expired = [t for t, (exp, _) in self._cache.items() if now > exp]
        for token in expired:
            del self._cache[token]
        if expired:
            # Best-effort: delete expired from DB as well
            try:
                with self._connect() as conn:
                    conn.execute(
                        "DELETE FROM confirmation_tokens WHERE expires_at <= ?", (now,)
                    )
                    conn.commit()
            except Exception:
                pass

# Global confirmation manager instance
confirmation_manager = ConfirmationManager()
