from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from engine.runtime_paths import write_private_text


class MissingEngineTokenError(RuntimeError):
    """Raised when a packaged engine starts without the Rust-provided token."""


@dataclass(frozen=True)
class RuntimeCredentialPolicy:
    token_file: Path
    is_frozen: bool
    env_var: str = "DBFOX_ENGINE_TOKEN"

    def resolve_token(self) -> str:
        env_token = os.environ.get(self.env_var, "").strip()
        if env_token:
            return env_token

        if self.is_frozen:
            raise MissingEngineTokenError(
                f"{self.env_var} is required when DBFox engine runs in frozen mode."
            )

        if self.token_file.exists():
            file_token = self.token_file.read_text(encoding="utf-8").strip()
            if file_token:
                return file_token

        token = secrets.token_hex(32)
        write_private_text(self.token_file, token)
        return token
