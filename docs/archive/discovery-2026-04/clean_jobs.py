
from sqlalchemy import create_engine, text
import os
import json

DATABASE_URL = "postgresql://cpi:cpi_secret@localhost:5432/cpi_db"
engine = create_engine(DATABASE_URL)

def clean_jobs():
    with engine.begin() as conn: # This starts a transaction
        q = "SELECT id, source_name, started_at FROM import_job WHERE source_name LIKE 'daily-ingest:JY/Airline_CPI_JY_2026-02-20.csv%'"
        result = conn.execute(text(q))
        jobs = result.fetchall()
        
        if not jobs:
            print("No jobs found to delete.")
            return

        print(f"Found {len(jobs)} matches to delete.")
        ids = [str(job.id) for job in jobs]
        ids_sql = ", ".join([f"'{i}'" for i in ids])

        # Delete from batches first
        conn.execute(text(f"DELETE FROM import_batch WHERE import_job_id IN ({ids_sql})"))
        # Delete from jobs
        conn.execute(text(f"DELETE FROM import_job WHERE id IN ({ids_sql})"))
        
        print(f"Successfully deleted {len(jobs)} jobs and their batches.")

if __name__ == "__main__":
    try:
        clean_jobs()
    except Exception as e:
        print(f"Error: {e}")
