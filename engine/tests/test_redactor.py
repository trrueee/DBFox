import pytest

from engine.policy.redactor import DataRedactor
from engine.policy.sensitivity import (
    _SENSITIVE_FALLBACK,
    load_sensitivity,
    projection_sensitivity_mask,
    redact_row,
)

def test_data_redactor_pii_and_credentials() -> None:
    # Test credentials redaction
    sql_cred = "UPDATE users SET password = 'super_secret_password_123', email = 'test@example.com' WHERE username = 'john_doe';"
    redacted = DataRedactor.redact_sql(sql_cred)
    assert "password = '[REDACTED_SECURE]'" in redacted
    assert "test@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "john_doe" in redacted

    ddl_cred = "CREATE TABLE users (password TEXT DEFAULT 'secret-value');"
    redacted_ddl = DataRedactor.redact_sql(ddl_cred)
    assert "secret-value" not in redacted_ddl
    assert "password TEXT DEFAULT '[REDACTED_SECURE]'" in redacted_ddl

    # Test phone numbers and credit cards
    sql_pii = "INSERT INTO customers (phone, card) VALUES ('13812345678', '4111-1111-1111-1111');"
    redacted_pii = DataRedactor.redact_sql(sql_pii)
    assert "13812345678" not in redacted_pii
    assert "4111-1111-1111-1111" not in redacted_pii
    assert "[REDACTED_PHONE]" in redacted_pii
    assert "[REDACTED_CARD]" in redacted_pii

    # Test standard queries are not affected
    sql_normal = "SELECT id, name FROM products WHERE price > 10.0 LIMIT 5;"
    assert DataRedactor.redact_sql(sql_normal) == sql_normal


def test_data_redactor_masks_common_phone_formats_without_card_false_positives() -> None:
    sql = (
        "INSERT INTO contacts (mobile, support_line, reference_no) VALUES "
        "('+1 (415) 555-2671', '415.555.0134', '2024-0000-0000-0001');"
    )

    redacted = DataRedactor.redact_sql(sql)

    assert "+1 (415) 555-2671" not in redacted
    assert "415.555.0134" not in redacted
    assert redacted.count("[REDACTED_PHONE]") == 2
    assert "2024-0000-0000-0001" in redacted
    assert "[REDACTED_CARD]" not in redacted


def test_data_redactor_does_not_corrupt_opaque_artifact_identifiers() -> None:
    artifact_id = "agent/run/console-run-08c893c1-75b6-4f23-a551-9863276fda4f/artifact/001"

    assert DataRedactor.redact_sql(artifact_id) == artifact_id


def test_data_redactor_masks_api_key_assignments_without_key_shaped_fixtures() -> None:
    message = "model provider rejected api_key = 'TEST_LLM_SECRET' for request"

    redacted = DataRedactor.redact_sql(message)

    assert "TEST_LLM_SECRET" not in redacted
    assert "api_key = '[REDACTED_SECURE]'" in redacted


def test_data_redactor_masks_unquoted_credentials_and_url_passwords() -> None:
    message = (
        "connection failed password=plain-secret "
        "dsn=postgresql://analyst:url-secret@db.example.test/app"
    )

    redacted = DataRedactor.redact_sql(message)

    assert "plain-secret" not in redacted
    assert "url-secret" not in redacted
    assert "password=[REDACTED_SECURE]" in redacted
    assert "postgresql://analyst:[REDACTED]@db.example.test/app" in redacted


def test_data_redactor_preserves_quoted_assignment_style() -> None:
    message = 'password = "double quoted secret" and token = \'single quoted secret\''

    redacted = DataRedactor.redact_sql(message)

    assert 'password = "[REDACTED_SECURE]"' in redacted
    assert "token = '[REDACTED_SECURE]'" in redacted
    assert "double quoted secret" not in redacted
    assert "single quoted secret" not in redacted


def test_sensitive_columns_mask_entire_values_not_only_recognizable_pii() -> None:
    secret = "opaque-value-that-does-not-look-like-a-credential"

    redacted = redact_row(
        {"password": secret, "email": "person@example.test", "display_name": "Ada"},
        _SENSITIVE_FALLBACK,
    )

    assert redacted == {
        "password": "[REDACTED]",
        "email": "[REDACTED]",
        "display_name": "Ada",
    }
    assert secret not in str(redacted)


def test_schema_pii_flag_extends_datasource_sensitivity_policy(db_session, test_datasource) -> None:
    from engine.models import SchemaColumn, SchemaTable

    table = SchemaTable(
        id="table-pii-policy",
        data_source_id=test_datasource.id,
        table_schema="main",
        table_name="customers",
    )
    db_session.add(table)
    db_session.flush()
    db_session.add(SchemaColumn(
        id="column-pii-policy",
        table_id=table.id,
        column_name="customer_code",
        is_pii=True,
    ))
    db_session.commit()

    sensitivity = load_sensitivity(db_session, test_datasource.id)
    redacted = redact_row({"customer_code": "internal-42", "status": "active"}, sensitivity)

    assert redacted == {"customer_code": "[REDACTED]", "status": "active"}


def test_projection_sensitivity_tracks_alias_expression_cte_and_star(
    db_session,
    test_datasource,
) -> None:
    from engine.models import SchemaColumn, SchemaTable

    table = SchemaTable(
        id="table-projection-sensitivity",
        data_source_id=test_datasource.id,
        table_schema="main",
        table_name="projection_users",
    )
    db_session.add(table)
    db_session.flush()
    db_session.add_all(
        [
            SchemaColumn(
                id="column-projection-name",
                table_id=table.id,
                column_name="display_name",
                data_type="TEXT",
            ),
            SchemaColumn(
                id="column-projection-password",
                table_id=table.id,
                column_name="password",
                data_type="TEXT",
            ),
        ]
    )
    db_session.commit()
    sensitivity = load_sensitivity(db_session, test_datasource.id)

    assert projection_sensitivity_mask(
        db_session,
        test_datasource.id,
        "SELECT password AS public_value FROM projection_users",
        "sqlite",
        sensitivity,
    ) == (True,)
    assert projection_sensitivity_mask(
        db_session,
        test_datasource.id,
        "SELECT UPPER(password) AS public_value FROM projection_users",
        "sqlite",
        sensitivity,
    ) == (True,)
    assert projection_sensitivity_mask(
        db_session,
        test_datasource.id,
        (
            "WITH source AS (SELECT password FROM projection_users) "
            "SELECT password AS public_value FROM source"
        ),
        "sqlite",
        sensitivity,
    ) == (True,)
    assert projection_sensitivity_mask(
        db_session,
        test_datasource.id,
        "SELECT * FROM projection_users",
        "sqlite",
        sensitivity,
    ) == (False, True)


def test_projection_sensitivity_fails_closed_for_unknown_source_column(
    db_session,
    test_datasource,
) -> None:
    sensitivity = load_sensitivity(db_session, test_datasource.id)

    assert projection_sensitivity_mask(
        db_session,
        test_datasource.id,
        "SELECT unindexed_value AS public_value FROM users",
        "sqlite",
        sensitivity,
    ) is None


def test_executor_redacts_sensitive_projection_hidden_by_alias(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    import engine.sql.executor as executor
    from engine.environment.schema_catalog_sync import ensure_catalog as sync_schema
    from engine.sql.row_serializer import QueryExecutionResult, ResultTruncation

    sync_schema(db_session, test_datasource.id)
    bounded_result = QueryExecutionResult(
        rows=[{"display_name": "secret@example.test"}],
        columns=["display_name"],
        truncation=ResultTruncation(),
        response_bytes=64,
        connect_ms=0,
        execute_ms=0,
        fetch_ms=0,
        serialize_ms=0,
    )
    monkeypatch.setattr(
        executor,
        "_execute_on_sqlite_profiled",
        lambda *_args, **_kwargs: bounded_result,
    )

    result = executor.execute_query(
        db_session,
        test_datasource.id,
        "SELECT email AS display_name FROM users LIMIT 1",
    )

    assert result["rows"] == [{"display_name": "[REDACTED]"}]
    assert "secret@example.test" not in str(result)


def test_streaming_executor_redacts_sensitive_projection_hidden_by_alias(
    db_session,
    test_datasource,
) -> None:
    from engine.environment.schema_catalog_sync import ensure_catalog as sync_schema
    from engine.sql.dialect_context import DialectContext
    from engine.sql.execution.streaming_executor import StreamingQueryExecutor
    from engine.sql.safety.service import SqlSafetyService

    sync_schema(db_session, test_datasource.id)
    sql = "SELECT email AS public_value FROM users ORDER BY id LIMIT 1"
    ctx = DialectContext.from_datasource_id(db_session, test_datasource.id)
    decision = SqlSafetyService(db_session).build_execution_decision(
        sql,
        ctx,
        policy="export",
    )

    rows = list(
        StreamingQueryExecutor(db_session).stream_rows(
            test_datasource.id,
            sql,
            decision,
        )
    )

    assert rows == [{"public_value": "[REDACTED]"}]
    assert "alice@example.com" not in str(rows)


def test_streaming_executor_fails_closed_when_projection_lineage_is_unavailable(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    from engine.environment.schema_catalog_sync import ensure_catalog as sync_schema
    from engine.sql.dialect_context import DialectContext
    from engine.sql.execution.streaming_executor import StreamingQueryExecutor
    from engine.sql.safety.service import SqlSafetyService

    sync_schema(db_session, test_datasource.id)
    sql = "SELECT username AS public_value FROM users ORDER BY id LIMIT 1"
    ctx = DialectContext.from_datasource_id(db_session, test_datasource.id)
    decision = SqlSafetyService(db_session).build_execution_decision(
        sql,
        ctx,
        policy="export",
    )
    monkeypatch.setattr(
        "engine.sql.execution.streaming_executor.projection_sensitivity_mask",
        lambda *_args, **_kwargs: None,
    )

    rows = list(
        StreamingQueryExecutor(db_session).stream_rows(
            test_datasource.id,
            sql,
            decision,
        )
    )

    assert rows == [{"public_value": "[REDACTED]"}]


def test_executor_redacts_sensitive_queries(db_session, test_datasource) -> None:
    from engine.tests.support.executor import execute_query_for_test
    from engine.models import QueryHistory

    # Execute a query containing a sensitive email and password assignment
    sensitive_sql = "SELECT id, email FROM users WHERE email = 'test@example.com'; -- password = 'supersecretpassword'"
    res = execute_query_for_test(db_session, test_datasource.id, sensitive_sql)

    assert res["success"] is True

    # Retrieve from QueryHistory and assert it is redacted
    history = db_session.query(QueryHistory).filter(QueryHistory.id == res["historyId"]).first()
    assert history is not None
    assert "test@example.com" not in history.submitted_sql
    assert "supersecretpassword" not in history.submitted_sql
    assert "[REDACTED_EMAIL]" in history.submitted_sql
    assert "password = '[REDACTED_SECURE]'" in history.submitted_sql


def test_executor_history_redacts_sensitive_error_messages(db_session, test_datasource, monkeypatch) -> None:
    from engine.app.safe_errors import FixedErrorCode, fixed_error_message
    from engine.models import QueryHistory
    from engine.sql.executor import _run_approved_query

    def fail_with_sensitive_driver_message(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("driver leaked user@example.com password='driver-secret'")

    monkeypatch.setattr("engine.sql.executor._execute_on_sqlite_profiled", fail_with_sensitive_driver_message)
    sql = "SELECT email FROM users WHERE email = 'user@example.com'; -- password = 'sql-secret'"

    with pytest.raises(Exception):
        _run_approved_query(
            db=db_session,
            ds=test_datasource,
            datasource_id=test_datasource.id,
            safe_sql=sql,
            sql_str=sql,
            question=None,
            execution_id="exec-sensitive-error",
            guard_res={"result": "pass", "safeSql": sql, "checks": [], "message": "ok"},
            guard_checks_json="[]",
            guardrail_ms=0,
        )

    history = (
        db_session.query(QueryHistory)
        .filter(QueryHistory.data_source_id == test_datasource.id)
        .order_by(QueryHistory.created_at.desc())
        .first()
    )
    assert history is not None
    assert "user@example.com" not in history.error_message
    assert "driver-secret" not in history.error_message
    assert history.error_message == fixed_error_message(FixedErrorCode.SQL_EXECUTION_FAILED)
