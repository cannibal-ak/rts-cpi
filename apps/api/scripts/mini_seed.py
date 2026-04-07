import os
import csv
import uuid
import sys
import traceback
from datetime import datetime
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")
TENANT_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")

def parse_date(date_str):
    if not date_str: return None
    for fmt in ("%d%b%y", "%d%B%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except:
            continue
    return None

def main():
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            # 1. Job
            job_id = uuid.uuid4()
            conn.execute(text("INSERT INTO import_job (id, tenant_id, domain, status, source_name) VALUES (:id, :tid, 'airline', 'committed', 'Local Test')"), {"id": job_id, "tid": TENANT_ID})
            
            # 2. Batch
            batch_id = uuid.uuid4()
            conn.execute(text("INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq) VALUES (:id, :tid, :job_id, 1)"), {"id": batch_id, "tid": TENANT_ID, "job_id": job_id})
            
            # 3. CSV
            with open("/app/data/JY/JY_200226.csv", 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row = next(reader)
                
                conn.execute(text("""
                    INSERT INTO airline_cpi_snapshot (
                        id, tenant_id, import_batch_id, cap_date, cap_time, trip_type,
                        ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date, ref_cab_code,
                        ref_tot_fare, ref_base_fare, ref_tax, ref_yq, ref_seats,
                        comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
                        comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats,
                        pos, poa
                    ) VALUES (
                        :id, :tid, :bid, :cd, :ct, :tt,
                        :ra, :rf, :ro, :rd, :rdd, :rcc,
                        :rtf, :rbf, :rtax, :ryq, :rs,
                        :ca, :cf, :co, :cdst, :cdd, :ccc,
                        :ctf, :cbf, :ctax, :cyq, :cs,
                        'US', 'US'
                    )
                """), {
                    "id": uuid.uuid4(), "tid": TENANT_ID, "bid": batch_id,
                    "cd": parse_date(row.get('CapDate')),
                    "ct": datetime.strptime(row.get('CapTime'), "%H:%M").time(),
                    "tt": "RT",
                    "ra": row.get('RefAL'), "rf": row.get('RefFltNum'), "ro": row.get('RefOrg'), "rd": row.get('RefDst'),
                    "rdd": parse_date(row.get('RefDepDate')), "rcc": row.get('RefCabCode', 'Y'),
                    "rtf": float(row.get('RefTotFare') or 0), "rbf": float(row.get('RefBaseFare') or 0),
                    "rtax": float(row.get('RefTax') or 0), "ryq": float(row.get('RefYQ') or 0), "rs": int(row.get('RefSeats') or 9),
                    "ca": row.get('CompAL'), "cf": row.get('CompFltNum'), "co": row.get('CompOrg'), "cdst": row.get('CompDst'),
                    "cdd": parse_date(row.get('CompDepDate')), "ccc": row.get('CompCabCode', 'Y'),
                    "ctf": float(row.get('CompTotFare') or 0), "cbf": float(row.get('CompBaseFare') or 0),
                    "ctax": float(row.get('CompTax') or 0), "cyq": float(row.get('CompYQ') or 0), "cs": int(row.get('CompSeats') or 9)
                })
            
            conn.commit()
            print("Finished successfully")
    except Exception as e:
        print(f"FAILED REPR: {repr(e)}")
        traceback.print_exc(file=sys.stdout)

if __name__ == "__main__":
    main()
