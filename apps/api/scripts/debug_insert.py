import os
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import UUID

DATABASE_URL = os.getenv("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")
TENANT_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    try:
        # 1. Create Job
        job_id = uuid.uuid4()
        conn.execute(text("""
            INSERT INTO import_job (id, tenant_id, domain, status, source_name, timeline)
            VALUES (:id, :tid, 'airline', 'committed', 'Debug Job', '[]'::jsonb)
        """), {"id": job_id, "tid": TENANT_ID})
        
        # 2. Create Batch
        batch_id = uuid.uuid4()
        conn.execute(text("""
            INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq)
            VALUES (:id, :tid, :job_id, 1)
        """), {"id": batch_id, "tid": TENANT_ID, "job_id": job_id})
        
        # 3. Create Snapshot
        conn.execute(text("""
            INSERT INTO airline_cpi_snapshot (
                id, tenant_id, import_batch_id, cap_date, cap_time, trip_type,
                ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date, ref_cab_code,
                ref_tot_fare, ref_base_fare, ref_tax, ref_yq, ref_seats,
                comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
                comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats,
                pos, poa, data_owner
            ) VALUES (
                :id, :tid, :bid, '2026-02-19', '11:47:00', 'RT',
                'JY', 'JY0554', 'BGI', 'ANU', '2026-04-04', 'Y',
                587.45, 425.25, 162.20, 0, 9,
                'BW', 'BW001', 'BGI', 'ANU', '2026-04-04', 'Y',
                500.00, 400.00, 100.00, 0, 9,
                'US', 'US', 'admin@skywave.com'
            )
        """), {"id": uuid.uuid4(), "tid": TENANT_ID, "bid": batch_id})
        
        conn.commit()
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
