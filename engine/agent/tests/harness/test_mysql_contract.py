"""Opt-in MySQL contract evaluation over the production Agent tool chain."""

from __future__ import annotations

import json
import os

import pymysql
import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.tests.harness.test_sqlite_scenarios import _final_turn, _tool_turn
from engine.environment.schema_catalog_sync import ensure_catalog
from engine.json_codec import load_object
from engine.models import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentToolInvocation,
    DataSource,
)
from engine.security import credential_vault
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def _mysql_settings() -> dict[str, object]:
    if os.getenv("DBFOX_RUN_MYSQL_CONTRACT") != "1":
        pytest.skip("set DBFOX_RUN_MYSQL_CONTRACT=1 for the isolated MySQL contract")
    password = os.getenv("DBFOX_AGENTBENCH_MYSQL_PASSWORD", "")
    if not password:
        pytest.fail("DBFOX_AGENTBENCH_MYSQL_PASSWORD is required")
    return {
        "host": os.getenv("DBFOX_AGENTBENCH_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("DBFOX_AGENTBENCH_MYSQL_PORT", "3306")),
        "user": os.getenv("DBFOX_AGENTBENCH_MYSQL_USER", "agentbench"),
        "password": password,
        "database": os.getenv("DBFOX_AGENTBENCH_MYSQL_DATABASE", "agentbench"),
        "charset": "utf8mb4",
    }


def _seed_mysql(settings: dict[str, object]) -> None:
    connection = pymysql.connect(**settings)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGINT PRIMARY KEY,
                    customer_name VARCHAR(100) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    total_amount DECIMAL(12, 2) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
            cursor.execute("DELETE FROM orders")
            cursor.executemany(
                """
                INSERT INTO orders
                    (id, customer_name, status, total_amount, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (1, "Alice", "completed", "120.50", "2026-01-01 09:00:00"),
                    (2, "Bob", "pending", "88.00", "2026-01-02 10:00:00"),
                    (3, "Carol", "completed", "42.25", "2026-01-03 11:00:00"),
                ],
            )
        connection.commit()
    finally:
        connection.close()


class _MySQLContractProvider:
    def __init__(self, turn: int, *, database: str) -> None:
        self.turn = turn
        self.database = database

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        qualified_table = f"{self.database}.orders"
        if self.turn == 1:
            yield from _tool_turn(
                "inspect-orders",
                "schema_inspect",
                {"targets": [qualified_table]},
            )
            return
        serialized = json.dumps(messages, ensure_ascii=False)
        if self.turn == 2:
            assert "inspect-orders" in serialized
            yield from _tool_turn(
                "preview-orders",
                "data_preview",
                {
                    "table": qualified_table,
                    "columns": ["id", "status", "total_amount"],
                    "limit": 10,
                    "where": {
                        "column": "status",
                        "op": "=",
                        "value": "completed",
                    },
                },
            )
            return
        preview_output = next(
            item
            for item in messages
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "preview-orders"
        )
        observation = json.loads(str(preview_output["output"]))
        assert observation["status"] == "succeeded", observation
        yield from _final_turn("MySQL 订单结构检查和数据预览已经完成。")


@pytest.mark.integration
def test_mysql_harness_uses_production_tool_and_connection_contract(
    db_session,
    monkeypatch,
) -> None:
    settings = _mysql_settings()
    _seed_mysql(settings)

    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret=str(settings["password"]),
    )
    monkeypatch.setattr(credential_vault, "_application_vault", vault)

    datasource = DataSource(
        id="agentbench-mysql",
        name="AgentBench MySQL",
        db_type="mysql",
        host=str(settings["host"]),
        port=int(settings["port"]),
        database_name=str(settings["database"]),
        username=str(settings["user"]),
        password_credential_id=credential_id,
        connection_generation=1,
        is_read_only=True,
        env="test",
    )
    db_session.add(datasource)
    db_session.commit()
    ensure_catalog(db_session, str(datasource.id))

    session_id = "agentbench-mysql-contract"
    db_session.add(
        AgentSession(
            id=session_id,
            title="MySQL contract",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(datasource.id),
        datasource_generation=1,
        content="检查订单结构并预览 completed 订单。",
        idempotency_key="mysql-contract",
        llm_credential_id="deterministic-fixture",
        api_base=None,
        model_name="scripted",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="harness", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    turn = {"value": 0}

    def model_factory(_settings):
        turn["value"] += 1
        return _MySQLContractProvider(
            turn["value"],
            database=str(settings["database"]),
        )

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    sql_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id, type="sql")
        .one()
    )
    result_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id, type="result_view")
        .one()
    )
    sql_payload = load_object(str(sql_artifact.payload_json))
    result_payload = load_object(str(result_artifact.payload_json))

    assert run is not None and run.status == "completed"
    assert answer is not None and answer.content.startswith("MySQL 订单结构检查")
    assert [item.tool_name for item in invocations] == [
        "schema_inspect",
        "data_preview",
    ]
    assert all(item.status == "succeeded" for item in invocations)
    assert turn["value"] == 3
    assert "completed" not in str(sql_payload["safeSql"])
    assert sql_payload["parameters"] == {"dbfox_p0": "completed"}
    assert result_payload["returnedRows"] == 2
