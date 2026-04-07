
from sqlalchemy import create_engine, text
import os

DATABASE_URL = "postgresql://cpi:cpi_secret@localhost:5432/cpi_db"
engine = create_engine(DATABASE_URL)

def prepare_cleanup():
    with engine.connect() as conn:
        # Find jobs
        q_jobs = "SELECT id, source_name FROM import_job WHERE source_name LIKE 'daily-ingest:JY/Airline_CPI_JY_2026-02-20.csv%'"
        result_jobs = conn.execute(text(q_jobs)).fetchall()
        
        if not result_jobs:
            print("No jobs found with that source name.")
            return

        job_ids = [str(job.id) for job in result_jobs]
        job_ids_sql = ", ".join([f"'{i}'" for i in job_ids])
        print(f"Jobs to delete: {job_ids}")

        # Find batches
        q_batches = f"SELECT id FROM import_batch WHERE import_job_id IN ({job_ids_sql})"
        result_batches = conn.execute(text(q_batches)).fetchall()
        batch_ids = [str(batch.id) for batch in result_batches]
        batch_ids_sql = ", ".join([f"'{i}'" for i in batch_ids])
        print(f"Batches to delete: {batch_ids}")

        # Now we know what to delete/update:
        # 1. Update airline_cpi_snapshot/cfl_cpi_snapshot to clear batch references or delete rows
        # 2. Delete from ingest_error
        # 3. Delete from import_batch
        # 4. Delete from import_job

        # Let's see how many rows are in snapshots
        if batch_ids:
            q_airline = f"SELECT count(*) FROM airline_cpi_snapshot WHERE import_batch_id IN ({batch_ids_sql})"
            q_cfl = f"SELECT count(*) FROM cfl_cpi_snapshot WHERE import_batch_id IN ({batch_ids_sql})"
            
            count_airline = conn.execute(text(q_airline)).scalar()
            count_cfl = conn.execute(text(q_cfl)).scalar()
            
            print(f"Snapshot rows to clear: airline={count_airline}, cfl={count_cfl}")
        else:
            print("No batches found for these jobs.")

if __name__ == "__main__":
    try:
        prepare_cleanup()
    except Exception as e:
        print(f"Error: {e}")
