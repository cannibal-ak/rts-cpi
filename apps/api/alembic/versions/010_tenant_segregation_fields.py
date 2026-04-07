"""Migration: Addition of tenant-segregation fields to snapshots.

Revision ID: 010
Revises: 009
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

revision = '010'
down_revision = '008' # Assuming 008 is the last one I saw in list_dir
branch_labels = None
depends_on = None

def upgrade():
    # Airline table
    op.add_column('airline_cpi_snapshot', sa.Column('tenant_code', sa.String(16), nullable=True))
    op.add_column('airline_cpi_snapshot', sa.Column('business_type', sa.String(16), nullable=True))
    op.add_column('airline_cpi_snapshot', sa.Column('report_date', sa.Date, nullable=True))
    op.add_column('airline_cpi_snapshot', sa.Column('source_file', sa.String(256), nullable=True))
    op.add_column('airline_cpi_snapshot', sa.Column('loaded_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=True))
    
    op.create_index('ix_air_snap_tenant_code', 'airline_cpi_snapshot', ['tenant_code'])
    op.create_index('ix_air_snap_business_type', 'airline_cpi_snapshot', ['business_type'])
    op.create_index('ix_air_snap_report_date', 'airline_cpi_snapshot', ['report_date'])

    # CFL table
    op.add_column('cfl_cpi_snapshot', sa.Column('tenant_code', sa.String(16), nullable=True))
    op.add_column('cfl_cpi_snapshot', sa.Column('business_type', sa.String(16), nullable=True))
    op.add_column('cfl_cpi_snapshot', sa.Column('report_date', sa.Date, nullable=True))
    op.add_column('cfl_cpi_snapshot', sa.Column('source_file', sa.String(256), nullable=True))
    op.add_column('cfl_cpi_snapshot', sa.Column('loaded_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=True))
    
    op.create_index('ix_cfl_snap_tenant_code', 'cfl_cpi_snapshot', ['tenant_code'])
    op.create_index('ix_cfl_snap_business_type', 'cfl_cpi_snapshot', ['business_type'])
    op.create_index('ix_cfl_snap_report_date', 'cfl_cpi_snapshot', ['report_date'])

def downgrade():
    # Remove indexes and columns (reverse order)
    op.drop_index('ix_cfl_snap_report_date', 'cfl_cpi_snapshot')
    op.drop_index('ix_cfl_snap_business_type', 'cfl_cpi_snapshot')
    op.drop_index('ix_cfl_snap_tenant_code', 'cfl_cpi_snapshot')
    op.drop_column('cfl_cpi_snapshot', 'loaded_at')
    op.drop_column('cfl_cpi_snapshot', 'source_file')
    op.drop_column('cfl_cpi_snapshot', 'report_date')
    op.drop_column('cfl_cpi_snapshot', 'business_type')
    op.drop_column('cfl_cpi_snapshot', 'tenant_code')

    op.drop_index('ix_air_snap_report_date', 'airline_cpi_snapshot')
    op.drop_index('ix_air_snap_business_type', 'airline_cpi_snapshot')
    op.drop_index('ix_air_snap_tenant_code', 'airline_cpi_snapshot')
    op.drop_column('airline_cpi_snapshot', 'loaded_at')
    op.drop_column('airline_cpi_snapshot', 'source_file')
    op.drop_column('airline_cpi_snapshot', 'report_date')
    op.drop_column('airline_cpi_snapshot', 'business_type')
    op.drop_column('airline_cpi_snapshot', 'tenant_code')
