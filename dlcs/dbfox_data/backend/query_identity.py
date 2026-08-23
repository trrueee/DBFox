"""Stable query identity bound to one authorized database resource."""

from __future__ import annotations

from hashlib import sha256

from dbfox_dlc_api import ResourceScopeRef

from .sql.bound_parameters import parameter_fingerprint


def query_fingerprint(
    ref: ResourceScopeRef,
    safe_sql: str,
    parameters: dict[str, object] | None = None,
) -> str:
    parameter_hash = parameter_fingerprint(parameters) or ""
    source_text = f"{ref.kind}\0{ref.id}\0{ref.version or ''}\0{safe_sql}"
    if parameter_hash:
        source_text += f"\0{parameter_hash}"
    source = source_text.encode("utf-8")
    return f"query_{sha256(source).hexdigest()}"
