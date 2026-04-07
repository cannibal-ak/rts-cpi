"""CFL snapshot — canonical raw data table with tenant isolation."""

import uuid
from sqlalchemy import Column, String, Integer, Numeric, Date, Time, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base


class CflCpiSnapshot(Base):
    __tablename__ = "cfl_cpi_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batch.id"), nullable=True)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("source_file.id"), nullable=True)
    record_hash = Column(String(64), nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    cap_date = Column(Date, nullable=False)
    cap_time = Column(Time, nullable=False)
    trip_type = Column(String(16), nullable=False)
    source = Column(String(64), nullable=False)
    org = Column(String(32), nullable=False)
    dest = Column(String(32), nullable=False)
    out_dep_date = Column(Date, nullable=False)
    out_dep_time = Column(Time, nullable=True)
    prod_family = Column(String(64), nullable=True)
    out_equip_name = Column(String(64), nullable=True)
    out_cab_type = Column(String(32), nullable=True)
    total_fare = Column(Numeric(12, 2), nullable=False)
    out_per_pax_fare = Column(Numeric(12, 2), nullable=True)
    out_veh_fare = Column(Numeric(12, 2), nullable=True)
    out_cab_fare = Column(Numeric(12, 2), nullable=True)
    out_taxes = Column(Numeric(12, 2), nullable=True)
    out_num_pax = Column(Integer, nullable=True)
    veh_size = Column(String(16), nullable=True)
    curr_code = Column(String(4), nullable=False, server_default="USD")
    out_avail = Column(String(16), nullable=True)
    data_owner = Column(String(32), nullable=True, index=True)

    # ── Tenant Segregation & Ingestion Metadata ──
    tenant_code = Column(String(16), nullable=True, index=True)
    business_type = Column(String(16), nullable=True, index=True)
    report_date = Column(Date, nullable=True, index=True)
    source_file = Column(String(256), nullable=True)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())
