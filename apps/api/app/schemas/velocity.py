"""Velocity snapshot schemas — mirrors vw_velocity_<tenant>_snapshot."""

from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date, datetime
from uuid import UUID


class VelocitySnapshotOut(BaseModel):
    id: UUID
    tenant_id: UUID
    dep_date: date
    dep_time: str
    dep_code: str
    city_pair: str
    origin: str
    destination: str
    eqp: str
    legseg_type: str
    leg_seg_order: int
    days_left: int
    compartment: str
    current_booking: int
    capacity: int
    actual_seat_factor: int
    forecasted_seat_factor: int
    seats_available: int
    booking_pct: float
    airline_code: str
    data_owner: Optional[str] = None
    tenant_code: Optional[str] = None
    business_type: Optional[str] = None
    report_date: Optional[date] = None
    file_date: Optional[date] = None
    source_file: Optional[str] = None
    loaded_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
