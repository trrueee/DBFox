"""
DataBox Agent Spider Text-to-SQL Evaluation Runner

Black-box evaluator: calls the DataBox HTTP API, parses SSE events,
auto-approves pending approvals, compares gold SQL vs agent SQL execution
results, and produces JSONL + Markdown reports.

Usage:
    python .agent_eval/run_agent_eval.py \
        --base-url http://127.0.0.1:18625 \
        --model gpt-4o-mini \
        --cases .agent_eval/prompts.spider.smoke.json \
        --datasource-map .agent_eval/datasource_map.json \
        --out .agent_eval/outputs/spider_smoke.jsonl

    # Or with config file:
    python .agent_eval/run_agent_eval.py \
        --config .agent_eval/config.local.json \
        --cases .agent_eval/prompts.spider.smoke.json \
        --out .agent_eval/outputs/spider_smoke.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pymysql

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / ".agent_eval"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from spider_sql_canonicalizer import canonicalize_gold_sql_with_warnings

STATUS_BUCKETS = [
    "pass",
    "eval_env_failed",
    "validation_blocked",
    "agent_execution_failed",
    "execution_mismatch",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str | None) -> dict[str, Any]:
    """Load config from JSON file, or return sensible defaults."""
    defaults: dict[str, Any] = {
        "base_url": "http://127.0.0.1:18625",
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "model": "gpt-4o-mini",
        "mysql": {
            "host": "127.0.0.1",
            "port": 3307,
            "user": "root",
            "password": "root",
        },
        "execute": True,
        "max_steps": 15,
    }
    if config_path:
        cfg_file = Path(config_path)
        if cfg_file.exists():
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            # Deep-merge mysql block
            if "mysql" in cfg:
                defaults["mysql"].update(cfg.pop("mysql"))
            defaults.update(cfg)
    return defaults


def get_local_token() -> str | None:
    """Retrieve the API auth token from known locations on disk."""
    appdata = os.environ.get("APPDATA")
    paths: list[Path] = []
    if appdata:
        paths.append(Path(appdata) / "DataBox" / "auth" / ".local_token")
    paths.append(PROJECT_ROOT / ".databox_runtime" / "auth" / ".local_token")
    for p in paths:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    return None


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def execute_mysql_query(
    host: str,
    port: int,
    user: str,
    password: str,
    db_name: str,
    sql: str,
) -> tuple[list[tuple] | None, list[str] | None, str | None]:
    """Execute a query on the target MySQL instance. Returns (rows, columns, error)."""
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            cursorclass=pymysql.cursors.Cursor,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                return rows, columns, None
        finally:
            conn.close()
    except Exception as exc:
        return None, None, str(exc)


def fetch_mysql_tables(
    host: str,
    port: int,
    user: str,
    password: str,
    db_name: str,
) -> tuple[list[str] | None, str | None]:
    """Return physical MySQL table names for the eval database."""
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            cursorclass=pymysql.cursors.Cursor,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                return [str(row[0]) for row in cursor.fetchall()], None
        finally:
            conn.close()
    except Exception as exc:
        return None, str(exc)


def execute_gold_sql_for_case(
    *,
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    mysql_db: str,
    db_id: str,
    gold_sql: str,
) -> dict[str, Any]:
    """Canonicalize and execute a Spider gold SQL query against imported MySQL."""
    mysql_tables, table_err = fetch_mysql_tables(
        mysql_host,
        mysql_port,
        mysql_user,
        mysql_password,
        mysql_db,
    )
    warnings: list[str] = []
    if table_err:
        canonical_gold_sql = gold_sql
        warnings.append(f"canonicalization_skipped_table_fetch_failed:{table_err}")
    else:
        canonical_gold_sql, warnings = canonicalize_gold_sql_with_warnings(
            gold_sql,
            db_id=db_id,
            table_names=mysql_tables or [],
        )

    rows, columns, error = execute_mysql_query(
        mysql_host,
        mysql_port,
        mysql_user,
        mysql_password,
        mysql_db,
        canonical_gold_sql,
    )

    return {
        "gold_rows": rows,
        "gold_cols": columns,
        "gold_error": error,
        "gold_sql_original": gold_sql,
        "gold_sql_canonical": canonical_gold_sql,
        "gold_sql_was_canonicalized": canonical_gold_sql != gold_sql,
        "gold_sql_canonicalization_warnings": warnings,
        "mysql_tables": mysql_tables or [],
    }


def fetch_databox_schema_tables(
    *,
    base_url: str,
    token: str,
    datasource_id: str,
) -> tuple[list[str] | None, str | None]:
    """Read DataBox's synced schema metadata for a datasource."""
    url = f"{base_url.rstrip('/')}/api/v1/schema/tables"
    headers = {"X-Local-Token": token}
    try:
        resp = httpx.get(
            url,
            params={"datasource_id": datasource_id},
            headers=headers,
            timeout=15.0,
        )
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
        payload = resp.json()
        if not isinstance(payload, list):
            return None, "DataBox schema tables response was not a list."
        table_names: list[str] = []
        for item in payload:
            if isinstance(item, dict) and item.get("table_name"):
                table_names.append(str(item["table_name"]))
        return table_names, None
    except Exception as exc:
        return None, str(exc)


def _normalized_table_set(tables: list[str] | set[str] | tuple[str, ...]) -> set[str]:
    return {str(table).strip().lower() for table in tables if str(table).strip()}


def schema_metadata_stale_reason(
    mysql_tables: list[str] | set[str] | tuple[str, ...],
    databox_tables: list[str] | set[str] | tuple[str, ...],
) -> str | None:
    """Return a stale metadata reason when DataBox schema diverges from MySQL."""
    mysql_normalized = _normalized_table_set(mysql_tables)
    databox_normalized = _normalized_table_set(databox_tables)

    reasons: list[str] = []
    non_lowercase = sorted(
        str(table).strip()
        for table in databox_tables
        if str(table).strip() and str(table).strip() != str(table).strip().lower()
    )
    if non_lowercase:
        reasons.append(
            "DataBox schema metadata has non-lowercase table names: "
            + ", ".join(non_lowercase[:8])
        )

    missing = sorted(mysql_normalized - databox_normalized)
    extra = sorted(databox_normalized - mysql_normalized)
    if missing:
        reasons.append("missing DataBox metadata for MySQL tables: " + ", ".join(missing[:8]))
    if extra:
        reasons.append("DataBox metadata contains stale tables: " + ", ".join(extra[:8]))

    return "; ".join(reasons) if reasons else None


def preflight_schema_metadata(
    *,
    base_url: str,
    token: str,
    datasource_id: str,
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    mysql_db: str,
) -> dict[str, Any]:
    """Verify DataBox schema metadata matches the imported Spider MySQL schema."""
    mysql_tables, mysql_err = fetch_mysql_tables(
        mysql_host,
        mysql_port,
        mysql_user,
        mysql_password,
        mysql_db,
    )
    if mysql_err:
        return {
            "ok": False,
            "reason": f"MySQL schema preflight failed: {mysql_err}",
            "mysql_tables": mysql_tables or [],
            "databox_tables": [],
        }

    databox_tables, databox_err = fetch_databox_schema_tables(
        base_url=base_url,
        token=token,
        datasource_id=datasource_id,
    )
    if databox_err:
        return {
            "ok": False,
            "reason": f"DataBox schema preflight failed: {databox_err}",
            "mysql_tables": mysql_tables or [],
            "databox_tables": databox_tables or [],
        }

    stale_reason = schema_metadata_stale_reason(mysql_tables or [], databox_tables or [])
    if stale_reason:
        return {
            "ok": False,
            "reason": f"schema_metadata_stale: {stale_reason}",
            "mysql_tables": mysql_tables or [],
            "databox_tables": databox_tables or [],
        }

    return {
        "ok": True,
        "reason": "",
        "mysql_tables": mysql_tables or [],
        "databox_tables": databox_tables or [],
    }


def clean_val(v: Any) -> Any:
    """Standardize scalar values for robust comparison."""
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    if isinstance(v, (int, str)):
        return v
    return str(v)


def compare_results(
    gold_rows: list[tuple],
    agent_rows: list[tuple],
    has_order_by: bool = False,
) -> tuple[bool, str]:
    """Compare two result sets allowing for float rounding and column reordering."""
    if len(gold_rows) != len(agent_rows):
        return False, f"Row count mismatch: gold={len(gold_rows)}, agent={len(agent_rows)}"

    gold_cleaned = [[clean_val(x) for x in row] for row in gold_rows]
    agent_cleaned = [[clean_val(x) for x in row] for row in agent_rows]

    if not gold_cleaned and not agent_cleaned:
        return True, "Both returned empty sets"

    if len(gold_cleaned[0]) != len(agent_cleaned[0]):
        return False, (
            f"Column count mismatch: gold={len(gold_cleaned[0])}, "
            f"agent={len(agent_cleaned[0])}"
        )

    if has_order_by:
        for idx, (g_row, a_row) in enumerate(zip(gold_cleaned, agent_cleaned)):
            if g_row != a_row:
                g_sorted = sorted(g_row, key=lambda x: str(x) if x is not None else "")
                a_sorted = sorted(a_row, key=lambda x: str(x) if x is not None else "")
                if g_sorted != a_sorted:
                    return False, f"Row mismatch at index {idx}: gold={g_row}, agent={a_row}"
    else:
        def _key(row: list) -> tuple:
            return tuple(str(x) for x in row)

        gold_sorted = sorted(gold_cleaned, key=_key)
        agent_sorted = sorted(agent_cleaned, key=_key)

        for idx, (g_row, a_row) in enumerate(zip(gold_sorted, agent_sorted)):
            if g_row != a_row:
                g_sorted_row = sorted(g_row, key=lambda x: str(x) if x is not None else "")
                a_sorted_row = sorted(a_row, key=lambda x: str(x) if x is not None else "")
                if g_sorted_row != a_sorted_row:
                    return False, f"Row mismatch: gold={g_row}, agent={a_row}"

    return True, "Success"


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------

def parse_sse_lines(response: httpx.Response) -> list[dict[str, Any]]:
    """Parse SSE text/event-stream into a list of decoded event dicts."""
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data: list[str] = []

    for raw_line in response.iter_lines():
        line = raw_line.strip() if raw_line else ""

        if not line:
            if current_data:
                payload = "\n".join(current_data)
                try:
                    event = json.loads(payload)
                    if current_event:
                        event["_sse_event"] = current_event
                    events.append(event)
                except json.JSONDecodeError:
                    events.append(
                        {"_sse_event": current_event or "unknown", "raw": payload}
                    )
            current_event = None
            current_data = []
            continue

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data.append(line[len("data:"):].strip())

    return events


# ---------------------------------------------------------------------------
# SSE event extraction
# ---------------------------------------------------------------------------

def extract_agent_sql(events: list[dict]) -> str | None:
    """Extract the final/generated SQL from SSE event stream."""
    for event in events:
        ev_type = event.get("_sse_event") or event.get("type", "")
        data = event.get("response") or event

        # Check artifact events
        if "artifact" in ev_type.lower():
            artifact = event.get("artifact") or data.get("artifact") or {}
            if isinstance(artifact, dict) and artifact.get("type") == "sql":
                return artifact.get("payload", {}).get("sql")

        # Check response body
        if isinstance(data, dict):
            if data.get("sql"):
                return data["sql"]
            # Also check safety.safe_sql
            safety = data.get("safety") or {}
            if isinstance(safety, dict) and safety.get("safe_sql"):
                return safety["safe_sql"]

    return None


def extract_safe_sql(events: list[dict]) -> str | None:
    """Extract safe_sql specifically (post-TrustGate processing)."""
    for event in events:
        data = event.get("response") or event
        if isinstance(data, dict):
            safety = data.get("safety") or {}
            if isinstance(safety, dict) and safety.get("safe_sql"):
                return safety["safe_sql"]
    return None


def extract_final_safety(events: list[dict]) -> dict[str, Any] | None:
    """Extract the final safety payload from the event stream."""
    for event in reversed(events):
        data = event.get("response") or event
        if not isinstance(data, dict):
            continue
        safety = data.get("safety")
        if isinstance(safety, dict):
            return safety
    return None


def extract_generation_metadata(events: list[dict]) -> dict[str, Any]:
    """Extract SQL generation metadata from response safety or SQL artifacts."""
    for event in reversed(events):
        data = event.get("response") or event
        if not isinstance(data, dict):
            continue
        safety = data.get("safety")
        if isinstance(safety, dict) and isinstance(safety.get("generation_metadata"), dict):
            return dict(safety["generation_metadata"])

    for event in reversed(events):
        artifact = event.get("artifact")
        if not isinstance(artifact, dict):
            data = event.get("response") or event
            artifact = data.get("artifact") if isinstance(data, dict) else None
        if not isinstance(artifact, dict):
            continue
        payload = artifact.get("payload")
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("generation_metadata")
        if isinstance(metadata, dict):
            return dict(metadata)
        if artifact.get("type") == "safety" and isinstance(payload.get("generation_metadata"), dict):
            return dict(payload["generation_metadata"])

    return {}


def agent_execution_plan(
    *,
    case_execute: bool,
    agent_sql: str | None,
    safe_sql: str | None,
    final_safety: dict[str, Any] | None,
) -> dict[str, Any]:
    if not agent_sql:
        return {
            "status": "agent_execution_failed",
            "sql_for_exec": None,
            "execution_match": None,
            "reason": "No SQL generated by agent",
        }

    if not case_execute:
        return {
            "status": "pass",
            "sql_for_exec": None,
            "execution_match": None,
            "reason": "SQL generated (execute=false)",
        }

    if final_safety is not None:
        can_execute = bool(final_safety.get("can_execute"))
        if not can_execute or not safe_sql:
            reasons = final_safety.get("blocked_reasons")
            reason_text = ", ".join(str(item) for item in reasons) if isinstance(reasons, list) else "TrustGate blocked execution"
            return {
                "status": "validation_blocked",
                "sql_for_exec": None,
                "execution_match": None,
                "reason": f"Validation blocked agent SQL: {reason_text}",
            }

    if not safe_sql:
        return {
            "status": "validation_blocked",
            "sql_for_exec": None,
            "execution_match": None,
            "reason": "Validation did not produce safe_sql.",
        }

    return {
        "status": "ready",
        "sql_for_exec": safe_sql,
        "execution_match": None,
        "reason": "",
    }


def build_status_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    return {bucket: sum(1 for item in results if item.get("status") == bucket) for bucket in STATUS_BUCKETS}


def extract_answer(events: list[dict]) -> str | None:
    """Extract the final answer text from the SSE event stream."""
    for event in events:
        data = event.get("response") or event
        if isinstance(data, dict):
            answer_obj = data.get("answer")
            if isinstance(answer_obj, dict) and answer_obj.get("answer"):
                return answer_obj["answer"]
            if data.get("explanation"):
                return data["explanation"]
    return None


def extract_steps(events: list[dict]) -> list[str]:
    """Extract executed step names from the SSE event stream."""
    steps: list[str] = []
    seen: set[str] = set()
    for event in events:
        step = event.get("step")
        if isinstance(step, dict):
            name = step.get("name")
            if name and name not in seen:
                steps.append(str(name))
                seen.add(name)
    return steps


def extract_artifacts(events: list[dict]) -> list[str]:
    """Extract produced artifact types from SSE events."""
    types: list[str] = []
    seen: set[str] = set()
    for event in events:
        # Direct artifact field
        artifact = event.get("artifact")
        if isinstance(artifact, dict):
            t = artifact.get("type")
            if t and t not in seen:
                types.append(str(t))
                seen.add(t)
        # Inside response.artifacts
        resp = event.get("response")
        if isinstance(resp, dict):
            for a in resp.get("artifacts") or []:
                if isinstance(a, dict):
                    t = a.get("type")
                    if t and t not in seen:
                        types.append(str(t))
                        seen.add(t)
    return types


def extract_approval(events: list[dict]) -> dict[str, Any] | None:
    """Extract approval info from SSE events."""
    for event in events:
        approval = event.get("approval")
        if isinstance(approval, dict):
            return {
                "id": approval.get("id"),
                "run_id": approval.get("run_id"),
                "status": approval.get("status"),
                "risk_level": approval.get("risk_level"),
                "tool_name": approval.get("tool_name"),
                "reason": approval.get("reason"),
            }
    return None


def extract_error(events: list[dict]) -> str | None:
    """Extract error message from SSE events."""
    for event in events:
        if event.get("error"):
            return str(event["error"])
        ev_type = event.get("_sse_event") or event.get("type", "")
        if "failed" in ev_type.lower():
            return event.get("error") or f"Agent run failed: {ev_type}"
    return None


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_agent_case(
    *,
    base_url: str,
    datasource_id: str,
    question: str,
    token: str,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    execute: bool = True,
    max_steps: int = 15,
    session_id: str | None = None,
    parent_run_id: str | None = None,
    workspace_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str | None, str | None, dict | None]:
    """Run a single agent case against the DataBox streaming API.

    Auto-approves any pending approvals and collects all SSE events.

    Returns (events, error, final_status, approval_info).
    """
    run_url = f"{base_url.rstrip('/')}/api/v1/agent-kernel/run/stream"
    resume_url = f"{base_url.rstrip('/')}/api/v1/agent-kernel/resume/stream"

    payload: dict[str, Any] = {
        "datasource_id": datasource_id,
        "question": question,
        "execute": execute,
        "max_steps": max_steps,
    }
    if session_id:
        payload["session_id"] = session_id
    if parent_run_id:
        payload["parent_run_id"] = parent_run_id
    if model:
        payload["model_name"] = model
    if api_key:
        payload["api_key"] = api_key
    if api_base:
        payload["api_base"] = api_base
    if workspace_context:
        payload["workspace_context"] = workspace_context

    headers = {
        "X-Local-Token": token,
        "Content-Type": "application/json",
    }

    all_events: list[dict[str, Any]] = []
    agent_error: str | None = None
    final_status: str | None = None
    approval_info: dict | None = None

    client = httpx.Client(timeout=60.0)
    active_url = run_url
    active_payload = payload
    resume_count = 0
    max_resumes = 5  # Safety limit

    try:
        while active_url is not None and resume_count <= max_resumes:
            print(f"    → POST {active_url}")
            with client.stream(
                "POST", active_url, json=active_payload, headers=headers, timeout=180.0
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="ignore")
                    agent_error = f"HTTP {resp.status_code}: {body[:500]}"
                    break

                events = parse_sse_lines(resp)
                all_events.extend(events)

                # Inspect events for completion, errors, or approvals
                pending_approval: dict | None = None
                for ev in events:
                    ev_type = ev.get("_sse_event") or ev.get("type", "")

                    # Terminal states
                    if ev_type in ("agent.run.completed",):
                        final_status = "completed"
                    elif ev_type in ("agent.run.failed",):
                        final_status = "failed"
                        agent_error = (
                            ev.get("error")
                            or extract_error(events)
                            or "Agent run failed"
                        )
                    elif ev_type in ("agent.run.waiting_approval",):
                        final_status = "waiting_approval"

                    # Approval required — capture and break to auto-approve
                    if ev_type == "agent.approval.required":
                        approval = ev.get("approval")
                        if isinstance(approval, dict) and approval.get("status") == "pending":
                            pending_approval = approval
                            approval_info = {
                                "id": approval.get("id"),
                                "run_id": approval.get("run_id"),
                                "status": approval.get("status"),
                                "risk_level": approval.get("risk_level"),
                                "tool_name": approval.get("tool_name"),
                                "reason": approval.get("reason"),
                            }
                            print(
                                f"      [APPROVAL] Approval required: {approval.get('tool_name')} "
                                f"— {approval.get('reason', 'no reason')}"
                            )
                            break

                if pending_approval:
                    active_url = resume_url
                    active_payload = {
                        "run_id": pending_approval["run_id"],
                        "approval_id": pending_approval["id"],
                        "approved": True,
                        "note": "Auto-approved by eval runner",
                    }
                    resume_count += 1
                    print(f"      [AUTO-APPROVE] Resuming (resume {resume_count}/{max_resumes})...")
                else:
                    active_url = None  # No more work — stream completed

    finally:
        client.close()

    return all_events, agent_error, final_status, approval_info


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def score_case(
    *,
    status: str | None,
    success: bool | None,
    agent_sql: str | None,
    execution_match: bool | None,
    steps: list[str],
    artifacts: list[str],
    answer: str | None,
    sql_error: str | None,
    agent_error: str | None,
) -> dict[str, Any]:
    """Compute a 5-point quality score per the eval rubric."""
    score = 0
    checks: dict[str, bool] = {}

    # 1 point: run completed successfully
    checks["completed"] = status == "completed" and (success is not False)
    if checks["completed"]:
        score += 1

    # 1 point: SQL was generated
    checks["sql_generated"] = bool(agent_sql)
    if checks["sql_generated"]:
        score += 1

    # 1 point: execution matches gold
    checks["execution_match"] = execution_match is True
    if checks["execution_match"]:
        score += 1

    # 1 point: safety artifact present
    checks["has_safety"] = "safety" in artifacts
    if checks["has_safety"]:
        score += 1

    # 1 point: answer is present (not hallucinated/empty)
    checks["has_answer"] = bool(answer)
    if checks["has_answer"]:
        score += 1

    # Additional diagnostics (not scored, but recorded)
    checks["has_query_plan"] = "query_plan" in artifacts
    checks["has_table"] = "table" in artifacts
    checks["has_error"] = bool(sql_error or agent_error)
    checks["flow_complete"] = len(steps) >= 4  # at least schema→plan→generate→validate

    return {
        "score": score,
        "max_score": 5,
        "sql_valid": checks["sql_generated"] and not bool(sql_error),
        "execution_match": execution_match,
        "has_safety_artifact": checks["has_safety"],
        "has_answer": checks["has_answer"],
        "flow_complete": checks["flow_complete"],
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_markdown_report(
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    out_dir: Path,
) -> Path:
    """Generate a Markdown eval report and return its path."""
    md_path = out_dir / "eval_report.md"

    total = summary["total_cases"]
    passed = summary["passed_cases"]
    failed_cases = total - passed

    lines: list[str] = []
    lines.append("# DataBox Agent Text-to-SQL Evaluation Report\n")
    lines.append(f"*Generated at: {summary['evaluation_time']}*\n")

    lines.append("## 📊 Overall Performance Summary\n")
    lines.append("| Metric | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Total Test Cases** | {total} |")
    lines.append(f"| **Passed Cases** | {passed} |")
    lines.append(f"| **Failed Cases** | {failed_cases} |")
    lines.append(f"| **Pass Rate** | **{summary['pass_rate']}%** |")
    lines.append(f"| **Average Latency** | {summary['average_latency_seconds']}s |")
    lines.append(f"| **Total Duration** | {summary['total_duration_seconds']}s |\n")

    # Case-by-case table
    lines.append("## 📋 Case-by-Case Breakdown\n")
    lines.append("| Case ID | DB | Difficulty | Status | Score | Latency | Reason |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for r in results:
        status_str = "🟢 PASS" if r["status"] == "pass" else "🔴 FAIL"
        diff = r.get("difficulty", "?")
        score = r.get("quality", {}).get("score", "?")
        lat = r.get("latency_seconds", 0)
        reason = (r.get("reason") or "")[:100]
        lines.append(
            f"| `{r['case_id']}` | `{r['db_id']}` | {diff} | **{status_str}** | "
            f"{score}/5 | {lat:.1f}s | {reason} |"
        )
    lines.append("")

    # Deep dive
    lines.append("## 🔍 Deep Dive Details\n")
    for r in results:
        emoji = "✅" if r["status"] == "pass" else "❌"
        lines.append(f"### {emoji} Case `{r['case_id']}` ({r.get('difficulty', '?')})\n")
        lines.append(f"- **Question:** {r['question']}")
        lines.append(f"- **DB Name:** `{r['db_id']}`")
        lines.append(f"- **Gold SQL:**\n  ```sql\n  {r['gold_sql']}\n  ```")
        if r.get("agent_sql"):
            lines.append(f"- **Agent SQL:**\n  ```sql\n  {r['agent_sql']}\n  ```")
        else:
            lines.append("- **Agent SQL:** *None generated*")
        if r.get("agent_answer"):
            lines.append(f"- **Agent Answer:** {r['agent_answer'][:300]}")
        if r.get("steps"):
            lines.append(f"- **Steps:** {', '.join(r['steps'])}")
        if r.get("artifacts"):
            lines.append(f"- **Artifacts:** {', '.join(r['artifacts'])}")
        lines.append(f"- **Result:** {r.get('reason', 'N/A')}")
        if r.get("agent_error"):
            lines.append(f"- **Error:** `{r['agent_error']}`")
        if r.get("quality"):
            q = r["quality"]
            lines.append(f"- **Quality Score:** {q['score']}/5 (checks: {json.dumps(q.get('checks', {}))})")

        # Collapsible event log
        lines.append("\n<details>")
        lines.append("<summary>💬 Agent SSE Event Stream</summary>\n")
        lines.append("```json")
        simplified = []
        for ev in r.get("events_log", [])[:50]:  # Limit to 50 events
            simplified.append({
                "event": ev.get("_sse_event") or ev.get("event"),
                "type": ev.get("type"),
                "step": ev.get("step", {}).get("name") if isinstance(ev.get("step"), dict) else None,
                "error": ev.get("error"),
                "artifact_type": ev.get("artifact", {}).get("type") if isinstance(ev.get("artifact"), dict) else None,
            })
        lines.append(json.dumps(simplified, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("</details>\n")
        lines.append("---\n")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def write_case_outputs(case_id: str, record: dict[str, Any]) -> None:
    """Write per-case detail and event stream files."""
    case_dir = RESULTS_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    detail_for_file = {k: v for k, v in record.items() if k != "events_log"}
    detail_for_file["event_count"] = len(record.get("events_log", []))
    (case_dir / "case_detail.json").write_text(
        json.dumps(detail_for_file, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (case_dir / "events.json").write_text(
        json.dumps(record.get("events_log", []), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DataBox Agent Spider Text-to-SQL Eval Runner"
    )
    parser.add_argument("--config", help="Path to config JSON file")
    parser.add_argument("--base-url", help="DataBox API base URL")
    parser.add_argument("--api-key", help="LLM API key")
    parser.add_argument("--model", help="Model name to pass to agent")
    parser.add_argument("--cases", required=True, help="Path to prompt cases JSON file")
    parser.add_argument(
        "--datasource-map", help="Path to datasource_map.json (db_id → datasource_id)"
    )
    parser.add_argument("--mysql-host", help="MySQL host")
    parser.add_argument("--mysql-port", type=int, help="MySQL port")
    parser.add_argument("--mysql-user", help="MySQL user")
    parser.add_argument("--mysql-password", help="MySQL password")
    parser.add_argument("--out", help="Path for JSONL output file")
    parser.add_argument("--no-execute", action="store_true", help="Disable SQL execution (global)")
    parser.add_argument("--max-steps", type=int, default=15, help="Max agent steps per case")
    args = parser.parse_args()

    # Load config (supports both legacy flat format and nested llm/backend format)
    cfg = load_config(args.config)

    # Resolve LLM config via eval_common for nested llm/backend format support
    from eval_common import load_llm_config
    llm_cfg = load_llm_config(args.config)
    if llm_cfg.get("api_key"):
        cfg["api_key"] = llm_cfg["api_key"]
    if llm_cfg.get("model_name"):
        cfg["model"] = llm_cfg["model_name"]
    if llm_cfg.get("api_base"):
        cfg["api_base"] = llm_cfg["api_base"]
    # Also resolve base_url from backend block
    if isinstance(cfg.get("backend"), dict):
        cfg["base_url"] = cfg["backend"].get("base_url", cfg.get("base_url"))

    base_url = args.base_url or cfg.get("base_url", "http://127.0.0.1:18625")
    api_key = args.api_key or cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
    api_base = cfg.get("api_base", "")
    model = args.model or cfg.get("model", "gpt-4o-mini")
    mysql_cfg = cfg.get("mysql", {})
    mysql_host = args.mysql_host or mysql_cfg.get("host", "127.0.0.1")
    mysql_port = args.mysql_port or mysql_cfg.get("port", 3307)
    mysql_user = args.mysql_user or mysql_cfg.get("user", "root")
    mysql_password = args.mysql_password or mysql_cfg.get("password", "root")
    global_execute = not args.no_execute
    max_steps = args.max_steps

    print("=" * 65)
    print("     DataBox Agent Spider Text-to-SQL Evaluation Runner")
    print("=" * 65)
    print(f"  Base URL:     {base_url}")
    print(f"  Model:        {model}")
    print(f"  MySQL:        {mysql_user}@{mysql_host}:{mysql_port}")
    print(f"  Execute SQL:  {global_execute}")
    print(f"  Max steps:    {max_steps}")
    print("=" * 65)

    # Auth token
    token = get_local_token()
    if not token:
        print("ERROR: Could not retrieve X-Local-Token!")
        print("  Ensure the DataBox backend is running and has written a token file.")
        sys.exit(1)
    print(f"  Token:        {token[:8]}...{token[-8:]}")

    # Load cases
    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"ERROR: Cases file not found: {cases_path}")
        sys.exit(1)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    print(f"  Cases:        {len(cases)}")
    print("=" * 65)

    # Load datasource map (optional — allows ds override)
    datasource_map: dict[str, dict] = {}
    if args.datasource_map:
        dm_path = Path(args.datasource_map)
        if dm_path.exists():
            datasource_map = json.loads(dm_path.read_text(encoding="utf-8"))

    # Output JSONL
    jsonl_path: Path | None = None
    if args.out:
        jsonl_path = Path(args.out)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    passed_count = 0
    total_cases = len(cases)
    eval_start = time.time()

    for idx, case in enumerate(cases):
        case_id = case.get("case_id") or case.get("id", f"case_{idx}")
        db_id = case["db_id"]
        question = case["question"]
        gold_sql = case.get("gold_sql") or case.get("query", "")
        difficulty = case.get("difficulty", "unknown")
        case_execute = case.get("execute", global_execute)
        mysql_db = f"spider_{db_id}"

        # Resolve datasource_id
        ds_info = datasource_map.get(db_id, {})
        datasource_id = ds_info.get("dev_datasource_id", f"ds-spider-{db_id.replace('_', '-')}")

        print(f"\n[{idx + 1}/{total_cases}] {case_id} ({difficulty})")
        print(f"  DB: {db_id}  |  DS: {datasource_id}")
        print(f"  Q:  {question}")
        print(f"  Gold SQL: {gold_sql}")

        case_start = time.time()
        gold_rows, gold_cols, gold_err = None, None, None
        gold_sql_original = gold_sql
        gold_sql_canonical = gold_sql
        gold_sql_was_canonicalized = False
        gold_sql_canonicalization_warnings: list[str] = []
        agent_rows, agent_cols, agent_exec_err = None, None, None
        execution_match: bool | None = None
        reason = ""
        schema_preflight: dict[str, Any] | None = None

        # --- Eval environment preflight ---
        if gold_sql:
            gold_exec = execute_gold_sql_for_case(
                mysql_host=mysql_host,
                mysql_port=mysql_port,
                mysql_user=mysql_user,
                mysql_password=mysql_password,
                mysql_db=mysql_db,
                db_id=db_id,
                gold_sql=gold_sql,
            )
            gold_rows = gold_exec["gold_rows"]
            gold_cols = gold_exec["gold_cols"]
            gold_err = gold_exec["gold_error"]
            gold_sql_original = gold_exec["gold_sql_original"]
            gold_sql_canonical = gold_exec["gold_sql_canonical"]
            gold_sql_was_canonicalized = bool(gold_exec["gold_sql_was_canonicalized"])
            gold_sql_canonicalization_warnings = list(
                gold_exec.get("gold_sql_canonicalization_warnings") or []
            )
            if gold_sql_was_canonicalized:
                print(f"  Canonical Gold SQL: {gold_sql_canonical}")
            if gold_sql_canonicalization_warnings:
                print(f"  Gold canonicalization warnings: {gold_sql_canonicalization_warnings}")
            if gold_err:
                reason = f"canonical_gold_failed: Gold SQL execution failed: {gold_err}"
                print(f"  [GOLD ERR] Gold SQL error: {gold_err}")
            else:
                print(f"  Gold rows: {len(gold_rows)} cols={gold_cols}")

        if not gold_err:
            schema_preflight = preflight_schema_metadata(
                base_url=base_url,
                token=token,
                datasource_id=datasource_id,
                mysql_host=mysql_host,
                mysql_port=mysql_port,
                mysql_user=mysql_user,
                mysql_password=mysql_password,
                mysql_db=mysql_db,
            )
            if not schema_preflight.get("ok"):
                reason = str(schema_preflight.get("reason") or "schema_metadata_stale")
                print(f"  [SCHEMA ERR] {reason}")
            else:
                print(
                    "  Schema preflight: "
                    f"MySQL={len(schema_preflight.get('mysql_tables', []))} "
                    f"DataBox={len(schema_preflight.get('databox_tables', []))}"
                )

        if gold_err or (schema_preflight and not schema_preflight.get("ok")):
            case_latency = time.time() - case_start
            quality = score_case(
                status="failed",
                success=False,
                agent_sql=None,
                execution_match=None,
                steps=[],
                artifacts=[],
                answer=None,
                sql_error=gold_err,
                agent_error=reason,
            )
            record = {
                "case_id": case_id,
                "db_id": db_id,
                "question": question,
                "difficulty": difficulty,
                "gold_sql": gold_sql,
                "gold_sql_original": gold_sql_original,
                "gold_sql_canonical": gold_sql_canonical,
                "gold_sql_was_canonicalized": gold_sql_was_canonicalized,
                "gold_sql_canonicalization_warnings": gold_sql_canonicalization_warnings,
                "agent_sql": None,
                "safe_sql": None,
                "agent_answer": None,
                "status": "eval_env_failed",
                "final_status": None,
                "execution_match": None,
                "reason": reason,
                "quality": quality,
                "steps": [],
                "artifacts": [],
                "approval": None,
                "latency_seconds": round(case_latency, 2),
                "gold_rows_count": len(gold_rows) if gold_rows is not None else 0,
                "agent_rows_count": 0,
                "gold_error": gold_err,
                "agent_error": None,
                "schema_preflight": schema_preflight,
                "events_log": [],
            }
            results.append(record)
            write_case_outputs(case_id, record)
            continue

        # --- Run agent ---
        events, agent_error, final_status, approval_info = run_agent_case(
            base_url=base_url,
            datasource_id=datasource_id,
            question=question,
            token=token,
            model=model,
            api_key=api_key,
            api_base=api_base,
            execute=case_execute,
            max_steps=max_steps,
        )
        case_latency = time.time() - case_start

        # --- Extract from events ---
        agent_sql = extract_agent_sql(events)
        safe_sql = extract_safe_sql(events)
        final_safety = extract_final_safety(events)
        generation_metadata = extract_generation_metadata(events)
        semantic_violations = generation_metadata.get("semantic_violations")
        if not isinstance(semantic_violations, list):
            semantic_violations = []
        semantic_retry_attempted = bool(generation_metadata.get("semantic_retry_attempted"))
        answer = extract_answer(events)
        steps = extract_steps(events)
        artifacts = extract_artifacts(events)
        stream_error = extract_error(events) or agent_error

        print(f"  Agent SQL:  {agent_sql}")
        print(f"  Safe SQL:   {safe_sql}")
        print(f"  Steps:      {steps}")
        print(f"  Artifacts:  {artifacts}")
        print(f"  Latency:    {case_latency:.1f}s")
        if approval_info:
            print(f"  Approval:   {approval_info.get('tool_name')} ({approval_info.get('status')})")
        if stream_error:
            print(f"  Error:      {stream_error}")

        # --- Execute & compare ---
        execution_plan = agent_execution_plan(
            case_execute=case_execute,
            agent_sql=agent_sql,
            safe_sql=safe_sql,
            final_safety=final_safety,
        )
        sql_for_exec = execution_plan["sql_for_exec"]

        if gold_err:
            # Gold SQL could not be executed in the evaluation environment
            status = "eval_env_failed"
        elif execution_plan["status"] == "validation_blocked":
            status = "validation_blocked"
            execution_match = None
            reason = str(execution_plan["reason"])
            print(f"  [VALIDATION BLOCKED] {reason}")
        elif stream_error and not agent_sql:
            status = "agent_execution_failed"
            reason = f"Agent stream error: {stream_error}"
        elif execution_plan["status"] == "agent_execution_failed":
            status = "agent_execution_failed"
            reason = str(execution_plan["reason"])
        elif execution_plan["status"] == "ready" and sql_for_exec:
            agent_rows, agent_cols, agent_exec_err = execute_mysql_query(
                mysql_host, mysql_port, mysql_user, mysql_password, mysql_db, sql_for_exec
            )
            if agent_exec_err:
                status = "agent_execution_failed"
                reason = f"Agent SQL execution failed: {agent_exec_err}"
                print(f"  [AGENT ERR] Agent SQL error: {agent_exec_err}")
            elif gold_rows is not None:
                has_order = "order by" in gold_sql_canonical.lower()
                is_match, match_reason = compare_results(gold_rows, agent_rows, has_order)
                execution_match = is_match
                if is_match:
                    status = "pass"
                    reason = "Execution match"
                    passed_count += 1
                    print(f"  [MATCH] Execution MATCH")
                else:
                    status = "execution_mismatch"
                    reason = f"Result mismatch: {match_reason}"
                    print(f"  [MISMATCH] Execution MISMATCH: {match_reason}")
            else:
                status = "pass"  # No gold to compare against — just check it ran
                reason = "Agent SQL executed (no gold comparison)"
                passed_count += 1
        else:
            # execute=false — just check SQL was generated
            status = str(execution_plan["status"])
            reason = str(execution_plan["reason"])
            if status == "pass":
                passed_count += 1
            print(f"  [INFO] SQL generated (not executed)")

        # --- Quality scoring ---
        quality = score_case(
            status=final_status or ("completed" if status == "pass" else "failed"),
            success=(status == "pass"),
            agent_sql=agent_sql,
            execution_match=execution_match,
            steps=steps,
            artifacts=artifacts,
            answer=answer,
            sql_error=agent_exec_err,
            agent_error=stream_error,
        )

        # --- Build result record ---
        record = {
            "case_id": case_id,
            "db_id": db_id,
            "question": question,
            "difficulty": difficulty,
            "gold_sql": gold_sql,
            "gold_sql_original": gold_sql_original,
            "gold_sql_canonical": gold_sql_canonical,
            "gold_sql_was_canonicalized": gold_sql_was_canonicalized,
            "gold_sql_canonicalization_warnings": gold_sql_canonicalization_warnings,
            "agent_sql": agent_sql,
            "safe_sql": safe_sql,
            "agent_answer": answer,
            "status": status,
            "final_status": final_status,
            "execution_match": execution_match,
            "reason": reason,
            "quality": quality,
            "steps": steps,
            "artifacts": artifacts,
            "approval": approval_info,
            "generation_metadata": generation_metadata,
            "semantic_violations": semantic_violations,
            "semantic_retry_attempted": semantic_retry_attempted,
            "latency_seconds": round(case_latency, 2),
            "gold_rows_count": len(gold_rows) if gold_rows is not None else 0,
            "agent_rows_count": len(agent_rows) if agent_rows is not None else 0,
            "gold_error": gold_err,
            "agent_error": stream_error or agent_exec_err,
            "schema_preflight": schema_preflight,
            "events_log": events,
        }
        results.append(record)

        # Save per-case detail
        write_case_outputs(case_id, record)

    # --- Summary ---
    eval_latency = time.time() - eval_start
    avg_latency = (
        sum(r["latency_seconds"] for r in results) / total_cases
        if total_cases > 0
        else 0.0
    )
    pass_rate = passed_count / total_cases if total_cases > 0 else 0.0
    semantic_violation_counts = Counter(
        str(item.get("code"))
        for r in results
        for item in (r.get("semantic_violations") or [])
        if isinstance(item, dict) and item.get("code")
    )

    summary = {
        "evaluation_time": datetime.now(timezone.utc).isoformat(),
        "total_cases": total_cases,
        "passed_cases": passed_count,
        "failed_cases": total_cases - passed_count,
        "pass_rate": round(pass_rate * 100, 2),
        "average_latency_seconds": round(avg_latency, 2),
        "total_duration_seconds": round(eval_latency, 2),
        "status_counts": build_status_summary(results),
        "semantic_violation_counts": dict(sorted(semantic_violation_counts.items())),
        "semantic_retry_attempted_count": sum(1 for r in results if r.get("semantic_retry_attempted")),
        "gold_sql_canonicalized_count": sum(
            1 for r in results if r.get("gold_sql_was_canonicalized")
        ),
        "gold_sql_canonicalization_failed_count": sum(
            1 for r in results if r.get("gold_error")
        ),
        "model": model,
        "cases": [
            {
                "case_id": r["case_id"],
                "db_id": r["db_id"],
                "difficulty": r.get("difficulty", "?"),
                "status": r["status"],
                "score": r.get("quality", {}).get("score", 0),
                "reason": r.get("reason", ""),
                "latency_seconds": r["latency_seconds"],
                "gold_sql_was_canonicalized": r.get("gold_sql_was_canonicalized", False),
                "semantic_violations": r.get("semantic_violations", []),
                "semantic_retry_attempted": r.get("semantic_retry_attempted", False),
            }
            for r in results
        ],
    }

    # Write summary JSON
    (EVAL_DIR / "eval_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Generate Markdown report
    report_path = generate_markdown_report(summary, results, EVAL_DIR)
    print(f"\n  Report: {report_path}")

    # Write JSONL output
    if jsonl_path:
        with jsonl_path.open("w", encoding="utf-8") as f:
            for r in results:
                # Serialize without full events_log in JSONL (keep summary)
                compact = {k: v for k, v in r.items() if k != "events_log"}
                compact["event_count"] = len(r.get("events_log", []))
                f.write(json.dumps(compact, ensure_ascii=False, default=str) + "\n")
        print(f"  JSONL:   {jsonl_path}")

    # Final summary
    avg_score = sum(r.get("quality", {}).get("score", 0) for r in results) / total_cases if total_cases > 0 else 0
    print("\n" + "=" * 65)
    print("                    EVALUATION COMPLETE")
    print(f"  Total:     {total_cases}")
    print(f"  Passed:    {passed_count}  |  Failed: {total_cases - passed_count}")
    print(f"  Pass Rate: {pass_rate * 100:.1f}%")
    print(f"  Avg Score: {avg_score:.1f}/5")
    print(f"  Avg Lat:   {avg_latency:.1f}s  |  Total: {eval_latency:.1f}s")
    print("=" * 65)


if __name__ == "__main__":
    main()
