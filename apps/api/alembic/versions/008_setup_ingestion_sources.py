"""Setup ingestion source systems for local CSV imports.

Revision ID: 008
Revises: 007
Create Date: 2026-03-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_A = "a0000000-0000-0000-0000-000000000001"

def upgrade() -> None:
    # Insert a clean source system for the local data folder
    op.execute(f"""
        INSERT INTO source_system (id, tenant_id, code, display_name, domain)
        VALUES ('ca100000-0000-0000-0000-000000000001', '{TENANT_A}', 'local-csv-folder', 'Local Data Folder', 'airline')
        ON CONFLICT (id) DO UPDATE SET code = 'local-csv-folder', display_name = 'Local Data Folder';
    """)

def downgrade() -> None:
    op.execute("DELETE FROM source_system WHERE code = 'local-csv-folder'")
