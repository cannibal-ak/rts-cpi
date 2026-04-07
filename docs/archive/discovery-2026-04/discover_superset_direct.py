import sqlite3
import os
import uuid

db_path = '/app/superset_home/superset.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
print("DASHBOARDS:")
cursor.execute('SELECT id, uuid, dashboard_title FROM dashboards')
for row in cursor.fetchall():
    u = uuid.UUID(bytes=row[1])
    print(f"ID: {row[0]} | UUID: {u} | Title: {row[2]}")
    
print("\nDATASETS:")
cursor.execute("SELECT id, table_name FROM tables")
for row in cursor.fetchall():
    print(f"ID: {row[0]} | Table: {row[1]}")
conn.close()
