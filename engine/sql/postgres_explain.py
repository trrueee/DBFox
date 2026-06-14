from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.datasource import get_postgres_connection_params
from engine.errors import GuardrailValidationError
from engine.models import DataSource
from engine.sql.executor import (
    _decision_block_message,
    _decision_checks_for_error,
    _resolve_execution_safety_decision,
)


def explain_postgres_sql(db: Session, datasource_id: str, sql_str: str) -> dict[str, Any]:
    """Run EXPLAIN for a PostgreSQL datasource with the same TrustGate checks."""
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
    conn_params = get_postgres_connection_params({
        "host": ds.host,
        "port": ds.port,
        "username": ds.username,
        "database_name": ds.database_name,
        "password_ciphertext": ds.password_ciphertext,
        "password_nonce": ds.password_nonce,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    })

    import psycopg2

    conn: Any = psycopg2.connect(**conn_params, connect_timeout=5)
    try:
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
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
    finally:
        conn.close()
