import os
import sys
import uuid
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "CPI_DATABASE_URL",
    "postgresql://cpi:cpi_secret@localhost:5432/cpi_db",
)

def check_jobs():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("--- All Import Jobs ---")
        rows = conn.execute(text("SELECT id, tenant_id, domain, status, source_name, records_total, started_at FROM import_job ORDER BY started_at DESC LIMIT 10")).fetchall()
        for r in rows:
            print(f"ID={r.id} Tenant={r.tenant_id} Domain={r.domain} Status={r.status} Source={r.source_name} Records={r.records_total} Started={r.started_at}")
        
        print("\n--- Summary Count ---")
        count = conn.execute(text("SELECT count(*) FROM import_job")).scalar()
        print(f"Total jobs in DB: {count}")

if __name__ == "__main__":
    check_jobs()
