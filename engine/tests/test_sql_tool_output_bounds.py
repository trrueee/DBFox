from __future__ import annotations

from types import SimpleNamespace

from engine.agent.repositories.artifact import ArtifactRepository
from engine.json_codec import byte_size
from engine.tools.builtin.query import SqlExecuteReadonlyTool
from engine.tools.runtime import ToolExecutor, ToolRegistry, ToolRuntime


def test_sql_result_keeps_artifact_draft_while_bounding_immediate_model_output(
    db_session, test_datasource, monkeypatch
) -> None:
    monkeypatch.setattr(
        ArtifactRepository,
        "require_validated_sql",
        lambda self, **kwargs: SimpleNamespace(
            safety={
                "can_execute": True,
                "safe_sql": "SELECT payload FROM wide_rows",
                "original_sql": "SELECT payload FROM wide_rows",
                "blocked_reasons": [],
            }
        ),
    )
    monkeypatch.setattr(
        ArtifactRepository,
        "result_for_sql_artifact",
        lambda self, **kwargs: None,
    )

    from engine.tools.builtin import query as query_module

    monkeypatch.setattr(
        query_module,
        "sql_execute_readonly",
        lambda *args, **kwargs: {
            "status": "success",
            "success": True,
            "rowCount": 1,
            "columns": ["payload"],
            "column_types": ["text"],
            "returned_rows": 1,
            "truncated": False,
            "rows": [{"payload": "x" * 2_000_000}],
            "safe_sql": "SELECT payload FROM wide_rows",
            "execution_time_ms": 2,
            "explain_plan": None,
            "warnings": [],
            "audit": {
                "history_id": "history_wide_result",
                "execution_id": "execution_wide_result",
            },
            "latency_ms": 2,
        },
    )

    tool = SqlExecuteReadonlyTool()
    registry = ToolRegistry().register(tool)
    runtime = ToolRuntime(registry)
    request = SimpleNamespace(
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        session_id="session_bounds",
        run_id="run_bounds",
        question="读取宽字段",
        execution_id="execution_wide_result",
    )
    executor = ToolExecutor(max_workers=1)
    try:
        result = executor.execute(
            tool=tool,
            scope_key="run_bounds",
            operation=lambda _control: runtime.invoke(
                tool_name=tool.name,
                raw_input={"validation_artifact_id": "artifact_sql_bounds"},
                request=request,
                idempotency_key="invocation_bounds",
                resources={"database": db_session},
            ),
        )
    finally:
        executor.close(wait=True)

    assert result.status == "success"
    assert result.error_code is None
    assert byte_size(result.output or {}) < tool.execution.max_output_bytes
    assert len((result.output or {})["rows"][0]["payload"]) <= 2_003
    assert len(result.artifact_drafts) == 1
    assert result.artifact_drafts[0].payload_ref == "history_wide_result"
    assert result.artifact_drafts[0].payload["returnedRows"] == 1
