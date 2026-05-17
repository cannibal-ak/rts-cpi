import os
import csv
import uuid
import sys
import traceback
from datetime import datetime
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")

# Define Tenant Mapping
TENANTS = {
    "JY": {
        "id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "code": "JY",
        "business_type": "AIRLINE",
        "name": "interCaribbean Airways"
    },
    "PW": {
        "id": uuid.UUID("bb000000-0000-0000-0000-000000000001"),
        "code": "PW",
        "business_type": "AIRLINE",
        "name": "Skybound - PW"
    },
    "FJL": {
        "id": uuid.UUID("cc000000-0000-0000-0000-000000000001"),
        "code": "FJL",
        "business_type": "CRUISE_FERRY",
        "name": "Baltic Ferries - FJL"
    }
}

def parse_date(date_str):
    if not date_str or date_str.strip() in ('0', ''): return None
    date_str = date_str.strip()
    for fmt in ("%d%b%y", "%d%B%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except:
            continue
    try:
        return datetime.strptime(date_str.upper(), "%d%b%y").date()
    except:
        return None

def parse_time(time_str):
    if not time_str or not time_str.strip(): return None
    time_str = time_str.strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except:
            continue
    return None

def safe_float(val):
    if not val: return 0.0
    try:
        return float(str(val).replace(',', '').strip() or 0)
    except:
        return 0.0

def safe_int(val):
    if not val: return 0
    try:
        return int(str(val).strip() or 0)
    except:
        return 0

def seed_airline(conn, folder, file_path, tenant_id, tenant_code, business_type):
    print(f"Seeding Airline [{tenant_code}]: {file_path}")
    source_name = f"Local: {folder}/{os.path.basename(file_path)}"
    
    job_id = uuid.uuid4()
    conn.execute(text("INSERT INTO import_job (id, tenant_id, domain, status, source_name, started_at) VALUES (:id, :tid, 'airline', 'validating', :src, now())"), {"id": job_id, "tid": tenant_id, "src": source_name})
    
    batch_id = uuid.uuid4()
    conn.execute(text("INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq) VALUES (:id, :tid, :job_id, 1)"), {"id": batch_id, "tid": tenant_id, "job_id": job_id})
    
    valid_count = 0
    rejected_count = 0
    total_count = 0
    
    # Extract report date from filename or content
    # For now, use a fixed date for the report if not found
    report_date = None
    
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_count += 1
            try:
                cap_date = parse_date(row.get('CapDate'))
                if not cap_date:
                    rejected_count += 1
                    continue
                
                if not report_date:
                    report_date = cap_date

                query = text("""
                    INSERT INTO airline_cpi_snapshot (
                        id, tenant_id, import_batch_id, cap_date, cap_time, trip_type,
                        ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date, ref_cab_code,
                        ref_tot_fare, ref_base_fare, ref_tax, ref_yq, ref_seats,
                        comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
                        comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats,
                        pos, poa, data_owner, tenant_code, business_type, report_date, source_file, loaded_at
                    ) VALUES (
                        :id, :tid, :bid, :cd, :ct, :tt,
                        :ra, :rf, :ro, :rd, :rdd, :rcc,
                        :rtf, :rbf, :rtax, :ryq, :rs,
                        :ca, :cf, :co, :cdst, :cdd, :ccc,
                        :ctf, :cbf, :ctax, :cyq, :cs,
                        'US', 'US', :owner, :tcode, :btype, :rdate, :sfile, now()
                    )
                """)
                
                params = {
                    "id": uuid.uuid4(), "tid": tenant_id, "bid": batch_id,
                    "cd": cap_date,
                    "ct": parse_time(row.get('CapTime')) or datetime.now().time(),
                    "tt": row.get('TripType', 'RT')[:4],
                    "ra": row.get('RefAL', 'JY')[:3],
                    "rf": row.get('RefFltNum', '')[:10],
                    "ro": row.get('RefOrg', '')[:4],
                    "rd": row.get('RefDst', '')[:4],
                    "rdd": parse_date(row.get('RefDepDate')) or cap_date,
                    "rcc": row.get('RefCabCode', 'Y')[:4],
                    "rtf": safe_float(row.get('RefTotFare')),
                    "rbf": safe_float(row.get('RefBaseFare')),
                    "rtax": safe_float(row.get('RefTax')),
                    "ryq": safe_float(row.get('RefYQ')),
                    "rs": safe_int(row.get('RefSeats') or 9),
                    "ca": row.get('CompAL', '')[:3],
                    "cf": row.get('CompFltNum', '')[:10],
                    "co": row.get('CompOrg', row.get('RefOrg', ''))[:4],
                    "cdst": row.get('CompDst', row.get('RefDst', ''))[:4],
                    "cdd": parse_date(row.get('CompDepDate')) or cap_date,
                    "ccc": row.get('CompCabCode', 'Y')[:4],
                    "ctf": safe_float(row.get('CompTotFare')),
                    "cbf": safe_float(row.get('CompBaseFare')),
                    "ctax": safe_float(row.get('CompTax')),
                    "cyq": safe_float(row.get('CompYQ')),
                    "cs": safe_int(row.get('CompSeats') or 9),
                    "owner": tenant_code,
                    "tcode": tenant_code,
                    "btype": business_type,
                    "rdate": report_date,
                    "sfile": os.path.basename(file_path)
                }
                
                conn.execute(query, params)
                valid_count += 1
            except Exception as e:
                rejected_count += 1
                if rejected_count <= 5:
                    print(f"DEBUG: Rejected row in {folder}: {e}")
    
    status = "committed" if rejected_count == 0 else "failed" if valid_count == 0 else "committed"
    conn.execute(text("UPDATE import_job SET records_total = :t, records_valid = :v, records_rejected = :r, status = :s, completed_at = now() WHERE id = :id"), 
                 {"t": total_count, "v": valid_count, "r": rejected_count, "s": status, "id": job_id})
    conn.execute(text("UPDATE import_batch SET record_count = :v WHERE id = :id"), {"v": valid_count, "id": batch_id})
    print(f"Stored {valid_count} Airline records for {tenant_code} (Total: {total_count})")

def seed_cfl(conn, folder, file_path, tenant_id, tenant_code, business_type):
    print(f"Seeding CFL [{tenant_code}]: {file_path}")
    source_name = f"Local: {folder}/{os.path.basename(file_path)}"
    
    job_id = uuid.uuid4()
    conn.execute(text("INSERT INTO import_job (id, tenant_id, domain, status, source_name, started_at) VALUES (:id, :tid, 'cfl', 'validating', :src, now())"), {"id": job_id, "tid": tenant_id, "src": source_name})
    
    batch_id = uuid.uuid4()
    conn.execute(text("INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq) VALUES (:id, :tid, :job_id, 1)"), {"id": batch_id, "tid": tenant_id, "job_id": job_id})
    
    valid_count = 0
    rejected_count = 0
    total_count = 0
    report_date = None
    
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_count += 1
            try:
                cap_date = parse_date(row.get('CapDate'))
                if not cap_date:
                    rejected_count += 1
                    continue
                
                if not report_date:
                    report_date = cap_date

                query = text("""
                    INSERT INTO cfl_cpi_snapshot (
                        id, tenant_id, data_owner, cap_date, cap_time, trip_type, source,
                        org, dest, out_dep_date, out_dep_time, prod_family, out_equip_name,
                        out_cab_type, total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare,
                        out_taxes, out_num_pax, veh_size, curr_code, out_avail,
                        tenant_code, business_type, report_date, source_file, loaded_at
                    ) VALUES (
                        :id, :tid, :owner, :cd, :ct, :tt, :src,
                        :org, :dst, :odd, :odt, :pf, :oen,
                        :oct, :tf, :oppf, :ovf, :ocf,
                        :otx, :onp, :vs, :cc, :oa,
                        :tcode, :btype, :rdate, :sfile, now()
                    )
                """)
                
                params = {
                    "id": uuid.uuid4(), "tid": tenant_id,
                    "owner": tenant_code,
                    "cd": cap_date,
                    "ct": parse_time(row.get('CapTime')) or datetime.now().time(),
                    "tt": row.get('TripType', 'ONE_WAY')[:16],
                    "src": row.get('Source', folder)[:64],
                    "org": row.get('Org', '')[:32],
                    "dst": row.get('Dest', '')[:32],
                    "odd": parse_date(row.get('OutDepDate')) or cap_date,
                    "odt": parse_time(row.get('OutDepTime')) or datetime.now().time(),
                    "pf": row.get('ProdFamily', 'Standard')[:64],
                    "oen": row.get('OutEquipName', '')[:64],
                    "oct": row.get('OutCabType', 'none')[:32],
                    "tf": safe_float(row.get('TotalFare')),
                    "oppf": safe_float(row.get('OutPerPaxFare')),
                    "ovf": safe_float(row.get('OutVehFare')),
                    "ocf": safe_float(row.get('OutCabFare')),
                    "otx": safe_float(row.get('OutTaxes')),
                    "onp": safe_int(row.get('OutNumPax') or 1),
                    "vs": row.get('VehSize', 'none')[:16],
                    "cc": row.get('CurrCode', 'EUR')[:4],
                    "oa": row.get('OutAvail', 'Available')[:16],
                    "tcode": tenant_code,
                    "btype": business_type,
                    "rdate": report_date,
                    "sfile": os.path.basename(file_path)
                }
                
                conn.execute(query, params)
                valid_count += 1
            except Exception as e:
                rejected_count += 1
                if rejected_count <= 5:
                    print(f"DEBUG: Rejected row in {folder}: {e}")
                
    status = "committed" if rejected_count == 0 else "failed" if valid_count == 0 else "committed"
    conn.execute(text("UPDATE import_job SET records_total = :t, records_valid = :v, records_rejected = :r, status = :s, completed_at = now() WHERE id = :id"), 
                 {"t": total_count, "v": valid_count, "r": rejected_count, "s": status, "id": job_id})
    conn.execute(text("UPDATE import_batch SET record_count = :v WHERE id = :id"), {"v": valid_count, "id": batch_id})
    print(f"Stored {valid_count} CFL records for {tenant_code} (Total: {total_count})")

def main():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            print("Clearing historical snapshot data...")
            conn.execute(text("TRUNCATE TABLE airline_cpi_snapshot CASCADE;"))
            conn.execute(text("TRUNCATE TABLE cfl_cpi_snapshot CASCADE;"))
            conn.execute(text("TRUNCATE TABLE import_batch CASCADE;"))
            conn.execute(text("TRUNCATE TABLE import_job CASCADE;"))
            
            # Ensure Tenants exist
            for key, t in TENANTS.items():
                res = conn.execute(text("SELECT 1 FROM tenant WHERE id = :tid"), {"tid": t["id"]}).fetchone()
                if not res:
                    print(f"Ensuring tenant exists: {t['name']}")
                    conn.execute(text("INSERT INTO tenant (id, slug, display_name) VALUES (:tid, :slug, :name)"), 
                                 {"tid": t["id"], "slug": t["code"].lower(), "name": t["name"]})

            # Data Seeding from flat folders for now (matching current structure)
            # JY
            seed_airline(conn, "JY", "/app/data/JY/JY_200226.csv", TENANTS["JY"]["id"], TENANTS["JY"]["code"], TENANTS["JY"]["business_type"])
            # PW
            seed_airline(conn, "PW", "/app/data/PW/PW_210226.csv", TENANTS["PW"]["id"], TENANTS["PW"]["code"], TENANTS["PW"]["business_type"])
            # FJL
            seed_cfl(conn, "FJL", "/app/data/FJL/FJL_210226.csv", TENANTS["FJL"]["id"], TENANTS["FJL"]["code"], TENANTS["FJL"]["business_type"])
            
            print("Seeding complete.")

if __name__ == "__main__":
    main()
