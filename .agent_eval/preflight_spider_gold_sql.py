#!/usr/bin/env python3
"""Preflight Spider gold SQL execution against imported MySQL databases."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from run_agent_eval import execute_gold_sql_for_case, load_config


def _load_cases(cases_path: Path) -> list[dict[str, Any]]:
    if not cases_path.exists():
        raise FileNotFoundError(f"Cases file not found: {cases_path}")
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Cases file must contain a JSON list.")
    return [case for case in payload if isinstance(case, dict)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight Spider gold SQL execution before running Agent eval."
    )
    parser.add_argument("--config", help="Path to eval config JSON file")
    parser.add_argument("--cases", required=True, help="Path to Spider prompt cases JSON")
    args = parser.parse_args()

    cfg = load_config(args.config)
    mysql_cfg = cfg.get("mysql", {})
    mysql_host = mysql_cfg.get("host", "127.0.0.1")
    mysql_port = int(mysql_cfg.get("port", 3307))
    mysql_user = mysql_cfg.get("user", "root")
    mysql_password = mysql_cfg.get("password", "root")

    cases = _load_cases(Path(args.cases))
    failures: list[dict[str, Any]] = []
    canonicalized_count = 0

    print("=" * 65)
    print("     Spider Gold SQL MySQL Preflight")
    print("=" * 65)
    print(f"  Cases: {len(cases)}")
    print(f"  MySQL: {mysql_user}@{mysql_host}:{mysql_port}")
    print("=" * 65)

    for idx, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or case.get("id") or f"case_{idx}")
        db_id = str(case.get("db_id") or "")
        gold_sql = str(case.get("gold_sql") or case.get("query") or "")
        mysql_db = f"spider_{db_id}"

        if not db_id or not gold_sql:
            failures.append(
                {
                    "case_id": case_id,
                    "db_id": db_id,
                    "gold_sql_original": gold_sql,
                    "gold_sql_canonical": gold_sql,
                    "error": "missing_db_id_or_gold_sql",
                    "warnings": [],
                }
            )
            print(f"[{idx}/{len(cases)}] {case_id}: FAIL missing_db_id_or_gold_sql")
            continue

        result = execute_gold_sql_for_case(
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_password=mysql_password,
            mysql_db=mysql_db,
            db_id=db_id,
            gold_sql=gold_sql,
        )
        if result.get("gold_sql_was_canonicalized"):
            canonicalized_count += 1

        if result.get("gold_error"):
            failures.append(
                {
                    "case_id": case_id,
                    "db_id": db_id,
                    "gold_sql_original": result.get("gold_sql_original"),
                    "gold_sql_canonical": result.get("gold_sql_canonical"),
                    "error": result.get("gold_error"),
                    "warnings": result.get("gold_sql_canonicalization_warnings") or [],
                }
            )
            print(f"[{idx}/{len(cases)}] {case_id}: FAIL {result.get('gold_error')}")
            print(f"  original:  {result.get('gold_sql_original')}")
            print(f"  canonical: {result.get('gold_sql_canonical')}")
        else:
            row_count = len(result.get("gold_rows") or [])
            print(f"[{idx}/{len(cases)}] {case_id}: OK rows={row_count}")

    failures_by_db_id = Counter(str(item["db_id"]) for item in failures)
    summary = {
        "total": len(cases),
        "gold_exec_ok": len(cases) - len(failures),
        "gold_exec_failed": len(failures),
        "gold_sql_canonicalized_count": canonicalized_count,
        "failures_by_db_id": dict(sorted(failures_by_db_id.items())),
        "failed_cases": failures,
    }

    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
