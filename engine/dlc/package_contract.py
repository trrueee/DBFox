"""Canonical package bounds shared by the DBFox host and developer tooling."""

from __future__ import annotations

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 150 * 1024 * 1024
MAX_FILE_COUNT = 1000
MAX_SINGLE_FILE_BYTES = 20 * 1024 * 1024
MAX_PATH_LENGTH = 255

CONTROL_FILES = frozenset({"manifest.json", "integrity.json", "signature.sig"})
PAYLOAD_ROOTS = frozenset({"backend", "frontend"})
PROHIBITED_EXTENSIONS = (
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".node",
)
