import sqlite3
import uuid
import datetime

db_path = '/app/superset_home/superset.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def enable_embedding():
    # 1. Ensure table info
    cursor.execute("PRAGMA table_info(embedded_dashboards)")
    columns = [c[1] for c in cursor.fetchall()]
    print(f"Columns in embedded_dashboards: {columns}")

    # 2. Get dashboards
    cursor.execute("SELECT id, dashboard_title FROM dashboards")
    dashboards = cursor.fetchall()

    for did, title in dashboards:
        cursor.execute("SELECT uuid FROM embedded_dashboards WHERE dashboard_id = ?", (did,))
        existing = cursor.fetchone()
        
        if existing:
            # Already exists, just print it
            # Superset stores UUIDs as bytes in SQLite sometimes
            u = existing[0]
            if isinstance(u, bytes):
                import uuid as uuid_lib
                u = str(uuid_lib.UUID(bytes=u))
            print(f"Dashboard '{title}' (ID: {did}) already has Embed UUID: {u}")
        else:
            # Create new embed
            new_uuid_str = str(uuid.uuid4())
            # Convert to bytes if the 'uuid' column in other tables is bytes
            # But let's check 'dashboards' table uuid type first
            cursor.execute("SELECT uuid FROM dashboards LIMIT 1")
            sample_uuid = cursor.fetchone()[0]
            
            target_uuid = new_uuid_str
            if isinstance(sample_uuid, bytes):
                import uuid as uuid_lib
                target_uuid = uuid_lib.UUID(new_uuid_str).bytes
            
            now = datetime.datetime.utcnow()
            
            # Simple insert - adjusting for column names found in standard Superset schema
            # id, uuid, dashboard_id, allow_domain_list, created_on, changed_on, created_by_fk, changed_by_fk
            try:
                # We'll try a minimal set and let SQLite defaults/nulls handle the rest if possible
                # Or we can specify them all.
                cursor.execute('''
                    INSERT INTO embedded_dashboards (uuid, dashboard_id, allow_domain_list, created_on, changed_on)
                    VALUES (?, ?, ?, ?, ?)
                ''', (target_uuid, did, 'localhost', now, now))
                print(f"Enabled embedding for '{title}' (ID: {did}) with UUID: {new_uuid_str}")
            except Exception as e:
                print(f"Failed to enable embedding for {did}: {e}")

    conn.commit()

if __name__ == "__main__":
    enable_embedding()
    conn.close()
