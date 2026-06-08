from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import importlib.util


def test_quick_agent_run_health_failure():
    # run quick_agent_run with unreachable base-url and assert it exits non-zero
    cmd = [sys.executable, ".agent_eval/quick_agent_run.py", "--base-url", "http://127.0.0.1:59999", "--cases", ".agent_eval/cases.smoke_subset.json"]
    # We expect exit code 2 per script when health check fails
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.returncode != 0
    assert "Health check" in p.stdout or "Please run: python .agent_eval/start_eval_backend.py" in p.stdout


def test_quick_agent_run_no_token(tmp_path):
    # Temporarily rename token if exists to simulate missing token
    from . import conftest  # silent import to ensure test package
    token_paths = [Path.home() / "AppData" / "Roaming" / "DataBox" / "auth" / ".local_token", Path(".local_token")]
    moved = []
    for p in token_paths:
        if p.exists():
            dest = p.with_suffix('.bak_test')
            p.rename(dest)
            moved.append((p, dest))
    try:
        cmd = [sys.executable, ".agent_eval/quick_agent_run.py", "--cases", ".agent_eval/cases.smoke_subset.json"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
        assert p.returncode != 0
        assert "Local token not found" in p.stdout or "Local token" in p.stdout
    finally:
        for orig, dest in moved:
            if dest.exists():
                dest.rename(orig)


def _runner_module():
    path = Path(__file__).resolve().parents[2] / ".agent_eval" / "run_agent_eval.py"
    spec = importlib.util.spec_from_file_location("run_agent_eval", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_safe_sql_does_not_fallback_to_response_sql() -> None:
    runner = _runner_module()
    events = [
        {
            "response": {
                "sql": "SELECT id FROM users ORDER BY ARRAY() LIMIT 100",
                "safety": {"can_execute": False, "safe_sql": None},
            }
        }
    ]

    assert runner.extract_agent_sql(events) == "SELECT id FROM users ORDER BY ARRAY() LIMIT 100"
    assert runner.extract_safe_sql(events) is None


def test_extract_final_safety_returns_last_response_safety() -> None:
    runner = _runner_module()
    events = [
        {"response": {"safety": {"can_execute": True, "safe_sql": "SELECT 1"}}},
        {"response": {"safety": {"can_execute": False, "safe_sql": None, "blocked_reasons": ["syntax_error"]}}},
    ]

    assert runner.extract_final_safety(events) == {
        "can_execute": False,
        "safe_sql": None,
        "blocked_reasons": ["syntax_error"],
    }


def test_agent_execution_plan_blocks_when_final_safety_cannot_execute() -> None:
    runner = _runner_module()

    plan = runner.agent_execution_plan(
        case_execute=True,
        agent_sql="SELECT id FROM users ORDER BY ARRAY() LIMIT 100",
        safe_sql=None,
        final_safety={"can_execute": False, "safe_sql": None, "blocked_reasons": ["syntax_error"]},
    )

    assert plan["status"] == "validation_blocked"
    assert plan["sql_for_exec"] is None
    assert plan["execution_match"] is None


def test_eval_status_counts_include_validation_and_environment_buckets() -> None:
    runner = _runner_module()
    summary = runner.build_status_summary([
        {"status": "pass"},
        {"status": "eval_env_failed"},
        {"status": "validation_blocked"},
        {"status": "agent_execution_failed"},
        {"status": "execution_mismatch"},
    ])

    assert summary == {
        "pass": 1,
        "eval_env_failed": 1,
        "validation_blocked": 1,
        "agent_execution_failed": 1,
        "execution_mismatch": 1,
    }


def test_schema_metadata_stale_reason_detects_missing_and_extra_tables() -> None:
    runner = _runner_module()

    reason = runner.schema_metadata_stale_reason(
        ["pets", "student", "has_pet"],
        ["products"],
    )

    assert reason is not None
    assert "missing DataBox metadata" in reason
    assert "stale tables" in reason


def test_schema_metadata_stale_reason_requires_lowercase_databox_tables() -> None:
    runner = _runner_module()

    reason = runner.schema_metadata_stale_reason(
        ["pets", "student"],
        ["Pets", "student"],
    )

    assert reason is not None
    assert "non-lowercase" in reason


def test_preflight_schema_metadata_reports_stale_metadata(monkeypatch) -> None:
    runner = _runner_module()

    monkeypatch.setattr(
        runner,
        "fetch_mysql_tables",
        lambda *_args, **_kwargs: (["pets", "student"], None),
    )
    monkeypatch.setattr(
        runner,
        "fetch_databox_schema_tables",
        lambda **_kwargs: (["products"], None),
    )

    result = runner.preflight_schema_metadata(
        base_url="http://127.0.0.1:18625",
        token="token",
        datasource_id="ds-spider-pets-1",
        mysql_host="127.0.0.1",
        mysql_port=3307,
        mysql_user="root",
        mysql_password="root",
        mysql_db="spider_pets_1",
    )

    assert result["ok"] is False
    assert str(result["reason"]).startswith("schema_metadata_stale:")
