#!/usr/bin/env python3
"""Complete dashboard 1's label_colors for the OLDER JY charts (43/46/47/50).

The 2026-09-01 backfill bound every NEW chart's series; the four older charts
still build composite series ('Avg Fare, JY', 'Min Fare, BW', ...) and the
velocity measure names, none of which have keys — 28 series fall through to
the scheme default (verify_dashboard_colors FAIL). This adds, ADDITIVELY and
at dashboard level only (dashboard label_colors bind for every chart; no
slice row is touched — slice 43 stays untouchable):

  * 'Avg Fare, X' / 'Min Fare, X' / 'Max Fare, X' for the 8 JY carriers,
    each = that carrier's existing bare-key hex (WM/DA composite pattern)
  * the six velocity measure spellings, translated to JY's palette the way
    DreamAir translated WinAir's (deep brand hue + tint for the seats pair,
    semantic green/violet for the rate pair; hexes avoid every carrier hue):
      Current Booking #1E4A7A (JY brand navy) · Capacity #7EA4C9 (navy tint)
      Actual Seat Factor(+' (1)') #10996B · Forecasted SF(+' (1)') #9B4FD8

Run inside cpi-superset-1:
  docker exec -i cpi-superset-1 python3 - --dry-run < scripts/superset/jy_dash1_key_completion.py
  docker exec -i cpi-superset-1 python3 - --apply   < scripts/superset/jy_dash1_key_completion.py
  docker exec -i cpi-superset-1 python3 - --revert  < scripts/superset/jy_dash1_key_completion.py

Backups on apply: full DB copy + in-DB table _jy_dash1_keys_backup listing
exactly the keys added (key-level revert; pre-existing keys are never
overwritten — an overlap aborts instead).
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
BACKUP_TABLE = "_jy_dash1_keys_backup"
DASH = 1

CARRIERS = ["JY", "BW", "WM", "9Q", "5L", "PY", "DO", "S6"]
COMPOSITE_PREFIXES = ["Avg Fare", "Min Fare", "Max Fare"]
MEASURES = {
    "Current Booking": "#1E4A7A",
    "Capacity": "#7EA4C9",
    "Actual Seat Factor": "#10996B",
    "Actual Seat Factor (1)": "#10996B",
    "Forecasted SF": "#9B4FD8",
    "Forecasted SF (1)": "#9B4FD8",
}


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
        rows = cur.execute(f"SELECT key FROM {BACKUP_TABLE}").fetchall()
        if not rows:
            die("backup table empty")
        meta = json.loads(cur.execute(
            "SELECT json_metadata FROM dashboards WHERE id=?", (DASH,)).fetchone()[0])
        for (k,) in rows:
            meta.get("label_colors", {}).pop(k, None)
        with con:
            cur.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                        (json.dumps(meta), now, DASH))
            cur.execute(f"DROP TABLE {BACKUP_TABLE}")
        print(f"reverted: {len(rows)} keys removed")
        return

    if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                   (BACKUP_TABLE,)).fetchone():
        die(f"{BACKUP_TABLE} exists — already applied")

    meta = json.loads(cur.execute(
        "SELECT json_metadata FROM dashboards WHERE id=?", (DASH,)).fetchone()[0])
    lc = meta.get("label_colors") or {}
    for c in CARRIERS:
        if c not in lc:
            die(f"carrier {c} has no bare key on dash {DASH} — survey stale")

    new_keys = {}
    for pfx in COMPOSITE_PREFIXES:
        for c in CARRIERS:
            new_keys[f"{pfx}, {c}"] = lc[c]
    new_keys.update(MEASURES)
    overlap = sorted(k for k in new_keys if k in lc)
    if overlap:
        die(f"keys already present (would overwrite): {overlap}")

    print(f"plan: add {len(new_keys)} keys to dash {DASH} label_colors "
          f"({len(lc)} -> {len(lc) + len(new_keys)}), 0 overwritten")
    for k in sorted(new_keys):
        print(f"  {k!r}: {new_keys[k]}")
    if args.dry_run:
        print("(no changes made)")
        return

    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    bak = f"{DB}.bak.{datetime.datetime.now(ist).strftime('%Y%m%dT%H%M%S')}_IST.jykeys"
    dst = sqlite3.connect(bak)
    with dst:
        con.backup(dst)
    dst.close()
    print(f"full backup: {bak}")

    lc.update(new_keys)
    meta["label_colors"] = lc
    with con:
        cur.execute(f"CREATE TABLE {BACKUP_TABLE} (key TEXT, ts TEXT)")
        cur.executemany(f"INSERT INTO {BACKUP_TABLE} VALUES (?,?)",
                        [(k, now) for k in new_keys])
        cur.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                    (json.dumps(meta), now, DASH))
    print("APPLIED. Revert with --revert.")


if __name__ == "__main__":
    main()
