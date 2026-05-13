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

    # Outbound Arrival (migration 024)
    out_arr_date: Optional[date] = None
    out_arr_time: Optional[time] = None

    prod_family: Optional[str] = None
    out_equip_name: Optional[str] = None
    out_cab_type: Optional[str] = None

    # Outbound Descriptions & Seats (migration 024)
    out_cabin_desc: Optional[str] = None
    out_seat_type: Optional[str] = None
    out_num_cabs: Optional[int] = None
    out_seat_fare: Optional[float] = None
    out_num_seats: Optional[int] = None

    total_fare: float
    out_per_pax_fare: Optional[float] = None
    out_veh_fare: Optional[float] = None
    out_cab_fare: Optional[float] = None
    out_taxes: Optional[float] = None
    out_num_pax: Optional[int] = None
    veh_size: Optional[str] = None
    curr_code: str
    out_avail: Optional[str] = None

    # Return Journey — Schedule & Product (migration 024)
    ret_dep_date: Optional[date] = None
    ret_dep_time: Optional[time] = None
    ret_arr_date: Optional[date] = None
    ret_arr_time: Optional[time] = None
    ret_equip_name: Optional[str] = None
    ret_cab_type: Optional[str] = None
    ret_cab_desc: Optional[str] = None
    ret_seat_type: Optional[str] = None
    ret_avail: Optional[str] = None

    # Return Journey — Fares (migration 024)
    ret_per_pax_fare: Optional[float] = None
    ret_num_pax: Optional[int] = None
    ret_veh_fare: Optional[float] = None
    ret_cab_fare: Optional[float] = None
    ret_num_cabs: Optional[int] = None
    ret_seat_fare: Optional[float] = None
    ret_num_seats: Optional[int] = None
    ret_taxes: Optional[float] = None

    # Total/Combined Fares (migration 024)
    tot_per_pax_fare: Optional[float] = None
    tot_num_pax: Optional[int] = None
    tot_veh_fare: Optional[float] = None
    tot_cab_fare: Optional[float] = None
    tot_num_cabs: Optional[int] = None
    tot_seat_fare: Optional[float] = None
    tot_num_seats: Optional[int] = None
    tot_taxes: Optional[float] = None

    # Duration (migration 024)
    duration: Optional[int] = None

    model_config = {"from_attributes": True}
