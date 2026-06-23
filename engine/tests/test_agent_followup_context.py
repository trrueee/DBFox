from __future__ import annotations

import json

from engine.agent_core.persistence.runs import build_followup_context_from_run
from engine.models import AgentArtifactRecord, AgentRun, AgentSession


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _artifact(
    *,
    run_id: str,
    session_id: str,
    artifact_id: str,
    artifact_type: str,
    payload: dict,
    sequence: int,
) -> AgentArtifactRecord:
    return AgentArtifactRecord(
        id=artifact_id,
        run_id=run_id,
        session_id=session_id,
        semantic_id=artifact_id,
        type=artifact_type,
        title=artifact_type,
        produced_by_step="execute_sql",
        depends_on_json=_json({"depends_on": []}),
        payload_json=_json(payload),
        presentation_json=_json({"mode": "both"}),
        refs_json=_json({}),
        sequence=sequence,
    )


def test_followup_context_prefers_evidence_sql_backed_results_and_skips_noise(
    db_session,
    test_datasource,
) -> None:
    session_id = "session-followup-context"
    run_id = "run-followup-context"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=test_datasource.id,
            title="工具使用分析",
            context_tables_json="[]",
        )
    )
    db_session.add(
        AgentRun(
            id=run_id,
            session_id=session_id,
            datasource_id=test_datasource.id,
            question="分析工具使用情况",
            status="completed",
            response_json=_json({
                "answer": {
                    "answer": "广告文案生成调用最多。",
                    "evidence": [
                        {
                            "artifact_id": "result-good",
                            "label": "工具调用统计",
                            "value": 5,
                        }
                    ],
                }
            }),
        )
    )
    db_session.add_all([
        _artifact(
            run_id=run_id,
            session_id=session_id,
            artifact_id="sql-suggestion-noise",
            artifact_type="sql_suggestion",
            payload={"proposed_sql": "SELECT broken FROM missing_table"},
            sequence=1,
        ),
        _artifact(
            run_id=run_id,
            session_id=session_id,
            artifact_id="result-empty",
            artifact_type="result_view",
            payload={
                "storageMode": "sql_backed",
                "safeSql": "SELECT id FROM users WHERE id = -1",
                "columns": ["id"],
                "rowCount": 0,
                "previewRowCount": 0,
            },
            sequence=2,
        ),
        _artifact(
            run_id=run_id,
            session_id=session_id,
            artifact_id="result-good",
            artifact_type="result_view",
            payload={
                "storageMode": "sql_backed",
                "safeSql": "SELECT tool_name, usage_count FROM ai_tools LIMIT 10",
                "columns": ["tool_name", "usage_count"],
                "rowCount": 5,
                "previewRowCount": 5,
            },
            sequence=3,
        ),
        _artifact(
            run_id=run_id,
            session_id=session_id,
            artifact_id="chart-good",
            artifact_type="chart",
            payload={"type": "bar", "x": "tool_name", "y": "usage_count"},
            sequence=4,
        ),
    ])
    db_session.commit()

    context = build_followup_context_from_run(db_session, run_id)

    assert context is not None
    artifact_ids = [artifact.id for artifact in context.artifacts]
    assert artifact_ids[0] == "result-good"
    assert "chart-good" in artifact_ids
    assert "result-empty" not in artifact_ids
    assert "sql-suggestion-noise" not in artifact_ids
