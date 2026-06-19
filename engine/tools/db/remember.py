"""db.remember — persist business-semantic memories proposed by the Agent."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import DBFoxError, ToolInputError
from engine.models import DataSource, SemanticAlias
from engine.tools.db._common import _string_list


def _success(output: dict[str, Any], start: float) -> dict[str, Any]:
    output["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return output

logger = logging.getLogger("dbfox.tools.db.remember")

# PII patterns that should be redacted before storage
_PII_PATTERNS = [
    (re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?86[-.\s]?)?1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<!\d)(?:\+?86[-.\s]?)?\d{3,4}[-\s]\d{7,8}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<![\d-])(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?![\d-])"), "[REDACTED_PHONE]"),
]


def _redact_pii(text: str) -> str:
    """Redact PII patterns from text before storage."""
    if not text:
        return text
    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def db_remember(db: Session, datasource_id: str, *, mem_type: str, target: str,
                evidence: str = "", **_extra: Any) -> dict[str, Any]:
    """Persist a business-semantic memory proposed by the Agent."""
    start = time.perf_counter()
    try:
        memory_type = mem_type.strip()
        target = target.strip()
        evidence = evidence.strip()

        if not memory_type or not target:
            raise ToolInputError("type and target are required.")

        from engine.tools.db._common import _datasource
        ds = _datasource(db, datasource_id)
        needs_approval = _remember_needs_approval(ds, memory_type)

        if memory_type in ("table_alias", "column_alias"):
            return _remember_alias(db, datasource_id, target, memory_type, evidence, **_extra)
        if memory_type == "column_values":
            return _remember_column_values(db, datasource_id, target, evidence, needs_approval, **_extra)
        if memory_type == "join_path":
            return _remember_join_path(db, datasource_id, target, evidence, needs_approval, **_extra)
        if memory_type == "business_definition":
            return _remember_business_def(db, datasource_id, target, evidence, needs_approval, **_extra)

        raise ToolInputError(f"Unknown memory type: {memory_type}")
    except ToolInputError:
        raise
    except DBFoxError as exc:
        logger.exception("db.remember failed")
        raise RuntimeError(f"db.remember failed: {exc}")
    except Exception as exc:
        logger.exception("db.remember failed unexpectedly")
        raise RuntimeError(f"db.remember failed: {exc}")


# ===================================================================
# db.remember helpers
# ===================================================================


def _remember_needs_approval(ds: DataSource, memory_type: str) -> bool:
    env = (ds.env or "dev").lower()
    if memory_type in ("table_alias", "column_alias", "column_values"):
        return env == "prod"
    # join_path, business_definition always need approval
    return True


def _remember_alias(db: Session, datasource_id: str, target: str, memory_type: str,
                   evidence: str, **_extra: Any) -> dict[str, Any]:
    target_type = "column" if "." in target else "table"
    aliases = _string_list(_extra.get("aliases"))
    value = _extra.get("value")
    if isinstance(value, str) and value.strip():
        aliases.append(value.strip())
    aliases = sorted(set(a.strip() for a in aliases if a.strip()))

    if not aliases:
        raise ToolInputError("aliases or value is required.")

    created: list[dict[str, Any]] = []
    for alias in aliases:
        existing = (
            db.query(SemanticAlias)
            .filter(SemanticAlias.data_source_id == datasource_id,
                    SemanticAlias.alias == alias,
                    SemanticAlias.target_type == target_type,
                    SemanticAlias.target == target)
            .first()
        )
        if existing is None:
            db.add(SemanticAlias(data_source_id=datasource_id, alias=alias,
                                 target_type=target_type, target=target,
                                 description=_redact_pii(evidence[:500])))
            created.append({"alias": alias, "target": target, "target_type": target_type})

    db.commit()
    return {"status": "remembered", "type": memory_type, "target": target,
            "created": created, "will_affect_future_search": len(created) > 0}


def _remember_column_values(db: Session, datasource_id: str, target: str, evidence: str,
                            needs_approval: bool, **_extra: Any) -> dict[str, Any]:
    if needs_approval:
        return {"status": "pending_confirmation", "type": "column_values", "target": target,
                "reason": "prod environment requires user confirmation for data observations."}

    values = _string_list(_extra.get("values") or _extra.get("value"))
    if not values:
        raise ToolInputError("values list is required for column_values.")

    created: list[dict[str, Any]] = []
    for v in values:
        existing = (
            db.query(SemanticAlias)
            .filter(SemanticAlias.data_source_id == datasource_id,
                    SemanticAlias.alias == v,
                    SemanticAlias.target_type == "column_value",
                    SemanticAlias.target == target)
            .first()
        )
        if existing is None:
            db.add(SemanticAlias(data_source_id=datasource_id, alias=v,
                                 target_type="column_value", target=target,
                                 description=_redact_pii(f"Observed via db.preview. {evidence}"[:500])))
            created.append({"value": v, "target": target})

    db.commit()
    return {"status": "remembered", "type": "column_values", "target": target,
            "created": created, "will_affect_future_search": len(created) > 0}


def _remember_join_path(db: Session, datasource_id: str, target: str, evidence: str,
                        needs_approval: bool, **_extra: Any) -> dict[str, Any]:
    join_value = _extra.get("value") or _extra.get("join_condition")
    if not isinstance(join_value, dict):
        raise ToolInputError(
            "value must be a join_condition dict {left_table, left_column, right_table, right_column, join_type, description}.")

    alias_text = (
        f"{join_value.get('left_table', '')}.{join_value.get('left_column', '')} "
        f"↔ {join_value.get('right_table', '')}.{join_value.get('right_column', '')}"
    )
    description = _redact_pii(str(join_value.get("description", evidence))[:500])

    existing = (
        db.query(SemanticAlias)
        .filter(SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type == "join_path",
                SemanticAlias.target == target,
                SemanticAlias.alias == alias_text.strip())
        .first()
    )
    if existing is None:
        db.add(SemanticAlias(data_source_id=datasource_id, alias=alias_text.strip(),
                             target_type="join_path", target=target, description=description))
        db.commit()

    return {"status": "pending_confirmation" if needs_approval else "remembered",
            "type": "join_path", "target": target, "join": join_value,
            "note": "requires user confirmation" if needs_approval else "saved"}


def _remember_business_def(db: Session, datasource_id: str, target: str, evidence: str,
                           needs_approval: bool, **_extra: Any) -> dict[str, Any]:
    definition = _extra.get("value") or _extra.get("definition")
    description = ""
    if isinstance(definition, dict):
        description = _redact_pii(str(definition.get("description", evidence))[:500])
        if "sql" in definition and isinstance(definition["sql"], str):
            definition = {**definition, "sql": _redact_pii(definition["sql"])}
    elif isinstance(definition, str):
        description = _redact_pii(definition[:500])

    if not definition:
        raise ToolInputError("definition or value is required for business_definition.")

    existing = (
        db.query(SemanticAlias)
        .filter(SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type == "business_definition",
                SemanticAlias.target == target)
        .first()
    )
    if existing is None:
        db.add(SemanticAlias(data_source_id=datasource_id, alias=target,
                             target_type="business_definition", target=target,
                             description=description))
        db.commit()

    return {"status": "pending_confirmation" if needs_approval else "remembered",
            "type": "business_definition", "target": target, "definition": definition,
            "note": "Business definitions always require user confirmation."}


# ===================================================================
# Synonym & sensitivity stores (database-backed)
# ===================================================================


def _load_synonyms(db: Session, datasource_id: str) -> dict[str, list[str]]:
    """Return synonym map from SemanticAlias (no bootstrap fallback)."""
    rows = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type.in_(("synonym", "table", "column")),
        )
        .all()
    )
    result: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        alias = str(r.alias).strip().lower()
        target = str(r.target).strip().lower()
        if r.target_type == "synonym":
            result[alias].append(target)
        elif r.target_type in ("table", "column"):
            result[target].append(alias)
    return dict(result)


def _load_aliases(db: Session, datasource_id: str) -> list[SemanticAlias]:
    """Return all user-facing aliases (table_alias, column_alias)."""
    return (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type.in_(("table", "column")),
        )
        .all()
    )
