from engine.models import DataSource
from engine.sql.trust_gate import TrustGate

# covers: TG-1 guardrail reject
def test_tg1_reject(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="dev",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: [])
    res = gate.evaluate("ds-1", "DROP TABLE t", policy="readonly")
    assert res["riskLevel"] == "danger"
    assert res["canExecute"] is False

# covers: TG-2 schema warnings
def test_tg2_schema_warnings(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="dev",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: ["Table not found"])
    res = gate.evaluate("ds-1", "SELECT id FROM t", policy="readonly")
    assert res["riskLevel"] == "warning"
    assert res["canExecute"] is True

# covers: TG-3 guardrail warning
def test_tg3_guardrail_warning(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="dev",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: [])
    res = gate.evaluate("ds-1", "SELECT * FROM t LIMIT 1", policy="readonly")
    assert res["riskLevel"] == "warning"

# covers: TG-4 all pass
def test_tg4_all_pass(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="dev",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: [])
    res = gate.evaluate("ds-1", "SELECT id FROM t LIMIT 5", policy="readonly")
    assert res["riskLevel"] == "safe"

# covers: TG-5 prod + agent_readonly
def test_tg5_prod_agent_readonly(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="prod",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: [])
    res = gate.evaluate("ds-1", "SELECT id FROM t LIMIT 5", policy="agent_readonly")
    assert res["requiresConfirmation"] is True

# covers: TG-6 dev + agent_readonly + warning
def test_tg6_dev_agent_readonly_warning(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="dev",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: ["Warning"])
    res = gate.evaluate("ds-1", "SELECT id FROM t LIMIT 5", policy="agent_readonly")
    assert res["requiresConfirmation"] is True

# covers: TG-7 user_readonly any env
def test_tg7_user_readonly_any_env(db_session):
    ds = DataSource(
        id="ds-1", name="test", db_type="sqlite", env="prod",
        host="localhost", database_name="test.db", username="test",
    )
    db_session.add(ds)
    db_session.commit()
    
    gate = TrustGate(db_session, lambda ast, db, ds_id: [])
    res = gate.evaluate("ds-1", "SELECT id FROM t LIMIT 5", policy="user_readonly")
    assert res["requiresConfirmation"] is False
