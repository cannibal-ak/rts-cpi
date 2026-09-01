#!/usr/bin/env python3
"""Sync PROD dataset 13 (jy_all_airlines_fares) to dev's SQL — the one
approved exception to the ds13-untouchable rule (Gate 1 D4d, 2026-08-31).

Dev wraps the fare columns in COALESCE(<col>, 0) (the 2026-08-05 d9463c5
continuous-series fix); prod still runs the raw columns, so prod JY charts
can break on NULL fares. This transforms prod's CURRENT sql in place:

    ref_tot_fare AS fare   ->  COALESCE(ref_tot_fare, 0) AS fare
    comp_tot_fare AS fare  ->  COALESCE(comp_tot_fare, 0) AS fare

and refuses to commit unless the result's whitespace-normalized md5 equals
dev's (8d22ea4f85be86f874db8e446b0965c4, measured 2026-08-31) — i.e. it can
only ever produce exactly the dev state, never a third variant.

Run inside PROD cpi-superset-1:
  docker exec -i cpi-superset-1 python3 - --dry-run < scripts/superset/jy_ds13_prod_sync.py
  docker exec -i cpi-superset-1 python3 - --apply   < scripts/superset/jy_ds13_prod_sync.py
  docker exec -i cpi-superset-1 python3 - --revert  < scripts/superset/jy_ds13_prod_sync.py

Backups on apply: full DB copy (sqlite3 backup API) named
superset.db.bak.<ts>_IST.ds13sync + in-DB table _jy_ds13_sync_backup with the
prior sql (also the applied-sentinel / revert source).
"""
import argparse
import datetime
import hashlib
import re
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
BACKUP_TABLE = "_jy_ds13_sync_backup"
DS = 13
DEV_NORM_MD5 = "8d22ea4f85be86f874db8e446b0965c4"

SUBS = [
    ("ref_tot_fare AS fare", "COALESCE(ref_tot_fare, 0) AS fare"),
    ("comp_tot_fare AS fare", "COALESCE(comp_tot_fare, 0) AS fare"),
]


def norm_md5(sql):
    return hashlib.md5(re.sub(r"\s+", " ", sql.strip().lower()).encode("utf-8")).hexdigest()


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

    if args.revert:
        row = cur.execute(f"SELECT old_sql FROM {BACKUP_TABLE}").fetchone()
        if not row:
            die("backup table empty")
        with con:
            cur.execute("UPDATE tables SET sql=?, changed_on=? WHERE id=?", (row[0], now, DS))
            cur.execute(f"DROP TABLE {BACKUP_TABLE}")
        print("reverted ds13 sql")
        return

    if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                   (BACKUP_TABLE,)).fetchone():
        die(f"{BACKUP_TABLE} exists — already applied")

    sql = cur.execute("SELECT sql FROM tables WHERE id=?", (DS,)).fetchone()[0]
    if norm_md5(sql) == DEV_NORM_MD5:
        print("ds13 already matches dev — nothing to do")
        return

    new = sql
    for old_frag, new_frag in SUBS:
        n = new.count(old_frag)
        if n != 1:
            die(f"expected exactly 1 occurrence of '{old_frag}', found {n} — SQL drifted")
        new = new.replace(old_frag, new_frag)
    if norm_md5(new) != DEV_NORM_MD5:
        die(f"transformed SQL md5 {norm_md5(new)} != dev {DEV_NORM_MD5} — refusing")

    print("plan: wrap ds13 fare columns in COALESCE(.., 0); result == dev's SQL exactly")
    if args.dry_run:
        print("(no changes made)")
        return

    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    bak = f"{DB}.bak.{datetime.datetime.now(ist).strftime('%Y%m%dT%H%M%S')}_IST.ds13sync"
    dst = sqlite3.connect(bak)
    with dst:
        con.backup(dst)
    dst.close()
    print(f"full backup: {bak}")

    with con:
        cur.execute(f"CREATE TABLE {BACKUP_TABLE} (old_sql TEXT, ts TEXT)")
        cur.execute(f"INSERT INTO {BACKUP_TABLE} VALUES (?,?)", (sql, now))
        cur.execute("UPDATE tables SET sql=?, changed_on=? WHERE id=?", (new, now, DS))
    print("APPLIED. Revert with --revert.")


if __name__ == "__main__":
    main()
