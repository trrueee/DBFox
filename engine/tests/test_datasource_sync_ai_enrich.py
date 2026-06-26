from __future__ import annotations

from fastapi.testclient import TestClient

from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def test_datasource_sync_ai_enrich_returns_catalog_result_without_second_enrich(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeSyncResult:
        tables_created = 1
        tables_updated = 2
        tables_removed = 0
        columns_created = 3
        columns_updated = 4
        columns_removed = 0
        synced = True
        ai_enrich_result = {
            "ai_enriched": True,
            "enriched_count": 3,
            "reason": "",
            "errors": [],
        }

    def fake_sync_catalog(db, datasource_id: str, **kwargs):
        calls.append({"datasource_id": datasource_id, **kwargs})
        return FakeSyncResult()

    def fail_second_enrich(*args, **kwargs):
        raise AssertionError("api_sync_schema should not call ai_enrich_catalog twice")

    monkeypatch.setattr("engine.api.datasources.schema._sync_catalog", fake_sync_catalog)
    monkeypatch.setattr("engine.ai_enrich.ai_enrich_catalog", fail_second_enrich)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/datasources/{test_datasource.id}/sync",
                json={
                    "ai_enrich": True,
                    "api_key": "sk-from-ui",
                    "api_base": "https://llm.example/v1",
                    "model_name": "qwen-plus",
                },
                headers=_headers(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls == [
        {
            "datasource_id": test_datasource.id,
            "ai_enrich": True,
            "ai_api_key": "sk-from-ui",
            "ai_api_base": "https://llm.example/v1",
            "ai_model_name": "qwen-plus",
        }
    ]
    assert response.json()["aiEnrich"] == FakeSyncResult.ai_enrich_result
