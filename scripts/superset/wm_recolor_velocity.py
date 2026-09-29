#!/usr/bin/env python3
"""Colour the WM velocity chart's measure series with WinAir Palette B.

Slice 103 ("Booking, Seat Factor, Capacity", mixed_timeseries on ds 34) had no
label_colors for its own metrics, so Superset fell through to the stock scheme
and drew the whole chart green — a colour with no relation to the WinAir brand.

Palette B is the measure-series palette from docs/winair-palette.md. Unlike
Palette A (wm_recolor_dash6.py) it colours METRICS, not airlines:

  seats, red ordinal pair   Capacity           #DE8078  (the envelope)
                            Current Booking    #CD1F25  (the part that sold)
  rates, two hues           Actual Seat Factor #0891B2  (measured)
                            Forecasted SF      #8B5CF6  (modelled)

Validated on white (Superset's canvas): worst adjacent CVD ΔE 12.6, worst
normal-vision ΔE 21.1, every slot >= 3:1. The seats pair also clears the
ordinal-ramp checks. Re-run scripts/validate_palette.js before changing a hex.

The keys are the metric labels VERBATIM from slice 103's params — in particular
"Forecasted SF", not "Forecasted Seat Factor". A key that does not match the
series name exactly is silently ignored, which is the usual way a recolour
appears to do nothing.

What it writes (and nothing else):
  * slice 103: the four MANAGED_KEYS inside ``params``.label_colors and inside
    ``query_context``.form_data.label_colors. Every other key in those dicts —
    including the carrier colours wm_recolor_dash6.py owns — is preserved.
  * dashboards.json_metadata (dash 6): the same four keys added to
    ``label_colors``. ``color_scheme_domain`` is NOT touched; that belongs to
    wm_recolor_dash6.py and the two scripts must not fight over it.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_recolor_velocity.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_recolor_velocity.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_recolor_velocity.py --show

Revert restores the verbatim pre-apply payloads from the in-DB backup table
(_wm_recolor_velocity_backup), written once on first apply. Take the external
superset.db backup BEFORE running, per standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 6
SLICE_ID = 103
BACKUP_TABLE = "_wm_recolor_velocity_backup"

# Palette B — measure series. Keys are metric labels exactly as slice 103
# spells them; see docs/winair-palette.md.
NEW_COLORS = {
    "Capacity": "#DE8078",
    "Current Booking": "#CD1F25",
    "Actual Seat Factor": "#0891B2",
    "Forecasted SF": "#8B5CF6",
}
MANAGED_KEYS = set(NEW_COLORS)


def remap(existing):
    """New label_colors dict: unmanaged keys kept verbatim, ours replaced."""
    out = {k: v for k, v in (existing or {}).items() if k not in MANAGED_KEYS}
    out.update(NEW_COLORS)
    return out


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _managed_view(d):
    return {k: v for k, v in (d or {}).items() if k in MANAGED_KEYS}


def show(con):
    jm = json.loads(con.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()[0] or "{}")
    print("dashboard %d managed label_colors: %s"
          % (DASH_ID, json.dumps(_managed_view(jm.get("label_colors")))))
    name, params, qc = con.execute(
        "SELECT slice_name, params, query_context FROM slices WHERE id=?",
        (SLICE_ID,)).fetchone()
    p = json.loads(params or "{}")
    print("slice %d (%s)" % (SLICE_ID, name))
    print("  metric labels A: %s" % [m.get("label") for m in p.get("metrics", [])])
    print("  metric labels B: %s" % [m.get("label") for m in p.get("metrics_b", [])])
    print("  params managed:  %s" % json.dumps(_managed_view(p.get("label_colors"))))
    q = json.loads(qc or "{}")
    fd = q.get("form_data") if isinstance(q.get("form_data"), dict) else {}
    print("  qc     managed:  %s" % json.dumps(_managed_view(fd.get("label_colors"))))


def check_labels(con):
    """Fail loudly if the chart's metric labels drifted from NEW_COLORS."""
    p = json.loads(con.execute(
        "SELECT params FROM slices WHERE id=?", (SLICE_ID,)).fetchone()[0] or "{}")
    labels = {m.get("label") for m in p.get("metrics", [])}
    labels |= {m.get("label") for m in p.get("metrics_b", [])}
    missing = MANAGED_KEYS - labels
    if missing:
        print("ABORT: slice %d has no series named %s — its metric labels are %s. "
              "A non-matching key is silently ignored, so this would look "
              "applied and change nothing." % (SLICE_ID, sorted(missing), sorted(labels)))
        return False
    return True


def backup_exists(con):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (BACKUP_TABLE,)).fetchone() is not None


def apply(con):
    if backup_exists(con):
        print("backup table %s already exists — applied before. --revert first "
              "if you need to re-apply." % BACKUP_TABLE)
        return 1
    if not check_labels(con):
        return 1
    con.execute("CREATE TABLE %s (kind TEXT, id INTEGER, payload TEXT)" % BACKUP_TABLE)

    raw = con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                      (DASH_ID,)).fetchone()[0] or "{}"
    con.execute("INSERT INTO %s VALUES ('dashboard', ?, ?)" % BACKUP_TABLE, (DASH_ID, raw))
    jm = json.loads(raw)
    jm["label_colors"] = remap(jm.get("label_colors"))
    con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                (json.dumps(jm), _now(), DASH_ID))
    print("dashboard %d json_metadata updated (%d label_colors keys total)"
          % (DASH_ID, len(jm["label_colors"])))

    name, params, qc = con.execute(
        "SELECT slice_name, params, query_context FROM slices WHERE id=?",
        (SLICE_ID,)).fetchone()
    con.execute("INSERT INTO %s VALUES ('slice_params', ?, ?)" % BACKUP_TABLE,
                (SLICE_ID, params))
    con.execute("INSERT INTO %s VALUES ('slice_qc', ?, ?)" % BACKUP_TABLE, (SLICE_ID, qc))
    changed = []
    if params:
        p = json.loads(params)
        p["label_colors"] = remap(p.get("label_colors"))
        con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                    (json.dumps(p), _now(), SLICE_ID))
        changed.append("params")
    if qc:
        q = json.loads(qc)
        if isinstance(q.get("form_data"), dict):
            q["form_data"]["label_colors"] = remap(q["form_data"].get("label_colors"))
            con.execute("UPDATE slices SET query_context=? WHERE id=?",
                        (json.dumps(q), SLICE_ID))
            changed.append("query_context")
    print("slice %d (%s): %s" % (SLICE_ID, name, ", ".join(changed) or "nothing to do"))

    con.commit()
    print("APPLIED. Charts cache their colors — expect correct colors after "
          "cache expiry or a forced refresh.")
    return 0


def revert(con):
    if not backup_exists(con):
        print("no backup table %s — nothing to revert." % BACKUP_TABLE)
        return 1
    for kind, rid, payload in con.execute(
            "SELECT kind, id, payload FROM %s" % BACKUP_TABLE):
        if kind == "dashboard":
            con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                        (payload, _now(), rid))
        elif kind == "slice_params":
            con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                        (payload, _now(), rid))
        elif kind == "slice_qc":
            con.execute("UPDATE slices SET query_context=? WHERE id=?", (payload, rid))
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
