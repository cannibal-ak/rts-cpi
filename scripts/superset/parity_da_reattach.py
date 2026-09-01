#!/usr/bin/env python3
"""Re-attach DreamAir's Deployed Capacity chart (slice 122) to dashboard 7,
mirroring WinAir's dash-6 Velocity-tab structure exactly (Gate 1 D4b —
undoes the 2026-08-20 detach).

What it does, single transaction:
  * INSERT dashboard_slices (7, 122)
  * position_json: recreate the WM-shaped subtree — TAB-wmvel-1
    ('🛫 Deployed Capacity') → ROW-wm-vel-1 → CHART-wm-depcap with
    chartId 122, slice 122's uuid, WM's displayed header + sliceNameOverride
    ('Flights Operated by Airline'), height 60 / width 12 — and append
    TAB-wmvel-1 to TABS-wmvel's children.
  * json_metadata: add 122 to global_chart_configuration.chartsInScope
    (WM has 110 there). Native filter scopes untouched — on WM, slice 110 is
    in no filter's chartsInScope and no scope.excluded, and 122 mirrors that.

Run INSIDE cpi-superset-1:
  docker exec -i cpi-superset-1 python3 - --dry-run < scripts/superset/parity_da_reattach.py
  docker exec -i cpi-superset-1 python3 - --apply   < scripts/superset/parity_da_reattach.py
  docker exec -i cpi-superset-1 python3 - --revert  < scripts/superset/parity_da_reattach.py

Backups: full DB copy (sqlite3 backup API, WAL-safe) named
superset.db.bak.<ts>_IST.dareattach + in-DB table _parity_da_reattach_backup
holding dash 7's prior position_json/json_metadata (also the applied-sentinel).
"""
import argparse
import datetime
import json
import sqlite3
import sys
import uuid as uuidlib

DB = "/app/superset_home/superset.db"
BACKUP_TABLE = "_parity_da_reattach_backup"
DASH = 7
SLICE = 122

NEW_NODES = {
    "TAB-wmvel-1": {
        "children": ["ROW-wm-vel-1"],
        "id": "TAB-wmvel-1",
        "meta": {"defaultText": "\U0001f6eb Deployed Capacity",
                 "placeholder": "\U0001f6eb Deployed Capacity",
                 "text": "\U0001f6eb Deployed Capacity"},
        "parents": ["ROOT_ID", "GRID_ID", "TABS-wmTopNav", "TAB-wmNav5", "TABS-wmvel"],
        "type": "TAB",
    },
    "ROW-wm-vel-1": {
        "children": ["CHART-wm-depcap"],
        "id": "ROW-wm-vel-1",
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": ["ROOT_ID", "GRID_ID", "TABS-wmTopNav", "TAB-wmNav5", "TABS-wmvel",
                    "TAB-wmvel-1"],
        "type": "ROW",
    },
    "CHART-wm-depcap": {
        "children": [],
        "id": "CHART-wm-depcap",
        "type": "CHART",
        "meta": {"chartId": SLICE, "height": 60, "width": 12,
                 "sliceName": "Deployed Capacity — Flights Operated by Airline",
                 "sliceNameOverride": "Flights Operated by Airline",
                 "uuid": None},  # filled from slice 122's real uuid at runtime
        "parents": ["ROOT_ID", "GRID_ID", "TABS-wmTopNav", "TAB-wmNav5", "TABS-wmvel",
                    "TAB-wmvel-1", "ROW-wm-vel-1"],
    },
}


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _ist_stamp():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).strftime("%Y%m%dT%H%M%S")


def die(msg):
    sys.exit(f"ABORT (nothing committed): {msg}")


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    cur = con.cursor()

    if args.revert:
        row = cur.execute(
            f"SELECT position_json, json_metadata FROM {BACKUP_TABLE}").fetchone()
        if not row:
            die("backup table empty")
        with con:
            cur.execute("UPDATE dashboards SET position_json=?, json_metadata=?, "
                        "changed_on=? WHERE id=?", (row[0], row[1], _now(), DASH))
            cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                        (DASH, SLICE))
            cur.execute(f"DROP TABLE {BACKUP_TABLE}")
        print("reverted: slice 122 detached again, dash 7 layout/metadata restored")
        return

    if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                   (BACKUP_TABLE,)).fetchone():
        die(f"{BACKUP_TABLE} exists — already applied")

    srow = cur.execute("SELECT slice_name, uuid FROM slices WHERE id=?", (SLICE,)).fetchone()
    if not srow:
        die(f"slice {SLICE} missing")
    if srow[0] != "Deployed Capacity — Flights Operated by Airline":
        die(f"slice {SLICE} name is '{srow[0]}' — survey stale")
    slice_uuid = str(uuidlib.UUID(bytes=srow[1])) if isinstance(srow[1], bytes) else str(srow[1])
    if cur.execute("SELECT 1 FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                   (DASH, SLICE)).fetchone():
        die("dashboard_slices row already present")

    pj_raw, meta_raw = cur.execute(
        "SELECT position_json, json_metadata FROM dashboards WHERE id=?", (DASH,)).fetchone()
    pj, meta = json.loads(pj_raw), json.loads(meta_raw)

    for key in NEW_NODES:
        if key in pj:
            die(f"layout node {key} already exists on dash {DASH}")
    tabs = pj.get("TABS-wmvel")
    if not tabs or tabs.get("children") != ["TAB-wmvel-0"]:
        die(f"TABS-wmvel children unexpected: {tabs and tabs.get('children')}")
    gcc = meta.get("global_chart_configuration") or {}
    scope = gcc.get("chartsInScope") or []
    if SLICE in scope:
        die("122 already in global_chart_configuration scope")

    print(f"plan: attach slice {SLICE} (uuid {slice_uuid}) to dash {DASH}: "
          f"dashboard_slices row + 3 layout nodes + global scope entry")
    if args.dry_run:
        print("(no changes made)")
        return

    # full DB backup (WAL-safe)
    bak = f"{DB}.bak.{_ist_stamp()}_IST.dareattach"
    dest = sqlite3.connect(bak)
    with dest:
        con.backup(dest)
    dest.close()
    print(f"full backup: {bak}")

    nodes = json.loads(json.dumps(NEW_NODES))  # deep copy
    nodes["CHART-wm-depcap"]["meta"]["uuid"] = slice_uuid
    pj.update(nodes)
    pj["TABS-wmvel"]["children"].append("TAB-wmvel-1")
    scope.append(SLICE)
    gcc["chartsInScope"] = scope
    meta["global_chart_configuration"] = gcc

    with con:
        cur.execute(f"CREATE TABLE {BACKUP_TABLE} (position_json TEXT, json_metadata TEXT, ts TEXT)")
        cur.execute(f"INSERT INTO {BACKUP_TABLE} VALUES (?,?,?)", (pj_raw, meta_raw, _now()))
        cur.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                    (DASH, SLICE))
        cur.execute("UPDATE dashboards SET position_json=?, json_metadata=?, changed_on=? "
                    "WHERE id=?", (json.dumps(pj), json.dumps(meta), _now(), DASH))
    print("APPLIED. Revert with --revert.")


if __name__ == "__main__":
    main()
