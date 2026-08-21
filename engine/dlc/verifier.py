"""Streaming ZIP package validation, integrity checking, and cryptographic verification."""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO


from engine.dlc.compat import check_dlc_compatibility
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.frontend_contract import validate_frontend_bundle
from engine.dlc.integrity import (
    DlcIntegrity,
    build_signed_message_bytes,
    canonical_json_bytes,
    normalize_posix_archive_path,
)
from engine.dlc.manifest import DlcManifest
from engine.dlc.package_contract import (
    CONTROL_FILES,
    MAX_ARCHIVE_BYTES,
    MAX_EXTRACTED_BYTES,
    MAX_FILE_COUNT,
    MAX_SINGLE_FILE_BYTES,
    PROHIBITED_EXTENSIONS,
)
from engine.dlc.trust import DlcTrustStatus, DlcTrustStore


@dataclass(frozen=True)
class VerifiedDlcPackage:
    """Immutable verified representation of a .dbfox-dlc package."""

    manifest: DlcManifest
    integrity: DlcIntegrity
    package_digest: str  # SHA256 of the entire .dbfox-dlc archive
    raw_archive_bytes: bytes
    trust_status: DlcTrustStatus
    publisher_key_id: str | None
    signature_base64: str | None
    publisher_key_base64: str | None


class DlcPackageVerifier:
    """Validates raw .dbfox-dlc archive bytes against format, integrity, and trust contracts."""

    def __init__(self, trust_store: DlcTrustStore | None = None) -> None:
        self.trust_store = trust_store or DlcTrustStore()

    def verify_archive_file(
        self,
        archive_path: Path,
        *,
        developer_mode: bool = False,
        publisher_key_base64: str | None = None,
    ) -> VerifiedDlcPackage:
        """Verify authenticity and require the resulting publisher trust policy."""
        verified_package = self.authenticate_archive_file(
            archive_path,
            developer_mode=developer_mode,
            publisher_key_base64=publisher_key_base64,
        )
        return self._require_trusted(verified_package)

    def authenticate_archive_file(
        self,
        archive_path: Path,
        *,
        developer_mode: bool = False,
        publisher_key_base64: str | None = None,
    ) -> VerifiedDlcPackage:
        """Authenticate a package without treating an unknown valid key as trusted."""
        if not archive_path.is_file():
            raise DlcError(
                DlcErrorCode.INVALID_ARCHIVE,
                f"DLC archive file does not exist: '{archive_path}'",
            )

        file_size = archive_path.stat().st_size
        if file_size > MAX_ARCHIVE_BYTES:
            raise DlcError(
                DlcErrorCode.PACKAGE_TOO_LARGE,
                f"Package file size ({file_size} bytes) exceeds limit of {MAX_ARCHIVE_BYTES} bytes (50 MiB)",
            )

        raw_bytes = archive_path.read_bytes()
        return self.authenticate_archive_bytes(
            raw_bytes,
            developer_mode=developer_mode,
            publisher_key_base64=publisher_key_base64,
        )

    def verify_archive_bytes(
        self,
        raw_bytes: bytes,
        *,
        developer_mode: bool = False,
        publisher_key_base64: str | None = None,
    ) -> VerifiedDlcPackage:
        """Verify authenticity and require the resulting publisher trust policy."""
        verified_package = self.authenticate_archive_bytes(
            raw_bytes,
            developer_mode=developer_mode,
            publisher_key_base64=publisher_key_base64,
        )
        return self._require_trusted(verified_package)

    def authenticate_archive_bytes(
        self,
        raw_bytes: bytes,
        *,
        developer_mode: bool = False,
        publisher_key_base64: str | None = None,
    ) -> VerifiedDlcPackage:
        """Authenticate .dbfox-dlc bytes while preserving unknown-publisher state."""
        if len(raw_bytes) > MAX_ARCHIVE_BYTES:
            raise DlcError(
                DlcErrorCode.PACKAGE_TOO_LARGE,
                f"Package archive size ({len(raw_bytes)} bytes) exceeds limit of {MAX_ARCHIVE_BYTES} bytes",
            )

        # 1. Compute overall package digest
        package_digest = hashlib.sha256(raw_bytes).hexdigest().lower()

        # 2. Inspect ZIP structure
        import io

        try:
            zip_file = zipfile.ZipFile(io.BytesIO(raw_bytes), mode="r")
        except zipfile.BadZipFile as exc:
            raise DlcError(
                DlcErrorCode.INVALID_ARCHIVE,
                f"Invalid or corrupted ZIP archive: {exc}",
            ) from exc

        with zip_file:
            entries = zip_file.infolist()

            if len(entries) > MAX_FILE_COUNT:
                raise DlcError(
                    DlcErrorCode.TOO_MANY_FILES,
                    f"Archive contains {len(entries)} files, exceeding limit of {MAX_FILE_COUNT}",
                )

            # Check for encrypted or special entries
            normalized_entries: dict[str, zipfile.ZipInfo] = {}
            case_map: dict[str, str] = {}
            total_uncompressed = 0

            for info in entries:
                # Reject encrypted entries
                if info.is_dir():
                    continue
                if info.flag_bits & 0x1:
                    raise DlcError(
                        DlcErrorCode.INVALID_ARCHIVE,
                        f"Encrypted ZIP entry not permitted: '{info.filename}'",
                    )

                # Check path normalization
                norm_path = normalize_posix_archive_path(info.filename)

                # Check for duplicate normalized path
                if norm_path in normalized_entries:
                    raise DlcError(
                        DlcErrorCode.DUPLICATE_PATH,
                        f"Duplicate normalized entry in archive: '{norm_path}'",
                    )

                # Check for case collision
                lower_path = norm_path.lower()
                if lower_path in case_map:
                    raise DlcError(
                        DlcErrorCode.CASE_COLLISION,
                        f"Case-insensitive filename collision: '{norm_path}' collides with '{case_map[lower_path]}'",
                    )
                case_map[lower_path] = norm_path
                normalized_entries[norm_path] = info

                # Check prohibited native extension
                lower_name = norm_path.lower()
                for ext in PROHIBITED_EXTENSIONS:
                    if lower_name.endswith(ext):
                        raise DlcError(
                            DlcErrorCode.NATIVE_EXTENSION_NOT_ALLOWED,
                            f"Native binary extension not allowed in v1 DLC: '{norm_path}'",
                        )

                # Bounds check
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    raise DlcError(
                        DlcErrorCode.SINGLE_FILE_TOO_LARGE,
                        f"Entry '{norm_path}' size ({info.file_size} bytes) exceeds limit of {MAX_SINGLE_FILE_BYTES} bytes",
                    )
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_EXTRACTED_BYTES:
                    raise DlcError(
                        DlcErrorCode.EXTRACTED_TOO_LARGE,
                        f"Total extracted size exceeds limit of {MAX_EXTRACTED_BYTES} bytes (150 MiB)",
                    )

            # 3. Read and parse control files
            if "manifest.json" not in normalized_entries:
                raise DlcError(
                    DlcErrorCode.MISSING_FILE,
                    "Required control file 'manifest.json' missing from archive",
                )
            if "integrity.json" not in normalized_entries:
                raise DlcError(
                    DlcErrorCode.MISSING_FILE,
                    "Required control file 'integrity.json' missing from archive",
                )

            manifest_bytes = zip_file.read(normalized_entries["manifest.json"])
            manifest = DlcManifest.from_bytes(manifest_bytes)

            integrity_bytes = zip_file.read(normalized_entries["integrity.json"])
            integrity = DlcIntegrity.from_bytes(integrity_bytes)

            signature_base64: str | None = None
            if "signature.sig" in normalized_entries:
                sig_raw = zip_file.read(normalized_entries["signature.sig"]).decode("utf-8").strip()
                if sig_raw:
                    signature_base64 = sig_raw

            # 4. Strict Archive Allowlist
            # Allowlist = { manifest.json, integrity.json, signature.sig } U set(integrity.entries.keys())
            payload_files = set(integrity.entries.keys())
            allowed_files = CONTROL_FILES | payload_files

            actual_files = set(normalized_entries.keys())

            # Check for unlisted files
            unlisted = actual_files - allowed_files
            if unlisted:
                raise DlcError(
                    DlcErrorCode.UNLISTED_FILE,
                    f"Archive contains unlisted files not permitted by integrity allowlist: {sorted(unlisted)}",
                )

            # Check for missing payload files declared in integrity
            missing = payload_files - actual_files
            if missing:
                raise DlcError(
                    DlcErrorCode.MISSING_FILE,
                    f"Integrity mapping lists payload files missing from archive: {sorted(missing)}",
                )

            # 5. Verify payload hashes and streaming extraction bounds
            for payload_path, expected_hash in integrity.entries.items():
                info = normalized_entries[payload_path]
                with zip_file.open(info) as stream:
                    actual_hash, extracted_len = _compute_stream_sha256(stream)

                if extracted_len > MAX_SINGLE_FILE_BYTES:
                    raise DlcError(
                        DlcErrorCode.SINGLE_FILE_TOO_LARGE,
                        f"Decompressed stream for '{payload_path}' exceeded limit",
                    )

                if actual_hash.lower() != expected_hash.lower():
                    raise DlcError(
                        DlcErrorCode.HASH_MISMATCH,
                        f"SHA256 mismatch for '{payload_path}': expected {expected_hash}, got {actual_hash}",
                    )

            for entrypoint_kind, entrypoint_path in (
                ("Backend", manifest.entrypoints.backend),
                ("Frontend", manifest.entrypoints.frontend),
            ):
                if entrypoint_path and entrypoint_path not in normalized_entries:
                    raise DlcError(
                        DlcErrorCode.MISSING_FILE,
                        f"{entrypoint_kind} entrypoint '{entrypoint_path}' is missing from the package",
                    )
            if manifest.entrypoints.frontend:
                frontend_entrypoint = manifest.entrypoints.frontend
                validate_frontend_bundle(
                    frontend_entrypoint,
                    zip_file.read(normalized_entries[frontend_entrypoint]),
                )

            # 6. Verify Compatibility
            check_dlc_compatibility(
                manifest.manifest_schema_version,
                manifest.extension_api_version,
                manifest.requires_dbfox,
            )

            # 7. Verify Signature & Trust
            canonical_manifest = canonical_json_bytes(manifest.model_dump(by_alias=True, exclude_none=True))
            canonical_integrity = integrity.canonical_bytes()
            signed_payload = build_signed_message_bytes(canonical_manifest, canonical_integrity)

            embedded_publisher_key = manifest.publisher_key
            if manifest.manifest_schema_version == 2:
                if (
                    publisher_key_base64 is not None
                    and publisher_key_base64 != embedded_publisher_key
                ):
                    raise DlcError(
                        DlcErrorCode.PUBLISHER_KEY_MISMATCH,
                        "External publisher key does not match the signed manifest publisherKey",
                    )
                effective_publisher_key = embedded_publisher_key
                developer_trust_bypass = False
            else:
                effective_publisher_key = publisher_key_base64
                developer_trust_bypass = developer_mode

            trust_status, key_fingerprint = self.trust_store.verify_package_trust(
                signed_payload,
                signature_base64,
                effective_publisher_key,
                developer_mode=developer_trust_bypass,
            )

            return VerifiedDlcPackage(
                manifest=manifest,
                integrity=integrity,
                package_digest=package_digest,
                raw_archive_bytes=raw_bytes,
                trust_status=trust_status,
                publisher_key_id=key_fingerprint,
                signature_base64=signature_base64,
                publisher_key_base64=effective_publisher_key,
            )

    @staticmethod
    def _require_trusted(verified_package: VerifiedDlcPackage) -> VerifiedDlcPackage:
        if verified_package.trust_status != DlcTrustStatus.UNTRUSTED:
            return verified_package
        fingerprint = verified_package.publisher_key_id
        raise DlcError(
            DlcErrorCode.TRUST_REQUIRED,
            "Package signature is authentic, but the publisher is not trusted",
            details={
                "dlc_id": verified_package.manifest.id,
                "package_digest": verified_package.package_digest,
                "publisher_key_id": fingerprint,
                "publisher_key_base64": verified_package.publisher_key_base64,
            },
        )


def _compute_stream_sha256(stream: IO[bytes]) -> tuple[str, int]:

    """Compute SHA256 digest of a binary stream while counting bytes."""
    hasher = hashlib.sha256()
    total_bytes = 0
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        total_bytes += len(chunk)
        hasher.update(chunk)
    return hasher.hexdigest(), total_bytes
