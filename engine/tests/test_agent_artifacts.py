from __future__ import annotations

from engine.agent_core.artifacts import (
    AgentArtifactIdentity,
    build_profile_artifact,
    build_sql_artifact,
    build_table_artifact,
)
from engine.agent.nodes.observe_node import emit_artifacts_from_observation
from engine.agent_core.types import ResultProfile, ToolObservation
import pytest

pytestmark = pytest.mark.skip(reason="Needs restructuring for new db.* ReAct architecture")


def _profile() -> ResultProfile:
    return ResultProfile(row_count=0)


def test_profile_artifact_does_not_depend_on_missing_result_table_for_failed_execution() -> None:
    artifact = build_profile_artifact(
        _profile(),
        execution={"success": False, "rows": [], "columns": []},
        safety={"can_execute": False},
    )
    assert "result_table" not in artifact.depends_on


def test_profile_artifact_depends_on_result_table_for_successful_execution() -> None:
    artifact = build_profile_artifact(
        _profile(),
        execution={"success": True, "rows": [], "columns": []},
        safety={"can_execute": True},
    )
    assert artifact.depends_on == ["result_table"]


def test_artifact_emission_from_observe_node() -> None:
    state = {
        "run_id": "run-artifacts",
        "execution": {"success": False, "rows": [], "columns": []},
        "safety": {"can_execute": False},
        "result_profile": _profile().model_dump(),
        "artifacts": [],
    }
    artifacts = emit_artifacts_from_observation(
        "profile_result",
        ToolObservation(
            name="profile_result", status="success",
            output=state["result_profile"], latency_ms=0,
        ),
        state,
        "run-artifacts",
    )
    assert artifacts[0].semantic_id == "result_profile"
    assert "result_table" not in artifacts[0].depends_on


def test_table_artifact_is_complete() -> None:
    artifact = build_table_artifact(
        {"success": True, "columns": ["id"], "rows": [{"id": 1}], "rowCount": 1, "latencyMs": 12},
        safety={"can_execute": True},
    )
    assert artifact.semantic_id == "result_table"
    assert artifact.type == "table"
    assert artifact.payload["columns"] == ["id"]
    assert artifact.payload["rowCount"] == 1
    assert artifact.depends_on == ["sql_candidate", "safety_report"]


def test_sql_artifact_includes_generation_metadata() -> None:
    artifact = build_sql_artifact(
        "SELECT 1",
        safety={
            "can_execute": True,
            "generation_metadata": {
                "semantic_violations": [{"code": "distinct_missing"}],
                "semantic_retry_attempted": True,
            },
        },
    )
    assert artifact.payload["generation_metadata"]["semantic_retry_attempted"] is True
    assert artifact.payload["generation_metadata"]["semantic_violations"][0]["code"] == "distinct_missing"
