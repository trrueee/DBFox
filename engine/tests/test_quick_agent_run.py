from __future__ import annotations

import importlib.util
from pathlib import Path


def _runner_module():
    path = Path(__file__).resolve().parents[2] / ".agent_eval" / "quick_agent_run.py"
    spec = importlib.util.spec_from_file_location("quick_agent_run", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_summarize_events_extracts_generation_source_from_steps() -> None:
    runner = _runner_module()

    summary = runner.summarize_events([
        {
            "response": {
                "steps": [
                    {
                        "name": "generate_sql_candidate",
                        "output": {
                            "sql": "SELECT id FROM users LIMIT 10",
                            "model": "databox-query-plan-renderer",
                            "metadata": {"generation_source": "query_plan_rendered"},
                        },
                    }
                ]
            }
        }
    ])

    assert summary["generation_source"] == "query_plan_rendered"
    assert summary["model"] == "databox-query-plan-renderer"
    assert summary["agent_sql"] == "SELECT id FROM users LIMIT 10"


def test_summarize_events_extracts_sql_from_artifact() -> None:
    runner = _runner_module()

    summary = runner.summarize_events([
        {
            "type": "agent.artifact.created",
            "artifact": {
                "semantic_id": "sql_candidate",
                "type": "sql",
                "payload": {"sql": "SELECT COUNT(*) FROM singer LIMIT 100"},
            },
        }
    ])

    assert summary["agent_sql"] == "SELECT COUNT(*) FROM singer LIMIT 100"
    assert "sql_candidate" in summary["summary_debug"]["artifact_semantic_ids"]


def test_summarize_events_extracts_safety_from_safety_artifact() -> None:
    runner = _runner_module()

    summary = runner.summarize_events([
        {
            "type": "agent.artifact.created",
            "artifact": {
                "semantic_id": "safety_report",
                "type": "safety",
                "payload": {
                    "safe_sql": "SELECT id FROM users LIMIT 10",
                    "can_execute": False,
                    "blocked_reasons": ["syntax_error"],
                },
            },
        }
    ])

    assert summary["safe_sql"] == "SELECT id FROM users LIMIT 10"
    assert summary["safety.can_execute"] is False
    assert summary["blocked_reasons"] == ["syntax_error"]


def test_summarize_events_extracts_safety_from_trace_events() -> None:
    runner = _runner_module()

    summary = runner.summarize_events([
        {
            "response": {
                "trace_events": [
                    {
                        "name": "validate_sql",
                        "output": {
                            "safe_sql": None,
                            "can_execute": False,
                            "blocked_reasons": ["guardrail_reject"],
                        },
                    }
                ]
            }
        }
    ])

    assert summary["safe_sql"] is None
    assert summary["safety.can_execute"] is False
    assert summary["blocked_reasons"] == ["guardrail_reject"]
    assert "validate_sql" in summary["summary_debug"]["trace_step_names"]


def test_summarize_events_detects_execute_sql_step() -> None:
    runner = _runner_module()

    summary = runner.summarize_events([
        {"step": {"name": "execute_sql"}},
        {"response": {"steps": [{"name": "validate_sql"}]}},
    ])

    assert summary["execute_sql_step"] is True


def test_summarize_events_debug_for_missing_fields() -> None:
    runner = _runner_module()

    summary = runner.summarize_events([
        {"type": "agent.run.started", "_sse_event": "agent.run.started"}
    ])

    assert summary["generation_source"] is None
    assert summary["agent_sql"] is None
    assert "agent.run.started" in summary["summary_debug"]["event_types"]
    assert "agent.run.started" in summary["summary_debug"]["sse_events"]
