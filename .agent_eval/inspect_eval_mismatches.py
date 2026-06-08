"""Inspect execution_mismatch cases and classify false negatives.

Usage:
    python .agent_eval/inspect_eval_mismatches.py \
        --run .agent_eval/outputs/dev50_after_setop_distinct_antijoin.jsonl \
        --cases .agent_eval/prompts.spider.dev50.json \
        --out .agent_eval/reports/false_negative_mismatches.md \
        --out-json .agent_eval/reports/false_negative_mismatches.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


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


def classify_mismatch(record: dict) -> dict[str, Any]:
    """Classify an execution_mismatch case."""
    gold_rows = record.get("gold_rows_count", 0)
    agent_rows = record.get("agent_rows_count", 0)
    row_count_match = gold_rows == agent_rows

    gold_sql = record.get("gold_sql", "")
    agent_sql = record.get("agent_sql", "")
    safe_sql = record.get("safe_sql", "") or agent_sql
    answer = record.get("agent_answer", "")

    reasons: list[str] = []

    # Determine likely reasons
    if row_count_match:
        reasons.append("row_count_same")
    else:
        reasons.append("row_count_different")

    # Check for column order issues
    gold_upper = gold_sql.upper()
    agent_upper = safe_sql.upper()

    gold_has_distinct = "DISTINCT" in gold_upper
    agent_has_distinct = "DISTINCT" in agent_upper
    gold_has_group_by = "GROUP BY" in gold_upper
    agent_has_group_by = "GROUP BY" in agent_upper
    gold_has_order_by = "ORDER BY" in gold_upper
    agent_has_order_by = "ORDER BY" in agent_upper

    # Column count estimate
    gold_cols = gold_sql.count(",") + 1 if gold_sql else 0
    agent_cols = safe_sql.count(",") + 1 if safe_sql else 0
    if gold_cols > 1 or agent_cols > 1:
        # More accurate: count between SELECT and FROM
        import re
        g_match = re.search(r"SELECT\s+(.*?)\s+FROM", gold_sql, re.IGNORECASE | re.DOTALL)
        a_match = re.search(r"SELECT\s+(.*?)\s+FROM", safe_sql, re.IGNORECASE | re.DOTALL)
        gold_cols_exact = len(re.split(r",(?![^(]*\))", g_match.group(1))) if g_match else gold_cols
        agent_cols_exact = len(re.split(r",(?![^(]*\))", a_match.group(1))) if a_match else agent_cols
    else:
        gold_cols_exact = gold_cols
        agent_cols_exact = agent_cols

    same_column_count = gold_cols_exact == agent_cols_exact

    classification = "unknown"
    if row_count_match and same_column_count:
        classification = "likely_false_negative"
        if gold_rows == agent_rows > 0:
            reasons.append("same_rows_and_columns")
    elif row_count_match and not same_column_count:
        classification = "projection_column_count_mismatch"
        reasons.append(f"gold_cols={gold_cols_exact}, agent_cols={agent_cols_exact}")
    elif not row_count_match:
        classification = "actual_value_mismatch"
        reasons.append(f"gold_rows={gold_rows}, agent_rows={agent_rows}")

    # Check aggregate patterns
    has_aggregates = bool(
        "COUNT(" in agent_upper
        or "AVG(" in agent_upper
        or "SUM(" in agent_upper
        or "MAX(" in agent_upper
        or "MIN(" in agent_upper
    )
    if has_aggregates:
        reasons.append("has_aggregates")

    return {
        "case_id": record.get("case_id"),
        "question": record.get("question", ""),
        "gold_sql": gold_sql,
        "agent_sql": safe_sql,
        "gold_rows_count": gold_rows,
        "agent_rows_count": agent_rows,
        "row_count_match": row_count_match,
        "same_column_count": same_column_count,
        "gold_columns_approx": gold_cols_exact,
        "agent_columns_approx": agent_cols_exact,
        "classification": classification,
        "reasons": reasons,
        "gold_has_distinct": gold_has_distinct,
        "agent_has_distinct": agent_has_distinct,
        "gold_has_group_by": gold_has_group_by,
        "agent_has_group_by": agent_has_group_by,
        "gold_has_order_by": gold_has_order_by,
        "agent_has_order_by": agent_has_order_by,
    }


def build_report(
    records: dict[str, dict],
    cases: dict[str, dict],
    out_md: Path,
    out_json: Path | None,
) -> list[dict]:
    results = []
    for cid, record in sorted(records.items()):
        if record.get("status") != "execution_mismatch":
            continue
        info = classify_mismatch(record)
        results.append(info)

    # Summary counts
    by_class: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_class[r["classification"]].append(r)

    # Write JSON
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_mismatches": len(results),
                    "by_classification": {k: len(v) for k, v in by_class.items()},
                    "cases": results,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # Write Markdown
    lines = [
        "# False-Negative Mismatch Inspection Report",
        f"**Generated**: {datetime.now().isoformat()}",
        f"**Total mismatches**: {len(results)}",
        "",
        "## Summary by Classification",
        "",
        "| Classification | Count | Case IDs |",
        "| :--- | :--- | :--- |",
    ]
    for cls, items in sorted(by_class.items(), key=lambda x: -len(x[1])):
        case_list = ", ".join(i["case_id"] for i in items)
        lines.append(f"| {cls} | {len(items)} | {case_list} |")
    lines.append("")

    lines.append("## Detailed Cases")
    lines.append("")
    for r in results:
        lines.append(f"### {r['case_id']} — `{r['classification']}`")
        lines.append(f"**Question**: {r['question']}")
        lines.append(f"**Rows**: gold={r['gold_rows_count']}, agent={r['agent_rows_count']}, "
                     f"row_match={r['row_count_match']}, same_cols={r['same_column_count']} "
                     f"(gold={r['gold_columns_approx']}, agent={r['agent_columns_approx']})")
        lines.append(f"**Reasons**: {', '.join(r['reasons'])}")
        lines.append(f"**Gold SQL**")
        lines.append("```sql")
        lines.append(r['gold_sql'] or "-- none")
        lines.append("```")
        lines.append(f"**Agent SQL**")
        lines.append("```sql")
        lines.append(r['agent_sql'] or "-- none")
        lines.append("```")
        if r.get("answer"):
            lines.append(f"**Agent Answer**: {str(r.get('answer', ''))[:500]}")
        lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect execution_mismatch cases")
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
    results = build_report(records, cases, out_md, out_json)

    # Summary
    print(f"Total mismatches: {len(results)}")
    by_class: dict[str, int] = defaultdict(int)
    for r in results:
        by_class[r["classification"]] += 1
    for cls, count in sorted(by_class.items(), key=lambda x: -x[1]):
        case_ids = [r["case_id"] for r in results if r["classification"] == cls]
        print(f"  {cls}: {count} — {', '.join(case_ids)}")

    print(f"\nReport: {out_md}")
    if out_json:
        print(f"JSON:   {out_json}")


if __name__ == "__main__":
    main()
