#!/usr/bin/env python3
"""Bind the Exp (Expedia) carrier on dash-6 slices 105 and 109.

THE GAP. Palette A in docs/winair-palette.md lists eight carriers, but the
CARRIERS dict in wm_dash6_palette_keys.py and wm_carrier_consistency.py lists
only seven -- Exp was left out of both loops. So every per-series key those two
scripts generated ("Lowest Available Fare, <code>", "Sold out, <code> (1)",
"Not on sale, <code> (1)") exists for WM/5L/7Z/BW/DM/JY/S6 and not for Exp.
The bare 'Exp'/'Expedia' keys and the Max/Min Fare composites came from a
different script that did carry Exp, which is why the omission looked like it
could not be an omission.

WHY IT WAS NEVER CAUGHT. An unmatched key is silently ignored -- but so is a
missing one; the chart just falls through to rts_cpi_palette[0], forest green.
The verifier only reports a series it can see the API build, and dev's WinAir
dataset (169k rows) has no Exp rows on those two charts, so dev builds no Exp
series and passes. Prod (237k rows) does build them. Confirmed 2026-08-19:
dashboard 6's label_colors is 76 keys and BYTE-IDENTICAL on dev and prod, and
all three keys are missing in both. This is a real palette gap that only prod's
data reveals -- not drift, and not from the DreamAir deploy.

CONFIRMED AGAINST LIVE PROD DATA (verify_dashboard_colors.py 6), the three
series Superset actually builds and cannot colour:

    105  echarts_timeseries_bar  'Lowest Available Fare, Exp'
    109  mixed_timeseries        'Not on sale, Exp (1)'
    109  mixed_timeseries        'Sold out, Exp (1)'

Note the " (1)" on the 109 pair and its absence on 105: mixed_timeseries
suffixes every query-B series name when building the COLOUR key while leaving
the legend unsuffixed (MixedTimeseries/transformProps.ts:408). Both Exp markers
land in query B. Slice 105 is a plain bar chart with one metric and a groupby
with truncate_metric off, so its series are composite "<metric>, <carrier>".

NO NEW HEX. Exp is already bound to #A05A2C ('Exp', 'Expedia', 'Max Fare, Exp',
'Min Fare, Exp'); the markers reuse the availability pair (#F39C12 sold out,
#9E9E9E not on sale) that all seven other carriers already carry. Nothing here
needs a validator re-run -- every colour is an existing, validated Palette A /
availability-marker value, applied to a carrier that was skipped.

THE TWO UNSUFFIXED MARKER KEYS. wm_carrier_consistency.py writes four marker
keys per carrier -- both the bare and the " (1)" form -- so completing Exp into
that loop yields 'Sold out, Exp' and 'Not on sale, Exp' as well. Prod builds
neither today (the verifier proves only the suffixed pair is needed), so they
are inert; they are included so Exp is not the one carrier with a partial
marker set, and so the pair still binds if query composition ever puts those
series in query A. Drop EXP_MARKERS_UNSUFFIXED below to write only the three.

CONCURRENCY -- why revert is key-level, not payload-level.
Dashboard 6 is edited by more than one session. Restoring a whole json_metadata
blob would silently discard another session's work, so this records only the
keys it touches: for each, whether it was absent or what its previous value
was. Revert deletes the ones we added and restores the ones we overwrote,
leaving every other key alone.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_dash6_exp_keys.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_dash6_exp_keys.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_dash6_exp_keys.py --show

Take the external superset.db backup BEFORE running, per standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 6
BACKUP_TABLE = "_wm_dash6_exp_keys_backup"

EXP = "#A05A2C"           # Palette A, carrier identity -- already bound as 'Exp'
SOLD_OUT = "#F39C12"      # native theme.palette.warning.main
NOT_ON_SALE = "#9E9E9E"   # native text.disabled on light paper

# Include the bare marker forms so Exp matches the four-keys-per-carrier shape
# wm_carrier_consistency.py established. Inert today -- see the docstring.
EXP_MARKERS_UNSUFFIXED = True

# slice id -> {series name exactly as Superset builds it: hex}
PER_SLICE = {
    # Lowest Available Avg_Fare by Travel_Date. One metric + groupby,
    # truncate_metric off => composite "<metric>, <carrier>", no suffix.
    105: {"Lowest Available Fare, Exp": EXP},
    # Lowest Available Fare & Availability. The Exp markers are query-B series,
    # so the colour key -- and only the colour key -- carries " (1)".
    109: {
        "Sold out, Exp (1)": SOLD_OUT,
        "Not on sale, Exp (1)": NOT_ON_SALE,
    },
}

if EXP_MARKERS_UNSUFFIXED:
    PER_SLICE[109]["Sold out, Exp"] = SOLD_OUT
    PER_SLICE[109]["Not on sale, Exp"] = NOT_ON_SALE

# The dashboard's own label_colors is what actually binds when a chart renders
# inside a dashboard -- Chart.jsx overwrites each slice's copy with it. The
# slice copies are still written so Explore-from-dashboard agrees.
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
        print("backup table %s already exists -- applied before. --revert first."
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
                print("  slice %d: query_context not JSON -- SKIPPED" % sid)
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
        print("no backup table %s -- nothing to revert." % BACKUP_TABLE)
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

    con = sqlite3.connect(DB)
    try:
        if args.show:
            show(con)
            return 0
        if args.revert:
            return revert(con)
        return apply(con)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
