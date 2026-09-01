#!/usr/bin/env python3
"""Reorder dashboard 1's native filters so JY's visible bar reads in the
canonical WM order: Route (O&D), Flight Number, Days Left, Stops, Trip Type —
then Fare Family (JY's approved extra) last. Hidden filters keep their
relative order at the tail. Entries are MOVED only — never edited.

  docker exec -i cpi-superset-1 python3 - --dry-run < scripts/superset/jy_filter_order.py
  docker exec -i cpi-superset-1 python3 - --apply   < scripts/superset/jy_filter_order.py
  docker exec -i cpi-superset-1 python3 - --revert  < scripts/superset/jy_filter_order.py

Backup: in-DB table _jy_filter_order_backup stores the prior id order
(the entries themselves are untouched, so order is the only thing to revert).
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
BACKUP_TABLE = "_jy_filter_order_backup"
DASH = 1

VISIBLE_ORDER = [
    "NATIVE_FILTER-Route",         # Route (O&D)
    "NATIVE_FILTER-FlightNumber",  # Flight Number
    "NATIVE_FILTER-DaysLeft",      # Days Left
    "NATIVE_FILTER-Stops",         # Stops
    "NATIVE_FILTER-TripType",      # Trip Type
    "NATIVE_FILTER-FareFamily",    # Fare Family — JY-only extra, last
]


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
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")

    meta = json.loads(cur.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?", (DASH,)).fetchone()[0])
    nf = meta.get("native_filter_configuration") or []
    by_id = {f["id"]: f for f in nf}

    if args.revert:
        row = cur.execute(f"SELECT id_order FROM {BACKUP_TABLE}").fetchone()
        if not row:
            die("backup table empty")
        order = json.loads(row[0])
        if set(order) != set(by_id):
            die("filter id set changed since apply — revert manually")
        meta["native_filter_configuration"] = [by_id[i] for i in order]
        with con:
            cur.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                        (json.dumps(meta), now, DASH))
            cur.execute(f"DROP TABLE {BACKUP_TABLE}")
        print("reverted filter order")
        return

    if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                   (BACKUP_TABLE,)).fetchone():
        die(f"{BACKUP_TABLE} exists — already applied")
    missing = [i for i in VISIBLE_ORDER if i not in by_id]
    if missing:
        die(f"expected filters missing: {missing}")

    tail = [f for f in nf if f["id"] not in VISIBLE_ORDER]
    new_order = [by_id[i] for i in VISIBLE_ORDER] + tail
    print("plan:", [f["name"] for f in new_order])
    if new_order == nf:
        print("already in canonical order — nothing to do")
        return
    if args.dry_run:
        print("(no changes made)")
        return

    meta["native_filter_configuration"] = new_order
    with con:
        cur.execute(f"CREATE TABLE {BACKUP_TABLE} (id_order TEXT, ts TEXT)")
        cur.execute(f"INSERT INTO {BACKUP_TABLE} VALUES (?,?)",
                    (json.dumps([f["id"] for f in nf]), now))
        cur.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                    (json.dumps(meta), now, DASH))
    print("APPLIED. Revert with --revert.")


if __name__ == "__main__":
    main()
