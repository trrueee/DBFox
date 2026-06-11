import pytest
from fastapi.testclient import TestClient
from engine.main import app, LOCAL_SECURE_TOKEN
from engine.db import get_db


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers():
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_dump_agent_run(client, demo_datasource, monkeypatch):
    monkeypatch.setattr(
        "engine.tools.sql_tools.generate_sql_from_schema_context",
        lambda *a, **k: {
            "sql": "SELECT id, username FROM users LIMIT 10",
            "model": "test", "mode": "offline", "latencyMs": 1,
            "schemaValidationWarnings": [],
        },
    )
    monkeypatch.setattr("engine.tools.sql_tools._render_sql_from_query_plan", lambda *a, **k: None)
    ds_id = demo_datasource.id
    resp = client.post(f"/api/v1/datasources/{ds_id}/sync", headers=_headers())
    print("SYNC:", resp.status_code, resp.text[:200])

    resp = client.post("/api/v1/agent/run", json={
        "datasource_id": ds_id, "question": "查询所有用户", "execute": False,
    }, headers=_headers())
    print("STATUS:", resp.status_code)
    data = resp.json()
    print("success:", data.get("success"), "error:", data.get("error"))
    print("sql:", data.get("sql"))
    print("safety can_execute:", (data.get("safety") or {}).get("can_execute"))
    print("steps:", [s["name"] for s in data.get("steps", [])])
    print("artifacts:", [a["semantic_id"] for a in data.get("artifacts", [])])
    print("answer keys:", list((data.get("answer") or {}).keys()))
    print("evidence:", (data.get("answer") or {}).get("evidence"))
    print("context_summary:", data.get("context_summary"))
    print("events[0]:", (data.get("events") or [{}])[0].get("type") if data.get("events") else None)
    print("message_blocks types:", [b.get("type") for b in data.get("message_blocks") or []])
    print("trace_events count:", len(data.get("trace_events") or []))
