#!/usr/bin/env python3
"""Build a 50-case Spider dev subset with diverse SQL structures, difficulties,
and multi-database coverage.

Requirements:
- >= 50 cases
- >= 8 distinct db_ids
- >= 10 easy, >= 15 medium, >= 15 hard, >= 10 extra/complex
- Excludes smoke-validated questions

Usage:
    python .agent_eval/build_spider_dev_subset.py --min-dbs 8
"""

from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from collections import Counter

import pymysql

HERE = Path(__file__).resolve().parent
DEV = HERE / "spider" / "dev.json"
OUT = HERE / "prompts.spider.dev50.json"

SMOKE_QUESTIONS = {
    "How many singers do we have?",
    "Show name, country, age for all singers ordered by age from the oldest to the youngest.",
    "Show all countries and the number of singers in each country.",
    "List all song names by singers above the average age.",
    "Find the number of pets whose weight is heavier than 10.",
    "Find the maximum weight for each type of pet. List the maximum weight and pet type.",
    "Find number of pets owned by students who are older than 20.",
    "Find the number of dog pets that are raised by female students (with sex F).",
    "Find the major and age of students who do not have a cat pet.",
    "Find the first name of students who have both cat and dog pets.",
}


def classify_difficulty(sql: str, question: str) -> str:
    upper = sql.upper()
    ql = (question or "").lower()
    if "INTERSECT" in upper or "EXCEPT" in upper:
        return "extra"
    if upper.count("SELECT") >= 4:
        return "extra"
    if any(w in ql for w in ("both ", "all of", "two different", "at least two")):
        if upper.count("JOIN") >= 2:
            return "extra"
    anti = ("NOT EXISTS", "NOT IN")
    if any(m in upper for m in anti) and upper.count("JOIN") >= 2:
        return "extra"
    if upper.count("SELECT") >= 3:
        return "hard"
    if "HAVING" in upper:
        return "hard"
    if upper.count("JOIN") >= 3:
        return "hard"
    if upper.count("JOIN") >= 2 and ("GROUP BY" in upper or "COUNT(" in upper):
        return "hard"
    if any(m in upper for m in anti):
        return "hard"
    if "JOIN" in upper and ("GROUP BY" in upper or "COUNT(" in upper):
        return "medium"
    if upper.count("JOIN") >= 1 and upper.count("SELECT") >= 2:
        return "medium"
    if "GROUP BY" in upper:
        return "medium"
    if upper.count("JOIN") == 1:
        return "medium"
    return "easy"


def imported_dbs() -> list[str]:
    conn = pymysql.connect(host="127.0.0.1", port=3307, user="root", password="root")
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    dbs = [row[0].replace("spider_", "") for row in cursor.fetchall()
           if row[0].startswith("spider_")]
    conn.close()
    return dbs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-dbs", type=int, default=8)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    # Check available DBs
    available = imported_dbs()
    print(f"Imported Spider MySQL DBs: {len(available)}")
    if len(available) < args.min_dbs:
        print(f"ERROR: Only {len(available)} imported DBs available; need at least {args.min_dbs}.")
        print("Run: python .agent_eval/import_multi_spider_mysql.py --min-dbs 8")
        sys.exit(1)

    with open(DEV, encoding="utf-8") as f:
        all_cases = json.load(f)
    print(f"Loaded {len(all_cases)} cases from dev.json")

    # Filter to imported DBs only
    candidates = [c for c in all_cases if c.get("db_id", "") in available]
    print(f"Available DB filter: {len(candidates)}")

    # Remove smoke questions
    candidates = [c for c in candidates if c.get("question", "").strip() not in SMOKE_QUESTIONS]
    print(f"After smoke filter: {len(candidates)}")

    if len(candidates) < 50:
        print(f"ERROR: Only {len(candidates)} candidates after filtering; need at least 50.")
        print("Import more Spider databases: python .agent_eval/import_multi_spider_mysql.py --min-dbs 8")
        sys.exit(1)

    # Classify and tag
    for c in candidates:
        sql_text = c.get("query") or ""
        if isinstance(sql_text, dict):
            sql_text = ""
        c["difficulty"] = classify_difficulty(sql_text, c.get("question", ""))

    # Deduplicate by question
    seen = set()
    deduped = []
    for c in candidates:
        q = c.get("question", "").strip()
        if q not in seen:
            seen.add(q)
            deduped.append(c)
    candidates = deduped
    print(f"After dedup: {len(candidates)}")

    # Selection: ensure DB and difficulty coverage
    diff_quota = {"easy": 10, "medium": 15, "hard": 15, "extra": 10}

    # Phase 1: fill quotas with DB diversity
    selected = []
    db_used = Counter()
    for diff, quota in diff_quota.items():
        pool = sorted(
            [c for c in candidates if c["difficulty"] == diff],
            key=lambda c: db_used.get(c["db_id"], 0)
        )
        for c in pool:
            if len([s for s in selected if s["difficulty"] == diff]) >= quota:
                break
            if c in selected:
                continue
            selected.append(c)
            db_used[c["db_id"]] += 1

    # Phase 2: fill remaining to 50, preferring under-represented DBs
    remaining = [c for c in candidates if c not in selected]
    remaining.sort(key=lambda c: db_used.get(c["db_id"], 0))
    while len(selected) < 50 and remaining:
        c = remaining.pop(0)
        selected.append(c)
        db_used[c["db_id"]] += 1

    # Phase 3: ensure at least min_dbs DBs — swap from over-represented DBs
    while len(db_used) < args.min_dbs:
        missing = [db for db in available if db not in db_used]
        if not missing:
            break
        target_db = missing[0]
        overrepresented = db_used.most_common(1)[0][0]
        to_swap = next((c for c in selected if c["db_id"] == overrepresented and c["difficulty"] in ("easy", "medium")), None)
        replacement = next((c for c in candidates if c["db_id"] == target_db and c not in selected), None)
        if to_swap and replacement:
            selected.remove(to_swap)
            db_used[overrepresented] -= 1
            selected.append(replacement)
            db_used[target_db] += 1
        else:
            break

    # Build output
    output = []
    for c in selected:
        sql_text = c.get("query") or ""
        if isinstance(sql_text, dict):
            sql_text = ""
        output.append({
            "case_id": f"spider-dev-{len(output)+1:03d}",
            "db_id": c["db_id"],
            "question": c["question"],
            "gold_sql": sql_text,
            "difficulty": c.get("difficulty", "easy"),
        })

    out_path = Path(args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(output)} cases to {out_path}")

    # Report
    diffs = Counter(c["difficulty"] for c in output)
    dbs = Counter(c["db_id"] for c in output)
    print(f"\nDifficulty: {dict(diffs)}")
    print(f"DBs ({len(dbs)}): {dict(dbs)}")

    ok = (len(output) >= 50 and len(dbs) >= args.min_dbs
          and diffs.get("easy", 0) >= 10 and diffs.get("medium", 0) >= 15
          and diffs.get("hard", 0) >= 15 and diffs.get("extra", 0) >= 10)
    if not ok:
        print("WARNING: Quotas not fully met. Consider importing more DBs.")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
