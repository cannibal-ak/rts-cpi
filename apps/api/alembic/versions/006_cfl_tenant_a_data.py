"""Seed CFL demo data for Tenant A to align with Airline reference.

Revision ID: 006
Revises: 005
Create Date: 2026-03-10
"""
from typing import Sequence, Union
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_A = "a0000000-0000-0000-0000-000000000001"

def upgrade() -> None:
    # 1. Source System for CFL for Tenant A
    src_id = "ca200000-0000-0000-0000-000000000001"
    op.execute(f"""
        INSERT INTO source_system (id, tenant_id, code, display_name, domain)
        VALUES ('{src_id}', '{TENANT_A}', 'api-ferry-manual', 'Manual Ferry Feed', 'cfl')
        ON CONFLICT (id) DO NOTHING;
    """)

    # 2. Import Job
    job_id = "da300000-0000-0000-0000-000000000001"
    op.execute(f"""
        INSERT INTO import_job (id, tenant_id, source_system_id, domain, status, records_total, records_valid, records_rejected, timeline, completed_at)
        VALUES ('{job_id}', '{TENANT_A}', '{src_id}', 'cfl', 'committed', 10, 10, 0, '[]', '2026-03-10T10:00:00')
        ON CONFLICT (id) DO NOTHING;
    """)

    # 3. Import Batch
    batch_id = "ea200000-0000-0000-0000-000000000001"
    op.execute(f"""
        INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq, record_count)
        VALUES ('{batch_id}', '{TENANT_A}', '{job_id}', 1, 10)
        ON CONFLICT (id) DO NOTHING;
    """)

    # 4. CFL Snapshots for Tenant A
    op.execute(f"""
        INSERT INTO cfl_cpi_snapshot (
            tenant_id, import_batch_id, cap_date, cap_time, trip_type,
            source, org, dest, out_dep_date, out_dep_time,
            prod_family, out_equip_name, out_cab_type,
            total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare, out_taxes,
            out_num_pax, veh_size, curr_code, out_avail
        ) VALUES
        ('{TENANT_A}','{batch_id}','2026-03-09','09:15','ROUND_TRIP','P&O Ferries','Dover','Calais','2026-04-15','08:00','Standard','Spirit of Britain',NULL,145.50,32.00,65.00,NULL,12.50,4,'medium','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:15','ROUND_TRIP','P&O Ferries','Dover','Calais','2026-04-15','08:00','Flexi','Spirit of Britain',NULL,195.00,42.00,65.00,NULL,18.00,4,'medium','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:20','ONE_WAY','DFDS','Dover','Calais','2026-04-16','10:30','Standard','Côte des Flandres',NULL,85.00,21.25,40.00,NULL,7.50,4,'small','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:20','ROUND_TRIP','DFDS','Dover','Calais','2026-04-16','10:30','Premium','Côte des Flandres','Club',280.00,56.00,80.00,50.00,22.00,4,'medium','GBP','Limited'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:25','ROUND_TRIP','Irish Ferries','Holyhead','Dublin','2026-04-18','14:00','Economy','Ulysses',NULL,220.00,55.00,95.00,NULL,19.00,4,'large','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:30','ONE_WAY','Stena Line','Harwich','Hook of Holland','2026-04-20','22:00','Standard','Stena Adventurer','Outside',175.00,58.00,45.00,40.00,15.00,2,'medium','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:35','ROUND_TRIP','Brittany Ferries','Portsmouth','Le Havre','2026-04-22','08:30','Standard','Normandie',NULL,265.00,53.00,90.00,NULL,23.50,4,'medium','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-09','09:40','ONE_WAY','Viking Line','Helsinki','Tallinn','2026-04-25','10:00','Economy','Viking XPRS',NULL,42.00,21.00,NULL,NULL,3.50,2,'none','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-10','10:00','ONE_WAY','P&O Ferries','Liverpool','Belfast','2026-04-28','20:00','Standard','Norbay',NULL,115.00,28.75,50.00,NULL,9.00,4,'medium','GBP','Available'),
        ('{TENANT_A}','{batch_id}','2026-03-10','10:05','ROUND_TRIP','Stena Line','Liverpool','Belfast','2026-04-28','20:00','Flexi','Stena Lagan','Inside',275.00,55.00,75.00,50.00,24.00,4,'large','GBP','Limited');
    """)

def downgrade() -> None:
    op.execute(f"DELETE FROM cfl_cpi_snapshot WHERE tenant_id = '{TENANT_A}';")
    op.execute(f"DELETE FROM import_batch WHERE id = 'ea200000-0000-0000-0000-000000000001';")
    op.execute(f"DELETE FROM import_job WHERE id = 'da300000-0000-0000-0000-000000000001';")
    op.execute(f"DELETE FROM source_system WHERE id = 'ca200000-0000-0000-0000-000000000001';")
