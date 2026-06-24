from __future__ import annotations

from types import SimpleNamespace

from engine.memory.session_memory import SessionMemoryService


def test_session_memory_tracks_sql_backed_result_view_ids_and_sql() -> None:
    service = SessionMemoryService()
    safe_sql = "SELECT day, usage_count FROM ai_tool_invocations"
    response = SimpleNamespace(
        artifacts=[
            SimpleNamespace(
                id="result-view-1",
                type="result_view",
                payload={
                    "storageMode": "sql_backed",
                    "sourceSqlArtifactId": "sql-artifact-1",
                    "safeSql": safe_sql,
                },
            ),
            SimpleNamespace(
                id="legacy-table-1",
                type="table",
                payload={"sql": "SELECT * FROM legacy_payload"},
            ),
        ]
    )

    memory = service.update_from_run(
        session_id="thread-1",
        run_id="run-1",
        question="分析每日调用",
        final_state={"sql": safe_sql},
        response=response,
    )

    assert memory.last_result_artifact_id == "result-view-1"
    assert memory.last_source_sql_artifact_id == "sql-artifact-1"
    assert memory.last_result_safe_sql == safe_sql
    assert memory.last_sql == safe_sql
    assert memory.last_table_artifact_id is None

    context = service.build_context_text("thread-1")
    assert "Last result artifact: result-view-1" in context
    assert "Last source SQL artifact: sql-artifact-1" in context
