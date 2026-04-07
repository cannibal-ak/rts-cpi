"""CFL snapshot schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import date, time
from uuid import UUID


class CflSnapshotOut(BaseModel):
    id: UUID
    cap_date: date
    cap_time: time
    trip_type: str
    source: str
    org: str
    dest: str
    out_dep_date: date
    out_dep_time: Optional[time] = None
    prod_family: Optional[str] = None
    out_equip_name: Optional[str] = None
    out_cab_type: Optional[str] = None
    total_fare: float
    out_per_pax_fare: Optional[float] = None
    out_veh_fare: Optional[float] = None
    out_cab_fare: Optional[float] = None
    out_taxes: Optional[float] = None
    out_num_pax: Optional[int] = None
    veh_size: Optional[str] = None
    curr_code: str
    out_avail: Optional[str] = None

    model_config = {"from_attributes": True}
