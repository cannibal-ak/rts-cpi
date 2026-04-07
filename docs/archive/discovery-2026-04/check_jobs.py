
from sqlalchemy import create_engine, text
import os

DATABASE_URL = "postgresql://cpi:cpi_secret@localhost:5432/cpi_db"
engine = create_engine(DATABASE_URL)

def libcheck():
    with engine.connect() as conn:
        q = "SELECT id, tenant_id, source_name FROM import_job ORDER BY started_at DESC LIMIT 10"
        result = conn.execute(text(q))
        print("Check job source names:")
        for row in result:
            print(f"ID: {row.id}")
            print(f"TID: {row.tenant_id}")
            print(f"SRC: {row.source_name}")
            print("-" * 20)
        
if __name__ == "__main__":
    try:
        libcheck()
    except Exception as e:
        print(f"Error: {e}")
