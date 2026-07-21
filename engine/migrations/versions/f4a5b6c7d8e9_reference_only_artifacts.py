"""enforce reference-only artifact storage

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-19
"""
from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RESULT_VALUE_KEYS = frozenset({"rows", "results", "series", "previewRows", "preview_rows"})
_RESULT_DESCRIPTOR_KEYS = frozenset({
    "sourceSqlArtifactId", "queryFingerprint", "datasourceGeneration", "columns",
    "rowCount", "returnedRows", "latencyMs", "executedAt", "truncated",
})
_CHART_DESCRIPTOR_KEYS = frozenset({
    "sourceResultArtifactId", "chartType", "x", "y", "aggregation", "title",
})


def _without_result_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_result_values(item)
            for key, item in value.items()
            if key not in _RESULT_VALUE_KEYS
        }
    if isinstance(value, list):
        return [_without_result_values(item) for item in value]
    return value


def _scrub_json_column(table: str, key: str, column: str) -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if table not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns(table)}
    if key not in columns or column not in columns:
        return
    rows = connection.execute(sa.text(f'SELECT "{key}", "{column}" FROM "{table}"')).fetchall()
    statement = sa.text(f'UPDATE "{table}" SET "{column}" = :value WHERE "{key}" = :key')
    for row_key, raw in rows:
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        cleaned = _without_result_values(parsed)
        if cleaned != parsed:
            connection.execute(
                statement,
                {"key": row_key, "value": json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))},
            )


def _scrub_artifact_payloads() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        'SELECT "id", "type", "payload_json" FROM "agent_artifacts"'
    )).fetchall()
    statement = sa.text('UPDATE "agent_artifacts" SET "payload_json" = :value WHERE "id" = :key')
    for artifact_id, artifact_type, raw in rows:
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        cleaned = _without_result_values(parsed)
        if artifact_type == "result_view":
            cleaned = {key: value for key, value in cleaned.items() if key in _RESULT_DESCRIPTOR_KEYS}
        elif artifact_type == "chart":
            cleaned = {key: value for key, value in cleaned.items() if key in _CHART_DESCRIPTOR_KEYS}
            if isinstance(cleaned.get("y"), str):
                cleaned["y"] = [cleaned["y"]] if cleaned["y"].strip() else []
        if cleaned != parsed:
            connection.execute(statement, {
                "key": artifact_id,
                "value": json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")),
            })


def upgrade() -> None:
    connection = op.get_bind()
    artifact_columns = {item["name"] for item in sa.inspect(connection).get_columns("agent_artifacts")}
    if "preview_json" in artifact_columns:
        with op.batch_alter_table("agent_artifacts") as batch_op:
            batch_op.drop_column("preview_json")

    _scrub_artifact_payloads()
    for table, key, column in (
        ("agent_observations", "id", "facts_json"),
        ("agent_events", "id", "payload_json"),
        ("agent_turns", "id", "context_snapshot_json"),
        ("agent_session_memories", "id", "memory_json"),
        ("agent_runs", "id", "result_json"),
    ):
        _scrub_json_column(table, key, column)


def downgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("agent_artifacts")}
    if "preview_json" not in columns:
        with op.batch_alter_table("agent_artifacts") as batch_op:
            batch_op.add_column(sa.Column("preview_json", sa.Text(), nullable=False, server_default="{}"))
