"""Generate a detailed remaining-failure dossier from a dev50 eval run.

Usage:
    python .agent_eval/remaining_failure_dossier.py \
        --run .agent_eval/outputs/dev50_after_comparator.jsonl \
        --cases .agent_eval/prompts.spider.dev50.json \
        --out .agent_eval/reports/dev50_remaining_10.md \
        --out-json .agent_eval/reports/dev50_remaining_10.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> dict[str, dict]:
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
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {item["case_id"]: item for item in data}
    return {}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _norm_violations(record: dict) -> list[dict]:
    v = record.get("semantic_violations")
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return v


def _violation_codes(record: dict) -> set[str]:
    return {vi.get("code", "unknown") for vi in _norm_violations(record)}


def classify_failure(record: dict) -> dict[str, Any]:
    """Classify a single failed case into a detailed bucket."""
    agent_sql = (record.get("safe_sql") or record.get("agent_sql") or "").upper()
    gold_sql = (record.get("gold_sql") or "").upper()
    gold_rows = record.get("gold_rows_count", 0)
    agent_rows = record.get("agent_rows_count", 0)
    codes = _violation_codes(record)
    question = (record.get("question") or "").lower()

    # Estimate column counts
    gold_cols = len(re.findall(r",(?![^(]*\))", gold_sql)) + 1 if gold_sql else 0
    agent_cols = len(re.findall(r",(?![^(]*\))", agent_sql)) + 1 if agent_sql else 0

    bucket = "unknown"
    root_cause = ""
    proposed_fix = ""
    risk = "medium"

    # ---- Anti-join over-strict ----
    if gold_rows > 0 and agent_rows == 0 and ("NOT EXISTS" in agent_sql or "LEFT JOIN" in agent_sql):
        if agent_sql.count("NOT EXISTS") >= 2:
            bucket = "anti_join_over_strict"
            root_cause = (
                "Anti-join checks both sides of a bidirectional relationship "
                "(e.g. both student_id and friend_id in friend table). "
                "Gold only requires absence from one direction."
            )
            proposed_fix = (
                "Anti-join contract should prefer checking only one direction "
                "of bidirectional relations. When the question asks 'no friends', "
                "checking student_id is sufficient; checking friend_id excludes "
                "students who are friends-of-friends."
            )
            risk = "medium"
        elif "NOT EXISTS" in agent_sql and gold_cols + 1 == agent_cols:
            bucket = "projection_extra_columns"
            root_cause = "Anti-join SQL is correct but projection has extra duplicate column alias."
            proposed_fix = "Projection retry: strip duplicate column aliases."
            risk = "low"

    # ---- Set-logic wrong intersection ----
    if bucket == "unknown" and gold_rows > 0 and agent_rows > gold_rows:
        if "INTERSECT" in gold_sql and "INTERSECT" not in agent_sql:
            if "JOIN" in agent_sql and "JOIN" in agent_sql[agent_sql.find("FROM"):]:
                bucket = "setlogic_wrong_intersection"
                root_cause = (
                    "Set-intersection semantics required (INTERSECT) but SQL uses "
                    "JOIN which produces Cartesian-like duplicates across multiple matches."
                )
                proposed_fix = (
                    "Enforce INTERSECT generation when setlogic contract is active. "
                    "Add setlogic_missing to high-confidence retryable codes. "
                    "Retry guidance: prefer INTERSECT for MySQL."
                )
                risk = "low"

    # ---- Projection: wrong entity (SELECT * style) ----
    if bucket == "unknown" and agent_cols > gold_cols * 2:
        bucket = "projection_wrong_entity"
        root_cause = (
            "Agent selected all columns from the entity table instead of only "
            "the requested column (e.g. SELECT * instead of SELECT petid)."
        )
        proposed_fix = (
            "Add projection_extra_columns to high-confidence retryable codes. "
            "Targeted retry: fix only the SELECT list, keep FROM/JOIN/WHERE."
        )
        risk = "low"

    # ---- Projection: extra columns ----
    if bucket == "unknown" and gold_rows == agent_rows > 0 and agent_cols > gold_cols:
        bucket = "projection_extra_columns"
        root_cause = (
            f"Agent projection has {agent_cols} columns but gold has {gold_cols}. "
            "Extra duplicate aliases or unrequested columns present."
        )
        proposed_fix = (
            "Add projection_extra_columns to high-confidence retryable codes. "
            "Targeted retry: strip extra columns from SELECT list."
        )
        risk = "low"

    # ---- Projection: column count mismatch with row mismatch ----
    if bucket == "unknown" and gold_rows != agent_rows:
        if "DISTINCT" in gold_sql and "DISTINCT" not in agent_sql:
            bucket = "distinct_missing_with_projection"
            root_cause = "Missing DISTINCT causes duplicate rows; also projection mapping issues."
            proposed_fix = "DISTINCT contract already active; projection retry needed."
            risk = "medium"
        elif agent_cols != gold_cols:
            bucket = "projection_actual_mismatch"
            root_cause = f"Column mismatch (gold={gold_cols}, agent={agent_cols}) with row count difference."
            proposed_fix = "Projection retry: fix SELECT list to match requested columns."
            risk = "medium"

    # ---- LLM nondeterminism ----
    if bucket == "unknown":
        bucket = "llm_nondeterminism"
        root_cause = "SQL varies between runs; may pass on some runs but fail on others."
        proposed_fix = "Retry with targeted guidance; re-run 2-3x to confirm stability."
        risk = "high"

    return {
        "case_id": record.get("case_id"),
        "db_id": record.get("db_id", ""),
        "difficulty": record.get("difficulty", ""),
        "question": record.get("question", ""),
        "gold_sql": record.get("gold_sql", ""),
        "agent_sql": record.get("safe_sql") or record.get("agent_sql", ""),
        "status": record.get("status", ""),
        "execution_match": record.get("execution_match"),
        "gold_rows_count": gold_rows,
        "agent_rows_count": agent_rows,
        "gold_columns": gold_cols,
        "agent_columns": agent_cols,
        "semantic_violations": [v.get("code") for v in _norm_violations(record)],
        "retry_attempted": record.get("semantic_retry_attempted", False),
        "retry_accepted": record.get("semantic_retry_accepted"),
        "reason": record.get("reason", ""),
        "bucket": bucket,
        "root_cause": root_cause,
        "proposed_fix": proposed_fix,
        "risk": risk,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_report(
    records: dict[str, dict],
    cases: dict[str, dict],
    out_md: Path,
    out_json: Path | None,
) -> list[dict]:
    results = []
    for cid in sorted(records):
        record = records[cid]
        if record.get("status") == "pass":
            continue
        info = classify_failure(record)
        results.append(info)

    # Bucket summary
    bucket_counts: Counter[str] = Counter()
    bucket_cases: dict[str, list[str]] = defaultdict(list)
    for r in results:
        bucket_counts[r["bucket"]] += 1
        bucket_cases[r["bucket"]].append(r["case_id"])

    # ROI ranking: count * (3 if low risk, 2 if medium, 1 if high)
    def roi(bucket: str) -> float:
        count = bucket_counts[bucket]
        cases_in = bucket_cases[bucket]
        # Average risk score
        risk_score = sum(
            3 if r["risk"] == "low" else 2 if r["risk"] == "medium" else 1
            for r in results if r["bucket"] == bucket
        ) / max(count, 1)
        return count * risk_score

    ranked_buckets = sorted(bucket_counts, key=roi, reverse=True)

    # Write JSON
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_failures": len(results),
                    "bucket_summary": dict(bucket_counts),
                    "bucket_cases": dict(bucket_cases),
                    "ranked_buckets": ranked_buckets,
                    "cases": results,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # Write Markdown
    lines = [
        "# Dev50 Remaining Failure Dossier",
        f"**Generated**: {datetime.now().isoformat()}",
        f"**Total remaining failures**: {len(results)}",
        "",
        "## 1. Summary by Bucket",
        "",
        "| Bucket | Count | Cases | ROI Score |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for bucket in ranked_buckets:
        count = bucket_counts[bucket]
        case_list = ", ".join(bucket_cases[bucket])
        r = roi(bucket)
        lines.append(f"| **{bucket}** | {count} | {case_list} | {r:.1f} |")
    lines.append("")

    # ROI priority recommendation
    top = ranked_buckets[0] if ranked_buckets else "none"
    lines.append("## 2. Recommended Next Target")
    lines.append("")
    lines.append(f"**Highest ROI bucket**: `{top}` ({bucket_counts[top]} cases)")
    lines.append("")

    top_cases = [r for r in results if r["bucket"] == top]
    if top_cases:
        lines.append(f"**Proposed fix**: {top_cases[0]['proposed_fix']}")
        lines.append(f"**Risk**: {top_cases[0]['risk']}")
    lines.append("")

    lines.append("## 3. Detailed Case Analysis")
    lines.append("")
    for r in results:
        lines.append(f"### {r['case_id']} — `{r['bucket']}`")
        lines.append("")
        lines.append(f"| Field | Value |")
        lines.append(f"| :--- | :--- |")
        lines.append(f"| **DB** | {r['db_id']} |")
        lines.append(f"| **Difficulty** | {r['difficulty']} |")
        lines.append(f"| **Status** | {r['status']} |")
        lines.append(f"| **Rows** | gold={r['gold_rows_count']}, agent={r['agent_rows_count']} |")
        lines.append(f"| **Columns** | gold={r['gold_columns']}, agent={r['agent_columns']} |")
        lines.append(f"| **Retry** | attempted={r['retry_attempted']}, accepted={r['retry_accepted']} |")
        lines.append(f"| **Violations** | {r['semantic_violations'] or 'none'} |")
        lines.append(f"| **Bucket** | {r['bucket']} |")
        lines.append(f"| **Risk** | {r['risk']} |")
        lines.append("")
        lines.append(f"**Question**: {r['question']}")
        lines.append("")
        lines.append(f"**Root cause**: {r['root_cause']}")
        lines.append(f"**Proposed fix**: {r['proposed_fix']}")
        lines.append("")
        lines.append("**Gold SQL**")
        lines.append("```sql")
        lines.append(r['gold_sql'] or "-- none")
        lines.append("```")
        lines.append("**Agent SQL**")
        lines.append("```sql")
        lines.append(r['agent_sql'] or "-- none")
        lines.append("```")
        lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")

    # Print summary
    print(f"Total failures: {len(results)}")
    print(f"Buckets:")
    for bucket in ranked_buckets:
        print(f"  {bucket}: {bucket_counts[bucket]} — {', '.join(bucket_cases[bucket])}")
    print(f"\nRecommended next: {top} ({bucket_counts[top]} cases)")
    print(f"\nReport: {out_md}")
    if out_json:
        print(f"JSON:   {out_json}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate remaining failure dossier")
    parser.add_argument("--run", required=True, help="Path to JSONL run output")
    parser.add_argument("--cases", required=True, help="Path to case definitions JSON")
    parser.add_argument("--out", required=True, help="Path for Markdown report")
    parser.add_argument("--out-json", default=None, help="Path for JSON report")
    args = parser.parse_args()

    run_path = Path(args.run)
    cases_path = Path(args.cases)
    out_md = Path(args.out)
    out_json = Path(args.out_json) if args.out_json else None

    for p, name in [(run_path, "run"), (cases_path, "cases")]:
        if not p.exists():
            raise SystemExit(f"{name} file not found: {p}")

    records = load_jsonl(run_path)
    cases = load_cases(cases_path)
    build_report(records, cases, out_md, out_json)


if __name__ == "__main__":
    main()
