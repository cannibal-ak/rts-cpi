"""trip_type scoping on /airline/price-points/history.

Same conventions as test_price_points_availability.py: direct handler calls
against the transactional ``db_session`` fixture, WM fixture rows under
impossible-collision keys. The seeding helpers (and the wm_tenant_id
fixture) are imported from that file so the NOT-NULL column list has one
home.

The subject: a tenant carrying both OW and RT rows (5L is the first) has
TWO fare lines for the same airline/flight/date. Without a trip_type
predicate the history endpoint unions them into one mixed series.

Run ONLY this file (the full suite has known-unrelated failures):
    pytest tests/routers/test_price_history.py -q
"""

from tests.routers.test_price_points_availability import (  # noqa: F401
    CAP_DATE,
    DAY,
    _seed,
    wm_tenant_id,
)

from app.routers.airline import price_point_history

DEP_DATE = CAP_DATE + 10 * DAY


def _history(db, **overrides):
    """Direct handler call with every parameter passed explicitly."""
    db.flush()
    kwargs = dict(
        db=db,
        user_roles=["TENANT_ADMIN"],
        user_identity="RTS",
        tenant="WM",
        origin="ZZA",
        destination="ZZB",
        airline="WM",
        dep_date=DEP_DATE.isoformat(),
        flt_num=None,
        trip_type=None,
    )
    kwargs.update(overrides)
    return price_point_history(**kwargs)


def _seed_both_types(db, tenant_id):
    """Two captures x two itinerary types of the same WM flight/date.

    Distinct fares per (capture, trip_type) so every row survives the
    endpoint's SELECT DISTINCT and the mix is visible when unfiltered.
    """
    for cap_offset, ow_fare, rt_fare in ((0, 100, 150), (1, 110, 160)):
        for trip_type, fare in (("OW", ow_fare), ("RT", rt_fare)):
            _seed(
                db, tenant_id,
                cap_date=CAP_DATE + cap_offset * DAY,
                trip_type=trip_type,
                ref_dep_date=DEP_DATE,
                ref_tot_fare=fare,
                # Blank the competitor half so airline='WM' is the only match.
                comp_al="",
                comp_flt_num="",
                comp_tot_fare=0,
            )


def test_unfiltered_mixes_both_types(db_session, wm_tenant_id):
    """Back-compat: no trip_type returns every fare of the flight/date."""
    _seed_both_types(db_session, wm_tenant_id)
    resp = _history(db_session)
    assert sorted(p.tot_fare for p in resp.points) == [100, 110, 150, 160]
    assert resp.trip_type is None


def test_trip_type_scopes_history(db_session, wm_tenant_id):
    """trip_type pins the history to one itinerary type's fare line."""
    _seed_both_types(db_session, wm_tenant_id)
    ow = _history(db_session, trip_type="OW")
    assert sorted(p.tot_fare for p in ow.points) == [100, 110]
    assert ow.trip_type == "OW"
    rt = _history(db_session, trip_type="RT")
    assert sorted(p.tot_fare for p in rt.points) == [150, 160]
    assert rt.trip_type == "RT"


def test_trip_type_scopes_competitor_half(db_session, wm_tenant_id):
    """The predicate rides on the comp half of the union too."""
    for trip_type, fare in (("OW", 90), ("RT", 130)):
        _seed(
            db_session, wm_tenant_id,
            trip_type=trip_type,
            comp_dep_date=DEP_DATE,
            comp_tot_fare=fare,
            # Push the ref half off the queried dep_date so only the
            # competitor (XX) side answers.
            ref_dep_date=DEP_DATE + DAY,
        )
    rt = _history(db_session, airline="XX", trip_type="RT")
    assert sorted(p.tot_fare for p in rt.points) == [130]
