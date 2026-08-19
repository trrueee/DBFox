"""Cryptographic signature verification and trust store for DBFox DLC packages."""

from __future__ import annotations

import base64
import hashlib
from enum import StrEnum

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.errors import DlcError, DlcErrorCode


class DlcTrustStatus(StrEnum):
    TRUSTED_SIGNED = "trusted_signed"
    DEVELOPER_UNSIGNED = "developer_unsigned"
    DEVELOPER_SIGNED = "developer_signed"


def public_key_from_base64(b64_str: str) -> ed25519.Ed25519PublicKey:
    """Parse Ed25519 public key from raw 32-byte Base64 string."""
    try:
        raw_bytes = base64.b64decode(b64_str)
        if len(raw_bytes) != 32:
            raise ValueError(f"Expected 32 bytes, got {len(raw_bytes)}")
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
            sig_bytes = base64.b64decode(signature_base64)
            if len(sig_bytes) != 64:
                return False
            pub_key.verify(sig_bytes, signed_payload)
            return True
        except (InvalidSignature, ValueError, Exception):
            return False


class DlcTrustStore:
    """Host-managed repository of trusted publisher public keys."""

    def __init__(self, trusted_keys: dict[str, str] | None = None) -> None:
        # Map fingerprint -> public_key_base64
        self._trusted_keys: dict[str, str] = dict(trusted_keys or {})

    def add_trusted_key(self, public_key_base64: str) -> str:
        """Add a trusted public key and return its fingerprint."""
        pub_key = public_key_from_base64(public_key_base64)
        fingerprint = compute_key_fingerprint(pub_key)
        self._trusted_keys[fingerprint] = public_key_base64
        return fingerprint

    def get_public_key(self, fingerprint: str) -> str | None:
        return self._trusted_keys.get(fingerprint.lower())

    def is_trusted(self, fingerprint: str) -> bool:
        return fingerprint.lower() in self._trusted_keys

    def verify_package_trust(
        self,
        signed_payload: bytes,
        signature_base64: str | None,
        publisher_key_base64: str | None,
        *,
        developer_mode: bool = False,
    ) -> tuple[DlcTrustStatus, str | None]:
        """Authenticate package bytes against trust store or Developer Mode policy.

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

        # Check if publisher key is in trusted store
        if self.is_trusted(fingerprint):
            return DlcTrustStatus.TRUSTED_SIGNED, fingerprint

        # If not in trusted store, allow in developer mode
        if developer_mode:
            return DlcTrustStatus.DEVELOPER_SIGNED, fingerprint

        raise DlcError(
            DlcErrorCode.UNTRUSTED_PUBLISHER,
            f"Publisher key (fingerprint {fingerprint[:16]}...) is not in the DBFox trusted publisher store.",
            details={"fingerprint": fingerprint},
        )
