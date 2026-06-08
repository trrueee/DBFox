#!/usr/bin/env python3
"""Extract retry candidates from shadow dev50 results based on high-confidence violations."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent

HIGH_CONFIDENCE_CODES = frozenset({
    "having_missing", "group_by_missing", "having_count_missing",
    "antijoin_outer_join", "setlogic_contradictory_and", "projection_select_star",
})

SHADOW_ONLY_CODES = frozenset({
    "projection_extra_columns", "projection_order_mismatch",
    "projection_missing_requested_column", "distinct_missing",
    "setlogic_missing", "antijoin_missing",
})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shadow_jsonl", help="Path to shadow dev50 JSONL")
    parser.add_argument("--cases", default=str(HERE / "prompts.spider.dev50.json"),
                        help="Original cases JSON for gold_sql/difficulty")
    parser.add_argument("--out-cases", default=str(HERE / "_tmp_retry_candidates.json"),
                        help="Output candidate cases file")
    parser.add_argument("--out-report", default=str(HERE / "reports" / "semantic_candidates.md"),
                        help="Output report markdown")
    args = parser.parse_args()

    # Load shadow results
    records = {}
    with open(args.shadow_jsonl, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                records[r["case_id"]] = r

    # Load original cases
    with open(args.cases, encoding="utf-8") as f:
        orig = {c.get("case_id", c.get("id", "")): c for c in json.load(f)}

    # Find candidates with high-confidence violations
    candidates = []
    all_violations = Counter()
    for cid, rec in sorted(records.items()):
        violations = rec.get("semantic_violations") or []
        high_codes = [v.get("code") for v in violations
                       if isinstance(v, dict) and v.get("code") in HIGH_CONFIDENCE_CODES]
        shadow_codes = [v.get("code") for v in violations
                         if isinstance(v, dict) and v.get("code") in SHADOW_ONLY_CODES]
        for v in violations:
            if isinstance(v, dict):
                all_violations[v.get("code", "?")] += 1

        if high_codes:
            oc = orig.get(cid, {})
            candidates.append({
                "case_id": cid,
                "db_id": oc.get("db_id", rec.get("db_id", "")),
                "question": oc.get("question", rec.get("question", "")),
                "gold_sql": oc.get("gold_sql", ""),
                "difficulty": oc.get("difficulty", rec.get("difficulty", "unknown")),
                "baseline_status": rec.get("status"),
                "baseline_sql": (rec.get("agent_sql") or "")[:200],
                "high_confidence_violations": high_codes,
                "shadow_only_violations": shadow_codes,
            })

    # Write candidate cases
    out_cases = args.out_cases
    Path(out_cases).parent.mkdir(parents=True, exist_ok=True)
    with open(out_cases, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    # Write report
    out_rpt = args.out_report
    Path(out_rpt).parent.mkdir(parents=True, exist_ok=True)
    with open(out_rpt, "w", encoding="utf-8") as f:
        total = len(records)
        shadow_pass = sum(1 for r in records.values() if r.get("status") == "pass")
        f.write("# Semantic Candidate Report\n\n")
        f.write(f"Total shadow cases: {total}\n")
        f.write(f"Shadow pass: {shadow_pass}/{total}\n")
        f.write(f"Candidates with high-confidence violations: {len(candidates)}\n\n")

        f.write("## All violation codes\n\n")
        for code, n in all_violations.most_common():
            tag = "HIGH" if code in HIGH_CONFIDENCE_CODES else "shadow-only" if code in SHADOW_ONLY_CODES else "other"
            f.write(f"- {code}: {n} ({tag})\n")

        f.write("\n## Candidates\n\n")
        for c in candidates:
            f.write(f"### {c['case_id']} ({c.get('difficulty','?')})\n")
            f.write(f"- DB: {c.get('db_id','?')}\n")
            f.write(f"- Question: {c.get('question','')[:120]}\n")
            f.write(f"- Baseline status: {c.get('baseline_status','?')}\n")
            f.write(f"- Baseline SQL: `{c.get('baseline_sql','')}`\n")
            f.write(f"- High-conf violations: {c.get('high_confidence_violations',[])}\n")
            f.write(f"- Shadow-only violations: {c.get('shadow_only_violations',[])}\n\n")

    print(f"Candidates: {len(candidates)}/{total}")
    print(f"Shadow pass: {shadow_pass}/{total}")
    print(f"Violation codes: {dict(all_violations.most_common(10))}")
    print(f"Wrote: {out_cases}, {out_rpt}")


if __name__ == "__main__":
    main()
