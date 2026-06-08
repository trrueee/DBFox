#!/usr/bin/env python3
"""Semantic gap report: identify false negatives in dev50 shadow results."""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent

FAILURE_BUCKETS = [
    "distinct_missing", "projection_extra_columns", "projection_missing_columns",
    "projection_order_mismatch", "having_missing", "aggregation_mismatch",
    "antijoin_missing", "antijoin_outer_join", "setlogic_missing",
    "setlogic_contradictory_and", "join_path_wrong", "value_literal_mismatch",
    "schema_join_missing", "duplicate_rows", "unknown",
]


def classify_failure(rec: dict) -> str:
    """Heuristic classification of why gold vs agent execution differs."""
    gold = (rec.get("gold_sql") or "").lower()
    agent = (rec.get("agent_sql") or "").lower()
    question = (rec.get("question") or "").lower()
    reason = (rec.get("reason") or "").lower()
    gold_rows = rec.get("gold_rows_count", 0)
    agent_rows = rec.get("agent_rows_count", 0)

    # Row count mismatch analysis
    if "column count" in reason:
        gold_cols = gold.count("select")  # rough
        agent_cols = agent.count("select")
        if agent_cols > gold_cols:
            return "projection_extra_columns"
        return "projection_missing_columns"

    if "row count" in reason or "row mismatch" in reason:
        # DISTINCT missing
        if "distinct" in gold.lower() and "distinct" not in agent:
            return "distinct_missing"
        # HAVING missing
        if re.search(r"at least|more than \d|fewer than|less than \d", question):
            if "having" not in agent and "count(" in gold:
                return "having_missing"
        # Anti-join outer join
        if any(w in question for w in ("no ", "not have", "without", "never", "do not")):
            if re.search(r"\bjoin\b", agent.split("where")[0] if "where" in agent else agent):
                return "antijoin_outer_join"
        # Set logic
        if "both" in question or "intersect" in gold or "except" in gold:
            if " and " in agent.split("where")[-1] if "where" in agent else "":
                if gold_rows > 0 and agent_rows == 0:
                    return "setlogic_contradictory_and"
            return "setlogic_missing"
        # Aggregation mismatch
        if "count(" in gold and "count(" in agent and gold_rows != agent_rows:
            if "join" in gold and "join" not in agent:
                return "join_path_wrong"
        if "avg(" in gold or "sum(" in gold:
            return "aggregation_mismatch"
        if gold_rows != agent_rows:
            if gold_rows * 2 == agent_rows or agent_rows * 2 == gold_rows:
                return "duplicate_rows"
        return "unknown"

    return "unknown"


def expected_violations(bucket: str, rec: dict) -> list[str]:
    """What violation codes should have been detected for this failure bucket."""
    mapping = {
        "distinct_missing": ["distinct_missing"],
        "projection_extra_columns": ["projection_extra_columns"],
        "projection_missing_columns": ["projection_missing_requested_column"],
        "having_missing": ["having_missing", "group_by_missing"],
        "aggregation_mismatch": ["projection_extra_columns"],
        "antijoin_missing": ["antijoin_missing"],
        "antijoin_outer_join": ["antijoin_outer_join"],
        "setlogic_missing": ["setlogic_missing"],
        "setlogic_contradictory_and": ["setlogic_contradictory_and"],
        "join_path_wrong": ["antijoin_outer_join"],
    }
    return mapping.get(bucket, [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shadow_jsonl", help="Path to dev50 shadow JSONL")
    parser.add_argument("--cases", default=str(HERE / "prompts.spider.dev50.json"))
    parser.add_argument("--out-md", default=str(HERE / "reports" / "semantic_gap_report.md"))
    parser.add_argument("--out-json", default=str(HERE / "reports" / "semantic_gap_report.json"))
    args = parser.parse_args()

    with open(args.shadow_jsonl, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    with open(args.cases, encoding="utf-8") as f:
        orig = {c.get("case_id", c.get("id", "")): c for c in json.load(f)}

    total = len(records)
    passed = sum(1 for r in records if r.get("status") == "pass")
    failed = [r for r in records if r.get("status") != "pass"]

    gap_cases = []
    fn_by_bucket = Counter()
    for r in failed:
        cid = r["case_id"]
        bucket = classify_failure(r)
        violations = r.get("semantic_violations") or []
        violation_codes = {v.get("code") for v in violations if isinstance(v, dict)}
        expected = set(expected_violations(bucket, r))
        missing = expected - violation_codes
        if missing:
            fn_by_bucket[bucket] += 1

        gap_cases.append({
            "case_id": cid,
            "db_id": r.get("db_id"), "difficulty": r.get("difficulty"),
            "question": r.get("question", "")[:160],
            "gold_sql": r.get("gold_sql", "")[:200],
            "agent_sql": (r.get("agent_sql") or "")[:200],
            "status": r.get("status"),
            "execution_match": r.get("execution_match"),
            "gold_rows": r.get("gold_rows_count"),
            "agent_rows": r.get("agent_rows_count"),
            "failure_bucket": bucket,
            "semantic_violations": violations,
            "expected_violations": sorted(expected),
            "missing_violations": sorted(missing),
            "contract": (r.get("generation_metadata") or {}).get("semantic_contract", {}),
        })

    # Report
    out_dir = Path(args.out_md).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("# Semantic Gap Report\n\n")
        f.write(f"Total: {total}, Pass: {passed}, Failed: {len(failed)}\n\n")
        f.write(f"False negatives (failed cases with missing violation codes): {sum(fn_by_bucket.values())}\n\n")
        f.write("## False negative by bucket\n\n")
        for bucket, n in fn_by_bucket.most_common():
            f.write(f"- {bucket}: {n}\n")
        f.write("\n## Failed cases\n\n")
        for g in gap_cases:
            f.write(f"### {g['case_id']} ({g.get('difficulty','?')}) — {g['failure_bucket']}\n")
            f.write(f"- DB: {g.get('db_id','?')}\n")
            f.write(f"- Q: {g.get('question','')}\n")
            f.write(f"- Gold: `{g.get('gold_sql','')}`\n")
            f.write(f"- Agent: `{g.get('agent_sql','')}`\n")
            f.write(f"- Rows: gold={g.get('gold_rows')} agent={g.get('agent_rows')}\n")
            f.write(f"- Violations: {g.get('semantic_violations',[])}\n")
            f.write(f"- Expected: {g.get('expected_violations',[])}\n")
            f.write(f"- Missing: {g.get('missing_violations',[])}\n\n")

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({
            "total": total, "passed": passed, "failed": len(failed),
            "false_negatives": sum(fn_by_bucket.values()),
            "fn_by_bucket": dict(fn_by_bucket.most_common()),
            "cases": gap_cases,
        }, f, ensure_ascii=False, indent=2)

    print(f"Total: {total}, Pass: {passed}, Failed: {len(failed)}")
    print(f"False negatives: {sum(fn_by_bucket.values())}")
    print(f"FN by bucket: {dict(fn_by_bucket.most_common())}")
    print(f"Reports: {args.out_md}, {args.out_json}")


if __name__ == "__main__":
    main()
