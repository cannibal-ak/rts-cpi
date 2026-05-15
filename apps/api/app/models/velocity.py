"""Velocity snapshot — flight booking/load factor data, multi-tenant (airline_code)."""

import uuid
from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base


class VelocitySnapshot(Base):
    __tablename__ = "velocity_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batch.id"), nullable=True)

    # Flight identity
    dep_date = Column(Date, nullable=False)
    dep_time = Column(String(8), nullable=False)
    dep_code = Column(String(10), nullable=False)
    city_pair = Column(String(8), nullable=False)
    origin = Column(String(4), nullable=False)
    destination = Column(String(4), nullable=False)
    eqp = Column(String(8), nullable=False)

    # Leg/Segment breakdown
    legseg_type = Column(String(10), nullable=False)
    leg_seg_order = Column(Integer, nullable=False, default=1)

    # Booking & capacity
    days_left = Column(Integer, nullable=False, default=0)
    compartment = Column(String(4), nullable=False, default="Y")
    current_booking = Column(Integer, nullable=False, default=0)
    capacity = Column(Integer, nullable=False, default=0)
    actual_seat_factor = Column(Integer, nullable=False, default=0)
    forecasted_seat_factor = Column(Integer, nullable=False, default=0)

    # Tenant + airline discrimination & metadata
    airline_code = Column(String(8), nullable=False, index=True)
    data_owner = Column(String(32), nullable=True, index=True)
    tenant_code = Column(String(16), nullable=True, index=True)
    business_type = Column(String(16), nullable=True, index=True)
    report_date = Column(Date, nullable=True, index=True)
    source_file = Column(String(256), nullable=True)
    loaded_at = Column(DateTime(timezone=True), server_default=func.now())
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
