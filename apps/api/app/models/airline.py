"""Airline CPI snapshot — canonical raw data table with tenant isolation."""

import uuid
from sqlalchemy import Column, String, Integer, Numeric, Date, Time, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base


class AirlineCpiSnapshot(Base):
    __tablename__ = "airline_cpi_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batch.id"), nullable=True)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("source_file.id"), nullable=True)
    record_hash = Column(String(64), nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    cap_date = Column(Date, nullable=False)
    cap_time = Column(Time, nullable=False)
    trip_type = Column(String(4), nullable=False)
    ref_al = Column(String(3), nullable=False)
    ref_flt_num = Column(String(10), nullable=False)
    ref_org = Column(String(4), nullable=False)
    ref_dst = Column(String(4), nullable=False)
    ref_dep_date = Column(Date, nullable=False)
    ref_cab_code = Column(String(4), nullable=False)
    ref_tot_fare = Column(Numeric(12, 2), nullable=False)
    ref_base_fare = Column(Numeric(12, 2), nullable=False)
    ref_tax = Column(Numeric(12, 2), nullable=False)
    ref_yq = Column(Numeric(12, 2), nullable=False)
    ref_seats = Column(Integer, nullable=False)
    ref_curr = Column(String(4), nullable=True, server_default="USD")
    comp_al = Column(String(3), nullable=False)
    comp_flt_num = Column(String(10), nullable=False)
    comp_org = Column(String(4), nullable=False)
    comp_dst = Column(String(4), nullable=False)
    comp_dep_date = Column(Date, nullable=False)
    comp_cab_code = Column(String(4), nullable=False)
    comp_tot_fare = Column(Numeric(12, 2), nullable=False)
    comp_base_fare = Column(Numeric(12, 2), nullable=False)
    comp_tax = Column(Numeric(12, 2), nullable=False)
    comp_yq = Column(Numeric(12, 2), nullable=False)
    comp_seats = Column(Integer, nullable=False)
    comp_curr = Column(String(4), nullable=True, server_default="USD")
    pos = Column(String(4), nullable=False)
    poa = Column(String(4), nullable=False)
    data_owner = Column(String(32), nullable=True, index=True)

    # ── Tenant Segregation & Ingestion Metadata ──
    tenant_code = Column(String(16), nullable=True, index=True)
    business_type = Column(String(16), nullable=True, index=True)
    report_date = Column(Date, nullable=True, index=True)
    source_file = Column(String(256), nullable=True)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())
