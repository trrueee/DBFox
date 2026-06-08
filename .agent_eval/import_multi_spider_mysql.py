#!/usr/bin/env python3
"""Import multiple Spider SQLite databases into the Spider MySQL Docker container.

Usage:
    python .agent_eval/import_multi_spider_mysql.py --min-dbs 8
    python .agent_eval/import_multi_spider_mysql.py --dbs car_1,flight_2,network_1
"""

from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Any

import pymysql

from spider_import_mysql import import_database

HERE = Path(__file__).resolve().parent
SPIDER_DB_DIR = HERE / "spider" / "database"
IMPORT_REPORT = HERE / "import_report.json"

# Spider DBs recommended for multi-db coverage (small/medium, common in dev.json)
PRIORITY_DBS = [
    "concert_singer",
    "pets_1",
    "car_1",
    "flight_2",
    "employee_hire_evaluation",
    "museum_visit",
    "network_1",
    "orchestra",
    "singer",
    "voter_1",
    "world_1",
    "course_teach",
    "tvshow",
    "student_transcripts_tracking",
    "battle_death",
    "poker_player",
    "wta_1",
    "cre_Doc_Template_Mgt",
]


def available_spider_dbs() -> list[str]:
    """Return list of db_ids that have SQLite databases on disk."""
    if not SPIDER_DB_DIR.exists():
        return []
    dbs = []
    for p in sorted(SPIDER_DB_DIR.iterdir()):
        if p.is_dir() and list(p.glob("*.sqlite")):
            dbs.append(p.name)
    return dbs


def imported_mysql_dbs(mysql_conn) -> list[str]:
    """Return list of spider_* databases already in MySQL."""
    cursor = mysql_conn.cursor()
    cursor.execute("SHOW DATABASES")
    dbs = [row[0].replace("spider_", "") for row in cursor.fetchall()
           if row[0].startswith("spider_")]
    cursor.close()
    return dbs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-dbs", type=int, default=8,
                        help="Minimum number of Spider DBs to import")
    parser.add_argument("--dbs", default=None,
                        help="Comma-separated list of db_ids to import")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="root")
    args = parser.parse_args()

    available = available_spider_dbs()
    print(f"Available Spider SQLite DBs on disk: {len(available)}")

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, autocommit=True)
    imported = imported_mysql_dbs(conn)
    print(f"Already in MySQL: {len(imported)} ({imported})")

    # Determine which DBs to import
    if args.dbs:
        targets = [d.strip() for d in args.dbs.split(",")]
    else:
        targets = [d for d in PRIORITY_DBS if d in available and d not in imported]
        targets = targets[:max(0, args.min_dbs - len(imported))]

    if not targets:
        print(f"No DBs need importing. Already have {len(imported)}.")
        report = {"ok": True, "imported_dbs": imported, "total": len(imported)}
        with open(IMPORT_REPORT, "w") as f:
            json.dump(report, f, indent=2)
        conn.close()
        return

    print(f"Will import {len(targets)} DBs: {targets}")

    report_data: list[dict[str, Any]] = []
    for db_id in targets:
        sqlite_paths = list((SPIDER_DB_DIR / db_id).glob("*.sqlite"))
        if not sqlite_paths:
            print(f"  SKIP {db_id}: no SQLite file found")
            report_data.append({"db_id": db_id, "error": "no_sqlite_file"})
            continue
        sqlite_path = str(sqlite_paths[0])
        mysql_db = f"spider_{db_id}"
        try:
            import_database(db_id, sqlite_path, conn)
            # Count rows
            cursor = conn.cursor()
            cursor.execute(f"USE `{mysql_db}`")
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            row_counts = {}
            for t in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{t}`")
                row_counts[t] = cursor.fetchone()[0]
            cursor.close()
            report_data.append({
                "db_id": db_id,
                "mysql_database": mysql_db,
                "table_count": len(tables),
                "tables": tables,
                "row_counts": row_counts,
                "ok": True,
            })
            print(f"  OK {db_id}: {len(tables)} tables, rows={row_counts}")
        except Exception as exc:
            print(f"  FAIL {db_id}: {exc}")
            report_data.append({"db_id": db_id, "error": str(exc)})

    imported = imported_mysql_dbs(conn)
    conn.close()

    report = {
        "ok": len(imported) >= args.min_dbs,
        "imported_dbs": imported,
        "total": len(imported),
        "details": report_data,
    }
    with open(IMPORT_REPORT, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nDone. {len(imported)} DBs imported. Report: {IMPORT_REPORT}")
    if len(imported) < args.min_dbs:
        print(f"WARNING: Only {len(imported)} DBs, need at least {args.min_dbs}")
        sys.exit(1)


if __name__ == "__main__":
    main()
