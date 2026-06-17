import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from engine.models import Base, SchemaTable, SchemaColumn, DataSource
from engine.sql.safety_gate import validate_sql_schema, _resolve_execution_safety_decision
from engine.errors import GuardrailValidationError
from engine.sql.trust_gate import ExecutionSafetyDecision

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

def _create_test_ds(db_session, ds_id="ds-123", env="dev"):
    ds = DataSource(
        id=ds_id,
        name="test_ds",
        db_type="sqlite",
        env=env,
        host="localhost",
        database_name="test.db",
        username="test",
        password_ciphertext="cipher",
        password_nonce="nonce"
    )
    db_session.add(ds)
    db_session.commit()
    return ds

# covers: SV-1 Schema empty cache
def test_sv1_empty_cache(db_session):
    _create_test_ds(db_session, "ds-123")
    warnings = validate_sql_schema("SELECT id FROM users", db_session, "ds-123")
    assert warnings == []

# covers: SV-2 Table and column exist
def test_sv2_exist(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("SELECT id FROM users", db_session, "ds-123")
    assert warnings == []

# covers: SV-3 Table does not exist
def test_sv3_ghost_table(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("SELECT id FROM ghost_table", db_session, "ds-123")
    assert any("不存在" in w for w in warnings)

# covers: SV-4 Column does not exist in table
def test_sv4_ghost_column(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("SELECT ghost_col FROM users", db_session, "ds-123")
    assert any("不存在" in w for w in warnings)

# covers: SV-5 CTE exclusion
def test_sv5_cte_exclude(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("WITH x AS (SELECT id FROM users) SELECT id FROM x", db_session, "ds-123")
    assert warnings == []

# covers: SV-6 Subquery alias exclusion
def test_sv6_subquery_alias(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("SELECT * FROM (SELECT id FROM users) sub", db_session, "ds-123")
    assert warnings == []

# covers: SV-7 projection alias reference in ORDER BY
def test_sv7_projection_alias(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("SELECT id AS x FROM users ORDER BY x", db_session, "ds-123")
    assert warnings == []

# covers: SV-8 Case insensitivity
def test_sv8_case_insensitive(db_session):
    _create_test_ds(db_session, "ds-123")
    tbl = SchemaTable(data_source_id="ds-123", table_name="users", table_schema="public")
    tbl.columns.append(SchemaColumn(column_name="id", column_type="integer"))
    db_session.add(tbl)
    db_session.commit()
    
    warnings = validate_sql_schema("SELECT ID FROM Users", db_session, "ds-123")
    assert warnings == []

# covers: SV-exc syntax error in parse
def test_sv_exc(db_session):
    _create_test_ds(db_session, "ds-123")
    warnings = validate_sql_schema("SELECTT 1 FROM", db_session, "ds-123")
    assert warnings == []


# covers: RES-1/RES-2 ExecutionSafetyDecision preset
def test_res1_res2_preset(db_session):
    _create_test_ds(db_session, "ds-123")
    
    decision = ExecutionSafetyDecision(
        datasource_id="ds-123",
        policy="readonly",
        original_sql="SELECT 1",
        safe_sql="SELECT 1",
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail={"result": "pass", "originalSql": "SELECT 1", "safeSql": "SELECT 1", "checks": [], "message": ""},
    )
    res = _resolve_execution_safety_decision(
        db_session, "ds-123", "SELECT 1", bypass_guardrail=False, safety_decision=decision
    )
    assert res.decision_id == decision.decision_id

# covers: RES-3 Mismatched datasource
def test_res3_mismatched_datasource(db_session):
    _create_test_ds(db_session, "ds-123")
    decision = ExecutionSafetyDecision(
        datasource_id="ds-other",
        policy="readonly",
        original_sql="SELECT 1",
        safe_sql="SELECT 1",
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail={"result": "pass", "originalSql": "SELECT 1", "safeSql": "SELECT 1", "checks": [], "message": ""},
    )
    with pytest.raises(GuardrailValidationError) as exc:
        _resolve_execution_safety_decision(
            db_session, "ds-123", "SELECT 1", bypass_guardrail=False, safety_decision=decision
        )
    assert any(c["rule"] == "safety_decision_datasource_mismatch" for c in exc.value.checks)

# covers: RES-4 Mismatched SQL
def test_res4_mismatched_sql(db_session):
    _create_test_ds(db_session, "ds-123")
    decision = ExecutionSafetyDecision(
        datasource_id="ds-123",
        policy="readonly",
        original_sql="SELECT 1",
        safe_sql="SELECT 1",
        passed=True,
        can_execute=True,
        requires_confirmation=False,
        guardrail={"result": "pass", "originalSql": "SELECT 1", "safeSql": "SELECT 1", "checks": [], "message": ""},
    )
    with pytest.raises(GuardrailValidationError) as exc:
        _resolve_execution_safety_decision(
            db_session, "ds-123", "SELECT 2", bypass_guardrail=False, safety_decision=decision
        )
    assert any(c["rule"] == "safety_decision_sql_mismatch" for c in exc.value.checks)

# covers: RES-5 bypass disabled
def test_res5_bypass_disabled(db_session, monkeypatch):
    _create_test_ds(db_session, "ds-123")
    monkeypatch.setenv("DBFOX_TESTING", "0")
    monkeypatch.setenv("DBFOX_ALLOW_GUARDRAIL_BYPASS", "0")
    with pytest.raises(GuardrailValidationError) as exc:
        _resolve_execution_safety_decision(
            db_session, "ds-123", "SELECT 1", bypass_guardrail=True, safety_decision=None
        )
    assert any(c["rule"] == "trust_gate_bypass_disabled" for c in exc.value.checks)

# covers: RES-6 bypass blocked on non-dev env
def test_res6_bypass_env_blocked(db_session, monkeypatch):
    monkeypatch.setenv("DBFOX_TESTING", "1")
    monkeypatch.setenv("DBFOX_ALLOW_GUARDRAIL_BYPASS", "1")
    _create_test_ds(db_session, "ds-123", env="prod")
    with pytest.raises(GuardrailValidationError) as exc:
        _resolve_execution_safety_decision(
            db_session, "ds-123", "SELECT 1", bypass_guardrail=True, safety_decision=None
        )
    assert any(c["rule"] == "trust_gate_bypass_env_blocked" for c in exc.value.checks)

# covers: RES-7 bypass allowed
def test_res7_bypass_allowed(db_session, monkeypatch):
    monkeypatch.setenv("DBFOX_TESTING", "1")
    monkeypatch.setenv("DBFOX_ALLOW_GUARDRAIL_BYPASS", "1")
    _create_test_ds(db_session, "ds-123", env="dev")
    res = _resolve_execution_safety_decision(
        db_session, "ds-123", "SELECT 1", bypass_guardrail=True, safety_decision=None
    )
    assert res.passed
    assert res.scope_state.get("bypass_guardrail") is True
