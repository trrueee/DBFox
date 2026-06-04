# tools/sync_schema.py
"""
Trigger schema sync for a specific DataSource in the local DataBox metadata DB.
Run from project root: python tools/sync_schema.py
"""
from engine.db import SessionLocal
from engine.models import DataSource
from engine.schema_sync import sync_schema
import sys

HOST = "127.0.0.1"   # 修改为你的 MySQL host
PORT = 3307          # 修改为你的 MySQL port（导入脚本使用的端口）
DBNAME = "spider_pets_1"  # 修改为你要同步的数据库名


def main():
    db = SessionLocal()
    try:
        ds = db.query(DataSource).filter(
            DataSource.host == HOST,
            DataSource.port == PORT,
            DataSource.database_name == DBNAME
        ).first()
        if not ds:
            print("未找到匹配的数据源，请确认 host/port/database_name。")
            sys.exit(2)
        print("Found datasource id:", ds.id)
        res = sync_schema(db, str(ds.id))
        print("sync_schema result:", res)
    finally:
        db.close()


if __name__ == "__main__":
    main()
