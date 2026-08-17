#!/usr/bin/env python3
"""Recolor the WM dashboard's airline series to the WinAir brand palette.

WM's line becomes the brand red #CD1F25 and the competitor hues are re-spaced
around it (CVD-validated set, 2026-08-17 rebrand). The map MUST stay equal to
KNOWN_AIRLINE_COLORS in apps/web/src/components/dashboard/winair/
priceChartTheme.ts and WM_COLORS in scripts/superset_provision_winair.py —
the native Latest Prices chart and these Superset charts share the palette.

What it writes (and nothing else):
  * dashboards.json_metadata (dash 6): ``label_colors`` (managed keys only)
    and ``color_scheme_domain``. Every other key — and the whole ``css``
    column with its WM-EMBED blocks — is untouched.
  * every slice CURRENTLY ON the dashboard (discovered via dashboard_slices,
    so the same script fits prod's different slice ids): ``label_colors``
    inside ``params`` and inside ``query_context``.form_data.

Composite keys ("Min Fare, WM", "Max Fare, BW", …) are included because
multi-metric groupby charts (Min/Max_Fare) label their series that way — the
old bare-code map never matched them, which is why that chart ignored the
forced colors and fell back to palette order.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_recolor_dash6.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_recolor_dash6.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_recolor_dash6.py --show

Revert restores the verbatim pre-apply payloads from the in-DB backup table
(_wm_recolor_dash6_backup), written once on first apply. Take the external
superset.db + json_metadata file backups BEFORE running, per standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 6
BACKUP_TABLE = "_wm_recolor_dash6_backup"

# 2026-08-17 brand palette — WM = WinAir logo red, competitors CVD-spaced.
NEW_COLORS = {
    "WM": "#CD1F25", "5L": "#1BAF7A", "7Z": "#8B5CF6", "BW": "#C08A00",
    "DM": "#0891B2", "Exp": "#A05A2C", "Expedia": "#A05A2C",
    "JY": "#2A78D6", "S6": "#D6208F",
}
NEW_DOMAIN = ["#CD1F25", "#1BAF7A", "#8B5CF6", "#C08A00", "#0891B2",
              "#A05A2C", "#2A78D6", "#D6208F", "#64748B", "#0070C0"]
# Metric labels that produce composite series names on groupby charts.
COMPOSITE_METRICS = ["Min Fare", "Max Fare"]

# Keys this script owns: current codes, the codes the old map carried, and
# every composite spelling of either. Everything else in a label_colors dict
# (e.g. slice 101's recommendation-label colors) is preserved verbatim.
_ALL_CODES = set(NEW_COLORS) | {"9Q", "PY", "DO"}
MANAGED_KEYS = set(_ALL_CODES) | {
    "%s, %s" % (m, c) for m in COMPOSITE_METRICS for c in _ALL_CODES
}


def target_map():
    out = dict(NEW_COLORS)
    for metric in COMPOSITE_METRICS:
        for code, color in NEW_COLORS.items():
            out["%s, %s" % (metric, code)] = color
    return out


def remap(existing):
    """New label_colors dict: unmanaged keys kept, managed keys replaced."""
    out = {k: v for k, v in (existing or {}).items() if k not in MANAGED_KEYS}
    out.update(target_map())
    return out


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def live_slice_ids(con):
    return [r[0] for r in con.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=? ORDER BY slice_id",
        (DASH_ID,))]


def show(con):
    jm = json.loads(con.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?", (DASH_ID,)).fetchone()[0] or "{}")
    print("dashboard %d label_colors: %s" % (DASH_ID, json.dumps(jm.get("label_colors"), indent=1)))
    print("dashboard %d color_scheme_domain: %s" % (DASH_ID, jm.get("color_scheme_domain")))
    for sid in live_slice_ids(con):
        name, params = con.execute(
            "SELECT slice_name, params FROM slices WHERE id=?", (sid,)).fetchone()
        try:
            lc = json.loads(params or "{}").get("label_colors")
        except ValueError:
            lc = "<params unparseable>"
        print("slice %d (%s) params.label_colors: %s" % (sid, name, json.dumps(lc)))


def backup_exists(con):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (BACKUP_TABLE,)).fetchone() is not None


def apply(con):
    if backup_exists(con):
        print("backup table %s already exists — applied before. --revert first "
              "if you need to re-apply." % BACKUP_TABLE)
        return 1
    con.execute("CREATE TABLE %s (kind TEXT, id INTEGER, payload TEXT)" % BACKUP_TABLE)

    # Dashboard metadata.
    raw = con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                      (DASH_ID,)).fetchone()[0] or "{}"
    con.execute("INSERT INTO %s VALUES ('dashboard', ?, ?)" % BACKUP_TABLE, (DASH_ID, raw))
    jm = json.loads(raw)
    jm["label_colors"] = remap(jm.get("label_colors"))
    jm["color_scheme_domain"] = NEW_DOMAIN
    con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                (json.dumps(jm), _now(), DASH_ID))
    print("dashboard %d json_metadata updated (%d label_colors keys)"
          % (DASH_ID, len(jm["label_colors"])))

    # Live slices: params + query_context.
    for sid in live_slice_ids(con):
        name, params, qc = con.execute(
            "SELECT slice_name, params, query_context FROM slices WHERE id=?",
            (sid,)).fetchone()
        con.execute("INSERT INTO %s VALUES ('slice_params', ?, ?)" % BACKUP_TABLE, (sid, params))
        con.execute("INSERT INTO %s VALUES ('slice_qc', ?, ?)" % BACKUP_TABLE, (sid, qc))
        changed = []
        if params:
            try:
                p = json.loads(params)
                p["label_colors"] = remap(p.get("label_colors"))
                con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                            (json.dumps(p), _now(), sid))
                changed.append("params")
            except ValueError:
                print("  slice %d: params not JSON — SKIPPED" % sid)
        if qc:
            try:
                q = json.loads(qc)
                if isinstance(q.get("form_data"), dict):
                    q["form_data"]["label_colors"] = remap(q["form_data"].get("label_colors"))
                    con.execute("UPDATE slices SET query_context=? WHERE id=?",
                                (json.dumps(q), sid))
                    changed.append("query_context")
            except ValueError:
                print("  slice %d: query_context not JSON — SKIPPED" % sid)
        print("slice %d (%s): %s" % (sid, name, ", ".join(changed) or "nothing to do"))

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
