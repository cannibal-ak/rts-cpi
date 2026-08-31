#!/usr/bin/env python3
"""Bind the Exp carrier on DreamAir's dashboard 7.

THE GAP. `CARRIER_COLORS` in scripts/superset_provision_dreamair.py lists the
nine competitors the Jan-Jun 2026 window contained (DA + TC/KQ/Fli/Aur/YS/Coa/
UI/CQ). On 2026-08-19 the DreamAir load was widened to PW's whole archive
(b1cd1e0), and the 2025-09 data brought a tenth carrier, `comp_al = 'Exp'` --
32,557 rows in vw_airline_cpi_da_snapshot, cap_date 2025-09-03..2025-09-15.
Nothing regenerated label_colors, so dashboard 7 still carries the 94 keys the
nine-carrier run produced and Exp has none of them.

This is the same omission WinAir hit and fixed the same day
(scripts/superset/wm_dash6_exp_keys.py) -- there the CARRIERS loops were one
carrier short; here the loop is complete but its input dict predates the data.

WHY IT LOOKS FINE TODAY. An unmatched key is silently ignored, and so is a
missing one: the series just falls through to rts_cpi_palette[0], forest green.
The dashboard's date picker reads vw_da_dashboard_dates, whose INTERSECT of the
fares and velocity feeds starts 2025-12-12 -- after Exp's last date. So with a
cap_date-scoped guest token all 12 slices render correctly and the verifier
passes. Only a request with NO cap_date clause reaches Exp. Measured with such
a token before this script, /api/v1/chart/data built six unbindable series:

    113  echarts_timeseries_line  'Max Fare, Exp', 'Min Fare, Exp'
    118  echarts_timeseries_bar   'Lowest Available Fare, Exp'
    121  mixed_timeseries         'Exp', 'Not on sale, Exp (1)', 'Sold out, Exp (1)'
    122  echarts_timeseries_bar   'Exp'
    123  echarts_timeseries_bar   'Exp'

Note the " (1)" on the 121 markers and its absence elsewhere: mixed_timeseries
suffixes every query-B series name when building the COLOUR key while leaving
the legend unsuffixed (MixedTimeseries/transformProps.ts:408).

NO NEW HUE -- #0F766E WAS ALREADY THERE. docs/dreamair-palette.md forbids a
ninth carrier hue (no ninth colour keeps the set separable) and prescribes the
neutral fallback list instead: #64748B, #0F766E, #B45309, #7C3AED, with CQ
pinned to the first. Exp takes the second, #0F766E -- already slot 10 of
DA_DOMAIN in the provisioning script, so this binds a hex the palette had
reserved rather than inventing one. CQ keeps #64748B: by raw volume the widened
data now puts Exp (32,557) just above CQ (30,675), but re-basing CQ would be a
modification, and the doc pins CQ by name.

WHY #0F766E IS ACCEPTABLE, MEASURED. On the full ten-slot set the validator's
worst all-pairs normal-vision pair becomes #0F766E vs UI #2E7D32 at 9.2, below
the 15 floor -- but that pair cannot render: on the cap_dates where Exp has
rows, only TC, KQ, Aur, Fli and Coa appear. UI, CQ and YS start 2026-05-09 and
never co-occur with Exp. The worst pair Exp can actually be seen beside is
Aur #0E9DA8:

    #0F766E vs #0E9DA8   normal ΔE 12.9   CVD ΔE 12.6 (deutan)

against the palette's existing, documented and accepted worst reachable pair:

    #C08A00 vs #E8632A   normal ΔE 11.4   CVD ΔE  1.1 (deutan)

So Exp's worst realisable neighbour is better than the palette's own on both
axes. #0F766E's chroma (0.086) sits under the 0.10 floor; that is the intent
of a neutral overflow slot, exactly as with CQ's #64748B (0.041) -- do not
saturate it.

NINE KEYS, NOT SIX. build_label_colors() emits nine spellings per carrier, so
adding "Exp": "#0F766E" to CARRIER_COLORS yields nine. This script writes the
same nine -- the six proven above plus 'Avg Fare, Exp', 'Sold out, Exp' and
'Not on sale, Exp', which no slice builds today. They are included so Exp is
not the one carrier with a partial key set and so re-running the provisioning
script produces a byte-identical dict. Set EXP_INERT_KEYS = False to write only
the six.

Applied to the dashboard AND all 12 slices, because that is the shape
provisioning leaves behind: every dash-7 slice carries the identical dict in
both params and query_context. The dashboard's copy is the one that binds when
a chart renders inside a dashboard (Chart.jsx overwrites each slice's copy);
the slice copies keep Explore consistent.

CONCURRENCY -- why revert is key-level, not payload-level. Dashboard 7 may be
edited by another session. Restoring a whole json_metadata blob would silently
discard that work, so this records only the keys it touches: for each, whether
it was absent or what it previously held. Revert deletes what we added and
restores what we overwrote, leaving every other key alone. All writes run in
one transaction and roll back together on any error.

  Apply:   docker exec cpi-superset-1 python3 /tmp/da_dash7_exp_keys.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/da_dash7_exp_keys.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/da_dash7_exp_keys.py --show

Take the external superset.db backup BEFORE running, per the standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 7
BACKUP_TABLE = "_da_dash7_exp_keys_backup"

EXP = "#0F766E"           # neutral fallback #2, DA_DOMAIN slot 10 -- see docstring
SOLD_OUT = "#F39C12"      # availability marker, carried from WinAir unchanged
NOT_ON_SALE = "#9E9E9E"

# The three spellings no dash-7 slice builds today. Kept so Exp matches the
# nine-keys-per-carrier shape build_label_colors() produces.
EXP_INERT_KEYS = True

# Exactly what build_label_colors() emits for one carrier code.
EXP_KEYS = {
    "Exp": EXP,
    "Min Fare, Exp": EXP,
    "Max Fare, Exp": EXP,
    "Lowest Available Fare, Exp": EXP,
    "Sold out, Exp (1)": SOLD_OUT,
    "Not on sale, Exp (1)": NOT_ON_SALE,
}
if EXP_INERT_KEYS:
    EXP_KEYS["Avg Fare, Exp"] = EXP
    EXP_KEYS["Sold out, Exp"] = SOLD_OUT
    EXP_KEYS["Not on sale, Exp"] = NOT_ON_SALE


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


def dash7_slice_ids(con):
    return [r[0] for r in con.execute(
        "SELECT s.id FROM slices s JOIN dashboard_slices ds ON ds.slice_id = s.id "
        "WHERE ds.dashboard_id = ? ORDER BY s.id", (DASH_ID,))]


def backup_exists(con):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (BACKUP_TABLE,)).fetchone() is not None


def show(con):
    jm = json.loads(con.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()[0] or "{}")
    lc = jm.get("label_colors") or {}
    ok = sum(1 for k, v in EXP_KEYS.items() if lc.get(k) == v)
    print("dashboard %d: %d label_colors keys; Exp bound %d/%d"
          % (DASH_ID, len(lc), ok, len(EXP_KEYS)))
    for k in sorted(EXP_KEYS):
        print("   %-30s %s" % (k, lc.get(k, "-- ABSENT --")))
    for sid in dash7_slice_ids(con):
        name, params, qc = con.execute(
            "SELECT slice_name, params, query_context FROM slices WHERE id=?",
            (sid,)).fetchone()
        p = json.loads(params or "{}").get("label_colors") or {}
        q = {}
        if qc:
            try:
                fd = json.loads(qc).get("form_data")
                if isinstance(fd, dict):
                    q = fd.get("label_colors") or {}
            except ValueError:
                pass
        print("  slice %d %-34s params %d/%d  qc %d/%d"
              % (sid, name[:34],
                 sum(1 for k, v in EXP_KEYS.items() if p.get(k) == v), len(EXP_KEYS),
                 sum(1 for k, v in EXP_KEYS.items() if q.get(k) == v), len(EXP_KEYS)))


def apply(con):
    if backup_exists(con):
        print("backup table %s already exists -- applied before. --revert first."
              % BACKUP_TABLE)
        return 1
    con.execute("CREATE TABLE %s (target TEXT, id INTEGER, key TEXT, "
                "had INTEGER, old TEXT)" % BACKUP_TABLE)

    def record(target, rid, existing):
        for key, had, old in _prior(existing, EXP_KEYS):
            con.execute("INSERT INTO %s VALUES (?,?,?,?,?)" % BACKUP_TABLE,
                        (target, rid, key, 1 if had else 0, old))

    raw = con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                      (DASH_ID,)).fetchone()[0] or "{}"
    jm = json.loads(raw)
    before = len(jm.get("label_colors") or {})
    record("dashboard", DASH_ID, jm.get("label_colors"))
    jm["label_colors"] = merge(jm.get("label_colors"), EXP_KEYS)
    con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                (json.dumps(jm), _now(), DASH_ID))
    print("dashboard %d label_colors: %d -> %d keys"
          % (DASH_ID, before, len(jm["label_colors"])))

    for sid in dash7_slice_ids(con):
        name, params, qc = con.execute(
            "SELECT slice_name, params, query_context FROM slices WHERE id=?",
            (sid,)).fetchone()
        changed = []
        if params:
            p = json.loads(params)
            if isinstance(p.get("label_colors"), dict):
                record("slice_params", sid, p.get("label_colors"))
                p["label_colors"] = merge(p.get("label_colors"), EXP_KEYS)
                con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                            (json.dumps(p), _now(), sid))
                changed.append("params")
        if qc:
            try:
                q = json.loads(qc)
            except ValueError:
                q = None
                print("  slice %d: query_context not JSON -- SKIPPED" % sid)
            if q is not None and isinstance(q.get("form_data"), dict) \
                    and isinstance(q["form_data"].get("label_colors"), dict):
                record("slice_qc", sid, q["form_data"].get("label_colors"))
                q["form_data"]["label_colors"] = merge(
                    q["form_data"].get("label_colors"), EXP_KEYS)
                con.execute("UPDATE slices SET query_context=? WHERE id=?",
                            (json.dumps(q), sid))
                changed.append("query_context")
        print("  slice %d (%s): +%d keys in %s"
              % (sid, name[:34], len(EXP_KEYS), ", ".join(changed) or "nothing"))

    print("APPLIED. Reload dashboard 7 to see it.")
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

    rows = list(con.execute(
        "SELECT target, id, key, had, old FROM %s" % BACKUP_TABLE))
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
        print("  slice %d reverted" % sid)

    con.execute("DROP TABLE %s" % BACKUP_TABLE)
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
        # One transaction for every write: a failure part-way through must not
        # leave the dashboard bound and half the slices not.
        try:
            rc = revert(con) if args.revert else apply(con)
        except Exception:
            con.rollback()
            print("ERROR -- rolled back, nothing written.")
            raise
        if rc == 0:
            con.commit()
        else:
            con.rollback()
        return rc
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
