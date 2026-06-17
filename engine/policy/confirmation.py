import uuid
import time
import logging
import os
import sys
import hashlib
import threading
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
    def __init__(self, ttl_seconds: int = 300):
        self._confirmations: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create_confirmation(self, datasource_id: str, action: str, details: dict[str, Any], expected_confirm_text: str) -> str:
        with self._lock:
            # Clean expired first
            now = time.time()
            self._cleanup(now)
            
            token = str(uuid.uuid4())
            self._confirmations[token] = (
                now + self._ttl,
                {
                    "datasource_id": str(datasource_id),
                    "action": action,
                    "details": details,
                    "expected_confirm_text": expected_confirm_text
                }
            )
            logger.info("Created confirmation token %s... for action %s on datasource %s", token[:8], action, datasource_id)
            return token

    def validate_and_consume(
        self,
        token: str,
        confirm_text: str,
        *,
        expected_action: str,
        expected_datasource_id: str,
        expected_details: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Validates and consumes a confirmation token with strict context-matching to prevent tampering or token reuse.
        Returns (is_valid, error_message)
        """
        with self._lock:
            now = time.time()
            self._cleanup(now)
            
            if not token or token not in self._confirmations:
                return False, "确认令牌无效或已过期，请重新发起操作。"
                
            expire_at, data = self._confirmations[token]
            # Consume token immediately (one-time use)
            del self._confirmations[token]
            
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
                
            logger.info("Successfully consumed confirmation token %s... for action %s", token[:8], data["action"])
            return True, ""

    def _cleanup(self, now: float) -> None:
        expired = [token for token, (exp_time, _) in self._confirmations.items() if now > exp_time]
        for token in expired:
            del self._confirmations[token]

# Global confirmation manager instance
confirmation_manager = ConfirmationManager()
