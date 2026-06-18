from __future__ import annotations

from engine.tools.runtime.context import ToolContext
from engine.agent_core.types import AgentRunRequest
from engine.semantic.tools import semantic_resolve
from engine.environment.tools import environment_get_profile


def test_semantic_resolve_uses_state_view(db_session, test_datasource, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResolution:
        def model_dump(self, mode: str = "json") -> dict:
            return {"resolved_terms": [], "mode": mode}

    def fake_resolve(self, **kwargs):
        captured.update(kwargs)
        return _FakeResolution()

    monkeypatch.setattr("engine.semantic.tools.SemanticResolver.resolve", fake_resolve)

    req = AgentRunRequest(datasource_id=test_datasource.id, question="统计销售额")
    ctx = ToolContext(
        db=db_session,
        request=req,
        state_view={
            "datasource_id": test_datasource.id,
            "question": "统计销售额",
            "workspace_context": {"selected_sql": "SELECT 1"},
        },
    )

    obs = semantic_resolve(ctx, {})

    assert obs.status == "success"
    assert captured["datasource_id"] == test_datasource.id
    assert captured["question"] == "统计销售额"
    assert captured["workspace_context"] == {"selected_sql": "SELECT 1"}


def test_environment_get_profile_uses_state_view(db_session, test_datasource, monkeypatch) -> None:
    from engine.environment.models import DataEnvironmentProfile

    def fake_get_profile(db, datasource_id: str):
        assert datasource_id == test_datasource.id
        return DataEnvironmentProfile(
            datasource_id=datasource_id,
            env="dev",
            dialect="sqlite",
            catalog_status="fresh",
            table_count=1,
            warnings=[],
        )

    monkeypatch.setattr("engine.environment.tools._svc.get_profile", fake_get_profile)
    monkeypatch.setattr(
        "engine.environment.database_map.build_database_map",
        lambda *args, **kwargs: None,
    )

    req = AgentRunRequest(datasource_id=test_datasource.id, question="hello")
    ctx = ToolContext(
        db=db_session,
        request=req,
        state_view={"datasource_id": test_datasource.id},
    )

    obs = environment_get_profile(ctx, {})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["datasource_id"] == test_datasource.id
