#!/usr/bin/env python3
"""Give every carrier its identity colour across dashboard 6 (WinAir).

Two independent pieces, one transaction:

1. REPLACE "Competitor Breakdown" (slice 97, legacy dist_bar) with a clone
   built as echarts_timeseries_bar. dist_bar colours by SERIES, and 97's only
   series is the metric "Avg Fare" — the airlines are x-axis categories, so
   per-carrier bars are structurally unreachable in that viz type (the earlier
   "Avg Fare" -> red key made the bars uniform red, which is not what carrier
   identity means). The clone makes the airline the series:
     x_axis=airline + groupby=[airline] + truncate_metric -> series are the
     BARE carrier codes -> Palette A binds -> WM red, 5L green, 7Z violet,
     BW gold, DM cyan, JY blue, S6 magenta — matching every other chart and
     the native Latest Prices panel.
   Shape verified by an in-container dry run against ds 32 (result columns
   ['airline','5L','7Z','BW','DM','JY','S6','WM']); stack=true collapses the
   diagonal matrix to one full-width bar per carrier; x_axis_sort_series="sum"
   descending restores 97's value ordering (x_axis_sort is dead when groupby
   is present); show_value+only_total prints one $ label per bar.
   Slice 97 itself is NOT modified — it is parked off the dashboard (the
   slice-104 pattern) and remains intact as instant rollback.

   The swap must touch every place the dashboard references chart 97 BY ID —
   missing one makes filters silently skip the new chart:
     * dashboard_slices row
     * position_json node (chartId + meta.uuid; sliceName text left as-is)
     * native_filter_configuration: 5 filters carry 97 in chartsInScope,
       6 carry it in scope.excluded
     * global_chart_configuration.chartsInScope
     * chart_configuration (cross-filter scopes), if present
   The app needs NO code change: tabs and chart lists are discovered live
   from position_json (verified in routers/superset.py + useDashboardTabs).

2. RECOLOUR slice 109's availability markers to match the NATIVE chart.
   The 14 scatter series ("Sold out, <AL>" / "Not on sale, <AL>") never bound
   their intended colours because mixed_timeseries suffixes query-B colour
   keys with " (1)". Rather than binding the old #D32F2F — which sits DeltaE 4
   from WM red and would make sold-out markers read as WM datapoints — they
   take the native panel's colours (LatestPricesPanel.tsx):
     sold out     #F39C12  (theme.palette.warning.main, mode-independent)
     not on sale  #9E9E9E  (text.disabled resolved on light paper)
   Both the " (1)"-suffixed keys (which bind) and the unsuffixed originals
   (kept consistent for the day the metrics move queries) are written.

Backups are KEY-LEVEL, not payload-level: another session edits dashboard 6
concurrently, and restoring whole blobs would discard their work. Revert
deletes the clone, re-links 97, and puts back exactly the keys we touched.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_carrier_consistency.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_carrier_consistency.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_carrier_consistency.py --show

Take the external superset.db backup BEFORE running, per standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys
import uuid as uuidlib

DB = "/app/superset_home/superset.db"
DASH_ID = 6
OLD_SLICE = 97
BACKUP_TABLE = "_wm_carrier_consistency_backup"

PALETTE_A = {
    "WM": "#CD1F25", "5L": "#1BAF7A", "7Z": "#8B5CF6", "BW": "#C08A00",
    "DM": "#0891B2", "JY": "#2A78D6", "S6": "#D6208F",
}
SOLD_OUT = "#F39C12"      # native theme.palette.warning.main
NOT_ON_SALE = "#9E9E9E"   # native text.disabled on light paper

MARKER_SLICE = 109
MARKER_KEYS = {}
for _code in PALETTE_A:
    MARKER_KEYS["Sold out, %s" % _code] = SOLD_OUT
    MARKER_KEYS["Sold out, %s (1)" % _code] = SOLD_OUT
    MARKER_KEYS["Not on sale, %s" % _code] = NOT_ON_SALE
    MARKER_KEYS["Not on sale, %s (1)" % _code] = NOT_ON_SALE

# ── clone definition (dry-run verified 2026-08-18) ──
CLONE_NAME = "Competitor Breakdown"
CLONE_METRIC = {
    "expressionType": "SQL",
    "sqlExpression": "ROUND(AVG(NULLIF(fare, 0))::numeric, 2)",
    "label": "Avg Fare",
    "hasCustomLabel": True,
    "optionName": "metric_avg_fare_comp97",
}
# The x-axis is an ADHOC column labelled "Airline", not the plain string
# "airline": the series column is also "airline", and the chart-data endpoint
# rejects duplicate labels across columns+metrics with a 400 ("Duplicate
# column/metric labels"). The engine-level dry run does NOT run that check —
# only the REST path does, which is exactly the path the dashboard uses.
CLONE_X_AXIS = {
    "expressionType": "SQL",
    "sqlExpression": "airline",
    "label": "Airline",
}
CLONE_PARAMS = {
    "datasource": "32__table",
    "viz_type": "echarts_timeseries_bar",
    "x_axis": CLONE_X_AXIS,
    "x_axis_sort_series": "sum",
    "x_axis_sort_series_ascending": False,
    "metrics": [CLONE_METRIC],
    "groupby": ["airline"],
    "adhoc_filters": [
        {"clause": "WHERE", "comparator": "No filter", "expressionType": "SIMPLE",
         "operator": "TEMPORAL_RANGE", "subject": "cap_date", "isExtra": False,
         "isNew": False, "filterOptionName": "filter_cap_date_comp97a"},
        {"clause": "WHERE", "comparator": "No filter", "expressionType": "SIMPLE",
         "operator": "TEMPORAL_RANGE", "subject": "travel_date", "isExtra": False,
         "isNew": False, "filterOptionName": "filter_travel_date_comp97b"},
    ],
    "order_desc": True,
    "row_limit": 100,
    "truncate_metric": True,
    "show_empty_columns": True,
    "stack": True,
    "show_value": True,
    "only_total": True,
    "show_legend": False,
    "legendType": "scroll",
    "legendOrientation": "top",
    "x_axis_title": "Airline",
    "x_axis_title_margin": 35,
    "y_axis_title": "Average Fare ($)",
    "y_axis_title_margin": 45,
    "y_axis_format": "$,.0f",
    "y_axis_bounds": [None, None],
    "rich_tooltip": True,
    "tooltipTimeFormat": "%d-%m-%Y",
    "x_axis_time_format": "%d/%m",
    "xAxisLabelRotation": 0,
    "truncateXAxis": False,
    "truncateYAxis": False,
    "zoomable": False,
    "color_scheme": "rts_cpi_palette",
    "label_colors": dict(PALETTE_A),
    "extra_form_data": {},
    "dashboards": [DASH_ID],
}


def clone_query_context(slice_id):
    fd = dict(CLONE_PARAMS)
    fd["slice_id"] = slice_id
    return {
        "datasource": {"id": 32, "type": "table"},
        "force": False,
        "result_format": "json",
        "result_type": "full",
        "queries": [{
            "filters": [
                {"col": "cap_date", "op": "TEMPORAL_RANGE", "val": "No filter"},
                {"col": "travel_date", "op": "TEMPORAL_RANGE", "val": "No filter"},
            ],
            "extras": {"having": "", "where": ""},
            "applied_time_extras": {},
            "columns": [
                {"columnType": "BASE_AXIS", "sqlExpression": "airline",
                 "label": "Airline", "expressionType": "SQL"},
                "airline",
            ],
            "metrics": [CLONE_METRIC],
            "orderby": [[CLONE_METRIC, False]],
            "annotation_layers": [],
            "row_limit": 100,
            "series_columns": ["airline"],
            "series_limit": 0,
            "order_desc": True,
            "url_params": {},
            "custom_params": {},
            "custom_form_data": {},
            "time_offsets": [],
            "post_processing": [
                {"operation": "pivot", "options": {
                    "index": ["Airline"], "columns": ["airline"],
                    "aggregates": {"Avg Fare": {"operator": "mean"}},
                    "drop_missing_columns": False}},
                {"operation": "rename", "options": {
                    "columns": {"Avg Fare": None}, "level": 0, "inplace": True}},
                {"operation": "flatten"},
            ],
        }],
        "form_data": fd,
    }


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def backup_exists(con):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (BACKUP_TABLE,)).fetchone() is not None


def _bk(con, kind, ref, payload):
    con.execute("INSERT INTO %s VALUES (?,?,?)" % BACKUP_TABLE,
                (kind, ref, json.dumps(payload)))


def _swap(lst, old, new):
    return [new if x == old else x for x in (lst or [])]


def show(con):
    pos = json.loads(con.execute(
        "SELECT position_json FROM dashboards WHERE id=?", (DASH_ID,)).fetchone()[0])
    for key, node in pos.items():
        if isinstance(node, dict) and node.get("type") == "CHART" \
                and node.get("meta", {}).get("sliceName", "").startswith("Competitor Breakdown — Bar"):
            print("layout node %s -> chartId %s" % (key, node["meta"].get("chartId")))
    linked = [r[0] for r in con.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=?", (DASH_ID,))]
    print("dashboard_slices:", sorted(linked), "| 97 linked:", OLD_SLICE in linked)
    jm = json.loads(con.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?", (DASH_ID,)).fetchone()[0])
    lc = jm.get("label_colors") or {}
    bound = sum(1 for k, v in MARKER_KEYS.items() if lc.get(k) == v)
    print("marker keys bound in dashboard metadata: %d/%d" % (bound, len(MARKER_KEYS)))
    gcc = jm.get("global_chart_configuration") or {}
    print("global chartsInScope:", sorted(gcc.get("chartsInScope") or []))


def apply(con):
    if backup_exists(con):
        print("backup table %s already exists — applied before. --revert first."
              % BACKUP_TABLE)
        return 1
    linked = [r[0] for r in con.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=?", (DASH_ID,))]
    if OLD_SLICE not in linked:
        print("ABORT: slice %d is not on dashboard %d — state has moved under us."
              % (OLD_SLICE, DASH_ID))
        return 1
    con.execute("CREATE TABLE %s (kind TEXT, ref TEXT, payload TEXT)" % BACKUP_TABLE)

    # ── 1. clone slice 97's row, overriding what makes it the new chart ──
    cols = [r[1] for r in con.execute("PRAGMA table_info(slices)")]
    src = dict(zip(cols, con.execute(
        "SELECT %s FROM slices WHERE id=?" % ",".join(cols), (OLD_SLICE,)).fetchone()))
    new_uuid = uuidlib.uuid4()
    row = dict(src)
    row.pop("id")
    row.update({
        "slice_name": CLONE_NAME,
        "viz_type": "echarts_timeseries_bar",
        "params": json.dumps(CLONE_PARAMS),
        "query_context": None,          # filled in once the id is known
        "uuid": new_uuid.bytes,
        "created_on": _now(),
        "changed_on": _now(),
        "last_saved_at": None,
        "last_saved_by_fk": None,
    })
    keys = list(row)
    cur = con.execute(
        "INSERT INTO slices (%s) VALUES (%s)" % (",".join(keys), ",".join("?" * len(keys))),
        [row[k] for k in keys])
    new_id = cur.lastrowid
    p = dict(CLONE_PARAMS)
    p["slice_id"] = new_id
    con.execute("UPDATE slices SET params=?, query_context=? WHERE id=?",
                (json.dumps(p), json.dumps(clone_query_context(new_id)), new_id))
    _bk(con, "clone_slice", str(new_id), {})
    print("clone inserted: slice %d (%s)" % (new_id, CLONE_NAME))

    # ── 2. dashboard_slices: unlink 97, link the clone ──
    con.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                (DASH_ID, OLD_SLICE))
    con.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                (DASH_ID, new_id))
    _bk(con, "dashboard_slices", str(OLD_SLICE), {"unlinked": OLD_SLICE, "linked": new_id})
    print("dashboard_slices: %d out, %d in" % (OLD_SLICE, new_id))

    # ── 3. position_json: repoint the one node that references 97 ──
    raw_pos = con.execute("SELECT position_json FROM dashboards WHERE id=?",
                          (DASH_ID,)).fetchone()[0]
    pos = json.loads(raw_pos)
    hits = [k for k, v in pos.items() if isinstance(v, dict)
            and v.get("type") == "CHART" and v.get("meta", {}).get("chartId") == OLD_SLICE]
    if len(hits) != 1:
        print("ABORT: expected exactly 1 layout node with chartId %d, found %r"
              % (OLD_SLICE, hits))
        con.execute("DROP TABLE %s" % BACKUP_TABLE)
        con.rollback()
        return 1
    node_key = hits[0]
    meta = pos[node_key]["meta"]
    _bk(con, "layout_node", node_key,
        {"chartId": meta.get("chartId"), "uuid": meta.get("uuid")})
    meta["chartId"] = new_id
    meta["uuid"] = str(new_uuid)
    print("layout node %s repointed to %d" % (node_key, new_id))

    # ── 4. json_metadata: filter scopes + cross-filter scopes + marker keys ──
    jm = json.loads(con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                                (DASH_ID,)).fetchone()[0])
    for f in jm.get("native_filter_configuration") or []:
        cis = f.get("chartsInScope") or []
        exc = (f.get("scope") or {}).get("excluded") or []
        if OLD_SLICE in cis or OLD_SLICE in exc:
            _bk(con, "filter_scope", f.get("id", f.get("name", "?")),
                {"chartsInScope": cis, "excluded": exc})
            if OLD_SLICE in cis:
                f["chartsInScope"] = _swap(cis, OLD_SLICE, new_id)
            if OLD_SLICE in exc:
                f["scope"]["excluded"] = _swap(exc, OLD_SLICE, new_id)
    gcc = jm.get("global_chart_configuration")
    if gcc and OLD_SLICE in (gcc.get("chartsInScope") or []):
        _bk(con, "global_scope", "gcc", {"chartsInScope": gcc["chartsInScope"]})
        gcc["chartsInScope"] = _swap(gcc["chartsInScope"], OLD_SLICE, new_id)
    cc = jm.get("chart_configuration") or {}
    if cc:
        _bk(con, "chart_configuration", "cc", cc)
        if str(OLD_SLICE) in cc:
            entry = cc.pop(str(OLD_SLICE))
            if isinstance(entry, dict):
                entry["id"] = new_id
            cc[str(new_id)] = entry
        for entry in cc.values():
            xf = entry.get("crossFilters") if isinstance(entry, dict) else None
            if isinstance(xf, dict) and OLD_SLICE in (xf.get("chartsInScope") or []):
                xf["chartsInScope"] = _swap(xf["chartsInScope"], OLD_SLICE, new_id)
    lc = jm.get("label_colors") or {}
    _bk(con, "dash_marker_keys", "lc",
        [(k, k in lc, lc.get(k)) for k in MARKER_KEYS])
    lc.update(MARKER_KEYS)
    jm["label_colors"] = lc
    con.execute("UPDATE dashboards SET json_metadata=?, position_json=?, changed_on=? "
                "WHERE id=?", (json.dumps(jm), json.dumps(pos), _now(), DASH_ID))
    print("json_metadata: scopes repointed, %d marker keys bound" % len(MARKER_KEYS))

    # ── 5. slice 109's own copies of the marker keys ──
    params, qc = con.execute(
        "SELECT params, query_context FROM slices WHERE id=?", (MARKER_SLICE,)).fetchone()
    if params:
        sp = json.loads(params)
        slc = sp.get("label_colors") or {}
        _bk(con, "slice109_params", "lc",
            [(k, k in slc, slc.get(k)) for k in MARKER_KEYS])
        slc.update(MARKER_KEYS)
        sp["label_colors"] = slc
        con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                    (json.dumps(sp), _now(), MARKER_SLICE))
    if qc:
        q = json.loads(qc)
        if isinstance(q.get("form_data"), dict):
            qlc = q["form_data"].get("label_colors") or {}
            _bk(con, "slice109_qc", "lc",
                [(k, k in qlc, qlc.get(k)) for k in MARKER_KEYS])
            qlc.update(MARKER_KEYS)
            q["form_data"]["label_colors"] = qlc
            con.execute("UPDATE slices SET query_context=? WHERE id=?",
                        (json.dumps(q), MARKER_SLICE))
    print("slice %d marker keys bound in params + query_context" % MARKER_SLICE)

    con.commit()
    print("APPLIED. New Competitor Breakdown = slice %d; slice %d parked (intact)."
          % (new_id, OLD_SLICE))
    return 0


def revert(con):
    if not backup_exists(con):
        print("no backup table %s — nothing to revert." % BACKUP_TABLE)
        return 1
    rows = list(con.execute("SELECT kind, ref, payload FROM %s" % BACKUP_TABLE))
    by_kind = {}
    for kind, ref, payload in rows:
        by_kind.setdefault(kind, []).append((ref, json.loads(payload)))

    new_id = int(by_kind["clone_slice"][0][0]) if "clone_slice" in by_kind else None

    if new_id is not None:
        con.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                    (DASH_ID, new_id))
        con.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                    (DASH_ID, OLD_SLICE))
        con.execute("DELETE FROM slices WHERE id=?", (new_id,))
        print("clone slice %d deleted; slice %d re-linked" % (new_id, OLD_SLICE))

    raw_pos = con.execute("SELECT position_json FROM dashboards WHERE id=?",
                          (DASH_ID,)).fetchone()[0]
    pos = json.loads(raw_pos)
    for node_key, saved in by_kind.get("layout_node", []):
        if node_key in pos and isinstance(pos[node_key], dict):
            pos[node_key]["meta"]["chartId"] = saved["chartId"]
            pos[node_key]["meta"]["uuid"] = saved["uuid"]

    jm = json.loads(con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                                (DASH_ID,)).fetchone()[0])
    saved_scopes = dict(by_kind.get("filter_scope", []))
    for f in jm.get("native_filter_configuration") or []:
        key = f.get("id", f.get("name", "?"))
        if key in saved_scopes:
            f["chartsInScope"] = saved_scopes[key]["chartsInScope"]
            if f.get("scope") is not None:
                f["scope"]["excluded"] = saved_scopes[key]["excluded"]
    for _, saved in by_kind.get("global_scope", []):
        if jm.get("global_chart_configuration"):
            jm["global_chart_configuration"]["chartsInScope"] = saved["chartsInScope"]
    for _, saved in by_kind.get("chart_configuration", []):
        jm["chart_configuration"] = saved

    def restore_keys(d, saved):
        out = dict(d or {})
        for key, had, old in saved:
            if had:
                out[key] = old
            else:
                out.pop(key, None)
        return out

    for _, saved in by_kind.get("dash_marker_keys", []):
        jm["label_colors"] = restore_keys(jm.get("label_colors"), saved)
    con.execute("UPDATE dashboards SET json_metadata=?, position_json=?, changed_on=? "
                "WHERE id=?", (json.dumps(jm), json.dumps(pos), _now(), DASH_ID))

    params, qc = con.execute(
        "SELECT params, query_context FROM slices WHERE id=?", (MARKER_SLICE,)).fetchone()
    for _, saved in by_kind.get("slice109_params", []):
        if params:
            sp = json.loads(params)
            sp["label_colors"] = restore_keys(sp.get("label_colors"), saved)
            con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                        (json.dumps(sp), _now(), MARKER_SLICE))
    for _, saved in by_kind.get("slice109_qc", []):
        if qc:
            q = json.loads(qc)
            if isinstance(q.get("form_data"), dict):
                q["form_data"]["label_colors"] = restore_keys(
                    q["form_data"].get("label_colors"), saved)
                con.execute("UPDATE slices SET query_context=? WHERE id=?",
                            (json.dumps(q), MARKER_SLICE))

    con.execute("DROP TABLE %s" % BACKUP_TABLE)
    con.commit()
    print("reverted (backup table dropped).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    con = sqlite3.connect(DB, timeout=30)
    try:
        if args.show:
            show(con)
            return 0
        return revert(con) if args.revert else apply(con)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
