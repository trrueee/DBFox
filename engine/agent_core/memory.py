from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


def normalize_sql_for_fingerprint(sql: str) -> str:
    return " ".join(sql.strip().lower().split())


def sql_fingerprint(sql: str) -> str:
    normalized = normalize_sql_for_fingerprint(sql)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sql_{digest[:24]}"


def upsert_memory_ref(
    refs: list[dict[str, Any]],
    candidate: dict[str, Any],
    *,
    max_refs: int,
) -> list[dict[str, Any]]:
    result = [deepcopy(ref) for ref in refs if isinstance(ref, dict)]
    datasource_id = candidate.get("datasource_id")
    fingerprint = candidate.get("sql_fingerprint")
    kind = candidate.get("kind")

    match_index = next(
        (
            index
            for index, ref in enumerate(result)
            if ref.get("datasource_id") == datasource_id
            and ref.get("sql_fingerprint") == fingerprint
            and ref.get("kind") == kind
        ),
        None,
    )

    if match_index is None:
        inserted = deepcopy(candidate)
        inserted["usage_count"] = int(inserted.get("usage_count") or 0) or 1
        result.append(inserted)
    else:
        current = result[match_index]
        merged = {**current, **candidate, "id": current.get("id") or candidate.get("id")}
        merged["usage_count"] = int(current.get("usage_count") or 0) + 1
        result[match_index] = merged

    result.sort(
        key=lambda ref: (
            bool(ref.get("pinned")),
            str(ref.get("last_used_at") or ""),
        ),
        reverse=True,
    )
    return result[:max_refs]
