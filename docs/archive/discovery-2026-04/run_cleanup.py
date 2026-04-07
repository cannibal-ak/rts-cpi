import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "CPI_DATABASE_URL",
    "postgresql://cpi:cpi_secret@localhost:5432/cpi_db",
)

def fix_jobs():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            print("Fixing existing import_job records...")
            rows = conn.execute(text("SELECT id, source_name FROM import_job WHERE data_owner IS NULL")).fetchall()
            fixed = 0
            for r in rows:
                sn = r.source_name or ""
                # "Local: FJL/..."
                if "Local: " in sn:
                    try:
                        code = sn.split("Local: ")[1].split("/")[0]
                        conn.execute(text("UPDATE import_job SET data_owner = :code WHERE id = :id"), {"code": code, "id": r.id})
                        print(f"  Fixed job {str(r.id)[:8]}: set data_owner = {code}")
                        fixed += 1
                    except:
                        pass
                # "daily-ingest:JY/..."
                elif "daily-ingest:" in sn:
                    try:
                        code = sn.split(":")[1].split("/")[0]
                        conn.execute(text("UPDATE import_job SET data_owner = :code WHERE id = :id"), {"code": code, "id": r.id})
                        print(f"  Fixed job {str(r.id)[:8]}: set data_owner = {code}")
                        fixed += 1
                    except:
                        pass
            print(f"Done. Fixed {fixed} records.")

if __name__ == "__main__":
    fix_jobs()
