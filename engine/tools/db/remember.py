"""db.remember — persist business-semantic memories proposed by the Agent."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from engine.agent_core.tool_registry import ToolContext
from engine.agent_core.types import ToolObservation
from engine.errors import DBFoxError, ToolInputError
from engine.models import DataSource, SemanticAlias
from engine.tools.db._common import (
    _datasource,
    _execution_failed,
    _failed,
    _string_list,
    _success,
)

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


def db_remember(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Persist a business-semantic memory proposed by the Agent.

    Memory types
    ------------
    - ``table_alias``         — alias names for a table
    - ``column_alias``        — alias names for a column
    - ``column_values``       — observed enum-like values for a column
    - ``join_path``           — a discovered JOIN relationship + description
    - ``business_definition`` — a named business metric with SQL + description
    """
    start = time.perf_counter()
    try:
        memory_type = str(args.get("type") or "").strip()
        target = str(args.get("target") or "").strip()
        evidence = str(args.get("evidence") or args.get("description") or "").strip()

        if not memory_type or not target:
            raise ToolInputError("type and target are required.")

        ds = _datasource(ctx.db, ctx.request.datasource_id)
        needs_approval = _remember_needs_approval(ds, memory_type)

        if memory_type in ("table_alias", "column_alias"):
            return _remember_alias(ctx, args, target, memory_type, evidence, start)
        if memory_type == "column_values":
            return _remember_column_values(ctx, args, target, evidence, needs_approval, start)
        if memory_type == "join_path":
            return _remember_join_path(ctx, args, target, evidence, needs_approval, start)
        if memory_type == "business_definition":
            return _remember_business_def(ctx, args, target, evidence, needs_approval, start)

        raise ToolInputError(f"Unknown memory type: {memory_type}")
    except ToolInputError:
        raise
    except DBFoxError as exc:
        logger.exception("db.remember failed")
        return _execution_failed("db.remember", args, exc, start)
    except Exception as exc:
        logger.exception("db.remember failed unexpectedly")
        return _execution_failed("db.remember", args, exc, start)


# ===================================================================
# db.remember helpers
# ===================================================================


def _remember_needs_approval(ds: DataSource, memory_type: str) -> bool:
    env = (ds.env or "dev").lower()
    if memory_type in ("table_alias", "column_alias", "column_values"):
        return env == "prod"
    # join_path, business_definition always need approval
    return True


def _remember_alias(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    memory_type: str,
    evidence: str,
    start: float,
) -> ToolObservation:
    target_type = "column" if "." in target else "table"
    aliases = _string_list(args.get("aliases"))
    value = args.get("value")
    if isinstance(value, str) and value.strip():
        aliases.append(value.strip())
    aliases = sorted(set(a.strip() for a in aliases if a.strip()))

    if not aliases:
        return _failed("db.remember", args, "aliases or value is required.", start)

    created: list[dict[str, Any]] = []
    for alias in aliases:
        existing = (
            ctx.db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == ctx.request.datasource_id,
                SemanticAlias.alias == alias,
                SemanticAlias.target_type == target_type,
                SemanticAlias.target == target,
            )
            .first()
        )
        if existing is None:
            ctx.db.add(SemanticAlias(
                data_source_id=ctx.request.datasource_id,
                alias=alias,
                target_type=target_type,
                target=target,
                description=_redact_pii(evidence[:500]),
            ))
            created.append({"alias": alias, "target": target, "target_type": target_type})

    ctx.db.commit()
    return _success("db.remember", args, {
        "status": "remembered",
        "type": memory_type,
        "target": target,
        "created": created,
        "will_affect_future_search": len(created) > 0,
    }, start)


def _remember_column_values(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    evidence: str,
    needs_approval: bool,
    start: float,
) -> ToolObservation:
    if needs_approval:
        return _success("db.remember", args, {
            "status": "pending_confirmation",
            "type": "column_values",
            "target": target,
            "reason": "prod environment requires user confirmation for data observations.",
        }, start)

    values = _string_list(args.get("values") or args.get("value"))
    if not values:
        return _failed("db.remember", args, "values list is required for column_values.", start)

    created: list[dict[str, Any]] = []
    for v in values:
        existing = (
            ctx.db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == ctx.request.datasource_id,
                SemanticAlias.alias == v,
                SemanticAlias.target_type == "column_value",
                SemanticAlias.target == target,
            )
            .first()
        )
        if existing is None:
            ctx.db.add(SemanticAlias(
                data_source_id=ctx.request.datasource_id,
                alias=v,
                target_type="column_value",
                target=target,
                description=_redact_pii(f"Observed via db.preview. {evidence}"[:500]),
            ))
            created.append({"value": v, "target": target})

    ctx.db.commit()
    return _success("db.remember", args, {
        "status": "remembered",
        "type": "column_values",
        "target": target,
        "created": created,
        "will_affect_future_search": len(created) > 0,
    }, start)


def _remember_join_path(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    evidence: str,
    needs_approval: bool,
    start: float,
) -> ToolObservation:
    join_value = args.get("value") or args.get("join_condition")
    if not isinstance(join_value, dict):
        return _failed("db.remember", args,
                        "value must be a join_condition dict {left_table, left_column, right_table, right_column, join_type, description}.",
                        start)

    alias_text = (
        f"{join_value.get('left_table', '')}.{join_value.get('left_column', '')} "
        f"↔ {join_value.get('right_table', '')}.{join_value.get('right_column', '')}"
    )
    description = _redact_pii(str(join_value.get("description", evidence))[:500])

    existing = (
        ctx.db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == ctx.request.datasource_id,
            SemanticAlias.target_type == "join_path",
            SemanticAlias.target == target,
            SemanticAlias.alias == alias_text.strip(),
        )
        .first()
    )
    if existing is None:
        ctx.db.add(SemanticAlias(
            data_source_id=ctx.request.datasource_id,
            alias=alias_text.strip(),
            target_type="join_path",
            target=target,
            description=description,
        ))
        ctx.db.commit()

    approval_note = "requires user confirmation" if needs_approval else "saved"
    return _success("db.remember", args, {
        "status": "pending_confirmation" if needs_approval else "remembered",
        "type": "join_path",
        "target": target,
        "join": join_value,
        "note": approval_note,
    }, start)


def _remember_business_def(
    ctx: ToolContext,
    args: dict[str, Any],
    target: str,
    evidence: str,
    needs_approval: bool,
    start: float,
) -> ToolObservation:
    definition = args.get("value") or args.get("definition")
    description = ""
    if isinstance(definition, dict):
        description = _redact_pii(str(definition.get("description", evidence))[:500])
        # Also redact PII from the SQL field itself — it may contain
        # sensitive values in WHERE clauses (emails, phone numbers, etc.)
        if "sql" in definition and isinstance(definition["sql"], str):
            definition = {**definition, "sql": _redact_pii(definition["sql"])}
    elif isinstance(definition, str):
        description = _redact_pii(definition[:500])

    existing = (
        ctx.db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == ctx.request.datasource_id,
            SemanticAlias.target_type == "business_definition",
            SemanticAlias.target == target,
        )
        .first()
    )
    if existing is None:
        ctx.db.add(SemanticAlias(
            data_source_id=ctx.request.datasource_id,
            alias=target,
            target_type="business_definition",
            target=target,
            description=description,
        ))
        ctx.db.commit()

    return _success("db.remember", args, {
        "status": "pending_confirmation" if needs_approval else "remembered",
        "type": "business_definition",
        "target": target,
        "definition": definition,
        "note": "Business definitions always require user confirmation.",
    }, start)


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
