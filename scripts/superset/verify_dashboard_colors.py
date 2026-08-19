#!/usr/bin/env python3
"""Verify a dashboard's charts return data AND that label_colors actually binds.

Two failures this catches that nothing else does:

  1. A chart that passes an engine-level dry run and 400s on the dashboard.
     QueryContext.get_payload() skips the duplicate-label validator the REST
     endpoint runs, so testing in-container proves less than it looks.
     This posts to /api/v1/chart/data with a guest token, the real path.

  2. A label_colors key that does not match the series name Superset builds.
     There is no error for this -- the key is ignored and the chart falls
     through to rts_cpi_palette[0], forest green. The only way to know is to
     ask the API what series it actually built and compare.

Run inside the superset container (it needs superset.db and requests):

    # get a guest token from the CPI API first, e.g.
    #   GET /api/v1/superset/guest-token?dashboard_id=<app id>
    docker cp scripts/superset/verify_dashboard_colors.py cpi-superset-1:/tmp/
    docker exec cpi-superset-1 python3 /tmp/verify_dashboard_colors.py 7 "<guest-token>"

Exit status is non-zero if any chart errors or any series is unbound, so it
can gate a deploy.
"""
import json
import sqlite3
import sys

import requests

DB = "/app/superset_home/superset.db"
SUPERSET = "http://localhost:8088"

# Viz types that colour by series. A table has no series to colour, so an
# unbound name there is not a finding.
COLOURED_VIZ = {
    "echarts_timeseries_line", "echarts_timeseries_bar", "echarts_timeseries",
    "mixed_timeseries", "dist_bar", "echarts_area", "pie",
}
# Column names that are the axis, never a series.
AXIS_NAMES = {"__timestamp", "travel_date", "dep_date", "cap_date", "date"}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    dash_id = int(sys.argv[1])
    guest = sys.argv[2]

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    row = con.execute("SELECT dashboard_title, json_metadata FROM dashboards WHERE id=?",
                      (dash_id,)).fetchone()
    if row is None:
        print(f"no dashboard {dash_id}")
        return 2
    bound = json.loads(row["json_metadata"] or "{}").get("label_colors", {})
    print(f"dashboard {dash_id}: {row['dashboard_title']}")
    print(f"label_colors: {len(bound)} keys\n")

    slices = con.execute(
        "SELECT s.id, s.slice_name, s.viz_type, s.query_context "
        "FROM slices s JOIN dashboard_slices ds ON ds.slice_id = s.id "
        "WHERE ds.dashboard_id = ? ORDER BY s.id", (dash_id,)).fetchall()

    # MUST be X-GuestToken (GUEST_TOKEN_HEADER_NAME in infra/superset_config.py).
    # With Authorization: Bearer the request still authenticates, but Superset
    # does not treat it as a guest user, so the token's RLS rules -- including
    # the cap_date clause -- are silently NOT applied and the check passes on
    # unfiltered data the dashboard would never show.
    hdr = {"X-GuestToken": guest, "Content-Type": "application/json"}
    errors, unbound_all, empty = [], set(), []

    for s in slices:
        name = s["slice_name"][:42]
        if not s["query_context"]:
            print(f"  {s['id']} {name:44s} SKIP (no query_context)")
            continue
        qc = json.loads(s["query_context"])
        # the guest-access branch requires dashboardId in form_data
        qc.setdefault("form_data", {})["dashboardId"] = dash_id
        qc["result_format"] = "json"
        qc["result_type"] = "full"
        qc["force"] = True   # bypass the chart cache; a hit would mask a real failure

        try:
            r = requests.post(f"{SUPERSET}/api/v1/chart/data", headers=hdr,
                              data=json.dumps(qc), timeout=180)
        except Exception as exc:  # noqa: BLE001
            print(f"  {s['id']} {name:44s} EXC {exc}")
            errors.append(s["id"])
            continue
        if r.status_code != 200:
            print(f"  {s['id']} {name:44s} HTTP {r.status_code} {r.text[:120]}")
            errors.append(s["id"])
            continue

        result = r.json()["result"]
        rows = sum(q.get("rowcount", 0) for q in result)

        series = []
        for qi, q in enumerate(result):
            cols = q.get("colnames", [])
            cand = cols[1:] if cols else []
            # mixed_timeseries appends " (1)" to every query-B series name;
            # the legend shows the bare name but the colour lookup is suffixed
            if s["viz_type"] == "mixed_timeseries" and qi == 1:
                cand = [f"{x} (1)" for x in cand]
            series.extend(cand)
        series = [x for x in series if x not in AXIS_NAMES]

        if s["viz_type"] in COLOURED_VIZ:
            miss = sorted({x for x in series if x not in bound})
            status = "ALL BOUND" if not miss else f"{len(miss)} UNBOUND"
            unbound_all.update(miss)
        else:
            status = "n/a (no series colour)"

        print(f"  {s['id']} {name:44s} {s['viz_type']:24s} rows={rows:<7} {status}")
        if s["viz_type"] in COLOURED_VIZ and series and not rows:
            empty.append(s["id"])
        if s["viz_type"] in COLOURED_VIZ:
            miss = sorted({x for x in series if x not in bound})
            if miss:
                print(f"       built but unbound: {miss}")

    print()
    if empty:
        print(f"WARNING: 200 but zero rows: {empty}")
    if errors or unbound_all:
        if errors:
            print(f"FAIL: charts erroring: {errors}")
        if unbound_all:
            print(f"FAIL: {len(unbound_all)} series would fall through to the "
                  f"scheme default: {sorted(unbound_all)}")
        return 1
    print("PASS: every chart returns data and every coloured series is bound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
