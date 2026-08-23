"""Cryptographic signature verification and trust store for DBFox DLC packages."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from enum import StrEnum
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.integrity import canonical_json_bytes

TRUST_STORE_SCHEMA_VERSION = 1
MAX_TRUST_STORE_BYTES = 1024 * 1024
MAX_TRUSTED_PUBLISHERS = 1024
KEY_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DlcTrustStatus(StrEnum):
    TRUSTED_SIGNED = "trusted_signed"
    DEVELOPER_UNSIGNED = "developer_unsigned"
    DEVELOPER_SIGNED = "developer_signed"
    UNTRUSTED = "untrusted"



def public_key_from_base64(b64_str: str) -> ed25519.Ed25519PublicKey:
    """Parse Ed25519 public key from raw 32-byte Base64 string."""
    try:
        if not isinstance(b64_str, str):
            raise TypeError("public key must be a Base64 string")
        raw_bytes = base64.b64decode(b64_str, validate=True)
        if len(raw_bytes) != 32:
            raise ValueError(f"Expected 32 bytes, got {len(raw_bytes)}")
        if base64.b64encode(raw_bytes).decode("ascii") != b64_str:
            raise ValueError("Expected canonical padded Base64 encoding")
        return ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)
    except Exception as exc:
        raise DlcError(
            DlcErrorCode.INVALID_SIGNATURE,
            f"Invalid Ed25519 public key encoding: {exc}",
        ) from exc


def public_key_to_base64(public_key: ed25519.Ed25519PublicKey) -> str:
    """Export Ed25519 public key to raw 32-byte Base64 string."""
    raw_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw_bytes).decode("ascii")


def compute_key_fingerprint(public_key: ed25519.Ed25519PublicKey) -> str:
    """Compute SHA256 hex fingerprint of raw 32-byte public key."""
    raw_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw_bytes).hexdigest().lower()


class DlcTrustVerifier:
    """Verifies Ed25519 digital signatures over canonical signed payload bytes."""

    @staticmethod
    def verify_signature(
        signed_payload: bytes,
        signature_base64: str,
        public_key_base64: str,
    ) -> bool:
        """Verify Ed25519 signature."""
        try:
            pub_key = public_key_from_base64(public_key_base64)
            sig_bytes = base64.b64decode(signature_base64, validate=True)
            if len(sig_bytes) != 64:
                return False
            pub_key.verify(sig_bytes, signed_payload)
            return True
        except (InvalidSignature, ValueError, TypeError, DlcError):
            return False


class TrustedPublishersPayload(BaseModel):
    """Strict, metadata-free persistent publisher trust contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=TRUST_STORE_SCHEMA_VERSION, ge=1, le=1)
    trusted_publishers: dict[str, str] = Field(
        default_factory=dict,
        max_length=MAX_TRUSTED_PUBLISHERS,
    )

    @field_validator("trusted_publishers")
    @classmethod
    def validate_publishers(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_fingerprint, public_key_base64 in value.items():
            fingerprint = raw_fingerprint.lower()
            if not KEY_FINGERPRINT_PATTERN.fullmatch(fingerprint):
                raise ValueError(f"Invalid publisher fingerprint: {raw_fingerprint!r}")
            public_key = public_key_from_base64(public_key_base64)
            actual_fingerprint = compute_key_fingerprint(public_key)
            if actual_fingerprint != fingerprint:
                raise ValueError(
                    f"Publisher key fingerprint mismatch: expected {fingerprint}, got {actual_fingerprint}"
                )
            normalized[fingerprint] = public_key_to_base64(public_key)
        return normalized


class DlcTrustStore:
    """Host-managed repository of trusted publisher public keys."""

    def __init__(
        self,
        trusted_keys: dict[str, str] | None = None,
        *,
        storage_root: Path | None = None,
    ) -> None:
        self.storage_root = storage_root.resolve() if storage_root is not None else None
        self.trust_store_file = (
            self.storage_root / "trusted_publishers.json"
            if self.storage_root is not None
            else None
        )
        self._trusted_keys: dict[str, str] = {}
        for public_key_base64 in (trusted_keys or {}).values():
            public_key = public_key_from_base64(public_key_base64)
            self._trusted_keys[compute_key_fingerprint(public_key)] = public_key_to_base64(
                public_key
            )

    def load(self) -> dict[str, str]:
        """Load trusted publishers, failing closed on any malformed persisted state."""
        if self.trust_store_file is None:
            return dict(self._trusted_keys)
        if not self.trust_store_file.is_file():
            return dict(self._trusted_keys)

        file_size = self.trust_store_file.stat().st_size
        if file_size > MAX_TRUST_STORE_BYTES:
            raise DlcError(
                DlcErrorCode.TRUST_STORE_CORRUPT,
                f"trusted_publishers.json exceeds size limit ({file_size} bytes)",
            )
        try:
            raw_bytes = self.trust_store_file.read_bytes()
            data = json.loads(raw_bytes.decode("utf-8"))
            payload = TrustedPublishersPayload.model_validate(data)
            # Host-bundled publisher keys are immutable trust roots. Persisted
            # user decisions extend that set; they cannot remove or replace a
            # key compiled into the running Host.
            trusted_publishers = dict(payload.trusted_publishers)
            for fingerprint, public_key in self._trusted_keys.items():
                persisted = trusted_publishers.get(fingerprint)
                if persisted is not None and persisted != public_key:
                    raise ValueError(
                        f"trusted publisher fingerprint collision: {fingerprint}"
                    )
                trusted_publishers[fingerprint] = public_key
            return trusted_publishers
        except Exception as exc:
            raise DlcError(
                DlcErrorCode.TRUST_STORE_CORRUPT,
                f"Failed to parse trusted_publishers.json: {exc}",
            ) from exc

    def save(self, trusted_publishers: dict[str, str]) -> None:
        """Atomically persist the complete bounded trust mapping."""
        payload = TrustedPublishersPayload(
            schema_version=TRUST_STORE_SCHEMA_VERSION,
            trusted_publishers=trusted_publishers,
        )
        if self.trust_store_file is None or self.storage_root is None:
            self._trusted_keys = dict(payload.trusted_publishers)
            return

        canonical_bytes = canonical_json_bytes(payload.model_dump())
        if len(canonical_bytes) > MAX_TRUST_STORE_BYTES:
            raise DlcError(
                DlcErrorCode.INSTALL_IO_ERROR,
                "trusted_publishers.json exceeds its serialized size limit",
            )

        self.storage_root.mkdir(parents=True, exist_ok=True)
        fd, temp_path_str = tempfile.mkstemp(
            prefix="trusted_publishers_tmp_",
            dir=str(self.storage_root),
        )
        temp_path = Path(temp_path_str)
        try:
            with os.fdopen(fd, "wb") as file_handle:
                file_handle.write(canonical_bytes)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temp_path, self.trust_store_file)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            raise DlcError(
                DlcErrorCode.INSTALL_IO_ERROR,
                f"Failed to atomically write trusted_publishers.json: {exc}",
            ) from exc

    def add_trusted_key(self, public_key_base64: str) -> str:
        """Add a trusted public key and return its fingerprint."""
        pub_key = public_key_from_base64(public_key_base64)
        fingerprint = compute_key_fingerprint(pub_key)
        trusted_publishers = self.load()
        if (
            fingerprint not in trusted_publishers
            and len(trusted_publishers) >= MAX_TRUSTED_PUBLISHERS
        ):
            raise DlcError(
                DlcErrorCode.TRUST_STORE_FULL,
                f"Trusted publisher limit of {MAX_TRUSTED_PUBLISHERS} has been reached",
            )
        trusted_publishers[fingerprint] = public_key_to_base64(pub_key)
        self.save(trusted_publishers)
        return fingerprint

    def get_public_key(self, fingerprint: str) -> str | None:
        return self.load().get(fingerprint.lower())

    def is_trusted(self, fingerprint: str) -> bool:
        return fingerprint.lower() in self.load()

    def list_trusted_keys(self) -> list[str]:
        """Return list of all trusted public key Base64 strings."""
        trusted_publishers = self.load()
        return [trusted_publishers[key] for key in sorted(trusted_publishers)]

    def verify_package_trust(
        self,
        signed_payload: bytes,
        signature_base64: str | None,
        publisher_key_base64: str | None,
        *,
        developer_mode: bool = False,
    ) -> tuple[DlcTrustStatus, str | None]:
        """Authenticate signature bytes, then project the independent trust state.

        Returns (DlcTrustStatus, publisher_key_fingerprint).
        """
        # Case 1: Unsigned package
        if not signature_base64 or not publisher_key_base64:
            if developer_mode:
                return DlcTrustStatus.DEVELOPER_UNSIGNED, None
            raise DlcError(
                DlcErrorCode.SIGNATURE_REQUIRED,
                "Package is unsigned or missing signature.sig. Developer Mode is required to install unsigned packages.",
            )

        # Case 2: Signed package - verify signature bytes
        is_valid = DlcTrustVerifier.verify_signature(
            signed_payload,
            signature_base64,
            publisher_key_base64,
        )
        if not is_valid:
            raise DlcError(
                DlcErrorCode.INVALID_SIGNATURE,
                "Digital signature verification failed. Package contents or manifest may have been tampered with.",
            )

        pub_key = public_key_from_base64(publisher_key_base64)
        fingerprint = compute_key_fingerprint(pub_key)

        # Trust is a separate durable policy decision from signature authenticity.
        if self.is_trusted(fingerprint):
            return DlcTrustStatus.TRUSTED_SIGNED, fingerprint

        # If not in trusted store, allow in developer mode
        if developer_mode:
            return DlcTrustStatus.DEVELOPER_SIGNED, fingerprint

        return DlcTrustStatus.UNTRUSTED, fingerprint
