from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.datasource import datasource_connection_dict
from engine.errors import GuardrailValidationError
from engine.models import DataSource
from engine.sql.safety_gate import (
    _decision_block_message,
    _decision_checks_for_error,
    _resolve_execution_safety_decision,
)


def explain_postgres_sql(db: Session, datasource_id: str, sql_str: str) -> dict[str, Any]:
    """Run PostgreSQL EXPLAIN inside the shared read-only connection scope."""

    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    decision = _resolve_execution_safety_decision(
        db=db,
        datasource_id=datasource_id,
        sql_str=sql_str,
        bypass_guardrail=False,
        safety_decision=None,
        policy="explain",
    )
    if not decision.can_execute or not str(decision.safe_sql or "").strip():
        raise GuardrailValidationError(
            _decision_block_message(decision),
            checks=_decision_checks_for_error(decision),
        )

    safe_sql = str(decision.safe_sql or "").strip()
    from engine.sql.explain_validator import validate_explain_sql as _validate_explain_sql

    _validate_explain_sql(safe_sql, "postgres")
    profile = ConnectionProfile.from_mapping(datasource_connection_dict(ds))
    if profile.dialect != "postgresql":
        raise ValueError("Datasource is not PostgreSQL")

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    with ConnectionFactory().connection_scope(
        profile,
        purpose=ConnectionPurpose.EXPLAIN,
        read_only=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {safe_sql}")
            for row in cursor.fetchall():
                plan_line = str(row[0]) if row else ""
                records.append({"Plan": plan_line})
                if "SEQ SCAN" in plan_line.upper():
                    warnings.append("检测到顺序扫描 (Seq Scan)，建议检查过滤字段或连接字段上的索引。")

    return {
        "success": True,
        "records": records,
        "warnings": list(dict.fromkeys(warnings)),
        "safetyDecision": decision.model_dump(mode="json"),
    }
