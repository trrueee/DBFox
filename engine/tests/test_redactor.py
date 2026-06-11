from engine.policy.redactor import DataRedactor

def test_data_redactor_pii_and_credentials() -> None:
    # Test credentials redaction
    sql_cred = "UPDATE users SET password = 'super_secret_password_123', email = 'test@example.com' WHERE username = 'john_doe';"
    redacted = DataRedactor.redact_sql(sql_cred)
    assert "password = '[REDACTED_SECURE]'" in redacted
    assert "test@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "john_doe" in redacted

    # Test phone numbers and credit cards
    sql_pii = "INSERT INTO customers (phone, card) VALUES ('13812345678', '4321-1234-5678-9876');"
    redacted_pii = DataRedactor.redact_sql(sql_pii)
    assert "13812345678" not in redacted_pii
    assert "4321-1234-5678-9876" not in redacted_pii
    assert "[REDACTED_PHONE]" in redacted_pii
    assert "[REDACTED_CARD]" in redacted_pii

    # Test standard queries are not affected
    sql_normal = "SELECT id, name FROM products WHERE price > 10.0 LIMIT 5;"
    assert DataRedactor.redact_sql(sql_normal) == sql_normal


def test_executor_redacts_sensitive_queries(db_session, test_datasource) -> None:
    from engine.sql.executor import execute_query
    from engine.models import QueryHistory

    # Execute a query containing a sensitive email and password assignment
    sensitive_sql = "SELECT id, email FROM users WHERE email = 'test@example.com'; -- password = 'supersecretpassword'"
    res = execute_query(db_session, test_datasource.id, sensitive_sql, bypass_guardrail=True)

    assert res["success"] is True

    # Retrieve from QueryHistory and assert it is redacted
    history = db_session.query(QueryHistory).filter(QueryHistory.id == res["historyId"]).first()
    assert history is not None
    assert "test@example.com" not in history.submitted_sql
    assert "supersecretpassword" not in history.submitted_sql
    assert "[REDACTED_EMAIL]" in history.submitted_sql
    assert "password = '[REDACTED_SECURE]'" in history.submitted_sql

