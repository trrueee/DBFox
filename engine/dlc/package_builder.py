"""Deterministic DBFox DLC package construction and Ed25519 signing."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.frontend_contract import validate_frontend_bundle
from engine.dlc.integrity import (
    DlcIntegrity,
    build_signed_message_bytes,
    canonical_json_bytes,
    normalize_posix_archive_path,
)
from engine.dlc.manifest import DlcManifest, DlcManifestV2
from engine.dlc.package_contract import (
    CONTROL_FILES,
    MAX_ARCHIVE_BYTES,
    MAX_EXTRACTED_BYTES,
    MAX_FILE_COUNT,
    MAX_SINGLE_FILE_BYTES,
    PAYLOAD_ROOTS,
    PROHIBITED_EXTENSIONS,
)
from engine.dlc.trust import compute_key_fingerprint, public_key_to_base64

MANIFEST_TEMPLATE_NAME = "manifest.template.json"
PUBLISHER_KEY_PLACEHOLDER = "__PUBLISHER_KEY_BASE64__"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_IGNORED_DIRECTORY_NAMES = frozenset({"__pycache__", "node_modules", ".git"})


@dataclass(frozen=True)
class BuiltDlcPackage:
    archive_bytes: bytes
    package_digest: str
    manifest: DlcManifest
    publisher_fingerprint: str | None


def load_private_key(
    path: Path,
    *,
    password: bytes | None = None,
) -> ed25519.Ed25519PrivateKey:
    try:
        loaded = serialization.load_pem_private_key(path.read_bytes(), password=password)
    except Exception as exc:
        raise ValueError(f"Unable to load private key '{path}': {exc}") from exc
    if not isinstance(loaded, ed25519.Ed25519PrivateKey):
        raise ValueError(f"Private key '{path}' is not an Ed25519 key")
    return loaded


def load_public_key(path: Path) -> ed25519.Ed25519PublicKey:
    try:
        loaded = serialization.load_pem_public_key(path.read_bytes())
    except Exception as exc:
        raise ValueError(f"Unable to load public key '{path}': {exc}") from exc
    if not isinstance(loaded, ed25519.Ed25519PublicKey):
        raise ValueError(f"Public key '{path}' is not an Ed25519 key")
    return loaded


def write_keypair(
    private_key_path: Path,
    *,
    password: bytes | None,
) -> tuple[Path, str]:
    """Create an Ed25519 keypair without overwriting or printing private bytes."""
    private_key_path = private_key_path.resolve()
    public_key_path = private_key_path.with_suffix(private_key_path.suffix + ".pub")
    if private_key_path.exists() or public_key_path.exists():
        raise FileExistsError("Refusing to overwrite an existing publisher key")
    private_key_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = ed25519.Ed25519PrivateKey.generate()
    encryption: serialization.KeySerializationEncryption
    if password is None:
        encryption = serialization.NoEncryption()
    else:
        encryption = serialization.BestAvailableEncryption(password)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _write_new_private_file(private_key_path, private_bytes)
    try:
        public_key_path.write_bytes(public_bytes)
    except Exception:
        private_key_path.unlink(missing_ok=True)
        raise
    return public_key_path, compute_key_fingerprint(private_key.public_key())


def _write_new_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def read_manifest_template(source_root: Path) -> dict[str, Any]:
    path = source_root / MANIFEST_TEMPLATE_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Unable to read '{path}': {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"'{path}' must contain one JSON object")
    return value


def collect_payload_files(source_root: Path) -> dict[str, bytes]:
    """Collect only backend/frontend payload trees and reject symlink inputs."""
    source_root = source_root.resolve()
    payload: dict[str, bytes] = {}
    for root_name in sorted(PAYLOAD_ROOTS):
        payload_root = source_root / root_name
        if not payload_root.exists():
            continue
        if payload_root.is_symlink() or not payload_root.is_dir():
            raise ValueError(f"Payload root '{payload_root}' must be a real directory")
        for current_root, directories, filenames in os.walk(payload_root, followlinks=False):
            current_path = Path(current_root)
            for directory in list(directories):
                directory_path = current_path / directory
                if directory in _IGNORED_DIRECTORY_NAMES:
                    directories.remove(directory)
                elif directory_path.is_symlink():
                    raise ValueError(f"Symlink payload paths are not allowed: '{directory_path}'")
            for filename in sorted(filenames):
                path = current_path / filename
                if path.is_symlink():
                    raise ValueError(f"Symlink payload paths are not allowed: '{path}'")
                relative = normalize_posix_archive_path(path.relative_to(source_root).as_posix())
                payload[relative] = path.read_bytes()
    if not payload:
        raise ValueError("DLC source contains no backend or frontend payload files")
    return dict(sorted(payload.items()))


def build_dlc_package(
    manifest_data: Mapping[str, Any],
    payload_files: Mapping[str, bytes | str],
    *,
    private_key: ed25519.Ed25519PrivateKey | None = None,
    public_key: ed25519.Ed25519PublicKey | None = None,
) -> BuiltDlcPackage:
    """Build a byte-for-byte deterministic signed or unsigned package."""
    if private_key is not None and public_key is not None:
        if public_key_to_base64(private_key.public_key()) != public_key_to_base64(public_key):
            raise ValueError("Private and public publisher keys do not match")
    effective_public_key = private_key.public_key() if private_key is not None else public_key
    manifest_dict = dict(manifest_data)
    if effective_public_key is not None:
        supplied_publisher_key = public_key_to_base64(effective_public_key)
        declared_publisher_key = manifest_dict.get("publisherKey")
        if declared_publisher_key not in (
            None,
            PUBLISHER_KEY_PLACEHOLDER,
            supplied_publisher_key,
        ):
            raise ValueError("Publisher key does not match manifest publisherKey")
        manifest_dict["publisherKey"] = supplied_publisher_key
    if manifest_dict.get("publisherKey") == PUBLISHER_KEY_PLACEHOLDER:
        raise ValueError("A publisher private or public key is required to replace the manifest placeholder")
    manifest = DlcManifestV2.model_validate(manifest_dict)

    payload_bytes = _validate_payloads(manifest, payload_files)
    integrity = DlcIntegrity(
        {path: hashlib.sha256(content).hexdigest() for path, content in payload_bytes.items()}
    )
    canonical_manifest = canonical_json_bytes(
        manifest.model_dump(by_alias=True, exclude_none=True)
    )
    canonical_integrity = integrity.canonical_bytes()
    signature_base64: str | None = None
    publisher_fingerprint = (
        compute_key_fingerprint(effective_public_key)
        if effective_public_key is not None
        else None
    )
    if private_key is not None:
        signature = private_key.sign(
            build_signed_message_bytes(canonical_manifest, canonical_integrity)
        )
        signature_base64 = base64.b64encode(signature).decode("ascii")

    archive_bytes = _write_archive(
        canonical_manifest,
        canonical_integrity,
        payload_bytes,
        signature_base64=signature_base64,
    )
    return BuiltDlcPackage(
        archive_bytes=archive_bytes,
        package_digest=hashlib.sha256(archive_bytes).hexdigest(),
        manifest=manifest,
        publisher_fingerprint=publisher_fingerprint,
    )


def build_dlc_package_from_source(
    source_root: Path,
    *,
    private_key: ed25519.Ed25519PrivateKey | None = None,
    public_key: ed25519.Ed25519PublicKey | None = None,
) -> BuiltDlcPackage:
    source_root = source_root.resolve()
    return build_dlc_package(
        read_manifest_template(source_root),
        collect_payload_files(source_root),
        private_key=private_key,
        public_key=public_key,
    )


def sign_unsigned_archive(
    archive_bytes: bytes,
    private_key: ed25519.Ed25519PrivateKey,
) -> BuiltDlcPackage:
    """Authenticate an unsigned builder archive structurally, then sign it."""
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Unsigned archive exceeds the package size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            names = archive.namelist()
            if "signature.sig" in names:
                raise ValueError("Input archive is already signed")
            if len(names) != len(set(names)):
                raise ValueError("Unsigned archive contains duplicate paths")
            if "manifest.json" not in names or "integrity.json" not in names:
                raise ValueError("Unsigned archive is missing control files")
            manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
            integrity = DlcIntegrity.from_bytes(archive.read("integrity.json"))
            payload = {path: archive.read(path) for path in integrity.entries}
            if set(names) != {"manifest.json", "integrity.json", *payload}:
                raise ValueError("Unsigned archive contains files outside its integrity allowlist")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid unsigned archive: {exc}") from exc
    for path, expected in integrity.entries.items():
        if hashlib.sha256(payload[path]).hexdigest() != expected:
            raise ValueError(f"Unsigned archive payload digest mismatch for '{path}'")
    declared_publisher_key = manifest_data.get("publisherKey")
    signing_publisher_key = public_key_to_base64(private_key.public_key())
    if declared_publisher_key not in (
        None,
        PUBLISHER_KEY_PLACEHOLDER,
        signing_publisher_key,
    ):
        raise ValueError("Signing key does not match the unsigned package publisherKey")
    return build_dlc_package(manifest_data, payload, private_key=private_key)


def _validate_payloads(
    manifest: DlcManifest,
    payload_files: Mapping[str, bytes | str],
) -> dict[str, bytes]:
    if len(payload_files) > MAX_FILE_COUNT - len(CONTROL_FILES):
        raise DlcError(DlcErrorCode.TOO_MANY_FILES, "DLC payload has too many files")
    normalized: dict[str, bytes] = {}
    case_map: dict[str, str] = {}
    total_size = 0
    for raw_path, raw_content in payload_files.items():
        path = normalize_posix_archive_path(raw_path)
        if path in CONTROL_FILES or path.split("/", 1)[0] not in PAYLOAD_ROOTS:
            raise DlcError(
                DlcErrorCode.UNLISTED_FILE,
                f"Payload path '{path}' is outside the backend/frontend allowlist",
            )
        lower_path = path.lower()
        if lower_path in case_map:
            raise DlcError(
                DlcErrorCode.CASE_COLLISION,
                f"Case-insensitive payload collision: '{path}' and '{case_map[lower_path]}'",
            )
        if lower_path.endswith(PROHIBITED_EXTENSIONS):
            raise DlcError(
                DlcErrorCode.NATIVE_EXTENSION_NOT_ALLOWED,
                f"Native binary extension is not allowed: '{path}'",
            )
        content = raw_content.encode("utf-8") if isinstance(raw_content, str) else raw_content
        if len(content) > MAX_SINGLE_FILE_BYTES:
            raise DlcError(DlcErrorCode.SINGLE_FILE_TOO_LARGE, f"Payload '{path}' is too large")
        total_size += len(content)
        if total_size > MAX_EXTRACTED_BYTES:
            raise DlcError(DlcErrorCode.EXTRACTED_TOO_LARGE, "DLC payload is too large")
        normalized[path] = content
        case_map[lower_path] = path

    for entrypoint in (manifest.entrypoints.backend, manifest.entrypoints.frontend):
        if entrypoint and entrypoint not in normalized:
            raise DlcError(
                DlcErrorCode.MISSING_FILE,
                f"Declared entrypoint '{entrypoint}' is missing from the payload",
            )
    if manifest.entrypoints.frontend:
        frontend_path = manifest.entrypoints.frontend
        validate_frontend_bundle(frontend_path, normalized[frontend_path])
    return dict(sorted(normalized.items()))


def _write_archive(
    manifest_bytes: bytes,
    integrity_bytes: bytes,
    payload_files: Mapping[str, bytes],
    *,
    signature_base64: str | None,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        _write_zip_entry(archive, "manifest.json", manifest_bytes)
        _write_zip_entry(archive, "integrity.json", integrity_bytes)
        if signature_base64 is not None:
            _write_zip_entry(archive, "signature.sig", signature_base64.encode("ascii"))
        for path in sorted(payload_files):
            _write_zip_entry(archive, path, payload_files[path])
    result = buffer.getvalue()
    if len(result) > MAX_ARCHIVE_BYTES:
        raise DlcError(DlcErrorCode.PACKAGE_TOO_LARGE, "Built package exceeds 50 MiB")
    return result


def _write_zip_entry(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    info.flag_bits = 0
    archive.writestr(info, content)
