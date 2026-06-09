import sqlite3
from engine.tests.conftest import SPIDER_SQLITE_DBS

path = SPIDER_SQLITE_DBS["concert_singer"]
conn = sqlite3.connect(path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", cursor.fetchall())
conn.close()
