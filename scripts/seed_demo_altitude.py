#!/usr/bin/env python3
"""Seed SYNTHETIC demo data for the Sky Airways (ALT) demo tenant.

Idempotent: deletes existing ALT rows first (tenant_code='ALT' fares /
airline_code='ALT' velocity), then reinserts. Connects as the cpi superuser
(CPI_DATABASE_URL) which bypasses RLS, so ALT-tagged rows insert directly.

Run inside the API container (has python3 + SQLAlchemy + DB env):
    docker cp scripts/seed_demo_altitude.py cpi-api-1:/tmp/seed.py
    docker exec cpi-api-1 python /tmp/seed.py

All data is fabricated. NO real JY/PW/FJL rows are copied. Sky Airways is a
LHR-centric UK/European short-haul carrier (routes deliberately disjoint from
the JY Caribbean network). Fares are positioned so ALT undercuts on 4 routes
and sits premium on 4 routes, for interesting fare-gap / undercut charts.
"""
import os
import random
from datetime import date, timedelta

import sqlalchemy as sa

ALT_TID = "ee000000-0000-0000-0000-000000000001"
random.seed(42)  # deterministic synthetic noise

# Network (LHR-centric, disjoint from the JY Caribbean routes)
# (origin, dest, market_base_GBP, alt_position)  alt_position>0 => premium
ROUTES = [
    ("LHR", "CDG", 120, 0.15),
    ("LHR", "AMS", 110, -0.16),
    ("LHR", "DUB", 90, -0.18),
    ("LGW", "BCN", 140, 0.12),
    ("MAN", "DUB", 85, -0.14),
    ("LHR", "EDI", 95, 0.14),
    ("LGW", "FAO", 160, -0.20),
    ("BHX", "AMS", 130, 0.16),
]
EQP_BY_ROUTE = {
    "LHRCDG": "320", "LHRAMS": "319", "LHRDUB": "32N", "LGWBCN": "738",
    "MANDUB": "AT7", "LHREDI": "321", "LGWFAO": "738", "BHXAMS": "E90",
}

# Competitors and their market position (relative to route base)
COMPS = [("MR", 0.04), ("CD", 0.00), ("VR", -0.06), ("SX", 0.09)]

TRIPS = [("OW", 1.0), ("RT", 1.9)]

LATEST_CAP = date(2026, 6, 2)
# 12 weekly capture snapshots ending at the latest (~2.5 months back)
CAP_DATES = [LATEST_CAP - timedelta(weeks=k) for k in range(12)]
# 6 forward departure dates (after the latest cap_date) shared by fares+velocity
DEP_DATES = [date(2026, 6, 13) + timedelta(days=14 * k) for k in range(6)]

# Per-cap_date price trend: fares firm as the departure window nears, scaling
# from ~0.8x at the earliest snapshot up to ~1.4x at the latest. The SAME factor
# is applied to the host carrier and every competitor, so the 4-undercut /
# 4-premium ordering is preserved (only the absolute level, and hence the
# fare-gap magnitude, moves) — which makes the avg-fare tiles/charts visibly
# respond when the Cap Date filter changes on stage.
_N_CAPS = len(CAP_DATES)
CAP_TREND = {cap: 0.8 + 0.6 * (_N_CAPS - 1 - i) / (_N_CAPS - 1)
             for i, cap in enumerate(CAP_DATES)}


def _decompose(tot):
    """Split a headline fare into yq / tax / base (all > 0, sum == tot)."""
    tot = max(25.0, round(tot, 2))
    yq = round(tot * 0.12, 2)
    tax = round(tot * 0.18, 2)
    base = round(tot - yq - tax, 2)
    return base, tax, yq


def build_airline_rows():
    rows = []
    for cap in CAP_DATES:
        trend = CAP_TREND[cap]
        for (org, dst, base, alt_pos) in ROUTES:
            for (trip, tmult) in TRIPS:
                for dep in DEP_DATES:
                    noise_a = 1 + random.uniform(-0.04, 0.04)
                    alt_tot = base * (1 + alt_pos) * tmult * trend * noise_a
                    alt_base, alt_tax, alt_yq = _decompose(alt_tot)
                    for (comp_al, comp_pos) in COMPS:
                        noise_c = 1 + random.uniform(-0.05, 0.05)
                        comp_tot = base * (1 + comp_pos) * tmult * trend * noise_c
                        c_base, c_tax, c_yq = _decompose(comp_tot)
                        rows.append({
                            "tenant_id": ALT_TID,
                            "cap_date": cap, "cap_time": "06:00:00",
                            "trip_type": trip,
                            "ref_al": "SKY",
                            "ref_flt_num": "ALT" + org[0] + dst[0] + str(random.randint(100, 999)),
                            "ref_org": org, "ref_dst": dst,
                            "ref_dep_date": dep, "ref_cab_code": "Y",
                            "ref_curr": "GBP",
                            "ref_tot_fare": round(alt_base + alt_tax + alt_yq, 2),
                            "ref_base_fare": alt_base, "ref_tax": alt_tax, "ref_yq": alt_yq,
                            "ref_seats": random.randint(1, 9),
                            "comp_al": comp_al,
                            "comp_flt_num": comp_al + str(random.randint(100, 999)),
                            "comp_org": org, "comp_dst": dst,
                            "comp_dep_date": dep, "comp_cab_code": "Y",
                            "comp_curr": "GBP",
                            "comp_tot_fare": round(c_base + c_tax + c_yq, 2),
                            "comp_base_fare": c_base, "comp_tax": c_tax, "comp_yq": c_yq,
                            "comp_seats": random.randint(1, 9),
                            "data_owner": "ALT", "tenant_code": "ALT",
                            "business_type": "AIRLINE", "report_date": cap,
                            "source_file": "seed_demo_altitude",
                        })
    return rows


def build_velocity_rows():
    rows = []
    cap_pax = {"LHRCDG": 116, "LHRAMS": 110, "LHRDUB": 96, "LGWBCN": 120,
               "MANDUB": 84, "LHREDI": 100, "LGWFAO": 120, "BHXAMS": 90}
    for cap in CAP_DATES:
        for (org, dst, base, _pos) in ROUTES:
            cp = org + dst
            pax = cap_pax[cp]
            for dep in DEP_DATES:
                days_left = (dep - cap).days
                frac = max(0.06, min(0.97, 1 - days_left / 180.0))
                frac *= (1 + random.uniform(-0.05, 0.05))
                frac = max(0.05, min(0.98, frac))
                booking = max(4, int(round(pax * frac)))
                booking = min(booking, pax - 2)
                asf = max(1, min(99, int(round(booking / pax * 100))))
                fsf = min(99, asf + random.randint(2, 8))
                for legseg in ("Leg", "Segment"):
                    rows.append({
                        "tenant_id": ALT_TID,
                        "dep_date": dep, "dep_time": "0700",
                        "dep_code": str(random.randint(1000, 1999)),
                        "city_pair": cp, "origin": org, "destination": dst,
                        "eqp": EQP_BY_ROUTE[cp], "legseg_type": legseg,
                        "leg_seg_order": 1, "days_left": days_left,
                        "compartment": "Y",
                        "current_booking": booking, "capacity": pax,
                        "actual_seat_factor": asf, "forecasted_seat_factor": fsf,
                        "data_owner": "ALT", "tenant_code": "ALT",
                        "business_type": "AIRLINE", "report_date": cap,
                        "airline_code": "ALT", "source_file": "seed_demo_altitude",
                    })
    return rows


AIR_INSERT = sa.text("""
INSERT INTO airline_cpi_snapshot
 (tenant_id, cap_date, cap_time, trip_type, ref_al, ref_flt_num, ref_org, ref_dst,
  ref_dep_date, ref_cab_code, ref_curr, ref_tot_fare, ref_base_fare, ref_tax, ref_yq,
  ref_seats, comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
  comp_curr, comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats,
  data_owner, tenant_code, business_type, report_date, source_file)
VALUES
 (:tenant_id, :cap_date, :cap_time, :trip_type, :ref_al, :ref_flt_num, :ref_org, :ref_dst,
  :ref_dep_date, :ref_cab_code, :ref_curr, :ref_tot_fare, :ref_base_fare, :ref_tax, :ref_yq,
  :ref_seats, :comp_al, :comp_flt_num, :comp_org, :comp_dst, :comp_dep_date, :comp_cab_code,
  :comp_curr, :comp_tot_fare, :comp_base_fare, :comp_tax, :comp_yq, :comp_seats,
  :data_owner, :tenant_code, :business_type, :report_date, :source_file)
""")

VEL_INSERT = sa.text("""
INSERT INTO velocity_snapshot
 (tenant_id, dep_date, dep_time, dep_code, city_pair, origin, destination, eqp,
  legseg_type, leg_seg_order, days_left, compartment, current_booking, capacity,
  actual_seat_factor, forecasted_seat_factor, data_owner, tenant_code, business_type,
  report_date, airline_code, source_file)
VALUES
 (:tenant_id, :dep_date, :dep_time, :dep_code, :city_pair, :origin, :destination, :eqp,
  :legseg_type, :leg_seg_order, :days_left, :compartment, :current_booking, :capacity,
  :actual_seat_factor, :forecasted_seat_factor, :data_owner, :tenant_code, :business_type,
  :report_date, :airline_code, :source_file)
""")


def main():
    url = os.environ["CPI_DATABASE_URL"]
    engine = sa.create_engine(url)
    air = build_airline_rows()
    vel = build_velocity_rows()
    with engine.begin() as conn:
        d1 = conn.execute(sa.text("DELETE FROM airline_cpi_snapshot WHERE tenant_code='ALT'")).rowcount
        d2 = conn.execute(sa.text("DELETE FROM velocity_snapshot WHERE airline_code='ALT'")).rowcount
        conn.execute(AIR_INSERT, air)
        conn.execute(VEL_INSERT, vel)
    with engine.connect() as conn:
        a = conn.execute(sa.text("SELECT count(*), min(ref_tot_fare), max(ref_tot_fare) FROM airline_cpi_snapshot WHERE tenant_code='ALT'")).fetchone()
        v = conn.execute(sa.text("SELECT count(*), min(actual_seat_factor), max(actual_seat_factor) FROM velocity_snapshot WHERE airline_code='ALT'")).fetchone()
        z = conn.execute(sa.text("SELECT count(*) FROM airline_cpi_snapshot WHERE tenant_code='ALT' AND (ref_tot_fare<=0 OR comp_tot_fare<=0)")).scalar()
    print("deleted: %d fare, %d velocity rows (idempotent reset)" % (d1, d2))
    print("inserted airline_cpi_snapshot: %d rows  (ref_tot_fare %s..%s GBP)" % (a[0], a[1], a[2]))
    print("inserted velocity_snapshot:    %d rows  (actual_seat_factor %s..%s)" % (v[0], v[1], v[2]))
    print("zero-fare rows (must be 0): %s" % z)


if __name__ == "__main__":
    main()
