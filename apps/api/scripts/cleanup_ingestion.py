import os
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")

def main():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_engine(DATABASE_URL)
    
    tables_to_clean = [
        "airline_cpi_snapshot",
        "cfl_cpi_snapshot",
        "ingest_error",
        "import_batch",
        "import_job",
        "alert_event",
        "audit_event"
    ]
    
    with engine.connect() as conn:
        with conn.begin():
            print("Cleaning up ingestion tables...")
            for table in tables_to_clean:
                print(f"Truncating {table}...")
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
            print("Cleanup complete.")

if __name__ == "__main__":
    main()
