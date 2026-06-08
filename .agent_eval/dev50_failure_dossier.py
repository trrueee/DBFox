#!/usr/bin/env python3
"""Generate dev50 failure dossier with bucketed root-cause analysis."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent


def classify_failure(rec: dict) -> str:
    gold = (rec.get("gold_sql") or "").lower()
    agent = (rec.get("agent_sql") or "").lower()
    question = (rec.get("question") or "").lower()
    reason = (rec.get("reason") or "").lower()
    gold_rows = rec.get("gold_rows_count", 0)
    agent_rows = rec.get("agent_rows_count", 0)

    # Column count mismatch
    if "column count" in reason:
        # Count columns in SELECT
        gold_cols = _count_select_columns(gold)
        agent_cols = _count_select_columns(agent)
        if "select *" in agent or agent_cols > gold_cols + 2:
            return "projection_extra_columns"
        if agent_cols < gold_cols:
            return "projection_missing_columns"
        return "projection_extra_columns"

    # Row count mismatch
    if "row count" in reason or "row mismatch" in reason:
        # DISTINCT
        if "distinct" in gold and "distinct" not in agent:
            return "distinct_missing"
        # HAVING threshold
        if _has_count_threshold(question) and "having" not in agent:
            return "having_missing"
        # Duplicate rows (gold * 2 == agent or vice versa)
        if gold_rows > 0 and (agent_rows == gold_rows * 2 or gold_rows == agent_rows * 2):
            return "duplicate_rows"
        # Anti-join outer join
        if _is_antijoin_question(question) and _has_outer_join_before_where(agent):
            return "antijoin_outer_join"
        # Anti-join missing
        if _is_antijoin_question(question):
            return "antijoin_missing"
        # Set logic
        if _is_set_logic(question, gold, agent):
            if _has_contradictory_and(agent) and gold_rows > 0 and agent_rows == 0:
                return "setlogic_contradictory_and"
            return "setlogic_missing"
        # Aggregation
        if re.search(r"avg\(|sum\(|max\(|min\(", gold) and re.search(r"avg\(|sum\(|max\(|min\(", agent):
            return "aggregation_mismatch"
        # Join path
        if "join" in gold and "join" not in agent:
            return "join_path_wrong"
        # Value literal
        if _extract_literal_values(gold) != _extract_literal_values(agent):
            return "value_literal_mismatch"
        return "unknown"
    return "unknown"


def _count_select_columns(sql: str) -> int:
    """Count SELECT projection columns (rough)."""
    m = re.search(r"select\s+(.+?)\s+from\b", sql, re.DOTALL | re.IGNORECASE)
    if not m:
        return 0
    cols = m.group(1)
    return len(cols.split(","))


def _has_count_threshold(question: str) -> bool:
    return bool(re.search(r"at least|more than|fewer than|less than", question))


def _is_antijoin_question(question: str) -> bool:
    markers = (" no ", "without", "do not have", "not have", "never ",
               "have no", "has no", "not received", "do not hire",
               "do not own", "not any")
    return any(m in question for m in markers)


def _has_outer_join_before_where(sql: str) -> bool:
    before_where = sql.split("where")[0] if "where" in sql else sql
    return "join" in before_where


def _is_set_logic(question: str, gold: str, agent: str) -> bool:
    markers = ("both ", "all of", "shared by", "common to", "intersect")
    if any(m in question for m in markers):
        return True
    if "intersect" in gold or "except" in gold:
        return True
    return False


def _has_contradictory_and(sql: str) -> bool:
    """Detect AND with mutually exclusive conditions like age<30 AND age>40."""
    return bool(re.search(r"<\s*\d+.*and.*>\s*\d+", sql) or re.search(r">\s*\d+.*and.*<\s*\d+", sql))


def _extract_literal_values(sql: str) -> set:
    """Extract string/numeric literals from SQL for comparison."""
    return set(re.findall(r"'[^']*'|\d+", sql))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", help="Path to dev50 shadow/off JSONL")
    parser.add_argument("--out-md", default=str(HERE / "reports" / "dev50_failure_dossier.md"))
    parser.add_argument("--out-json", default=str(HERE / "reports" / "dev50_failure_dossier.json"))
    parser.add_argument("--out-projection", default=str(HERE / "_tmp_projection_bucket.json"))
    parser.add_argument("--out-distinct", default=str(HERE / "_tmp_distinct_bucket.json"))
    args = parser.parse_args()

    with open(args.jsonl, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    with open(str(HERE / "prompts.spider.dev50.json"), encoding="utf-8") as f:
        orig = {c.get("case_id", c.get("id", "")): c for c in json.load(f)}

    total = len(records)
    passed = sum(1 for r in records if r.get("status") == "pass")
    failed = [r for r in records if r.get("status") != "pass"]

    buckets = Counter()
    dossier = []
    projection_cases = []
    distinct_cases = []
    for r in failed:
        cid = r["case_id"]
        bucket = classify_failure(r)
        buckets[bucket] += 1
        violations = [v.get("code") for v in (r.get("semantic_violations") or []) if isinstance(v, dict)]
        entry = {
            "case_id": cid, "db_id": r.get("db_id"), "difficulty": r.get("difficulty"),
            "question": r.get("question", ""), "gold_sql": r.get("gold_sql", ""),
            "agent_sql": (r.get("agent_sql") or ""), "safe_sql": r.get("safe_sql"),
            "reason": r.get("reason", ""),
            "gold_rows": r.get("gold_rows_count"), "agent_rows": r.get("agent_rows_count"),
            "failure_bucket": bucket, "semantic_violations": violations,
            "contract": (r.get("generation_metadata") or {}).get("semantic_contract", {}),
        }
        dossier.append(entry)

        oc = orig.get(cid, {})
        if bucket in ("projection_extra_columns", "projection_missing_columns", "projection_order_mismatch"):
            projection_cases.append({"case_id": cid, "db_id": r.get("db_id"),
                                      "question": oc.get("question", r.get("question","")),
                                      "gold_sql": oc.get("gold_sql", r.get("gold_sql","")),
                                      "difficulty": r.get("difficulty","unknown")})
        if bucket in ("distinct_missing", "duplicate_rows"):
            distinct_cases.append({"case_id": cid, "db_id": r.get("db_id"),
                                    "question": oc.get("question", r.get("question","")),
                                    "gold_sql": oc.get("gold_sql", r.get("gold_sql","")),
                                    "difficulty": r.get("difficulty","unknown")})

    # Write bucket files
    for path, data in [(args.out_projection, projection_cases), (args.out_distinct, distinct_cases)]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Write markdown report
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(f"# Dev50 Failure Dossier\n\nTotal: {total} | Pass: {passed} | Failed: {len(failed)}\n\n")
        f.write("## Bucket distribution\n\n")
        for b, n in buckets.most_common():
            f.write(f"- {b}: {n}\n")
        f.write("\n## Failed cases\n\n")
        for entry in dossier:
            f.write(f"### {entry['case_id']} ({entry.get('difficulty','?')}) — {entry['failure_bucket']}\n")
            f.write(f"- DB: {entry.get('db_id','?')}\n- Q: {entry.get('question','')}\n")
            f.write(f"- Gold: `{entry.get('gold_sql','')}`\n- Agent: `{entry.get('agent_sql','')}`\n")
            f.write(f"- Rows: gold={entry.get('gold_rows')} agent={entry.get('agent_rows')}\n")
            f.write(f"- Reason: {entry.get('reason','')}\n")
            f.write(f"- Violations: {entry.get('semantic_violations',[])}\n\n")

    # JSON
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({"total": total, "passed": passed, "failed": len(failed),
                    "buckets": dict(buckets.most_common()), "cases": dossier}, f, ensure_ascii=False, indent=2)

    print(f"Total: {total} Pass: {passed} Failed: {len(failed)}")
    print(f"Buckets: {dict(buckets.most_common())}")
    print(f"Projection cases: {len(projection_cases)}, Distinct cases: {len(distinct_cases)}")
    print(f"Reports: {out_md}, {args.out_json}")


if __name__ == "__main__":
    main()
