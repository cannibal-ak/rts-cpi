import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "CPI_DATABASE_URL",
    "postgresql://cpi:cpi_secret@localhost:5432/cpi_db",
)

def check():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("--- Tenants ---")
        rows = conn.execute(text("SELECT id, slug, display_name FROM tenant")).fetchall()
        for r in rows:
            print(f"ID={r.id} Slug={r.slug} Name={r.display_name}")
        
        print("\n--- Import Jobs ---")
        rows = conn.execute(text("SELECT id, tenant_id, data_owner, domain FROM import_job")).fetchall()
        for r in rows:
            print(f"ID={r.id} TenantId={r.tenant_id} Owner={r.data_owner} Domain={r.domain}")

if __name__ == "__main__":
    check()
