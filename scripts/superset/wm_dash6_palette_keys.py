#!/usr/bin/env python3
"""Bind WinAir brand colours to the dash-6 charts that still fall through to green.

An audit of every slice on dashboard 6 (2026-08-18) found six charts rendering
rts_cpi_palette colours — forest green #2B6B2B and friends — because their
label_colors keys never match the series names Superset actually builds. This
script fixes four of them. Slices 101 and 109 are deliberately NOT touched:
both need a design decision first (see docs/winair-palette.md).

WHY THE EXISTING KEYS MISS — two distinct causes, both verified in source:

  * dist_bar (slice 97, 107) colours by SERIES key, and with an empty
    "Breakdowns" (columns=[]) there is exactly one series per METRIC; the
    groupby values become x-axis categories. So a chart grouped by airline has
    series named "Avg Fare" / "Base" / "Tax" / "YQ", and the 27 carrier keys on
    it are silently ignored. (/app/superset/viz.py DistributionBarViz.get_data,
    pivot at ~line 1326; NVD3Vis.js colours by d['key'].)

  * mixed_timeseries (slice 103) appends " (1)" to every query-B (metrics_b)
    series when building the COLOUR key, while leaving the legend name
    unsuffixed — so "Forecasted SF" shows in the legend but the colour is looked
    up as "Forecasted SF (1)". Verified in MixedTimeseries/transformProps.ts
    lines 408-409 (recovered from the shipped sourcemap):
        const seriesName = `${inverted[entryName] || entryName} (1)`;
        const colorScaleKey = getOriginalSeries(seriesName, array);
    Query A (line 364) has no suffix, which is why Capacity and Current Booking
    already bind and the two seat-factor lines do not.

  * echarts_timeseries_bar (slice 105) has one metric AND a groupby with
    truncate_metric off, so series are composite "<metric>, <carrier>" —
    "Lowest Available Fare, WM", not "WM".

Colours come from docs/winair-palette.md. Palette A (carrier identity) for
slice 105; Palette B (measure series) for 97, 103 and 107.

CONCURRENCY — why revert is key-level, not payload-level.
Another session is actively editing dashboard 6 (slice 110 was added mid-audit).
Restoring a whole json_metadata blob would silently discard their work, so this
script records only the keys it touches: for each, whether it was absent or what
its previous value was. Revert deletes the ones we added and restores the ones
we overwrote, leaving every other key — and every concurrent edit — alone.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_dash6_palette_keys.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_dash6_palette_keys.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_dash6_palette_keys.py --show

Take the external superset.db backup BEFORE running, per standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 6
BACKUP_TABLE = "_wm_dash6_palette_keys_backup"

CARRIERS = {
    "WM": "#CD1F25", "5L": "#1BAF7A", "7Z": "#8B5CF6", "BW": "#C08A00",
    "DM": "#0891B2", "JY": "#2A78D6", "S6": "#D6208F",
}

# slice id -> {series name as Superset builds it: hex}
PER_SLICE = {
    # Competitor Breakdown. One series ("Avg Fare"); airlines are x categories,
    # so per-bar carrier colour is unreachable here. A single measure series
    # takes a single colour — WinAir red.
    97: {"Avg Fare": "#CD1F25"},
    # Booking / Seat Factor / Capacity. Only the two query-B keys are new; the
    # query-A pair was bound by wm_recolor_velocity.py and is left alone.
    103: {"Actual Seat Factor (1)": "#0891B2", "Forecasted SF (1)": "#8B5CF6"},
    # Lowest Available Avg_Fare — series are carriers, so Palette A applies.
    105: {"Lowest Available Fare, %s" % code: hex_ for code, hex_ in CARRIERS.items()},
    # Fare Composition. Stacked measure series: Base and Tax are the red ordinal
    # pair (they read as siblings in a stack), YQ takes Palette B cyan.
    # Validated as a set on white: worst adjacent CVD dE 9.5, normal-vision 17.8.
    107: {"Base": "#CD1F25", "Tax": "#DE8078", "YQ": "#0891B2"},
}

# The dashboard's own label_colors is what actually binds when a chart renders
# inside a dashboard — Chart.jsx overwrites each slice's copy with it. The slice
# copies are still written so Explore-from-dashboard agrees and the two do not
# drift.
DASH_KEYS = {k: v for m in PER_SLICE.values() for k, v in m.items()}


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def merge(existing, additions):
    """Add our keys to a label_colors dict, preserving everything else."""
    out = dict(existing or {})
    out.update(additions)
    return out


def _prior(existing, additions):
    """[(key, had_it, old_value)] so revert can be surgical."""
    e = existing or {}
    return [(k, k in e, e.get(k)) for k in additions]


def backup_exists(con):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (BACKUP_TABLE,)).fetchone() is not None


def show(con):
    jm = json.loads(con.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()[0] or "{}")
    lc = jm.get("label_colors") or {}
    print("dashboard %d: %d label_colors keys; ours present: %d/%d"
          % (DASH_ID, len(lc),
             sum(1 for k in DASH_KEYS if lc.get(k) == DASH_KEYS[k]), len(DASH_KEYS)))
    for k in sorted(DASH_KEYS):
        print("   %-32s %s" % (k, lc.get(k, "-- ABSENT --")))
    for sid, additions in sorted(PER_SLICE.items()):
        name, params = con.execute(
            "SELECT slice_name, params FROM slices WHERE id=?", (sid,)).fetchone()
        p = json.loads(params or "{}")
        slc = p.get("label_colors") or {}
        ok = sum(1 for k in additions if slc.get(k) == additions[k])
        print("slice %d (%s): %d/%d bound" % (sid, name, ok, len(additions)))


def apply(con):
    if backup_exists(con):
        print("backup table %s already exists — applied before. --revert first."
              % BACKUP_TABLE)
        return 1
    con.execute("CREATE TABLE %s (target TEXT, id INTEGER, key TEXT, "
                "had INTEGER, old TEXT)" % BACKUP_TABLE)

    def record(target, rid, existing, additions):
        for key, had, old in _prior(existing, additions):
            con.execute("INSERT INTO %s VALUES (?,?,?,?,?)" % BACKUP_TABLE,
                        (target, rid, key, 1 if had else 0, old))

    raw = con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                      (DASH_ID,)).fetchone()[0] or "{}"
    jm = json.loads(raw)
    before = len(jm.get("label_colors") or {})
    record("dashboard", DASH_ID, jm.get("label_colors"), DASH_KEYS)
    jm["label_colors"] = merge(jm.get("label_colors"), DASH_KEYS)
    con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                (json.dumps(jm), _now(), DASH_ID))
    print("dashboard %d label_colors: %d -> %d keys"
          % (DASH_ID, before, len(jm["label_colors"])))

    for sid, additions in sorted(PER_SLICE.items()):
        name, params, qc = con.execute(
            "SELECT slice_name, params, query_context FROM slices WHERE id=?",
            (sid,)).fetchone()
        changed = []
        if params:
            p = json.loads(params)
            record("slice_params", sid, p.get("label_colors"), additions)
            p["label_colors"] = merge(p.get("label_colors"), additions)
            con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                        (json.dumps(p), _now(), sid))
            changed.append("params")
        if qc:
            try:
                q = json.loads(qc)
            except ValueError:
                q = None
                print("  slice %d: query_context not JSON — SKIPPED" % sid)
            if q is not None and isinstance(q.get("form_data"), dict):
                record("slice_qc", sid, q["form_data"].get("label_colors"), additions)
                q["form_data"]["label_colors"] = merge(
                    q["form_data"].get("label_colors"), additions)
                con.execute("UPDATE slices SET query_context=? WHERE id=?",
                            (json.dumps(q), sid))
                changed.append("query_context")
        print("slice %d (%s): +%d keys in %s"
              % (sid, name, len(additions), ", ".join(changed) or "nothing"))

    con.commit()
    print("APPLIED. Reload dashboard 6 to see it.")
    return 0


def revert(con):
    if not backup_exists(con):
        print("no backup table %s — nothing to revert." % BACKUP_TABLE)
        return 1

    def restore(d, rows):
        out = dict(d or {})
        for _, _, key, had, old in rows:
            if had:
                out[key] = old
            else:
                out.pop(key, None)
        return out

    rows = list(con.execute("SELECT target, id, key, had, old FROM %s" % BACKUP_TABLE))
    dash_rows = [r for r in rows if r[0] == "dashboard"]
    if dash_rows:
        jm = json.loads(con.execute(
            "SELECT json_metadata FROM dashboards WHERE id=?",
            (DASH_ID,)).fetchone()[0] or "{}")
        jm["label_colors"] = restore(jm.get("label_colors"), dash_rows)
        con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                    (json.dumps(jm), _now(), DASH_ID))
        print("dashboard %d: %d keys removed/restored" % (DASH_ID, len(dash_rows)))

    for sid in sorted({r[1] for r in rows if r[0] != "dashboard"}):
        p_rows = [r for r in rows if r[0] == "slice_params" and r[1] == sid]
        q_rows = [r for r in rows if r[0] == "slice_qc" and r[1] == sid]
        params, qc = con.execute(
            "SELECT params, query_context FROM slices WHERE id=?", (sid,)).fetchone()
        if p_rows and params:
            p = json.loads(params)
            p["label_colors"] = restore(p.get("label_colors"), p_rows)
            con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                        (json.dumps(p), _now(), sid))
        if q_rows and qc:
            q = json.loads(qc)
            if isinstance(q.get("form_data"), dict):
                q["form_data"]["label_colors"] = restore(
                    q["form_data"].get("label_colors"), q_rows)
                con.execute("UPDATE slices SET query_context=? WHERE id=?",
                            (json.dumps(q), sid))
        print("slice %d reverted" % sid)

    con.execute("DROP TABLE %s" % BACKUP_TABLE)
    con.commit()
    print("reverted from %s (table dropped)." % BACKUP_TABLE)
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
