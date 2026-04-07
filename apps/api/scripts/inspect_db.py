import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")

def main():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        for table in ["import_job", "import_batch", "airline_cpi_snapshot", "cfl_cpi_snapshot"]:
            print(f"--- Columns for {table} ---")
            res = conn.execute(text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'"))
            for col in res:
                print(f"  {col[0]}: {col[1]}")

if __name__ == "__main__":
    main()
