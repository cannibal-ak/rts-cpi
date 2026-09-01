#!/usr/bin/env python3
"""Apply the Gate-1-approved parity renames (WM-canonical titles/labels).

Scope: slice TITLES, their displayed dashboard headers, tab LABELS
(meta.text) and native-filter DISPLAY names only. Metrics, label_colors keys,
tab NODE ids and chart internals are never touched — the script refuses
anything else by construction. Slice 43 and dataset 13 are hard-refused.
Dashboards allowlist: {1}. (PW's two filter renames ride the dash-3 canonical
rebuild instead — its filter config is replaced wholesale there.)

Displayed-header convention (discovered in the 2026-08-31 audit dry-run, do
not "fix"): position_json meta.sliceName is the header the dashboard SHOWS,
and the older six charts on every dashboard carry deliberate view-type
suffixes ("<slice name> — Line/Bar/Table"). A slice rename therefore rewrites
each layout header by swapping the slice-name PREFIX and preserving the
suffix, so JY's headers land exactly on WM's displayed forms.

Run INSIDE cpi-superset-1 (plain sqlite3, stdlib only):

  Recon:    docker exec -i cpi-superset-1 python3 - --show     < scripts/superset/parity_rename.py
  Dry-run:  docker exec -i cpi-superset-1 python3 - --dry-run  < scripts/superset/parity_rename.py
  Apply:    docker exec -i cpi-superset-1 python3 - --apply    < scripts/superset/parity_rename.py
  Revert:   docker exec -i cpi-superset-1 python3 - --revert   < scripts/superset/parity_rename.py

Before the first write: full DB copy via the sqlite3 backup API (WAL-safe)
named superset.db.bak.<ts>_IST.parityrename, plus the in-DB backup table
_parity_rename_backup (also the revert source and applied-sentinel).
Every rename asserts the CURRENT value equals the expected old value and
aborts the whole transaction on any mismatch — an unexpected value means the
survey is stale, never something to "fix" silently.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
BACKUP_TABLE = "_parity_rename_backup"
UNTOUCHABLE_SLICES = {43}
RENAME_DASHES = {1}

# (slice_id, expected_old, new) — approved proposed_renames.csv, Gate 1 D1.
SLICE_RENAMES = [
    (50, "Avg Fare by Travel Date", "Lowest Available Avg_Fare by Travel_Date"),
    (51, "Avg Fare by Travel Date", "Lowest Available Avg_Fare by Travel_Date"),
    (46, "Min/Max Fare by Date", "Min/Max_Fare by Travel_Date"),
    (52, "Min/Max Fare by Date", "Min/Max_Fare by Travel_Date"),
    (48, "Pricing Recommendations — Detail", "Pricing Recommendations"),
    (47, "Fare Trends - Booking, Seat Factor, Capacity", "Booking, Seat Factor, Capacity"),
]

# (dashboard_id, tab_node_id, expected_old_label, new_label)
TAB_RENAMES = [
    (1, "TAB-jyNav5", "Fare Trends", "Velocity"),
]

# (dashboard_id, native_filter_id, expected_old_name, new_name)
FILTER_RENAMES = [
    (1, "NATIVE_FILTER-Route", "Route", "Route (O&D)"),
]


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _ist_stamp():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).strftime("%Y%m%dT%H%M%S")


def full_backup(con):
    path = f"{DB}.bak.{_ist_stamp()}_IST.parityrename"
    dest = sqlite3.connect(path)
    with dest:
        con.backup(dest)
    dest.close()
    print(f"full backup: {path}")


def record(cur, dash_id, otype, okey, old, new):
    cur.execute(
        f"INSERT INTO {BACKUP_TABLE} (dashboard_id, object_type, object_key, old_value, new_value, ts) "
        "VALUES (?,?,?,?,?,?)", (dash_id, otype, str(okey), old, new, _now()))


def die(msg):
    sys.exit(f"ABORT (nothing committed): {msg}")


def plan(cur):
    """Compute every change as (kind, args...) after asserting current state."""
    steps = []
    for sid, old, new in SLICE_RENAMES:
        if sid in UNTOUCHABLE_SLICES:
            die(f"slice {sid} is untouchable")
        row = cur.execute(
            "SELECT s.slice_name, ds.dashboard_id FROM slices s "
            "JOIN dashboard_slices ds ON ds.slice_id=s.id WHERE s.id=?", (sid,)).fetchone()
        if row is None:
            die(f"slice {sid} not found")
        if row[1] not in RENAME_DASHES:
            die(f"slice {sid} lives on dashboard {row[1]}, outside rename allowlist")
        if row[0] == new:
            steps.append(("noop", f"slice {sid} already '{new}'"))
            continue
        if row[0] != old:
            die(f"slice {sid} is '{row[0]}', expected '{old}' — survey stale")
        steps.append(("slice", sid, old, new, row[1]))
    for dash_id, node, old, new in TAB_RENAMES:
        if dash_id not in RENAME_DASHES:
            die(f"tab rename on dashboard {dash_id} outside allowlist")
        pj = json.loads(cur.execute(
            "SELECT position_json FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
        tab = pj.get(node)
        if not tab:
            die(f"tab node {node} not found on dashboard {dash_id}")
        cur_label = (tab.get("meta") or {}).get("text")
        if cur_label == new:
            steps.append(("noop", f"tab {node} already '{new}'"))
            continue
        if cur_label != old:
            die(f"tab {node} label is '{cur_label}', expected '{old}'")
        steps.append(("tab", dash_id, node, old, new))
    for dash_id, fid, old, new in FILTER_RENAMES:
        if dash_id not in RENAME_DASHES:
            die(f"filter rename on dashboard {dash_id} outside allowlist")
        meta = json.loads(cur.execute(
            "SELECT json_metadata FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
        entry = next((f for f in meta.get("native_filter_configuration") or []
                      if f.get("id") == fid), None)
        if entry is None:
            die(f"native filter {fid} not found on dashboard {dash_id}")
        if entry.get("name") == new:
            steps.append(("noop", f"filter {fid} already '{new}'"))
            continue
        if entry.get("name") != old:
            die(f"filter {fid} name is '{entry.get('name')}', expected '{old}'")
        steps.append(("filter", dash_id, fid, old, new))
    return steps


def header_plan(cur, steps):
    """Displayed-header updates implied by the slice renames:
    (dash_id, node_key, old_header, new_header), suffix-preserving."""
    fixes = []
    by_dash = {}
    for step in steps:
        if step[0] == "slice":
            _, sid, old, new, dash_id = step
            by_dash.setdefault(dash_id, []).append((sid, old, new))
    for dash_id, renames in by_dash.items():
        pj = json.loads(cur.execute(
            "SELECT position_json FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
        for key, node in pj.items():
            if not isinstance(node, dict) or node.get("type") != "CHART":
                continue
            meta = node.get("meta") or {}
            for sid, old, new in renames:
                if meta.get("chartId") != sid:
                    continue
                header = meta.get("sliceName")
                if not header:
                    continue
                if not header.startswith(old):
                    die(f"dash {dash_id} node {key}: header '{header}' does not start "
                        f"with '{old}' — survey stale")
                fixes.append((dash_id, key, header, new + header[len(old):]))
    return fixes


def apply_all(con, steps, layout_fixes, pending_slice_renames):
    cur = con.cursor()
    cur.execute(f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} "
                "(dashboard_id INT, object_type TEXT, object_key TEXT, "
                "old_value TEXT, new_value TEXT, ts TEXT)")
    now = _now()
    dirty_dashboards = set()

    for step in steps:
        if step[0] == "noop":
            continue
        if step[0] == "slice":
            _, sid, old, new, dash_id = step
            cur.execute("UPDATE slices SET slice_name=?, changed_on=? WHERE id=? AND slice_name=?",
                        (new, now, sid, old))
            if cur.rowcount != 1:
                die(f"slice {sid} update matched {cur.rowcount} rows")
            record(cur, dash_id, "slice", sid, old, new)
        elif step[0] == "tab":
            _, dash_id, node, old, new = step
            pj = json.loads(cur.execute(
                "SELECT position_json FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
            pj[node]["meta"]["text"] = new
            cur.execute("UPDATE dashboards SET position_json=? WHERE id=?",
                        (json.dumps(pj), dash_id))
            record(cur, dash_id, "tab", node, old, new)
            dirty_dashboards.add(dash_id)
        elif step[0] == "filter":
            _, dash_id, fid, old, new = step
            meta = json.loads(cur.execute(
                "SELECT json_metadata FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
            for f in meta["native_filter_configuration"]:
                if f["id"] == fid:
                    f["name"] = new
            cur.execute("UPDATE dashboards SET json_metadata=? WHERE id=?",
                        (json.dumps(meta), dash_id))
            record(cur, dash_id, "filter", fid, old, new)
            dirty_dashboards.add(dash_id)

    # displayed-header updates (suffix-preserving), grouped per dashboard
    for dash_id in {f[0] for f in layout_fixes}:
        pj = json.loads(cur.execute(
            "SELECT position_json FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
        for f_dash, key, old_header, new_header in layout_fixes:
            if f_dash != dash_id:
                continue
            node = pj.get(key)
            if not node or (node.get("meta") or {}).get("sliceName") != old_header:
                die(f"dash {dash_id} node {key}: header changed underneath us")
            node["meta"]["sliceName"] = new_header
            record(cur, dash_id, "layout_name", key, old_header, new_header)
        cur.execute("UPDATE dashboards SET position_json=? WHERE id=?",
                    (json.dumps(pj), dash_id))
        dirty_dashboards.add(dash_id)

    for dash_id in dirty_dashboards:
        cur.execute("UPDATE dashboards SET changed_on=? WHERE id=?", (now, dash_id))


def revert(con):
    cur = con.cursor()
    rows = cur.execute(
        f"SELECT dashboard_id, object_type, object_key, old_value, new_value FROM {BACKUP_TABLE} "
        "ORDER BY rowid DESC").fetchall()
    if not rows:
        die("backup table empty — nothing to revert")
    now = _now()
    for dash_id, otype, okey, old, new in rows:
        if otype == "slice":
            cur.execute("UPDATE slices SET slice_name=?, changed_on=? WHERE id=? AND slice_name=?",
                        (old, now, int(okey), new))
        elif otype in ("tab", "layout_name"):
            pj = json.loads(cur.execute(
                "SELECT position_json FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
            node = pj.get(okey)
            if node:
                if otype == "tab":
                    node["meta"]["text"] = old
                else:
                    node["meta"]["sliceName"] = old
                cur.execute("UPDATE dashboards SET position_json=?, changed_on=? WHERE id=?",
                            (json.dumps(pj), now, dash_id))
        elif otype == "filter":
            meta = json.loads(cur.execute(
                "SELECT json_metadata FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0])
            for f in meta.get("native_filter_configuration") or []:
                if f.get("id") == okey and f.get("name") == new:
                    f["name"] = old
            cur.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                        (json.dumps(meta), now, dash_id))
    cur.execute(f"DROP TABLE {BACKUP_TABLE}")
    print(f"reverted {len(rows)} changes; backup table dropped")


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--show", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    try:
        cur = con.cursor()
        if args.revert:
            with con:
                revert(con)
            return
        applied = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (BACKUP_TABLE,)).fetchone()
        if applied and args.apply:
            die(f"{BACKUP_TABLE} exists — already applied (revert first to re-apply)")

        steps = plan(cur)
        layout_fixes = header_plan(cur, steps)
        print(f"{len([s for s in steps if s[0] != 'noop'])} renames, "
              f"{len([s for s in steps if s[0] == 'noop'])} already done, "
              f"{len(layout_fixes)} displayed-header updates (suffix-preserving):")
        for s in steps:
            if s[0] == "noop":
                print(f"  noop: {s[1]}")
            elif s[0] == "slice":
                print(f"  slice {s[1]}: '{s[2]}' -> '{s[3]}'")
            elif s[0] == "tab":
                print(f"  tab {s[2]} (dash {s[1]}): '{s[3]}' -> '{s[4]}'")
            elif s[0] == "filter":
                print(f"  filter {s[2]} (dash {s[1]}): '{s[3]}' -> '{s[4]}'")
        for dash_id, key, old, new in layout_fixes:
            print(f"  layout dash {dash_id} {key}: '{old}' -> '{new}'")

        if args.show or args.dry_run:
            print("(no changes made)")
            return

        full_backup(con)
        with con:
            apply_all(con, steps, layout_fixes, None)
        print("APPLIED. Revert with --revert; nuclear option is the .bak file.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
