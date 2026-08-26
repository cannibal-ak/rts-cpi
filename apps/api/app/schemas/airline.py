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

    # ── Provenance (1) ──
    path: Optional[str] = None

    # ── Dictionary columns added 2026-05-09 (migration 023) ──
    ref_pos: Optional[str] = None
    ref_channel: Optional[str] = None
    comp_pos: Optional[str] = None
    comp_channel: Optional[str] = None

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


# ── Price points — one row per OBSERVED FARE ────────────────────────────
#
# AirlineSnapshotOut above mirrors how the data is stored: a reference fare
# and a competitor fare side by side on one row. That shape is right for the
# grid, but wrong for a chart, where each airline's fare is its own plotted
# point. PricePointOut is the unpivoted view — the ref and comp halves of a
# stored row become two independent observations, so "one airline, one
# flight, one price" is a single object regardless of which side it came in
# on. Fields are named without the ref_/comp_ prefix for that reason.


class PricePointOut(BaseModel):
    """A single airline's fare for a single flight, as observed on one capture."""

    airline: str
    # 'reference' = the tenant's own airline, 'competitor' = someone they
    # track. Drives which series is highlighted as "ours" in the chart.
    role: str
    flt_num: Optional[str] = None

    # The REFERENCE market this observation was matched on, "ORG-DST". Group
    # a multi-route chart by this, never by origin/destination below: a
    # competitor row carries its own stations, which can differ from the
    # market it was compared in.
    market: str
    origin: str
    destination: str
    dep_date: date
    # Times are strings, not `time`: the feeds send "HH:MM" (WinAir) or
    # "HHMM" (JY/PW) and neither is guaranteed present. Parsing them into a
    # real time here would force a format decision the data does not support.
    dep_time: Optional[str] = None
    arr_time: Optional[str] = None
    # Derived from dep_time/arr_time when both parse; None otherwise. No
    # feed carries an elapsed-time column.
    duration_min: Optional[int] = None
    stops: Optional[int] = None
    via: Optional[str] = None
    # 'OW' | 'RT' where the feed states it; an itinerary-level attribute shared
    # by the reference and competitor halves of the same snapshot row.
    trip_type: Optional[str] = None

    cab_code: Optional[str] = None
    cab_name: Optional[str] = None
    bkg_class: Optional[str] = None
    ff_code: Optional[str] = None
    equip_code: Optional[str] = None
    seats: Optional[int] = None

    curr: Optional[str] = None
    base_fare: float
    tax: float
    yq: float
    yr: float
    tot_fare: float

    cap_date: date
    cap_time: Optional[time] = None
    # Days before departure at the moment of capture (dep_date - cap_date).
    # Negative would mean the flight had already gone; kept as-is rather
    # than clamped so bad data stays visible.
    dbd: Optional[int] = None


class NoFareDayOut(BaseModel):
    """A day on which an airline had no purchasable fare, classified.

    Such a day produces no PricePointOut at all — the chart shows a silent
    gap. This row says which kind of gap it is. 'sold_out': flights were
    offered but every fare arrived as 0, which is how the feed writes a
    flight whose inventory is gone (a sold-out reference row still carries
    its stops count; a sold-out competitor row still carries a flight
    number). 'not_on_sale': the schedule showed nothing offerable, so the
    source cells were blank and ingestion coerced them to 0 (no stops, no
    flight number). A day where any flight still carried a real fare is
    not listed here at all.
    """

    # The same "ORG-DST" string PricePointOut.market carries — markers join
    # to their fare line on this key.
    market: str
    airline: str
    dep_date: date
    # 'sold_out' | 'not_on_sale'. One sold-out flight is enough to call the
    # day sold out; only an entirely blank day counts as not on sale.
    status: str
    # Days before departure at capture, same convention as PricePointOut.dbd.
    dbd: int


class PricePointsResponse(BaseModel):
    cap_date: Optional[date] = None
    # Echoes the routes actually queried, as "ORG-DST" strings. A list
    # rather than a single origin/destination pair because the dashboard's
    # Route filter is multi-select: plotting only the first selection would
    # quietly disagree with the Superset charts beside it.
    routes: list[str] = []
    # The dominant currency across the returned points, or None when the
    # selection mixes currencies (FJL does; the airline tenants do not).
    currency: Optional[str] = None
    # True when the per-market cap was hit on any route — the caller should
    # say so rather than present a partial chart as complete.
    truncated: bool = False
    # Which markets were cut, so the warning can name them instead of leaving
    # the reader to guess which line is incomplete.
    truncated_routes: list[str] = []
    points: list[PricePointOut] = []
    # Whole-day availability markers, populated only when the caller sends
    # include_availability. Empty otherwise — a caller that never asks can
    # ignore both availability fields entirely.
    no_fare_days: list[NoFareDayOut] = []
    # True when a stops/flt_num filter forced the markers off: a no-fare day
    # carries NULL stops and a blank flight number, so it cannot honestly
    # satisfy either filter. Lets the caller say why the markers vanished.
    availability_suppressed: bool = False


class PriceHistoryPointOut(BaseModel):
    """One flight's fare as seen on one capture date."""

    cap_date: date
    cap_time: Optional[time] = None
    tot_fare: float
    seats: Optional[int] = None
    dbd: Optional[int] = None


class PriceHistoryResponse(BaseModel):
    airline: str
    flt_num: Optional[str] = None
    # Echoes the trip_type the caller scoped by; None when unscoped.
    trip_type: Optional[str] = None
    origin: str
    destination: str
    dep_date: date
    curr: Optional[str] = None
    points: list[PriceHistoryPointOut] = []
