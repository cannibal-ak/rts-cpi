import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "CPI_DATABASE_URL",
    "postgresql://cpi:cpi_secret@localhost:5432/cpi_db",
)

def list_jobs():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("--- Detailed Jobs ---")
        rows = conn.execute(text("SELECT id, source_name FROM import_job")).fetchall()
        for r in rows:
             print(f"ID={r.id} SourceName='{r.source_name}'")

if __name__ == "__main__":
    list_jobs()
