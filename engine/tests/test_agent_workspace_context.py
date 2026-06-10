from __future__ import annotations

import json

from engine.agent import AgentContextArtifact, AgentFollowUpContext, AgentRunRequest, AgentWorkspaceContext
from engine.agent_contracts.workspace_context import build_agent_context_bundle
from engine.models import SemanticAlias, SemanticDimension, SemanticMetric
from engine.schema_sync import sync_schema


def test_workspace_context_bundle_uses_selected_table_and_omits_secrets(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    db_session.add(
        SemanticAlias(
            data_source_id=demo_datasource.id,
            alias="GMV",
            target_type="column",
            target="orders.total_amount",
            description="gross merchandise value",
        )
    )
    db_session.add(
        SemanticMetric(
            data_source_id=demo_datasource.id,
            name="GMV",
            expression="SUM(orders.total_amount)",
            source_columns_json='["orders.total_amount"]',
        )
    )
    db_session.add(
        SemanticDimension(
            data_source_id=demo_datasource.id,
            name="Order date",
            column_ref="orders.created_at",
            transform="DATE",
        )
    )
    db_session.commit()

    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Explain the users table",
        workspace_context=AgentWorkspaceContext(
            project_id="project-1",
            datasource_id=demo_datasource.id,
            active_sql="SELECT id, username FROM users LIMIT 10",
            selected_table_names=["users"],
            last_query_result_preview={
                "columns": ["id", "username"],
                "rows": [{"id": 1, "username": "alice"}],
                "rowCount": 1,
            },
            last_error="previous syntax error",
        ),
    )

    bundle = build_agent_context_bundle(db_session, req)

    assert bundle["datasource"]["id"] == demo_datasource.id
    assert bundle["datasource"]["database_name"] == demo_datasource.database_name
    assert bundle["selected_table_schema"][0]["name"] == "users"
    assert "active SQL available" in bundle["context_summary"]
    assert bundle["semantic_context"]["aliases"][0]["alias"] == "GMV"
    dumped = json.dumps(bundle, default=str).lower()
    assert "password_ciphertext" not in dumped
    assert "password_nonce" not in dumped
    assert "api_key" not in dumped


def test_workspace_context_bundle_can_include_selected_followup_artifact(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    artifact = AgentContextArtifact(
        id="artifact-sql",
        type="sql",
        title="Prior SQL",
        summary="SELECT id FROM users LIMIT 5",
        payload={"sql": "SELECT id FROM users LIMIT 5"},
    )
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="Continue from the selected artifact",
        follow_up_context=AgentFollowUpContext(artifacts=[artifact]),
        workspace_context=AgentWorkspaceContext(
            datasource_id=demo_datasource.id,
            selected_artifact_id="artifact-sql",
        ),
    )

    bundle = build_agent_context_bundle(db_session, req)

    assert bundle["selected_artifact"]["id"] == "artifact-sql"
    assert bundle["selected_artifact"]["payload"]["sql"].startswith("SELECT")


def test_workspace_context_bundle_falls_back_to_schema_linking(db_session, demo_datasource) -> None:
    sync_schema(db_session, demo_datasource.id)
    req = AgentRunRequest(
        datasource_id=demo_datasource.id,
        question="How many orders are there?",
        workspace_context=AgentWorkspaceContext(datasource_id=demo_datasource.id),
    )

    bundle = build_agent_context_bundle(db_session, req)

    assert "schema_linking" in bundle
    assert "orders" in bundle["schema_linking"]["selected_tables"]
    assert bundle["schema_linking"]["schema_context"]
