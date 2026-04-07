"""Airline snapshot schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import date, time
from uuid import UUID


class AirlineSnapshotOut(BaseModel):
    id: UUID
    cap_date: date
    cap_time: time
    trip_type: str
    ref_al: str
    ref_flt_num: str
    ref_org: str
    ref_dst: str
    ref_dep_date: date
    ref_cab_code: str
    ref_tot_fare: float
    ref_base_fare: float
    ref_tax: float
    ref_yq: float
    ref_seats: int
    comp_al: str
    comp_flt_num: str
    comp_org: str
    comp_dst: str
    comp_dep_date: date
    comp_cab_code: str
    comp_tot_fare: float
    comp_base_fare: float
    comp_tax: float
    comp_yq: float
    comp_seats: int
    pos: str
    poa: str
    # Derived fields from view
    fare_delta: Optional[float] = None
    fare_delta_pct: Optional[float] = None


    model_config = {"from_attributes": True}
