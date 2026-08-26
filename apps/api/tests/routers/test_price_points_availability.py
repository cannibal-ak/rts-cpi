"""Availability markers on /airline/price-points (no-fare day classification).

Mirrors the direct-handler-call convention of tests/test_subtenant_role.py:
list_price_points() is invoked against the transactional ``db_session``
fixture (all writes rolled back at test end). No TestClient/HTTP layer; the
platform-admin identity selects the WM view via the tenant parameter.

Fixture rows go straight into airline_cpi_snapshot with tenant_code='WM'
under impossible-collision keys (cap_date 1999-01-01, markets ZZA-ZZB /
ZZC-ZZD), so they can never shadow real WM data. The test engine connects
as the RLS-bypassing superuser role, so the WM view sees the rows without a
tenant GUC; add set_tenant_context to the seeding if that ever changes.

Run ONLY this file (the full suite has known-unrelated failures):
    pytest tests/routers/test_price_points_availability.py -q

Covers:
  a) ref sold-out day          b) ref blank-block day
  c) mixed day -> no marker    d) sold_out wins in a day-group (bool_or)
  e) comp both classes; blank comp_al dropped
  f) ref dedup across competitor copies
  g) include_availability default-off back-compat
  h) stops / flt_num suppression
  i) cap_date + dep window + airlines + multi-market scoping
  j) trip_type filters points and SCOPES markers (no suppression)
"""

import inspect
import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import text

from app.models.airline import AirlineCpiSnapshot
from app.routers.airline import list_price_points

CAP_DATE = date(1999, 1, 1)
DAY = timedelta(days=1)


@pytest.fixture
def wm_tenant_id(db_session):
    """The WinAir tenant UUID — the NOT NULL FK every fixture row needs."""
    tid = db_session.execute(
        text("SELECT id FROM tenant WHERE slug = 'wm'")
    ).scalar()
    if tid is None:
        pytest.skip("WinAir tenant (slug='wm') not present in DB")
    return tid


def _seed(db, tenant_id, **overrides):
    """One snapshot row with every NOT NULL column filled; overrides win.

    The defaults are an ordinary on-sale row on ZZA-ZZB — WM reference fare
    100 against competitor XX fare 90, both departing CAP_DATE+10 — so a
    test only states the half it is exercising.
    """
    values = dict(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        tenant_code="WM",
        cap_date=CAP_DATE,
        cap_time=time(6, 0),
        trip_type="OW",
        ref_al="WM",
        ref_flt_num="101",
        ref_org="ZZA",
        ref_dst="ZZB",
        ref_dep_date=CAP_DATE + 10 * DAY,
        ref_cab_code="Y",
        ref_tot_fare=100,
        ref_base_fare=80,
        ref_tax=15,
        ref_yq=5,
        # yr is nullable in the table but PricePointOut requires it, and real
        # feed rows always carry it — a NULL here would fail the on-sale path.
        ref_yr=0,
        ref_seats=9,
        ref_stops=0,
        comp_al="XX",
        comp_flt_num="201",
        comp_org="ZZA",
        comp_dst="ZZB",
        comp_dep_date=CAP_DATE + 10 * DAY,
        comp_cab_code="Y",
        comp_tot_fare=90,
        comp_base_fare=70,
        comp_tax=15,
        comp_yq=5,
        comp_yr=0,
        comp_seats=9,
    )
    values.update(overrides)
    # Seeding through the ORM model doubles as a drift guard: if the model
    # ever disagrees with the live schema again, this INSERT fails loudly.
    db.add(AirlineCpiSnapshot(**values))


def _call(db, **overrides):
    """Direct handler call with every parameter passed explicitly.

    Bypassing the DI layer means the signature defaults are fastapi Query
    markers, not values, so nothing may be omitted. cap_date is always
    pinned to the fixture date — leaving it unset would pin to the tenant's
    real newest capture and see none of the seeded rows.
    """
    db.flush()  # seeded rows must reach the DB before the raw SQL reads it
    kwargs = dict(
        db=db,
        user_roles=["TENANT_ADMIN"],
        user_identity="RTS",
        tenant="WM",
        routes="ZZA-ZZB",
        origin=None,
        destination=None,
        cap_date=CAP_DATE.isoformat(),
        airlines=None,
        dep_from=None,
        dep_to=None,
        stops=None,
        flt_num=None,
        trip_type=None,
        include_availability=True,
    )
    kwargs.update(overrides)
    return list_price_points(**kwargs)


def _days(resp):
    """(market, airline, dep_date, status, dbd) tuples in response order."""
    return [
        (d.market, d.airline, d.dep_date, d.status, d.dbd)
        for d in resp.no_fare_days
    ]


# ── (a) ref sold-out day ─────────────────────────────────────────────────────

def test_ref_sold_out_day(db_session, wm_tenant_id):
    """Zero ref fare WITH a stops count -> one sold_out marker for WM."""
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1)
    resp = _call(db_session)
    assert _days(resp) == [("ZZA-ZZB", "WM", CAP_DATE + 10 * DAY, "sold_out", 10)]
    assert resp.availability_suppressed is False
    # The marker joins to its line on the exact market string the points
    # carry (the on-sale competitor half yields one).
    assert resp.points and resp.points[0].market == resp.no_fare_days[0].market


# ── (b) ref blank-block day ──────────────────────────────────────────────────

def test_ref_blank_block_day(db_session, wm_tenant_id):
    """Zero ref fare with NULL stops (blank source block) -> not_on_sale."""
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=None, ref_flt_num="")
    resp = _call(db_session)
    assert _days(resp) == [("ZZA-ZZB", "WM", CAP_DATE + 10 * DAY, "not_on_sale", 10)]


# ── (c) mixed day -> no marker ───────────────────────────────────────────────

def test_mixed_day_has_no_marker(db_session, wm_tenant_id):
    """Any purchasable fare on the day disqualifies it (HAVING clause)."""
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1)
    _seed(db_session, wm_tenant_id, ref_tot_fare=120, ref_flt_num="103")
    resp = _call(db_session)
    assert resp.no_fare_days == []


# ── (d) sold_out wins inside a day-group ─────────────────────────────────────

def test_sold_out_wins_inside_day_group(db_session, wm_tenant_id):
    """bool_or: one sold-out flight outweighs blank flights the same day."""
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=None, ref_flt_num="")
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=2, ref_flt_num="102")
    resp = _call(db_session)
    assert _days(resp) == [("ZZA-ZZB", "WM", CAP_DATE + 10 * DAY, "sold_out", 10)]


# ── (e) comp classes + blank comp_al guard ───────────────────────────────────

def test_comp_classes_and_blank_comp_al_dropped(db_session, wm_tenant_id):
    """Comp CASE keys on flight number; a wholly-blank comp half is dropped."""
    _seed(db_session, wm_tenant_id, comp_al="QQ", comp_tot_fare=0, comp_flt_num="301")
    _seed(db_session, wm_tenant_id, comp_al="RR", comp_tot_fare=0, comp_flt_num="")
    _seed(db_session, wm_tenant_id, comp_al="", comp_tot_fare=0, comp_flt_num="")
    resp = _call(db_session)
    # Ordered by market, dep_date, airline; no marker for airline ''.
    assert _days(resp) == [
        ("ZZA-ZZB", "QQ", CAP_DATE + 10 * DAY, "sold_out", 10),
        ("ZZA-ZZB", "RR", CAP_DATE + 10 * DAY, "not_on_sale", 10),
    ]


# ── (f) ref dedup across competitor copies ───────────────────────────────────

def test_ref_dedup_across_competitor_copies(db_session, wm_tenant_id):
    """A ref flight stored once per competitor still yields ONE marker."""
    for i, comp in enumerate(("AA", "BB", "CC")):
        _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1,
              comp_al=comp, comp_flt_num=f"30{i}", comp_tot_fare=90 + i)
    resp = _call(db_session)
    assert _days(resp) == [("ZZA-ZZB", "WM", CAP_DATE + 10 * DAY, "sold_out", 10)]


# ── (g) default-off back-compat ──────────────────────────────────────────────

def test_include_availability_defaults_off(db_session, wm_tenant_id):
    """Without the opt-in the response shape is exactly what it always was."""
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1)
    resp = _call(db_session, include_availability=False)
    assert resp.no_fare_days == []
    assert resp.availability_suppressed is False
    # The on-sale competitor point is untouched by the feature being off.
    assert [p.airline for p in resp.points] == ["XX"]
    # And the route-level Query default really is off.
    param = inspect.signature(list_price_points).parameters["include_availability"]
    assert param.default.default is False


# ── (h) stops / flt_num suppression ──────────────────────────────────────────

@pytest.mark.parametrize("filt", [{"stops": 1}, {"flt_num": "101"}])
def test_stops_and_flt_num_suppress_markers(db_session, wm_tenant_id, filt):
    """A no-fare day can't honestly satisfy stops/flt_num filters -> flag."""
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1)
    resp = _call(db_session, **filt)
    assert resp.no_fare_days == []
    assert resp.availability_suppressed is True


# ── (i) scoping: cap_date + dep window + airlines + markets ──────────────────

def test_scoping_dep_window_airlines_markets(db_session, wm_tenant_id):
    """Markers obey the same cap_date/dep-window/airlines/market predicates."""
    d5 = CAP_DATE + 5 * DAY
    # In-window sold-out days on both requested markets.
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1,
          ref_dep_date=d5, comp_dep_date=d5)
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1,
          ref_org="ZZC", ref_dst="ZZD", comp_org="ZZC", comp_dst="ZZD",
          ref_dep_date=d5, comp_dep_date=d5)
    # Below dep_from and above dep_to -> both excluded.
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1,
          ref_dep_date=CAP_DATE + 1 * DAY, comp_dep_date=CAP_DATE + 1 * DAY)
    _seed(db_session, wm_tenant_id, ref_tot_fare=0, ref_stops=1,
          ref_dep_date=CAP_DATE + 40 * DAY, comp_dep_date=CAP_DATE + 40 * DAY)
    # Non-WM no-fare comp day in-window -> excluded by the airlines filter.
    _seed(db_session, wm_tenant_id, comp_al="QQ", comp_tot_fare=0,
          comp_flt_num="301", comp_dep_date=d5)
    # Different capture -> excluded by the cap_date equality. Distinct
    # dep_date so a leak would surface as its own spurious marker.
    _seed(db_session, wm_tenant_id, cap_date=CAP_DATE + DAY, ref_tot_fare=0,
          ref_stops=1, ref_dep_date=CAP_DATE + 7 * DAY,
          comp_dep_date=CAP_DATE + 7 * DAY)
    resp = _call(
        db_session,
        routes="ZZA-ZZB,ZZC-ZZD",
        airlines="WM",
        dep_from=(CAP_DATE + 2 * DAY).isoformat(),
        dep_to=(CAP_DATE + 30 * DAY).isoformat(),
    )
    assert _days(resp) == [
        ("ZZA-ZZB", "WM", d5, "sold_out", 5),
        ("ZZC-ZZD", "WM", d5, "sold_out", 5),
    ]


# ── (j) trip_type filters points and scopes markers ──────────────────────────

def test_trip_type_filters_points(db_session, wm_tenant_id):
    """trip_type narrows both halves of the union and rides along on points."""
    _seed(db_session, wm_tenant_id)                       # OW pair (100 / 90)
    _seed(db_session, wm_tenant_id, trip_type="RT",
          ref_flt_num="102", ref_tot_fare=120, comp_flt_num="202", comp_tot_fare=110)
    unfiltered = _call(db_session)
    assert sorted(p.trip_type for p in unfiltered.points) == ["OW", "OW", "RT", "RT"]
    ow = _call(db_session, trip_type="OW")
    assert sorted(p.tot_fare for p in ow.points) == [90, 100]
    assert all(p.trip_type == "OW" for p in ow.points)
    rt = _call(db_session, trip_type="RT")
    assert sorted(p.tot_fare for p in rt.points) == [110, 120]
    assert all(p.trip_type == "RT" for p in rt.points)


def test_trip_type_scopes_markers_not_suppresses(db_session, wm_tenant_id):
    """trip_type is populated on no-fare rows, so it SCOPES the markers.

    A day whose only purchasable fares are OW is not a no-fare day overall,
    but it IS one under trip_type=RT — and the flag stays down throughout.
    """
    _seed(db_session, wm_tenant_id)                       # OW on sale
    _seed(db_session, wm_tenant_id, trip_type="RT",       # RT sold out all day
          ref_tot_fare=0, ref_stops=1, ref_flt_num="102",
          comp_tot_fare=0, comp_flt_num="202")
    unfiltered = _call(db_session)
    assert unfiltered.no_fare_days == []                  # OW fares save the day
    rt = _call(db_session, trip_type="RT")
    assert rt.points == []
    assert _days(rt) == [
        ("ZZA-ZZB", "WM", CAP_DATE + 10 * DAY, "sold_out", 10),
        ("ZZA-ZZB", "XX", CAP_DATE + 10 * DAY, "sold_out", 10),
    ]
    assert rt.availability_suppressed is False
