"""Typed errors and error codes for Runtime DLC package verification and installation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class DlcErrorCode(StrEnum):
    INVALID_ARCHIVE = "invalid_archive"
    PACKAGE_TOO_LARGE = "package_too_large"
    EXTRACTED_TOO_LARGE = "extracted_too_large"
    TOO_MANY_FILES = "too_many_files"
    SINGLE_FILE_TOO_LARGE = "single_file_too_large"
    PATH_TOO_LONG = "path_too_long"
    UNSAFE_PATH = "unsafe_path"
    DUPLICATE_PATH = "duplicate_path"
    CASE_COLLISION = "case_collision"
    UNLISTED_FILE = "unlisted_file"
    MISSING_FILE = "missing_file"
    INVALID_MANIFEST = "invalid_manifest"
    INVALID_INTEGRITY = "invalid_integrity"
    HASH_MISMATCH = "hash_mismatch"
    SIGNATURE_REQUIRED = "signature_required"
    INVALID_SIGNATURE = "invalid_signature"
    UNTRUSTED_PUBLISHER = "untrusted_publisher"
    INCOMPATIBLE_SCHEMA = "incompatible_schema"
    INCOMPATIBLE_EXTENSION_API = "incompatible_extension_api"
    INCOMPATIBLE_DBFOX_VERSION = "incompatible_dbfox_version"
    NATIVE_EXTENSION_NOT_ALLOWED = "native_extension_not_allowed"
    REGISTRY_CORRUPT = "registry_corrupt"
    INSTALL_IO_ERROR = "install_io_error"
    ALREADY_INSTALLED = "already_installed"
    CONFLICTING_DIGEST = "conflicting_digest"


class DlcError(Exception):
    """Base exception for all Runtime DLC package operations."""

    def __init__(
        self,
        code: DlcErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code
        self.message = message
        self.details = details or {}
