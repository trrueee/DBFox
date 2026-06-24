from __future__ import annotations

from engine.schema_sync import sync_schema
from engine.schemas import SQLExecuteRequest
from engine.sql.guardrail import GuardrailResult
from engine.sql.dialect_context import DialectContext
from engine.sql.safety.service import SqlSafetyService
from engine.sql.safety_gate import validate_derived_sql, validate_pagination_base_sql
from engine.sql.trust_gate import ExecutionSafetyDecision


def test_dialect_context_canonicalizes_datasource_dialect(test_datasource_module) -> None:
    original_db_type = test_datasource_module.db_type
    try:
        test_datasource_module.db_type = "postgres"
        ctx = DialectContext.from_datasource(test_datasource_module)
    finally:
        test_datasource_module.db_type = original_db_type

    assert ctx.datasource_id == test_datasource_module.id
    assert ctx.dialect == "postgresql"
    assert ctx.sqlglot_dialect == "postgres"


def test_source_artifact_validation_reuses_guardrail_rules() -> None:
    ctx = DialectContext(datasource_id="ds-source", dialect="mysql")

    warnings = SqlSafetyService().validate_source_artifact_sql("SELECT SLEEP(10)", ctx)

    assert warnings
    assert any("sleep" in warning.lower() or "dangerous" in warning.lower() for warning in warnings)


def test_pagination_base_wrapper_reuses_unified_safety_service() -> None:
    warnings = validate_pagination_base_sql("SELECT SLEEP(10)", dialect="mysql")

    assert warnings
    assert any("sleep" in warning.lower() or "dangerous" in warning.lower() for warning in warnings)


def test_derived_sql_wrapper_reuses_unified_safety_service() -> None:
    warnings = validate_derived_sql("SELECT * FROM users FOR UPDATE", dialect="mysql")

    assert warnings
    assert any("lock" in warning.lower() or "for update" in warning.lower() for warning in warnings)


def test_build_execution_decision_uses_dialect_context(
    db_session_module,
    test_datasource_module,
) -> None:
    sync_schema(db_session_module, test_datasource_module.id)
    ctx = DialectContext.from_datasource(test_datasource_module)

    decision = SqlSafetyService(db_session_module).build_execution_decision(
        "SELECT id, username FROM users LIMIT 3",
        ctx,
        policy="user_readonly",
    )

    assert decision.datasource_id == test_datasource_module.id
    assert decision.can_execute is True
    assert decision.safe_sql == "SELECT id, username FROM users LIMIT 3"


def test_query_execute_api_passes_explicit_safety_decision(
    db_session_module,
    test_datasource_module,
    monkeypatch,
) -> None:
    import engine.api.query as query_api

    guardrail: GuardrailResult = {
        "result": "pass",
        "originalSql": "SELECT id FROM users LIMIT 3",
        "safeSql": "SELECT id FROM users LIMIT 3",
        "checks": [],
        "message": "ok",
    }
    decision = ExecutionSafetyDecision(
        datasource_id=test_datasource_module.id,
        policy="user_readonly",
        original_sql="SELECT id FROM users LIMIT 3",
        safe_sql="SELECT id FROM users LIMIT 3",
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail=guardrail,
    )
    built: list[tuple[str, str]] = []
    received: list[ExecutionSafetyDecision | None] = []

    def fake_build_execution_decision(
        self: SqlSafetyService,
        sql: str,
        ctx: DialectContext,
        *,
        policy: str = "readonly",
    ) -> ExecutionSafetyDecision:
        built.append((sql, ctx.datasource_id))
        assert policy == "user_readonly"
        return decision

    def fake_execute_query(
        _db,
        datasource_id: str,
        sql: str,
        question: str | None = None,
        execution_id: str | None = None,
        safety_decision: ExecutionSafetyDecision | None = None,
        **_kwargs,
    ) -> dict[str, object]:
        assert datasource_id == test_datasource_module.id
        assert sql == "SELECT id FROM users LIMIT 3"
        assert question == "question"
        assert execution_id == "exec-test"
        received.append(safety_decision)
        return {"success": True}

    monkeypatch.setattr(SqlSafetyService, "build_execution_decision", fake_build_execution_decision)
    monkeypatch.setattr(query_api, "execute_query", fake_execute_query)

    result = query_api.api_execute_sql(
        SQLExecuteRequest(
            datasource_id=test_datasource_module.id,
            sql="SELECT id FROM users LIMIT 3",
            question="question",
            execution_id="exec-test",
        ),
        db_session_module,
    )

    assert result == {"success": True}
    assert built == [("SELECT id FROM users LIMIT 3", test_datasource_module.id)]
    assert received == [decision]


def test_db_query_tool_passes_explicit_safety_decision(
    db_session_module,
    test_datasource_module,
    monkeypatch,
) -> None:
    import engine.tools.db.query as query_tool

    decision = _test_decision(test_datasource_module.id, policy="agent_readonly")
    built: list[tuple[str, str, str]] = []
    received: list[ExecutionSafetyDecision | None] = []

    def fake_build_execution_decision(
        self: SqlSafetyService,
        sql: str,
        ctx: DialectContext,
        *,
        policy: str = "readonly",
    ) -> ExecutionSafetyDecision:
        built.append((sql, ctx.datasource_id, policy))
        return decision

    def fake_execute_query(
        _db,
        datasource_id: str,
        sql: str,
        **kwargs,
    ) -> dict[str, object]:
        received.append(kwargs.get("safety_decision"))
        return {
            "columns": ["id"],
            "rows": [{"id": "1"}],
            "latencyMs": 1,
            "safetyDecision": decision.model_dump(mode="json"),
            "guardrail": decision.guardrail,
        }

    monkeypatch.setattr(SqlSafetyService, "build_execution_decision", fake_build_execution_decision)
    monkeypatch.setattr(query_tool, "execute_query", fake_execute_query)

    result = query_tool.db_query(
        db_session_module,
        test_datasource_module.id,
        "SELECT id FROM users LIMIT 3",
    )

    assert result["status"] == "success"
    assert built == [("SELECT id FROM users LIMIT 3", test_datasource_module.id, "agent_readonly")]
    assert received == [decision]


def test_db_preview_tool_passes_explicit_safety_decision(
    db_session_module,
    test_datasource_module,
    monkeypatch,
) -> None:
    import engine.tools.db.preview as preview_tool

    sync_schema(db_session_module, test_datasource_module.id)
    decision = _test_decision(test_datasource_module.id, policy="table_preview")
    built: list[tuple[str, str, str]] = []
    received: list[ExecutionSafetyDecision | None] = []

    def fake_build_execution_decision(
        self: SqlSafetyService,
        sql: str,
        ctx: DialectContext,
        *,
        policy: str = "readonly",
    ) -> ExecutionSafetyDecision:
        built.append((sql, ctx.datasource_id, policy))
        return decision

    def fake_execute_query(
        _db,
        datasource_id: str,
        sql: str,
        **kwargs,
    ) -> dict[str, object]:
        received.append(kwargs.get("safety_decision"))
        return {
            "columns": ["id"],
            "rows": [{"id": "1"}],
            "latencyMs": 1,
            "safetyDecision": decision.model_dump(mode="json"),
        }

    monkeypatch.setattr(SqlSafetyService, "build_execution_decision", fake_build_execution_decision)
    monkeypatch.setattr(preview_tool, "execute_query", fake_execute_query)

    result = preview_tool.db_preview(
        db_session_module,
        test_datasource_module.id,
        table="users",
        columns=["id"],
        limit=1,
    )

    assert result["table"] == "users"
    assert len(built) == 1
    assert built[0][1:] == (test_datasource_module.id, "table_preview")
    assert received == [decision]


def test_sql_validate_tool_uses_sql_safety_service(
    db_session_module,
    test_datasource_module,
    monkeypatch,
) -> None:
    from engine.tools.db.sql_execution import sql_validate

    decision = _test_decision(test_datasource_module.id, policy="agent_readonly")
    built: list[tuple[str, str, str]] = []

    def fake_build_execution_decision(
        self: SqlSafetyService,
        sql: str,
        ctx: DialectContext,
        *,
        policy: str = "readonly",
    ) -> ExecutionSafetyDecision:
        built.append((sql, ctx.datasource_id, policy))
        return decision

    monkeypatch.setattr(SqlSafetyService, "build_execution_decision", fake_build_execution_decision)

    result = sql_validate(
        db_session_module,
        test_datasource_module.id,
        "SELECT id FROM users LIMIT 3",
    )

    assert result["can_execute"] is True
    assert built == [("SELECT id FROM users LIMIT 3", test_datasource_module.id, "agent_readonly")]


def test_test_data_fk_prefetch_passes_explicit_safety_decision(
    db_session_module,
    test_datasource_module,
    monkeypatch,
) -> None:
    import uuid

    import engine.test_data as test_data_module
    from engine.models import SchemaColumn, SchemaTable

    suffix = uuid.uuid4().hex[:8]
    parent_table = SchemaTable(
        data_source_id=test_datasource_module.id,
        table_schema="main",
        table_name=f"parent_safety_{suffix}",
    )
    child_table = SchemaTable(
        data_source_id=test_datasource_module.id,
        table_schema="main",
        table_name=f"child_safety_{suffix}",
    )
    db_session_module.add_all([parent_table, child_table])
    db_session_module.commit()

    parent_id = SchemaColumn(
        table_id=parent_table.id,
        column_name="id",
        column_type="INTEGER",
        is_primary_key=True,
    )
    child_id = SchemaColumn(
        table_id=child_table.id,
        column_name="id",
        column_type="INTEGER",
        is_primary_key=True,
    )
    db_session_module.add_all([parent_id, child_id])
    db_session_module.commit()

    child_parent_id = SchemaColumn(
        table_id=child_table.id,
        column_name="parent_id",
        column_type="INTEGER",
        is_foreign_key=True,
        foreign_table_id=parent_table.id,
        foreign_column_id=parent_id.id,
    )
    db_session_module.add(child_parent_id)
    db_session_module.commit()

    built: list[tuple[str, str, str]] = []
    received: list[ExecutionSafetyDecision | None] = []

    def fake_build_execution_decision(
        self: SqlSafetyService,
        sql: str,
        ctx: DialectContext,
        *,
        policy: str = "readonly",
    ) -> ExecutionSafetyDecision:
        built.append((sql, ctx.datasource_id, policy))
        return _test_decision(ctx.datasource_id, policy=policy, sql=sql)

    def fake_execute_query(_db, datasource_id: str, sql: str, **kwargs) -> dict[str, object]:
        received.append(kwargs.get("safety_decision"))
        assert kwargs.get("safety_policy") == "readonly"
        return {"success": True, "columns": ["id"], "rows": [{"id": 42}]}

    inserted: list[dict[str, object]] = []

    def fake_insert(_db, datasource_id: str, insert_sql: str, params: dict[str, object]) -> None:
        inserted.append(params)

    monkeypatch.setattr(SqlSafetyService, "build_execution_decision", fake_build_execution_decision)
    monkeypatch.setattr(test_data_module, "execute_query", fake_execute_query)
    monkeypatch.setattr(test_data_module, "_execute_test_data_insert", fake_insert)

    result = test_data_module.generate_smart_test_data(
        db_session_module,
        test_datasource_module.id,
        child_table.table_name,
        row_count=1,
    )

    expected_sql = f"SELECT `id` FROM `{parent_table.table_name}` LIMIT 200"
    assert result["success"] is True
    assert built == [(expected_sql, test_datasource_module.id, "readonly")]
    assert received and received[0] is not None
    assert inserted == [{"parent_id": 42}]


def _test_decision(
    datasource_id: str,
    *,
    policy: str,
    sql: str = "SELECT id FROM users LIMIT 3",
) -> ExecutionSafetyDecision:
    guardrail: GuardrailResult = {
        "result": "pass",
        "originalSql": sql,
        "safeSql": sql,
        "checks": [],
        "message": "ok",
    }
    return ExecutionSafetyDecision(
        datasource_id=datasource_id,
        policy=policy,  # type: ignore[arg-type]
        original_sql=sql,
        safe_sql=sql,
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail=guardrail,
    )
