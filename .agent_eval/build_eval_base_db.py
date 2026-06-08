#!/usr/bin/env python3
"""Build a seeded eval base DB with all Spider datasources and schema metadata.

Usage:
    python .agent_eval/build_eval_base_db.py --cases .agent_eval/prompts.spider.dev50.json --out .agent_eval/runtime/base_seeded.db
"""

from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(HERE / "prompts.spider.dev50.json"))
    parser.add_argument("--out", default=str(HERE / "runtime" / "base_seeded.db"))
    parser.add_argument("--source-db", default=str(PROJECT / "databox_local.db"))
    args = parser.parse_args()

    out_path = Path(args.out)
    source_path = Path(args.source_db)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Copy source DB
    if not source_path.exists():
        print(f"ERROR: Source DB not found: {source_path}")
        sys.exit(1)
    shutil.copy2(source_path, out_path)
    print(f"Copied {source_path} -> {out_path}")

    # Step 2: Point DATABOX_DATABASE_URL to the target DB for this process
    os.environ["DATABOX_DATABASE_URL"] = f"sqlite:///{out_path.resolve().as_posix()}"

    from engine.db import SessionLocal, engine
    from engine.models import DataSource, SchemaTable
    from engine.schema_sync import sync_schema

    db = SessionLocal()

    # Step 3: Read dev50 cases, collect needed db_ids
    with open(args.cases, encoding="utf-8") as f:
        cases = json.load(f)
    needed_dbs = sorted(set(c["db_id"] for c in cases))
    print(f"Dev50 needs {len(needed_dbs)} db_ids: {needed_dbs}")

    # Step 4: Ensure datasources exist
    for db_id in needed_dbs:
        ds_id = f"ds-spider-{db_id.replace('_', '-')}"
        mysql_db = f"spider_{db_id}"
        existing = db.query(DataSource).filter(DataSource.id == ds_id).first()
        if existing:
            print(f"  {ds_id}: exists (host={existing.host} db={existing.database_name})")
            # Resync schema to be safe
            try:
                sync_schema(db, ds_id)
                table_count = db.query(SchemaTable).filter(
                    SchemaTable.data_source_id == ds_id).count()
                print(f"    schema synced: {table_count} tables")
            except Exception as e:
                print(f"    schema sync FAILED: {e}")
        else:
            # Need to create datasource from template
            template = db.query(DataSource).filter(
                DataSource.id.like("ds-spider-%")).first()
            if not template:
                print(f"  {ds_id}: MISSING and no template — SKIP")
                continue
            ds = DataSource(
                id=ds_id,
                name=f"Spider {db_id}",
                host="127.0.0.1", port=3307,
                database_name=mysql_db,
                username="root",
                password_ciphertext=template.password_ciphertext,
                password_nonce=template.password_nonce,
                db_type="mysql",
            )
            db.add(ds)
            db.commit()
            try:
                sync_schema(db, ds_id)
                table_count = db.query(SchemaTable).filter(
                    SchemaTable.data_source_id == ds_id).count()
                print(f"  {ds_id}: CREATED, schema: {table_count} tables")
            except Exception as e:
                print(f"  {ds_id}: CREATED, schema sync FAILED: {e}")

    db.close()
    engine.dispose()
    print(f"\nDone. Seeded DB: {out_path}")


if __name__ == "__main__":
    main()
