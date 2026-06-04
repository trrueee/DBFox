"""Standalone report generator – reads a JSONL output file and produces a Markdown summary.

Usage:
    python .agent_eval/report.py \
        --jsonl .agent_eval/outputs/spider_smoke.jsonl \
        --out .agent_eval/outputs/spider_smoke.summary.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_records(jsonl_path: Path) -> list[dict]:
    records = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def difficulty_order(d: str) -> int:
    order = {"simple": 0, "medium": 1, "hard": 2, "extra hard": 3}
    return order.get(d.lower(), 99)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Markdown eval report from JSONL")
    parser.add_argument("--jsonl", required=True, help="Path to the JSONL output file")
    parser.add_argument("--out", required=True, help="Path for the generated Markdown report")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        raise SystemExit(f"JSONL file not found: {jsonl_path}")

    records = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    total = len(records)
    passed = sum(1 for r in records if r.get("execution_match") is True)
    completed = sum(1 for r in records if r.get("status") == "completed")
    failed = [r for r in records if not r.get("success")]
    has_safety = sum(1 for r in records if "safety" in (r.get("artifacts") or []))
    has_answer = sum(1 for r in records if r.get("answer"))

    # Group by difficulty
    by_difficulty: dict[str, list] = {}
    for r in records:
        d = r.get("difficulty", "unknown")
        by_difficulty.setdefault(d, []).append(r)

    lines = []
    lines.append("# DataBox Agent Spider Eval Report\n")
    lines.append(f"**Generated from**: `{jsonl_path.name}`\n")

    lines.append("## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("| :--- | :--- |")
    lines.append(f"| **Total cases** | {total} |")
    lines.append(f"| **Completed** | {completed}/{total} |")
    lines.append(f"| **Execution match** | {passed}/{total} ({_pct(passed, total)}) |")
    lines.append(f"| **Failed responses** | {len(failed)}/{total} |")
    lines.append(f"| **Has safety artifact** | {has_safety}/{total} |")
    lines.append(f"| **Has answer** | {has_answer}/{total} |")
    lines.append(f"| **Avg latency** | {_avg_latency(records)} |")
    lines.append("")

    if by_difficulty:
        lines.append("## By Difficulty\n")
        lines.append("| Difficulty | Count | Matched | Rate |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for d in sorted(by_difficulty, key=difficulty_order):
            group = by_difficulty[d]
            m = sum(1 for r in group if r.get("execution_match") is True)
            lines.append(f"| {d} | {len(group)} | {m} | {_pct(m, len(group))} |")
        lines.append("")

    # Score distribution
    scores = [r.get("quality", {}).get("score", 0) for r in records]
    lines.append("## Score Distribution\n")
    lines.append("| Score | Count |")
    lines.append("| :--- | :--- |")
    for s in range(6):
        cnt = scores.count(s)
        if cnt:
            label = {5: "Perfect", 4: "Good", 3: "Adequate", 2: "Weak", 1: "Poor", 0: "Failed"}.get(s, "")
            lines.append(f"| {s}/5 {label} | {cnt} |")
    lines.append("")

    # Strong / weak cases
    strong = sorted(
        [r for r in records if r.get("quality", {}).get("score", 0) >= 4],
        key=lambda r: r.get("quality", {}).get("score", 0),
        reverse=True,
    )
    weak = sorted(
        [r for r in records if r.get("quality", {}).get("score", 0) <= 2],
        key=lambda r: r.get("quality", {}).get("score", 0),
    )

    if strong:
        lines.append("## Strong Cases\n")
        for r in strong:
            lines.append(f"- **{r['case_id']}** ({r.get('difficulty', '?')}): {r['question'][:120]} — score {r.get('quality', {}).get('score', 0)}/5")
        lines.append("")

    if weak:
        lines.append("## Weak Cases\n")
        for r in weak:
            lines.append(f"- **{r['case_id']}** ({r.get('difficulty', '?')}): {r['question'][:120]} — score {r.get('quality', {}).get('score', 0)}/5")
            if r.get("sql_error"):
                lines.append(f"  - SQL Error: `{r['sql_error']}`")
            if r.get("reason"):
                lines.append(f"  - Reason: {r['reason']}")
        lines.append("")

    # Case details
    lines.append("## Case Details\n")
    for r in records:
        match_icon = "✅" if r.get("execution_match") else "❌"
        score = r.get("quality", {}).get("score", 0)
        lines.append(f"### {match_icon} {r['case_id']} / {r['db_id']} ({r.get('difficulty', '?')}) — {score}/5\n")
        lines.append(f"**Question**: {r['question']}\n")
        lines.append(f"**Status**: `{r.get('status')}` / success={r.get('success')}")
        lines.append(f"**Execution match**: {r.get('execution_match')}")
        lines.append(f"**Latency**: {r.get('latency_sec', '?')}s\n")

        lines.append("**Gold SQL**")
        lines.append("```sql")
        lines.append(r.get("gold_sql") or "-- none")
        lines.append("```\n")

        lines.append("**Agent Safe SQL**")
        lines.append("```sql")
        lines.append(r.get("safe_sql") or r.get("agent_sql") or "-- none")
        lines.append("```\n")

        steps = r.get("steps") or []
        artifacts = r.get("artifacts") or []
        if steps:
            lines.append(f"**Steps**: {', '.join(steps)}")
        if artifacts:
            lines.append(f"**Artifacts**: {', '.join(artifacts)}")
        lines.append("")

        if r.get("answer"):
            lines.append(f"**Answer**: {str(r['answer'])[:500]}\n")

        if r.get("sql_error"):
            lines.append(f"**SQL Error**: `{r['sql_error']}`\n")

        if r.get("approval"):
            lines.append(f"**Approval**: `{json.dumps(r['approval'], default=str)[:300]}`\n")

        lines.append("---\n")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {args.out}")


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{part / total * 100:.1f}%"


def _avg_latency(records: list[dict]) -> str:
    lats = [r.get("latency_sec") for r in records if r.get("latency_sec")]
    if not lats:
        return "N/A"
    return f"{sum(lats) / len(lats):.1f}s"


if __name__ == "__main__":
    main()
