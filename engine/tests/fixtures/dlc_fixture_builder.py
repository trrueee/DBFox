"""Test fixture helper for generating .dbfox-dlc test archives."""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.integrity import (
    DlcIntegrity,
    build_signed_message_bytes,
    canonical_json_bytes,
)
from engine.dlc.manifest import DlcManifest
from engine.dlc.trust import public_key_to_base64


def generate_test_keypair() -> tuple[ed25519.Ed25519PrivateKey, str]:
    """Generate Ed25519 private key and Base64 public key string."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key_b64 = public_key_to_base64(private_key.public_key())
    return private_key, public_key_b64


def build_test_dlc_archive(
    manifest_data: dict[str, Any] | None = None,
    payload_files: dict[str, bytes | str] | None = None,
    *,
    private_key: ed25519.Ed25519PrivateKey | None = None,
    omit_signature: bool = False,
    corrupt_signature: bool = False,
    corrupt_manifest: bool = False,
    corrupt_integrity: bool = False,
    corrupt_payload_hash: str | None = None,
    extra_unlisted_files: dict[str, bytes | str] | None = None,
    omit_payload_file: str | None = None,
    raw_zip_entries: list[tuple[str, bytes]] | None = None,
) -> bytes:
    """Build a deterministic in-memory .dbfox-dlc ZIP archive for testing."""
    if raw_zip_entries is not None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in raw_zip_entries:
                zinfo = zipfile.ZipInfo(name)
                zf.writestr(zinfo, content)
        return buf.getvalue()


    # Default manifest
    default_manifest = {
        "manifestSchemaVersion": 1,
        "id": "acme.test_dlc",
        "version": "1.0.0",
        "displayName": "Acme Test DLC",
        "publisher": "acme",
        "description": "Test DLC for automated test suite",
        "extensionApiVersion": "2",
        "requiresDbfox": ">=1.0.0",
        "entrypoints": {
            "backend": "backend/entry.py",
            "frontend": "frontend/index.js",
        },
        "permissions": ["network:api.github.com"],
    }
    manifest_dict = manifest_data or default_manifest

    # Default payloads
    default_payloads: dict[str, bytes | str] = {
        "backend/__init__.py": "# init\n",
        "backend/entry.py": "def register(host):\n    pass\n",
        "frontend/index.js": "export function register(host) {}\n",
        "frontend/index.css": "/* styles */\n",
    }
    payloads = dict(payload_files if payload_files is not None else default_payloads)

    # Compute payload integrity entries
    integrity_entries: dict[str, str] = {}
    payload_bytes_map: dict[str, bytes] = {}

    for path, content in payloads.items():
        if isinstance(content, str):
            b = content.encode("utf-8")
        else:
            b = content
        payload_bytes_map[path] = b
        digest = hashlib.sha256(b).hexdigest().lower()
        if corrupt_payload_hash and path == corrupt_payload_hash:
            digest = "0" * 64
        integrity_entries[path] = digest

    # Build canonical JSON bytes
    if corrupt_manifest:
        canonical_manifest = b'{"malformed_json": '
    else:
        # Validate through DlcManifest to ensure exact schema
        manifest_obj = DlcManifest.model_validate(manifest_dict)
        canonical_manifest = canonical_json_bytes(manifest_obj.model_dump(by_alias=True, exclude_none=True))

    integrity_obj = DlcIntegrity(integrity_entries)
    if corrupt_integrity:
        canonical_integrity = b'{"entries": "not_a_dict"}'
    else:
        canonical_integrity = integrity_obj.canonical_bytes()

    # Build signed bytes & signature
    signature_b64: str | None = None
    if not omit_signature:
        signed_payload = build_signed_message_bytes(canonical_manifest, canonical_integrity)
        if private_key:
            sig_bytes = private_key.sign(signed_payload)
            if corrupt_signature:
                sig_bytes = b"X" * 64
            signature_b64 = base64.b64encode(sig_bytes).decode("ascii")

    # Construct ZIP archive
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", canonical_manifest)
        zf.writestr("integrity.json", canonical_integrity)
        if signature_b64:
            zf.writestr("signature.sig", signature_b64)

        for path, b in payload_bytes_map.items():
            if omit_payload_file and path == omit_payload_file:
                continue
            zf.writestr(path, b)

        if extra_unlisted_files:
            for extra_path, extra_content in extra_unlisted_files.items():
                if isinstance(extra_content, str):
                    extra_b = extra_content.encode("utf-8")
                else:
                    extra_b = extra_content
                zf.writestr(extra_path, extra_b)

    return buf.getvalue()
