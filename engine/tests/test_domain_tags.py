from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DEFAULT_PROJECT_ID, DataSource, SchemaTable, DomainTagRule
from engine.tools.db_tools import _table_tags


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_domain_tag_rules_lifecycle(db_session, client):
    # 1. Create a DataSource and SchemaTable
    ds = DataSource(
        id="ds-tags-test",
        project_id=DEFAULT_PROJECT_ID,
        name="Tags Test DS",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name="test.db",
        username="root",
        password_ciphertext="",
        password_nonce="",
    )
    db_session.add(ds)
    db_session.commit()

    table = SchemaTable(
        id="table-tags-test",
        data_source_id="ds-tags-test",
        table_schema="main",
        table_name="my_user_accounts_table",
    )
    db_session.add(table)
    db_session.commit()

    # 2. Verify _table_tags dynamically bootstraps default rules and matches "user"
    tags = _table_tags(db_session, table)
    assert "user" in tags

    # Verify rules were bootstrapped in DB
    db_rules = db_session.query(DomainTagRule).filter(DomainTagRule.data_source_id == "ds-tags-test").all()
    assert len(db_rules) > 0

    # 3. Test API GET /datasources/{id}/domain-tags
    response = client.get("/api/v1/datasources/ds-tags-test/domain-tags", headers=_headers())
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data) > 0
    # Find the rule with tag "user" and pattern "user"
    user_rule = next(r for r in res_data if r["pattern"] == "user")
    assert user_rule["tag"] == "user"
    assert user_rule["priority"] == 10

    # 4. Test API POST /datasources/{id}/domain-tags to custom define rules
    # We define a custom tag "vip" with pattern "accounts" and high priority (100)
    custom_rules = [
        {"pattern": "accounts", "tag": "vip", "priority": 100},
        {"pattern": "user", "tag": "user", "priority": 10},
    ]
    post_res = client.post("/api/v1/datasources/ds-tags-test/domain-tags", json=custom_rules, headers=_headers())
    assert post_res.status_code == 200
    assert post_res.json() == {"success": True, "message": "Domain tag rules saved successfully"}

    # 5. Clear session and reload from DB to evaluate new tags
    db_session.expire_all()
    new_tags = _table_tags(db_session, table)
    # Since "accounts" matches "my_user_accounts_table" with priority 100, "vip" should be first
    assert new_tags[0] == "vip"
    assert "user" in new_tags
