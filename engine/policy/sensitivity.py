from __future__ import annotations
import re
from typing import Any
from sqlalchemy.orm import Session
from engine.models import SemanticAlias
from engine.policy.redactor import DataRedactor

_SENSITIVE_PATTERN_STRINGS = [
    r"\b(password|passwd|secret|token|credential|api_key)\b",
    r"\b(email|mail)\b",
    r"\b(phone|mobile|tel|telephone|msisdn)\b",
    r"\b(address|addr|postal|zip_code)\b",
    r"\b(ip_address|ipaddr|client_ip|server_ip)\b",
    r"\b(card|credit_card|debit_card)\b",
    r"\b(ssn|social_security|tax_id|national_id)\b",
    r"\b(passport|driver_license)\b",
]
_SENSITIVE_FALLBACK = re.compile("|".join(_SENSITIVE_PATTERN_STRINGS), re.IGNORECASE)

def _bootstrap_sensitivity(db: Session, datasource_id: str) -> None:
    """Write built-in sensitivity patterns into the database."""
    for pat in _SENSITIVE_PATTERN_STRINGS:
        db.add(SemanticAlias(
            data_source_id=datasource_id,
            alias=pat,
            target_type="sensitive",
            target="*",
            description="Bootstrapped default",
        ))
    db.commit()

def load_sensitivity(db: Session, datasource_id: str) -> re.Pattern:
    """Return a compiled regex of sensitive column patterns.

    Reads from SemanticAlias rows with target_type='sensitive'.
    Falls back to the built-in default set.
    """
    rows = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type == "sensitive",
        )
        .all()
    )
    if not rows:
        _bootstrap_sensitivity(db, datasource_id)
        rows = (
            db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type == "sensitive",
            )
            .all()
        )

    patterns = [str(r.alias) for r in rows]
    if not patterns:
        return _SENSITIVE_FALLBACK
    return re.compile("|".join(patterns))

def redact_row(row: dict[str, Any], sensitivity: re.Pattern | None = None) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in row.items():
        if sensitivity and sensitivity.search(key):
            if isinstance(value, str):
                redacted[key] = DataRedactor.redact_sql(value)
            elif value is not None:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = None
        else:
            redacted[key] = value
    return redacted
