from __future__ import annotations

import hashlib

from engine.agent_core.memory import normalize_sql_for_fingerprint, sql_fingerprint


def result_source_fingerprint(sql: str, dialect: str) -> str:
    normalized = normalize_sql_for_fingerprint(sql)
    digest = hashlib.sha256(f"{dialect}:{normalized}".encode("utf-8")).hexdigest()
    return f"{sql_fingerprint(sql)}:{digest[:24]}"

