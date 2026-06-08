#!/usr/bin/env python3
"""Generate semantic ablation report comparing off / shadow / retry eval runs."""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent


def load(path: str) -> dict[str, dict]:
    records = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            r = json.loads(line)
            cid = r.get("case_id", "")
            if cid: records[cid] = r
    return records


def main():
    if len(sys.argv) < 4:
        print("Usage: python semantic_ablation_report.py off.jsonl shadow.jsonl retry.jsonl")
        sys.exit(1)

    off = load(sys.argv[1])
    shadow = load(sys.argv[2])
    retry = load(sys.argv[3])

    all_ids = sorted(set(off) | set(shadow) | set(retry))
    if not all_ids:
        print("No records found.")
        sys.exit(1)

    # Summary
    off_pass = sum(1 for cid in all_ids if off.get(cid, {}).get("status") == "pass")
    shadow_pass = sum(1 for cid in all_ids if shadow.get(cid, {}).get("status") == "pass")
    retry_pass = sum(1 for cid in all_ids if retry.get(cid, {}).get("status") == "pass")

    # Shadow vs off diff (should be 0)
    sql_diffs = 0
    for cid in all_ids:
        off_sql = off.get(cid, {}).get("agent_sql") or ""
        shadow_sql = shadow.get(cid, {}).get("agent_sql") or ""
        if off_sql != shadow_sql:
            sql_diffs += 1

    # Retry analysis
    improved = []
    worsened = []
    retry_accepted = 0
    retry_attempted = 0
    for cid in all_ids:
        o = off.get(cid, {})
        r = retry.get(cid, {})
        if r.get("semantic_retry_accepted"):
            retry_accepted += 1
        if r.get("semantic_retry_attempted"):
            retry_attempted += 1
        o_pass = o.get("status") == "pass"
        r_pass = r.get("status") == "pass"
        if o_pass and not r_pass:
            worsened.append(cid)
        if not o_pass and r_pass:
            improved.append(cid)

    # Violation counts
    violations_off = Counter()
    violations_shadow = Counter()
    violations_retry = Counter()
    for cid in all_ids:
        for v in off.get(cid, {}).get("semantic_violations") or []:
            if isinstance(v, dict): violations_off[v.get("code","?")] += 1
        for v in shadow.get(cid, {}).get("semantic_violations") or []:
            if isinstance(v, dict): violations_shadow[v.get("code","?")] += 1
        for v in retry.get(cid, {}).get("semantic_violations") or []:
            if isinstance(v, dict): violations_retry[v.get("code","?")] += 1

    # False positives: violations on PASSED cases
    fp_off = Counter()
    for cid in all_ids:
        if off.get(cid, {}).get("status") == "pass":
            for v in off.get(cid, {}).get("semantic_violations") or []:
                if isinstance(v, dict): fp_off[v.get("code","?")] += 1

    total = len(all_ids)
    report = {
        "summary": {
            "total_cases": total,
            "off_pass": off_pass,
            "shadow_pass": shadow_pass,
            "retry_pass": retry_pass,
            "off_pass_rate": round(off_pass / total * 100, 1),
            "shadow_pass_rate": round(shadow_pass / total * 100, 1),
            "retry_pass_rate": round(retry_pass / total * 100, 1),
            "off_vs_shadow_sql_diffs": sql_diffs,
            "retry_improved": len(improved),
            "retry_worsened": len(worsened),
            "retry_accepted": retry_accepted,
            "retry_attempted": retry_attempted,
            "retry_improved_cases": improved,
            "retry_worsened_cases": worsened,
        },
        "violation_counts": {
            "off": dict(violations_off.most_common(20)),
            "shadow": dict(violations_shadow.most_common(20)),
            "retry": dict(violations_retry.most_common(20)),
        },
        "false_positive_violations_on_passed": dict(fp_off.most_common(10)),
        "cases": [],
    }

    for cid in all_ids:
        report["cases"].append({
            "case_id": cid,
            "db_id": off.get(cid, shadow.get(cid, retry.get(cid, {}))).get("db_id", ""),
            "difficulty": off.get(cid, shadow.get(cid, retry.get(cid, {}))).get("difficulty", ""),
            "question": (off.get(cid, shadow.get(cid, retry.get(cid, {}))).get("question") or "")[:120],
            "off_status": off.get(cid, {}).get("status", ""),
            "shadow_status": shadow.get(cid, {}).get("status", ""),
            "retry_status": retry.get(cid, {}).get("status", ""),
            "off_sql": (off.get(cid, {}).get("agent_sql") or "")[:200],
            "retry_sql": (retry.get(cid, {}).get("agent_sql") or "")[:200],
            "semantic_violations_off": off.get(cid, {}).get("semantic_violations", []),
            "semantic_violations_retry": retry.get(cid, {}).get("semantic_violations", []),
            "retry_accepted": retry.get(cid, {}).get("semantic_retry_accepted", False),
            "retry_attempted": retry.get(cid, {}).get("semantic_retry_attempted", False),
        })

    out_json = HERE / "reports" / "semantic_ablation.json"
    out_md = HERE / "reports" / "semantic_ablation.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(out_md, "w", encoding="utf-8") as f:
        s = report["summary"]
        f.write("# Semantic Ablation Report\n\n")
        f.write(f"Total cases: {total}\n\n")
        f.write("| Mode | Pass | Rate |\n|------|------|------|\n")
        f.write(f"| off | {s['off_pass']} | {s['off_pass_rate']}% |\n")
        f.write(f"| shadow | {s['shadow_pass']} | {s['shadow_pass_rate']}% |\n")
        f.write(f"| retry | {s['retry_pass']} | {s['retry_pass_rate']}% |\n\n")
        f.write(f"- off vs shadow SQL diffs: {s['off_vs_shadow_sql_diffs']} (must be 0)\n")
        f.write(f"- retry accepted: {s['retry_accepted']}\n")
        f.write(f"- retry attempted: {s['retry_attempted']}\n")
        f.write(f"- retry improved: {len(improved)}\n")
        f.write(f"- retry worsened: {len(worsened)}\n\n")
        if s["retry_worsened_cases"]:
            f.write(f"Worsened: {s['retry_worsened_cases']}\n")
        if s["retry_improved_cases"]:
            f.write(f"Improved: {s['retry_improved_cases']}\n")

    print(f"Report written: {out_json}, {out_md}")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
