import os
import csv
import uuid
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")
TENANT_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")

def main():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with open("/app/data/JY/JY_200226.csv", 'r') as f:
            reader = csv.DictReader(f)
            row = next(reader)
            print(f"Row data: {row}")
            try:
                conn.execute(text("""
                    INSERT INTO import_job (id, tenant_id, domain, status, source_name, timeline)
                    VALUES (:id, :tid, 'airline', 'committed', 'test', '[]'::jsonb)
                """), {"id": uuid.uuid4(), "tid": TENANT_ID})
                print("Inserted Job")
                conn.commit()
                print("Commit Jobed")
            except Exception as e:
                print(f"Job failed: {e}")
                return

if __name__ == "__main__":
    main()
