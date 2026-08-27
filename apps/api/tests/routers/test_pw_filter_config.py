"""PW (dashboard "2") wiring for the WinAir-family global filter bar.

Same conventions as test_price_points_availability.py: handlers are invoked
directly (no TestClient anywhere in this suite), every parameter is passed
explicitly, and Superset I/O is monkeypatched at the SupersetClient singleton
so no live Superset is needed. The handlers are async, so tests drive them
with asyncio.run() rather than depending on a pytest-asyncio mode.

The native-filter fixture mirrors what dev dashboard 3 actually defines
(read from superset.db 2026-08-27): eight filter_select filters across
datasets 4 / 25 / 26. PW's hidden set suppresses four of them; PW's carrier
column is `carrier` (NOT `airline` as on JY/WM/DA/5L), and unlike WM/DA/5L
there are no price_status/recommendation/lowest_competitor filters to hide —
listing any of those here would itself be the stale-entry bug these tests
watch for.

Run just this file (the full suite has known-unrelated failures):

    pytest tests/routers/test_pw_filter_config.py -q
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import superset as ss


def _f(fid: str, name: str, column: str, dataset_id: int, charts_in_scope=None):
    entry = {
        "id": fid,
        "name": name,
        "filterType": "filter_select",
        "targets": [{"datasetId": dataset_id, "column": {"name": column}}],
        "controlValues": {"multiSelect": True},
    }
    if charts_in_scope is not None:
        entry["chartsInScope"] = charts_in_scope
    return entry


# Dev dashboard 3's eight filters, in Superset's own order. Trip_Type's scope
# excludes every chart — it exists purely as a value source for the bar.
DASH3_FILTERS = [
    _f("NATIVE_FILTER-TripType", "Trip_Type", "trip_type", 4, []),
    _f("NATIVE_FILTER-Route", "Route", "route", 25, [76, 77, 78, 79, 80, 81, 82, 83]),
    _f("NATIVE_FILTER-Carrier", "Carrier", "carrier", 25, [76, 77, 78, 79, 80, 81, 83]),
    _f("NATIVE_FILTER-FlightNumber", "Flight Number", "flt_num", 25, [76, 77, 78, 79, 80, 81, 83]),
    _f("NATIVE_FILTER-DTDBucket", "Days to Departure", "dtd_bucket", 25, [76, 77, 78, 79, 80, 81, 83]),
    _f("NATIVE_FILTER-DaysLeft", "Days Left", "days_left", 26, [82]),
    _f("NATIVE_FILTER-Aircraft", "Aircraft", "eqp", 26, [82]),
    _f("NATIVE_FILTER-LegSegment", "Leg/Segment", "legseg_type", 26, [82]),
]

KEPT = ["trip_type", "route", "flt_num", "days_left"]
HIDDEN = {"carrier", "dtd_bucket", "eqp", "legseg_type"}


@pytest.fixture
def superset_stub(monkeypatch):
    """Stub the SupersetClient singleton: canned filters, recorded value fetches."""
    fetched: list[tuple[int, str]] = []

    async def fake_native_filters(superset_id: int):
        assert superset_id == 3  # PW's Superset id (app key "2" maps to dashboard 3)
        return DASH3_FILTERS

    async def fake_fetch_column_values(dataset_id: int, column: str, row_limit: int = 1000):
        fetched.append((dataset_id, column))
        return ["v1", "v2"]

    monkeypatch.setattr(ss.superset_client, "get_native_filters", fake_native_filters)
    monkeypatch.setattr(ss.superset_client, "fetch_column_values", fake_fetch_column_values)
    # The 300s values cache is process-global; keep tests order-independent.
    monkeypatch.setattr(ss, "_filter_values_cache", {})
    return fetched


# ── Registry shape ───────────────────────────────


def test_pw_registry_hides_exactly_four_columns():
    assert ss.DASHBOARDS["2"]["hidden_filter_columns"] == HIDDEN


def test_pw_hidden_set_lowercased_and_absent_key_is_empty():
    assert ss._hidden_filter_columns(ss.DASHBOARDS["2"]) == HIDDEN
    # Dashboards without the key (FJL here) keep every filter — absent == set().
    assert ss._hidden_filter_columns(ss.DASHBOARDS["3"]) == set()


def test_pw_hidden_set_names_no_foreign_columns():
    # PW's carrier filter targets `carrier` — hiding `airline` (the JY/WM/DA/5L
    # column name) would be a copy-paste trap that leaves Carrier visible AND
    # trips the stale-entry error log on every /filter-config call. Likewise
    # the WM/DA/5L-only filters do not exist on dashboard 3.
    hidden = ss.DASHBOARDS["2"]["hidden_filter_columns"]
    assert "airline" not in hidden
    assert not {"price_status", "recommendation", "lowest_competitor"} & hidden


# ── /filter-config read side ─────────────────────


def test_filter_config_returns_only_kept_filters(superset_stub):
    out = asyncio.run(
        ss.get_dashboard_filter_config("2", user_identity="PW", user_roles=["TENANT_ADMIN"])
    )
    assert out["dashboard_id"] == "2"
    assert [f["field"] for f in out["filters"]] == KEPT  # Superset order, hidden gone
    assert all(f["values"] == ["v1", "v2"] for f in out["filters"])


def test_filter_config_never_fetches_values_for_hidden_columns(superset_stub):
    asyncio.run(
        ss.get_dashboard_filter_config("2", user_identity="PW", user_roles=["TENANT_ADMIN"])
    )
    fetched_columns = {col for _, col in superset_stub}
    assert fetched_columns == set(KEPT)  # suppressed filters cost no query


def test_filter_config_logs_no_stale_entry_for_pw(superset_stub, caplog):
    with caplog.at_level("ERROR"):
        asyncio.run(
            ss.get_dashboard_filter_config("2", user_identity="PW", user_roles=["TENANT_ADMIN"])
        )
    assert "hidden_filter_columns entry" not in caplog.text


# ── /filter-params write side ────────────────────


def test_filter_params_drops_hidden_and_keeps_visible(superset_stub):
    req = ss.FilterParamsRequest(
        selections={
            "NATIVE_FILTER-Carrier": ["PW"],  # hidden -> silently dropped
            "NATIVE_FILTER-Route": ["ANU → DOM"],  # kept -> present in the rison
        }
    )
    out = asyncio.run(
        ss.build_dashboard_filter_params(
            "2", req, user_identity="PW", user_roles=["TENANT_ADMIN"]
        )
    )
    rison = out["native_filters"]
    assert "NATIVE_FILTER-Route" in rison
    assert "NATIVE_FILTER-Carrier" not in rison


# ── Access control ───────────────────────────────


def test_dashboard_2_access_is_pw_only():
    dash = ss._require_tenant_dashboard("2", "PW", ["TENANT_ADMIN"])
    assert dash["tenant"] == "PW"

    with pytest.raises(HTTPException) as e:
        ss._require_tenant_dashboard("2", "JY", ["TENANT_ADMIN"])
    assert e.value.status_code == 403

    with pytest.raises(HTTPException) as e:
        ss._require_tenant_dashboard("2", "RTS", ["TENANT_ADMIN"])
    assert e.value.status_code == 403
