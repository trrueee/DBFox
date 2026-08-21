"""Static frontend bundle rules for installable DLCs.

Frontend DLCs consume React through ``window.__DBFOX_EXTENSION_HOST__``.  Bare
React imports cannot resolve under the packaged asset protocol, while embedded
React copies violate the single-runtime Hook ABI contract.  These checks are
deliberately static; they do not execute extension code and are not a sandbox.
"""

from __future__ import annotations

import re

from engine.dlc.errors import DlcError, DlcErrorCode

_BARE_REACT_IMPORT = re.compile(
    r"(?:from\s*|import\s*\(|require\s*\()\s*['\"]react(?:-dom(?:/client)?)?['\"]"
)
_EMBEDDED_REACT_MARKERS = (
    "__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED",
    "__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE",
    "react.production.min.js",
    "react-dom.production.min.js",
)


def validate_frontend_bundle(path: str, content: bytes) -> None:
    """Reject unresolved React imports and recognizable bundled React runtimes."""
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DlcError(
            DlcErrorCode.INVALID_ARCHIVE,
            f"Frontend entrypoint '{path}' must be UTF-8 JavaScript: {exc}",
        ) from exc

    if _BARE_REACT_IMPORT.search(source):
        raise DlcError(
            DlcErrorCode.INVALID_ARCHIVE,
            f"Frontend entrypoint '{path}' must consume React from the DBFox host, not a bare React import",
        )
    if any(marker in source for marker in _EMBEDDED_REACT_MARKERS):
        raise DlcError(
            DlcErrorCode.INVALID_ARCHIVE,
            f"Frontend entrypoint '{path}' embeds a React runtime; React must remain host-owned",
        )
