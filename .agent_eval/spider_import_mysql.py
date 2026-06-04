import os
import sqlite3
import pymysql
from pathlib import Path

def map_type(sqlite_type):
    t = sqlite_type.upper().strip()
    if not t:
        return "TEXT"
    if "INT" in t:
        return "INT"
    if "CHAR" in t or "TEXT" in t or "CLOB" in t:
        if "(" in t:
            return t
        return "VARCHAR(255)"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "DOUBLE"
    if "NUM" in t or "DEC" in t:
        return "DECIMAL(10,2)"
    return "TEXT"

def import_database(db_id, sqlite_path, mysql_conn):
    print(f"Importing database {db_id} from {sqlite_path}...")
    
    # 1. Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()
    
    # Get all tables
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in sqlite_cursor.fetchall()]
    
    # Collect column types
    col_types = {}  # (table, col) -> type
    col_notnull = {}  # (table, col) -> notnull
    col_pk = {}  # (table, col) -> pk
    for table_name in tables:
        sqlite_cursor.execute(f"PRAGMA table_info(`{table_name}`);")
        for col in sqlite_cursor.fetchall():
            col_name = col[1]
            col_type = col[2]
            notnull = col[3]
            pk = col[5]
            col_types[(table_name, col_name)] = col_type
            col_notnull[(table_name, col_name)] = notnull
            col_pk[(table_name, col_name)] = pk
            
    # Collect foreign keys and update column types to match referenced column types
    for table_name in tables:
        sqlite_cursor.execute(f"PRAGMA foreign_key_list(`{table_name}`);")
        fkeys = sqlite_cursor.fetchall()
        for fk in fkeys:
            from_col = fk[3]
            ref_table = fk[2]
            ref_col = fk[4]
            ref_type = col_types.get((ref_table, ref_col))
            if ref_type:
                # Override to match referenced type
                col_types[(table_name, from_col)] = ref_type
                
    # 2. Setup MySQL DB
    mysql_cursor = mysql_conn.cursor()
    mysql_cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    mysql_cursor.execute(f"DROP DATABASE IF EXISTS `spider_{db_id}`;")
    mysql_cursor.execute(f"CREATE DATABASE `spider_{db_id}`;")
    mysql_cursor.execute(f"USE `spider_{db_id}`;")
    
    # 3. Create tables in MySQL
    for table_name in tables:
        sqlite_cursor.execute(f"PRAGMA table_info(`{table_name}`);")
        cols = sqlite_cursor.fetchall()
        
        pk_cols = []
        for col in cols:
            col_name = col[1]
            pk = col_pk[(table_name, col_name)]
            if pk:
                pk_cols.append(col_name)
                
        col_defs = []
        for col in cols:
            col_name = col[1]
            col_type = col_types[(table_name, col_name)]
            notnull = col_notnull[(table_name, col_name)]
            
            mysql_type = map_type(col_type)
            # MySQL requires all parts of primary key to be NOT NULL
            if col_name in pk_cols:
                null_def = "NOT NULL"
            else:
                null_def = "NOT NULL" if notnull else "NULL"
            
            col_defs.append(f"`{col_name}` {mysql_type} {null_def}")
                
        # Get foreign keys
        sqlite_cursor.execute(f"PRAGMA foreign_key_list(`{table_name}`);")
        fkeys = sqlite_cursor.fetchall()
        
        fk_defs = []
        for fk in fkeys:
            from_col = fk[3]
            ref_table = fk[2]
            to_col = fk[4]
            fk_defs.append(f"FOREIGN KEY (`{from_col}`) REFERENCES `{ref_table}` (`{to_col}`)")
            
        # Build CREATE TABLE DDL
        ddl_parts = col_defs.copy()
        if pk_cols:
            pk_col_escaped = [f"`{c}`" for c in pk_cols]
            ddl_parts.append(f"PRIMARY KEY ({', '.join(pk_col_escaped)})")
        ddl_parts.extend(fk_defs)
        
        ddl = f"CREATE TABLE `{table_name}` (\n  " + ",\n  ".join(ddl_parts) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        mysql_cursor.execute(ddl)
        
    # 4. Populate data
    for table_name in tables:
        sqlite_cursor.execute(f"SELECT * FROM `{table_name}`;")
        rows = sqlite_cursor.fetchall()
        if not rows:
            continue
            
        # Get columns again to build insert query
        sqlite_cursor.execute(f"PRAGMA table_info(`{table_name}`);")
        cols = sqlite_cursor.fetchall()
        col_names = [f"`{col[1]}`" for col in cols]
        
        placeholders = ", ".join(["%s"] * len(col_names))
        insert_query = f"INSERT INTO `{table_name}` ({', '.join(col_names)}) VALUES ({placeholders})"
        
        mysql_cursor.executemany(insert_query, rows)
        
    mysql_cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    mysql_conn.commit()
    mysql_cursor.close()
    sqlite_conn.close()
    print(f"Database spider_{db_id} imported successfully.\n")

def main():
    # Connect to MySQL on port 3307
    mysql_conn = pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="root"
    )
    
    # We only need 'concert_singer' and 'pets_1' for the smoke tests
    target_dbs = ["concert_singer", "pets_1"]
    eval_dir = Path(__file__).parent
    
    for db_id in target_dbs:
        sqlite_path = eval_dir / "spider" / "database" / db_id / f"{db_id}.sqlite"
        if not sqlite_path.exists():
            print(f"SQLite file not found for {db_id} at {sqlite_path}!")
            continue
        import_database(db_id, sqlite_path, mysql_conn)
        
    mysql_conn.close()

if __name__ == "__main__":
    main()
