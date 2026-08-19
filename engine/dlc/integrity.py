"""Cryptographic integrity mapping and canonical serialization for DBFox DLC packages."""

from __future__ import annotations

import json
import re
from typing import Any

from engine.dlc.errors import DlcError, DlcErrorCode

HEX_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SIGNED_PAYLOAD_MAGIC = b"DBFOX-DLC-V1\n"


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize a Python dict/data structure into canonical, deterministic UTF-8 JSON bytes."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def normalize_posix_archive_path(path_str: str) -> str:
    """Normalize and validate an archive relative path."""
    if not path_str or not isinstance(path_str, str):
        raise DlcError(DlcErrorCode.UNSAFE_PATH, "Empty archive path")

    # Reject backslashes
    if "\\" in path_str:
        raise DlcError(
            DlcErrorCode.UNSAFE_PATH,
            f"Backslash not allowed in archive path: '{path_str}'",
        )

    # Reject absolute or leading slash
    if path_str.startswith("/"):
        raise DlcError(
            DlcErrorCode.UNSAFE_PATH,
            f"Absolute path not allowed: '{path_str}'",
        )

    # Split into segments and validate
    segments = path_str.split("/")
    if any(s == ".." for s in segments):
        raise DlcError(
            DlcErrorCode.UNSAFE_PATH,
            f"Path traversal ('..') not allowed: '{path_str}'",
        )
    if any(s == "." for s in segments):
        raise DlcError(
            DlcErrorCode.UNSAFE_PATH,
            f"Current directory segment ('.') not allowed: '{path_str}'",
        )
    if any(s == "" for s in segments):
        raise DlcError(
            DlcErrorCode.UNSAFE_PATH,
            f"Empty path segment not allowed: '{path_str}'",
        )

    normalized = "/".join(segments)
    if len(normalized) > 255:
        raise DlcError(
            DlcErrorCode.PATH_TOO_LONG,
            f"Path exceeds 255 characters ({len(normalized)} chars): '{normalized}'",
        )

    return normalized


class DlcIntegrity:
    """Integrity mapping of normalized payload paths to SHA256 hex digests."""

    def __init__(self, entries: dict[str, str]) -> None:
        self._entries: dict[str, str] = {}
        for raw_path, digest in entries.items():
            norm_path = normalize_posix_archive_path(raw_path)
            # Integrity MUST NOT contain control files (integrity.json or signature.sig)
            if norm_path in ("integrity.json", "signature.sig"):
                raise DlcError(
                    DlcErrorCode.INVALID_INTEGRITY,
                    f"Control file '{norm_path}' cannot be listed in integrity.json",
                )
            if not isinstance(digest, str) or not HEX_SHA256_PATTERN.match(digest.lower()):
                raise DlcError(
                    DlcErrorCode.INVALID_INTEGRITY,
                    f"Invalid SHA256 hex digest for '{norm_path}': '{digest}'",
                )
            self._entries[norm_path] = digest.lower()

    @property
    def entries(self) -> dict[str, str]:
        return dict(self._entries)

    def get_digest(self, path: str) -> str | None:
        norm = normalize_posix_archive_path(path)
        return self._entries.get(norm)

    def to_dict(self) -> dict[str, Any]:
        return {"entries": dict(sorted(self._entries.items()))}

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_bytes(cls, raw_bytes: bytes) -> "DlcIntegrity":
        """Parse and strictly validate integrity.json from raw UTF-8 JSON bytes."""
        if len(raw_bytes) > 512 * 1024:
            raise DlcError(
                DlcErrorCode.PACKAGE_TOO_LARGE,
                f"integrity.json exceeds 512 KiB limit ({len(raw_bytes)} bytes)",
            )
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DlcError(
                DlcErrorCode.INVALID_INTEGRITY,
                f"Malformed JSON in integrity.json: {exc}",
            ) from exc

        if not isinstance(payload, dict) or "entries" not in payload:
            raise DlcError(
                DlcErrorCode.INVALID_INTEGRITY,
                "integrity.json must be a JSON object with an 'entries' mapping",
            )

        entries_raw = payload["entries"]
        if not isinstance(entries_raw, dict):
            raise DlcError(
                DlcErrorCode.INVALID_INTEGRITY,
                "'entries' in integrity.json must be a dictionary",
            )

        return cls(entries_raw)


def build_signed_message_bytes(
    canonical_manifest: bytes,
    canonical_integrity: bytes,
) -> bytes:
    """Construct the exact canonical byte representation for Ed25519 signature."""
    return SIGNED_PAYLOAD_MAGIC + canonical_manifest + b"\n" + canonical_integrity
