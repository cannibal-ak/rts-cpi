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
    ref_flt_num = Column(String(64), nullable=False)
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
    comp_flt_num = Column(String(64), nullable=False)
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

    # ── Reference flight — outbound additions (11) — Phase 2A migration 022 ──
    ref_dep_time = Column(String(8), nullable=True)
    ref_arr_time = Column(String(8), nullable=True)
    ref_stops = Column(Integer, nullable=True)
    ref_via = Column(String(4), nullable=True)
    ref_ff_code = Column(String(20), nullable=True)
    ref_cab_name = Column(String(20), nullable=True)
    ref_bkg_class = Column(String(16), nullable=True)
    ref_yr = Column(Numeric(12, 2), nullable=True)
    ref_anc_price = Column(Numeric(12, 2), nullable=True)
    ref_anc_type = Column(String(20), nullable=True)
    ref_equip_code = Column(String(128), nullable=True)

    # ── Reference flight — return-leg (11) — JY-only in source ──
    ref_ret_flt_num = Column(String(64), nullable=True)
    ref_ret_dep_date = Column(Date, nullable=True)
    ref_ret_dep_time = Column(String(8), nullable=True)
    ref_ret_arr_time = Column(String(8), nullable=True)
    ref_ret_stops = Column(Integer, nullable=True)
    ref_ret_via = Column(String(4), nullable=True)
    ref_ret_cab_name = Column(String(20), nullable=True)
    ref_ret_cab_code = Column(String(4), nullable=True)
    ref_ret_bkg_class = Column(String(16), nullable=True)
    ref_ret_seats = Column(Integer, nullable=True)
    ref_ret_equip_code = Column(String(128), nullable=True)

    # ── Competitor — outbound additions (11) ──
    comp_dep_time = Column(String(8), nullable=True)
    comp_arr_time = Column(String(8), nullable=True)
    comp_stops = Column(Integer, nullable=True)
    comp_via = Column(String(4), nullable=True)
    comp_ff_code = Column(String(20), nullable=True)
    comp_cab_name = Column(String(20), nullable=True)
    comp_bkg_class = Column(String(16), nullable=True)
    comp_yr = Column(Numeric(12, 2), nullable=True)
    comp_anc_price = Column(Numeric(12, 2), nullable=True)
    comp_anc_type = Column(String(20), nullable=True)
    comp_equip_code = Column(String(128), nullable=True)

    # ── Competitor — return-leg (11) — JY-only in source ──
    comp_ret_flt_num = Column(String(64), nullable=True)
    comp_ret_dep_date = Column(Date, nullable=True)
    comp_ret_dep_time = Column(String(8), nullable=True)
    comp_ret_arr_time = Column(String(8), nullable=True)
    comp_ret_stops = Column(Integer, nullable=True)
    comp_ret_via = Column(String(4), nullable=True)
    comp_ret_cab_name = Column(String(20), nullable=True)
    comp_ret_cab_code = Column(String(4), nullable=True)
    comp_ret_bkg_class = Column(String(16), nullable=True)
    comp_ret_seats = Column(Integer, nullable=True)
    comp_ret_equip_code = Column(String(128), nullable=True)

    # ── Point-of-* (PW source carries pod/poc) (2) ──
    pod = Column(String(4), nullable=True)
    poc = Column(String(4), nullable=True)

    # ── Provenance (1) — dictionary-required, currently absent from sources ──
    path = Column(String(50), nullable=True)

    data_owner = Column(String(32), nullable=True, index=True)

    # ── Tenant Segregation & Ingestion Metadata ──
    tenant_code = Column(String(16), nullable=True, index=True)
    business_type = Column(String(16), nullable=True, index=True)
    report_date = Column(Date, nullable=True, index=True)
    source_file = Column(String(256), nullable=True)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())
