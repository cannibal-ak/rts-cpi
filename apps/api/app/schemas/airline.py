"""Airline snapshot schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import date, time, datetime
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

    # ── Reference flight — outbound additions (11) — Phase 2E ──
    ref_dep_time: Optional[str] = None
    ref_arr_time: Optional[str] = None
    ref_stops: Optional[int] = None
    ref_via: Optional[str] = None
    ref_ff_code: Optional[str] = None
    ref_cab_name: Optional[str] = None
    ref_bkg_class: Optional[str] = None
    ref_yr: Optional[float] = None
    ref_anc_price: Optional[float] = None
    ref_anc_type: Optional[str] = None
    ref_equip_code: Optional[str] = None

    # ── Reference flight — return-leg (11) ──
    ref_ret_flt_num: Optional[str] = None
    ref_ret_dep_date: Optional[date] = None
    ref_ret_dep_time: Optional[str] = None
    ref_ret_arr_time: Optional[str] = None
    ref_ret_stops: Optional[int] = None
    ref_ret_via: Optional[str] = None
    ref_ret_cab_name: Optional[str] = None
    ref_ret_cab_code: Optional[str] = None
    ref_ret_bkg_class: Optional[str] = None
    ref_ret_seats: Optional[int] = None
    ref_ret_equip_code: Optional[str] = None

    # ── Competitor — outbound additions (11) ──
    comp_dep_time: Optional[str] = None
    comp_arr_time: Optional[str] = None
    comp_stops: Optional[int] = None
    comp_via: Optional[str] = None
    comp_ff_code: Optional[str] = None
    comp_cab_name: Optional[str] = None
    comp_bkg_class: Optional[str] = None
    comp_yr: Optional[float] = None
    comp_anc_price: Optional[float] = None
    comp_anc_type: Optional[str] = None
    comp_equip_code: Optional[str] = None

    # ── Competitor — return-leg (11) ──
    comp_ret_flt_num: Optional[str] = None
    comp_ret_dep_date: Optional[date] = None
    comp_ret_dep_time: Optional[str] = None
    comp_ret_arr_time: Optional[str] = None
    comp_ret_stops: Optional[int] = None
    comp_ret_via: Optional[str] = None
    comp_ret_cab_name: Optional[str] = None
    comp_ret_cab_code: Optional[str] = None
    comp_ret_bkg_class: Optional[str] = None
    comp_ret_seats: Optional[int] = None
    comp_ret_equip_code: Optional[str] = None

    # ── Point-of-* (PW source carries pod/poc) (2) ──
    pod: Optional[str] = None
    poc: Optional[str] = None

    # ── Provenance (1) ──
    path: Optional[str] = None

    # ── Currently-stripped infra/metadata fields now exposed (9) ──
    ref_curr: Optional[str] = None
    comp_curr: Optional[str] = None
    tenant_code: Optional[str] = None
    report_date: Optional[date] = None
    file_date: Optional[date] = None  # view alias for report_date
    source_file: Optional[str] = None
    business_type: Optional[str] = None
    ingested_at: Optional[datetime] = None
    loaded_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
