#!/usr/bin/env python3
"""Rebuild "Pricing Recommendations — Summary" with semantic per-category colours.

Slice 101 is a legacy dist_bar: its one series is the metric "Count", the
recommendation categories are x-axis labels, and so its carefully built
traffic-light label_colors ('Reduce' #F87171, 'Monitor' #A78BFA, ...) have
NEVER rendered — every key is dead, and all four bars paint the palette
fallthrough green. Same structural dead-end as the old Competitor Breakdown
(see wm_carrier_consistency.py), same cure: clone into echarts_timeseries_bar
with the category as the SERIES, park 101 intact as rollback.

  x_axis  = adhoc column  recommendation AS "Recommendation"
            (label MUST differ from the series column "recommendation" —
             duplicate labels 400 at /api/v1/chart/data)
  groupby = [recommendation] + truncate_metric -> series = the four bare
            category values, which finally makes them colourable.

Colours re-base the intended traffic-light onto sanctioned WinAir hexes
(docs/winair-palette.md):

  Reduce            #CD1F25   act: price is too high
  Monitor           #C08A00   watch
  No Change         #64748B   neutral — deliberately grey. The palette
                              validator flags it below the chroma floor;
                              that is the point: "nothing to do" should not
                              carry a hue (diverging-midpoint principle).
  Consider Increase #1BAF7A   opportunity

Validated in display order (value-desc) on white: worst adjacent CVD dE 12.1,
normal-vision 20.9; #1BAF7A's 2.82:1 contrast is relieved by the per-bar
value labels (show_value + only_total).

The swap repoints every by-id reference, exactly as before: dashboard_slices,
position_json node CHART-jy-53, all native filter chartsInScope/excluded
lists, global_chart_configuration, chart_configuration. Key-level backups —
other sessions edit this dashboard concurrently.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_reco_summary_semantic.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_reco_summary_semantic.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_reco_summary_semantic.py --show

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
OLD_SLICE = 101
BACKUP_TABLE = "_wm_reco_semantic_backup"

RECO_COLORS = {
    "Reduce": "#CD1F25",
    "Monitor": "#C08A00",
    "No Change": "#64748B",
    "Consider Increase": "#1BAF7A",
}

CLONE_NAME = "Pricing Recommendations — Summary"
CLONE_METRIC = {
    "expressionType": "SQL",
    "sqlExpression": "COUNT(*)",
    "label": "Count",
    "hasCustomLabel": True,
    "optionName": "metric_reco_count",
}
CLONE_X_AXIS = {
    "expressionType": "SQL",
    "sqlExpression": "recommendation",
    "label": "Recommendation",
}
CLONE_FILTERS = [
    {"clause": "WHERE", "comparator": "No filter", "expressionType": "SIMPLE",
     "operator": "TEMPORAL_RANGE", "subject": "cap_date", "isExtra": False,
     "isNew": False, "filterOptionName": "filter_cap_date_0570e0e3"},
    {"clause": "WHERE", "comparator": "No filter", "expressionType": "SIMPLE",
     "operator": "TEMPORAL_RANGE", "subject": "ref_dep_date", "isExtra": False,
     "isNew": False, "filterOptionName": "filter_ref_dep_date_04b5c78c"},
]
CLONE_PARAMS = {
    "datasource": "33__table",
    "viz_type": "echarts_timeseries_bar",
    "x_axis": CLONE_X_AXIS,
    "x_axis_sort_series": "sum",
    "x_axis_sort_series_ascending": False,
    "metrics": [CLONE_METRIC],
    "groupby": ["recommendation"],
    "adhoc_filters": CLONE_FILTERS,
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
    "x_axis_title": "",
    "x_axis_title_margin": 15,
    "y_axis_title": "Number of Departures",
    "y_axis_title_margin": 45,
    "y_axis_format": "SMART_NUMBER",
    "y_axis_bounds": [None, None],
    "rich_tooltip": True,
    "tooltipTimeFormat": "%d-%m-%Y",
    "x_axis_time_format": "%d/%m",
    "xAxisLabelRotation": 0,
    "truncateXAxis": False,
    "truncateYAxis": False,
    "zoomable": False,
    "color_scheme": "rts_cpi_palette",
    "label_colors": dict(RECO_COLORS),
    "extra_form_data": {},
    "dashboards": [DASH_ID],
}


def clone_query_context(slice_id):
    fd = dict(CLONE_PARAMS)
    fd["slice_id"] = slice_id
    return {
        "datasource": {"id": 33, "type": "table"},
        "force": False,
        "result_format": "json",
        "result_type": "full",
        "queries": [{
            "filters": [
                {"col": "cap_date", "op": "TEMPORAL_RANGE", "val": "No filter"},
                {"col": "ref_dep_date", "op": "TEMPORAL_RANGE", "val": "No filter"},
            ],
            "extras": {"having": "", "where": ""},
            "applied_time_extras": {},
            "columns": [
                {"columnType": "BASE_AXIS", "sqlExpression": "recommendation",
                 "label": "Recommendation", "expressionType": "SQL"},
                "recommendation",
            ],
            "metrics": [CLONE_METRIC],
            "orderby": [[CLONE_METRIC, False]],
            "annotation_layers": [],
            "row_limit": 100,
            "series_columns": ["recommendation"],
            "series_limit": 0,
            "order_desc": True,
            "url_params": {},
            "custom_params": {},
            "custom_form_data": {},
            "time_offsets": [],
            "post_processing": [
                {"operation": "pivot", "options": {
                    "index": ["Recommendation"], "columns": ["recommendation"],
                    "aggregates": {"Count": {"operator": "mean"}},
                    "drop_missing_columns": False}},
                {"operation": "rename", "options": {
                    "columns": {"Count": None}, "level": 0, "inplace": True}},
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
    linked = [r[0] for r in con.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=?", (DASH_ID,))]
    print("dashboard_slices:", sorted(linked), "| 101 linked:", OLD_SLICE in linked)
    jm = json.loads(con.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?", (DASH_ID,)).fetchone()[0])
    lc = jm.get("label_colors") or {}
    print("reco keys in dash metadata:",
          {k: lc.get(k, "-- ABSENT --") for k in RECO_COLORS})
    pos = json.loads(con.execute(
        "SELECT position_json FROM dashboards WHERE id=?", (DASH_ID,)).fetchone()[0])
    for k, v in pos.items():
        if isinstance(v, dict) and v.get("type") == "CHART" \
                and "Pricing Recommendations — Summary" in str(v.get("meta", {}).get("sliceName", "")):
            print("layout node %s -> chartId %s" % (k, v["meta"].get("chartId")))


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
        "query_context": None,
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

    con.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                (DASH_ID, OLD_SLICE))
    con.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                (DASH_ID, new_id))
    _bk(con, "dashboard_slices", str(OLD_SLICE), {"unlinked": OLD_SLICE, "linked": new_id})
    print("dashboard_slices: %d out, %d in" % (OLD_SLICE, new_id))

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
    _bk(con, "dash_reco_keys", "lc",
        [(k, k in lc, lc.get(k)) for k in RECO_COLORS])
    lc.update(RECO_COLORS)
    jm["label_colors"] = lc
    con.execute("UPDATE dashboards SET json_metadata=?, position_json=?, changed_on=? "
                "WHERE id=?", (json.dumps(jm), json.dumps(pos), _now(), DASH_ID))
    print("json_metadata: scopes repointed, %d reco keys bound" % len(RECO_COLORS))

    con.commit()
    print("APPLIED. New Pricing Recommendations — Summary = slice %d; "
          "slice %d parked (intact)." % (new_id, OLD_SLICE))
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

    pos = json.loads(con.execute("SELECT position_json FROM dashboards WHERE id=?",
                                 (DASH_ID,)).fetchone()[0])
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
    for _, saved in by_kind.get("dash_reco_keys", []):
        lc = dict(jm.get("label_colors") or {})
        for key, had, old in saved:
            if had:
                lc[key] = old
            else:
                lc.pop(key, None)
        jm["label_colors"] = lc
    con.execute("UPDATE dashboards SET json_metadata=?, position_json=?, changed_on=? "
                "WHERE id=?", (json.dumps(jm), json.dumps(pos), _now(), DASH_ID))

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
