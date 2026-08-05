from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from engine.json_codec import dumps


def normalize_sql_for_fingerprint(sql: str) -> str:
    return " ".join(sql.strip().lower().split())


def sql_fingerprint(sql: str) -> str:
    normalized = normalize_sql_for_fingerprint(sql)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sql_{digest[:24]}"


def result_source_fingerprint(
    sql: str,
    dialect: str,
    parameters: Mapping[str, Any] | None = None,
) -> str:
    normalized = normalize_sql_for_fingerprint(sql)
    canonical_parameters = dumps(dict(sorted((parameters or {}).items())))
    digest = hashlib.sha256(
        f"{dialect}:{normalized}:{canonical_parameters}".encode("utf-8")
    ).hexdigest()
    return f"{sql_fingerprint(sql)}:{digest[:24]}"

