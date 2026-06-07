"""Compare two eval JSONL runs and produce a detailed diff report.

Usage:
    python .agent_eval/compare_eval_runs.py \
        --before .agent_eval/outputs/dev50_shadow.jsonl \
        --after .agent_eval/outputs/dev50_final.jsonl \
        --cases .agent_eval/prompts.spider.dev50.json \
        --out .agent_eval/reports/dev50_27_to_32_diff.md \
        --out-json .agent_eval/reports/dev50_27_to_32_diff.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime
from collections import Counter


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> dict[str, dict]:
    """Load JSONL and index by case_id."""
    records: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        cid = obj.get("case_id")
        if cid:
            records[cid] = obj
    return records


def load_cases(path: Path) -> dict[str, dict]:
    """Load case definitions JSON array and index by case_id."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {item["case_id"]: item for item in data}
    return {}


# ---------------------------------------------------------------------------
# Violation helpers
# ---------------------------------------------------------------------------

def norm_violations(violations) -> list[dict]:
    """Normalize violations to a list of dicts."""
    if violations is None:
        return []
    if isinstance(violations, dict):
        return [violations]
    if isinstance(violations, list):
        return violations
    return []


def violation_codes(violations) -> list[str]:
    """Extract sorted list of violation codes."""
    codes = [v.get("code", "unknown") for v in norm_violations(violations)]
    return sorted(set(codes))


def classify_failure_bucket(record: dict) -> str:
    """Classify a failed record into a failure bucket.

    Priority order:
    1. semantic_violations codes (primary signal)
    2. status-based (validation_blocked, eval_env_failed)
    3. SQL analysis heuristics
    """
    violations = norm_violations(record.get("semantic_violations"))
    codes = violation_codes(violations)
    status = record.get("status", "unknown")

    # Status-level buckets
    if status == "validation_blocked":
        # Sub-classify if we have violations
        if any("projection" in c for c in codes):
            return "projection (validation_blocked)"
        if any("distinct" in c for c in codes):
            return "distinct_missing (validation_blocked)"
        if codes:
            return f"{'+'.join(codes)} (validation_blocked)"
        return "validation_blocked (no violation)"

    if status == "eval_env_failed":
        return "eval_env_failed"

    if status == "agent_execution_failed":
        return "agent_execution_failed"

    # Violation-code buckets (for execution_mismatch)
    if codes:
        parts = []
        if any("projection" in c for c in codes):
            parts.append("projection")
        if any("distinct" in c for c in codes):
            parts.append("distinct_missing")
        if any("antijoin" in c for c in codes):
            parts.append("antijoin_missing")
        if any("setlogic" in c for c in codes):
            parts.append("setlogic_missing")
        if any("aggregation" in c for c in codes):
            parts.append("aggregation_mismatch")
        if any("having" in c for c in codes):
            parts.append("having_missing")
        if any("duplicate" in c for c in codes):
            parts.append("duplicate_rows")
        if any("order" in c for c in codes):
            parts.append("projection_order_mismatch")
        remaining = [c for c in codes if c not in {
            "projection_missing_requested_column", "projection_extra_columns",
            "projection_order_mismatch", "distinct_missing", "antijoin_missing",
            "setlogic_missing", "aggregation_mismatch", "having_missing",
            "duplicate_rows",
        }]
        if remaining:
            parts.extend(remaining)
        if parts:
            return "+".join(parts)

    # Heuristic: analyze SQL for clues when no violations
    agent_sql = (record.get("safe_sql") or record.get("agent_sql") or "").strip().upper()
    gold_sql = (record.get("gold_sql") or "").strip().upper()

    if "DISTINCT" in gold_sql and "DISTINCT" not in agent_sql:
        return "distinct_missing (heuristic)"

    if "GROUP BY" in gold_sql and "GROUP BY" not in agent_sql:
        return "aggregation_mismatch (heuristic)"

    if ("NOT EXISTS" in gold_sql or "NOT IN" in gold_sql or "LEFT JOIN" in gold_sql) and \
       ("NOT EXISTS" not in agent_sql and "NOT IN" not in agent_sql and "LEFT JOIN" not in agent_sql):
        return "antijoin_missing (heuristic)"

    if "UNION" in gold_sql and "UNION" not in agent_sql:
        return "setlogic_missing (heuristic)"

    return "unknown"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    before_records: dict[str, dict],
    after_records: dict[str, dict],
    cases: dict[str, dict],
    before_file: str,
    after_file: str,
    out_md: Path,
    out_json: Path | None,
    label: str = "fast farm eval, not final correctness run",
) -> dict:
    """Generate diff report. Returns the report data dict."""
    all_case_ids = sorted(set(before_records.keys()) | set(after_records.keys()))

    before_total = len(before_records)
    after_total = len(after_records)
    before_pass = sum(1 for r in before_records.values() if r.get("status") == "pass")
    after_pass = sum(1 for r in after_records.values() if r.get("status") == "pass")

    improved: list[dict] = []
    worsened: list[dict] = []
    unchanged_passed: list[str] = []
    unchanged_failed: list[str] = []
    only_before: list[str] = []
    only_after: list[str] = []

    for cid in all_case_ids:
        in_before = cid in before_records
        in_after = cid in after_records

        if in_before and in_after:
            b_status = before_records[cid].get("status")
            a_status = after_records[cid].get("status")
            b_pass = b_status == "pass"
            a_pass = a_status == "pass"

            if not b_pass and a_pass:
                improved.append(build_case_diff(cid, before_records[cid], after_records[cid], cases))
            elif b_pass and not a_pass:
                worsened.append(build_case_diff(cid, before_records[cid], after_records[cid], cases))
            elif b_pass and a_pass:
                unchanged_passed.append(cid)
            else:
                unchanged_failed.append(cid)
        elif in_before and not in_after:
            only_before.append(cid)
        elif not in_before and in_after:
            only_after.append(cid)

    # Remaining failures by bucket (from after)
    remaining_buckets: Counter[str] = Counter()
    bucket_cases: dict[str, list[str]] = {}
    for cid in all_case_ids:
        if cid in after_records and after_records[cid].get("status") != "pass":
            bucket = classify_failure_bucket(after_records[cid])
            remaining_buckets[bucket] += 1
            bucket_cases.setdefault(bucket, []).append(cid)

    # P0 danger checks
    danger = run_danger_checks(after_records)

    report_data = {
        "generated_at": datetime.now().isoformat(),
        "label": label,
        "before_file": before_file,
        "after_file": after_file,
        "before_total": before_total,
        "before_pass": before_pass,
        "after_total": after_total,
        "after_pass": after_pass,
        "net_delta": after_pass - before_pass,
        "improved_count": len(improved),
        "worsened_count": len(worsened),
        "unchanged_passed_count": len(unchanged_passed),
        "unchanged_failed_count": len(unchanged_failed),
        "only_before": only_before,
        "only_after": only_after,
        "improved": improved,
        "worsened": worsened,
        "unchanged_passed": unchanged_passed,
        "unchanged_failed": unchanged_failed,
        "remaining_failures_by_bucket": dict(remaining_buckets.most_common()),
        "remaining_failure_cases_by_bucket": bucket_cases,
        "danger_checks": danger,
    }

    # Write Markdown
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(build_markdown(report_data), encoding="utf-8")

    # Write JSON
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    return report_data


def build_case_diff(case_id: str, before: dict, after: dict, cases: dict) -> dict:
    """Build a detailed diff entry for a single case."""
    case_meta = cases.get(case_id, {})
    b_status = before.get("status")
    a_status = after.get("status")
    b_violations = violation_codes(before.get("semantic_violations"))
    a_violations = violation_codes(after.get("semantic_violations"))

    return {
        "case_id": case_id,
        "db_id": case_meta.get("db_id", after.get("db_id", "")),
        "difficulty": case_meta.get("difficulty", after.get("difficulty", "")),
        "question": case_meta.get("question", after.get("question", "")),
        "before_status": b_status,
        "after_status": a_status,
        "before_sql": before.get("safe_sql") or before.get("agent_sql") or "",
        "after_sql": after.get("safe_sql") or after.get("agent_sql") or "",
        "gold_sql": case_meta.get("gold_sql", after.get("gold_sql", "")),
        "before_violations": b_violations,
        "after_violations": a_violations,
        "before_bucket": classify_failure_bucket(before),
        "after_bucket": classify_failure_bucket(after),
    }


def run_danger_checks(records: dict[str, dict]) -> dict:
    """Run P0 danger checks on the after records."""
    checks = {
        "eval_env_failed": 0,
        "validation_blocked": 0,
        "agent_execution_failed": 0,
        "schema_err_count": 0,
        "db_locked_error_count": 0,
        "safe_sql_null_but_executed": 0,
    }
    for r in records.values():
        status = r.get("status", "")
        if status == "eval_env_failed":
            checks["eval_env_failed"] += 1
        if status == "validation_blocked":
            checks["validation_blocked"] += 1
        if status == "agent_execution_failed":
            checks["agent_execution_failed"] += 1
        if status == "SCHEMA_ERR":
            checks["schema_err_count"] += 1
        if status == "db_locked_error":
            checks["db_locked_error_count"] += 1
        if r.get("execution_match") is not None and not r.get("safe_sql"):
            checks["safe_sql_null_but_executed"] += 1

    checks["all_clear"] = all(v == 0 for v in checks.values())
    return checks


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def build_markdown(data: dict) -> str:
    lines: list[str] = []

    lines.append("# Dev50 Eval Diff Report\n")
    lines.append(f"**Generated**: {data['generated_at']}")
    lines.append(f"**Label**: _{data['label']}_\n")

    # 1. Summary
    lines.append("## 1. Summary\n")
    lines.append("| Metric | Before | After | Delta |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **File** | `{Path(data['before_file']).name}` | `{Path(data['after_file']).name}` | |")
    lines.append(f"| **Total cases** | {data['before_total']} | {data['after_total']} | {data['after_total'] - data['before_total']:+d} |")
    lines.append(f"| **Pass** | {data['before_pass']} | {data['after_pass']} | {data['net_delta']:+d} |")
    lines.append(f"| **Pass rate** | {data['before_pass']}/{data['before_total']} | {data['after_pass']}/{data['after_total']} | |")
    lines.append(f"| **Improved** | — | {data['improved_count']} | |")
    lines.append(f"| **Worsened** | — | {data['worsened_count']} | |")
    lines.append(f"| **Unchanged (passed)** | — | {data['unchanged_passed_count']} | |")
    lines.append(f"| **Unchanged (failed)** | — | {data['unchanged_failed_count']} | |")
    lines.append("")

    if data["only_before"]:
        lines.append(f"**Only in before**: {', '.join(data['only_before'])}\n")
    if data["only_after"]:
        lines.append(f"**Only in after**: {', '.join(data['only_after'])}\n")

    # Branch decision hint
    improved = data["improved_count"]
    worsened = data["worsened_count"]
    if improved >= worsened + 3:
        lines.append("> **Branch**: improved_count >= worsened_count + 3 → retain projection prompt, enter next bucket.\n")
    elif improved > worsened:
        lines.append("> **Branch**: improved only slightly > worsened → check LLM nondeterminism; re-run key cases 2-3x.\n")
    else:
        lines.append("> **Branch**: worsened >= improved → check projection prompt for aggregation/count regressions; DO NOT proceed to DISTINCT.\n")

    # 2. Improved cases
    lines.append("## 2. Improved Cases\n")
    if data["improved"]:
        lines.append(f"**Count**: {len(data['improved'])}\n")
        for c in data["improved"]:
            lines.append(f"### ✅ {c['case_id']} — {c['db_id']} ({c['difficulty']})\n")
            lines.append(f"**Question**: {c['question']}\n")
            lines.append(f"**Status**: `{c['before_status']}` → `{c['after_status']}`")
            lines.append(f"**Before SQL**")
            lines.append("```sql")
            lines.append(c['before_sql'] or "-- none")
            lines.append("```\n")
            lines.append(f"**After SQL**")
            lines.append("```sql")
            lines.append(c['after_sql'] or "-- none")
            lines.append("```\n")
            lines.append(f"**Gold SQL**")
            lines.append("```sql")
            lines.append(c['gold_sql'] or "-- none")
            lines.append("```\n")
            lines.append(f"**Before violations**: {c['before_violations'] or 'none'}")
            lines.append(f"**After violations**: {c['after_violations'] or 'none'}")
            lines.append(f"**Before bucket**: `{c['before_bucket']}`")
            lines.append(f"**After bucket**: `{c['after_bucket']}`\n")
    else:
        lines.append("_No improved cases._\n")

    # 3. Worsened cases
    lines.append("## 3. Worsened Cases\n")
    if data["worsened"]:
        lines.append(f"**Count**: {len(data['worsened'])}\n")
        for c in data["worsened"]:
            lines.append(f"### ❌ {c['case_id']} — {c['db_id']} ({c['difficulty']})\n")
            lines.append(f"**Question**: {c['question']}\n")
            lines.append(f"**Status**: `{c['before_status']}` → `{c['after_status']}`")
            lines.append(f"**Before SQL**")
            lines.append("```sql")
            lines.append(c['before_sql'] or "-- none")
            lines.append("```\n")
            lines.append(f"**After SQL**")
            lines.append("```sql")
            lines.append(c['after_sql'] or "-- none")
            lines.append("```\n")
            lines.append(f"**Gold SQL**")
            lines.append("```sql")
            lines.append(c['gold_sql'] or "-- none")
            lines.append("```\n")
            lines.append(f"**Before violations**: {c['before_violations'] or 'none'}")
            lines.append(f"**After violations**: {c['after_violations'] or 'none'}")

            # Likely worsen reason
            a_violations = set(c['after_violations'])
            if "projection_missing_requested_column" in a_violations:
                reason = "projection prompt may produce wrong column mapping"
            elif "distinct_missing" in a_violations:
                reason = "distinct_missing now detected (was previously undetected or SQL changed)"
            elif c['after_status'] == "validation_blocked":
                if a_violations:
                    reason = "validation_blocked with violations — output was rejected"
                else:
                    reason = "validation_blocked without violations — possible guardrail false-positive or schema/env issue"
            else:
                reason = "unknown — analyze SQL diff"
            lines.append(f"**Likely worsen reason**: {reason}")

            source = classify_worsen_source(c)
            lines.append(f"**Likely source**: {source}\n")
    else:
        lines.append("_No worsened cases._\n")

    # 4. Remaining failures by bucket
    lines.append("## 4. Remaining Failures by Bucket\n")
    buckets = data["remaining_failures_by_bucket"]
    if buckets:
        lines.append("| Bucket | Count | Case IDs |")
        lines.append("| :--- | :--- | :--- |")
        for bucket, count in sorted(buckets.items(), key=lambda x: -x[1]):
            case_list = data["remaining_failure_cases_by_bucket"].get(bucket, [])
            case_str = ", ".join(case_list)
            lines.append(f"| {bucket} | {count} | {case_str} |")
        lines.append("")

        # Next bucket recommendation
        lines.append("### Next Bucket Recommendation\n")
        # Count by category
        distinct_count = sum(c for b, c in buckets.items() if "distinct" in b.lower())
        aggregation_count = sum(c for b, c in buckets.items() if "aggregation" in b.lower())
        antijoin_count = sum(c for b, c in buckets.items() if "antijoin" in b.lower())
        projection_count = sum(c for b, c in buckets.items() if "projection" in b.lower())
        unknown_count = sum(c for b, c in buckets.items() if "unknown" in b.lower())

        lines.append(f"- distinct_missing: **{distinct_count}**")
        lines.append(f"- aggregation_mismatch: **{aggregation_count}**")
        lines.append(f"- antijoin_missing: **{antijoin_count}**")
        lines.append(f"- projection: **{projection_count}**")
        lines.append(f"- unknown / other: **{unknown_count}**\n")

        # Priority rule
        if distinct_count > 0:
            lines.append("> **Recommendation**: DISTINCT bucket first (explicit distinct questions).\n")
        elif aggregation_count > 0:
            lines.append("> **Recommendation**: aggregation_mismatch bucket — but analyze each case first before changing prompt.\n")
        elif antijoin_count > 0:
            lines.append("> **Recommendation**: antijoin bucket.\n")
        else:
            lines.append("> **Recommendation**: analyze unknown cases individually.\n")
    else:
        lines.append("_No remaining failures._\n")

    # 5. P0 danger checks
    lines.append("## 5. P0 Danger Checks\n")
    d = data["danger_checks"]
    lines.append("| Check | Count |")
    lines.append("| :--- | :--- |")
    for key in ["eval_env_failed", "validation_blocked", "agent_execution_failed",
                 "schema_err_count", "db_locked_error_count", "safe_sql_null_but_executed"]:
        icon = "✅" if d[key] == 0 else "❌"
        lines.append(f"| {icon} {key} | {d[key]} |")
    lines.append("")
    if d["all_clear"]:
        lines.append("**All P0 danger checks clear.**\n")
    else:
        lines.append("**⚠️ P0 danger checks have non-zero values — investigate before proceeding.**\n")

    # 6. Unchanged cases (compact)
    lines.append("## 6. Unchanged Cases\n")
    lines.append(f"- **Passed (both runs)**: {', '.join(data['unchanged_passed']) if data['unchanged_passed'] else 'none'}")
    lines.append(f"- **Failed (both runs)**: {', '.join(data['unchanged_failed']) if data['unchanged_failed'] else 'none'}")
    lines.append("")

    return "\n".join(lines)


def classify_worsen_source(case_diff: dict) -> str:
    """Classify likely source of worsened case."""
    a_violations = set(case_diff["after_violations"])
    b_violations = set(case_diff["before_violations"])

    # If before had no violations but after does, check what changed
    if not b_violations and a_violations:
        if "projection_missing_requested_column" in a_violations:
            return "projection_prompt"
        if "distinct_missing" in a_violations:
            # Was always missing distinct, now detected
            return "LLM nondeterminism (SQL changed) or detection newly active"
        return "LLM nondeterminism or detection newly active"

    if case_diff["after_status"] == "validation_blocked":
        if not a_violations:
            return "schema/env or guardrail — no violations but blocked"

    # SQL changed
    if case_diff["before_sql"] != case_diff["after_sql"]:
        return "LLM nondeterminism (SQL changed)"

    return "unknown"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval JSONL runs and produce a diff report")
    parser.add_argument("--before", required=True, help="Path to baseline JSONL file")
    parser.add_argument("--after", required=True, help="Path to current JSONL file")
    parser.add_argument("--cases", required=True, help="Path to case definitions JSON file")
    parser.add_argument("--out", required=True, help="Path for generated Markdown report")
    parser.add_argument("--out-json", default=None, help="Path for generated JSON report data")
    parser.add_argument("--label", default="fast farm eval, not final correctness run",
                        help="Label for the report")
    args = parser.parse_args()

    before_path = Path(args.before)
    after_path = Path(args.after)
    cases_path = Path(args.cases)
    out_md = Path(args.out)
    out_json = Path(args.out_json) if args.out_json else None

    for p, name in [(before_path, "before"), (after_path, "after"), (cases_path, "cases")]:
        if not p.exists():
            raise SystemExit(f"{name} file not found: {p}")

    print(f"Loading before: {before_path.name}")
    before = load_jsonl(before_path)

    print(f"Loading after: {after_path.name}")
    after = load_jsonl(after_path)

    print(f"Loading cases: {cases_path.name}")
    cases = load_cases(cases_path)

    print(f"Generating report...")
    report_data = generate_report(
        before_records=before,
        after_records=after,
        cases=cases,
        before_file=str(before_path),
        after_file=str(after_path),
        out_md=out_md,
        out_json=out_json,
        label=args.label,
    )

    print(f"Report written to {out_md}")
    if out_json:
        print(f"JSON data written to {out_json}")

    # Quick summary to stdout
    print(f"\nQuick Summary:")
    print(f"  Before: {report_data['before_pass']}/{report_data['before_total']} pass")
    print(f"  After:  {report_data['after_pass']}/{report_data['after_total']} pass")
    print(f"  Delta:  {report_data['net_delta']:+d}")
    print(f"  Improved: {report_data['improved_count']}, Worsened: {report_data['worsened_count']}")
    print(f"  Remaining buckets: {dict(report_data['remaining_failures_by_bucket'])}")


if __name__ == "__main__":
    main()
