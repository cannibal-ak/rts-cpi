#!/usr/bin/env python3
"""Add a 'Trip Type' native filter to DreamAir dashboard 7.

Appends one filter_select entry (id NATIVE_FILTER-TripType, column trip_type,
dataset 40) to dash 7's native_filter_configuration. The external filter bar
renders whatever filter-config returns and trip_type is not in DreamAir's
hidden_filter_columns registry, so the bar picks it up with no code change.

Scope mirrors NATIVE_FILTER-Stops exactly: Pricing Recommendations (114/124)
and Velocity (117) excluded, and — like every existing filter on this
dashboard — Composition (120) and Deployed Capacity (122) are not in
chartsInScope.

Revert is entry-level, not blob-level: the backup table records only that the
entry was added, and --revert removes it from the CURRENT config, so another
session's concurrent json_metadata edits are never clobbered.

  Apply:   docker exec -i cpi-superset-1 python3 - < this_file
  Revert:  docker exec -i cpi-superset-1 python3 - --revert < this_file
  Show:    docker exec -i cpi-superset-1 python3 - --show < this_file

Take the external superset.db backup BEFORE running, per standing rule.
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 7
FILTER_ID = "NATIVE_FILTER-TripType"
BACKUP_TABLE = "_da_dash7_triptype_backup"

ENTRY = {
    "id": FILTER_ID,
    "name": "Trip Type",
    "filterType": "filter_select",
    "controlValues": {
        "enableEmptyFilter": False,
        "defaultToFirstItem": False,
        "multiSelect": True,
        "searchAllOptions": False,
        "inverseSelection": False,
    },
    "targets": [{"datasetId": 40, "column": {"name": "trip_type"}}],
    "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
    "cascadeParentIds": [],
    "scope": {"rootPath": ["ROOT_ID"], "excluded": [114, 124, 117]},
    "type": "NATIVE_FILTER",
    "description": "One-way vs round-trip",
    "chartsInScope": [121, 113, 123, 118, 119, 115, 116],
    "tabsInScope": [],
}


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _load(con):
    raw = con.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                      (DASH_ID,)).fetchone()[0] or "{}"
    return json.loads(raw)


def _save(con, jm):
    con.execute("UPDATE dashboards SET json_metadata=?, changed_on=? WHERE id=?",
                (json.dumps(jm), _now(), DASH_ID))


def show(con):
    nfc = _load(con).get("native_filter_configuration") or []
    print("dash %d: %d native filters" % (DASH_ID, len(nfc)))
    for f in nfc:
        tgt = (f.get("targets") or [{}])[0]
        col = (tgt.get("column") or {}).get("name")
        mark = " <== ours" if f.get("id") == FILTER_ID else ""
        print("  %-28s %-22s col=%s ds=%s%s"
              % (f.get("id"), f.get("name"), col, tgt.get("datasetId"), mark))


def apply(con):
    if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                   (BACKUP_TABLE,)).fetchone():
        print("backup table %s exists -- already applied. --revert first." % BACKUP_TABLE)
        return 1
    jm = _load(con)
    nfc = jm.get("native_filter_configuration") or []
    if any(f.get("id") == FILTER_ID for f in nfc):
        print("filter %s already present -- refusing." % FILTER_ID)
        return 1
    con.execute("CREATE TABLE %s (dash_id INTEGER, filter_id TEXT, added_at TEXT)"
                % BACKUP_TABLE)
    con.execute("INSERT INTO %s VALUES (?,?,?)" % BACKUP_TABLE,
                (DASH_ID, FILTER_ID, _now()))
    nfc.append(ENTRY)
    jm["native_filter_configuration"] = nfc
    _save(con, jm)
    con.commit()
    print("APPLIED: %s appended (%d filters now on dash %d)."
          % (FILTER_ID, len(nfc), DASH_ID))
    return 0


def revert(con):
    if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (BACKUP_TABLE,)).fetchone():
        print("no backup table %s -- nothing to revert." % BACKUP_TABLE)
        return 1
    jm = _load(con)
    nfc = jm.get("native_filter_configuration") or []
    kept = [f for f in nfc if f.get("id") != FILTER_ID]
    if len(kept) == len(nfc):
        print("filter %s not found in current config -- dropping table only." % FILTER_ID)
    else:
        jm["native_filter_configuration"] = kept
        _save(con, jm)
    con.execute("DROP TABLE %s" % BACKUP_TABLE)
    con.commit()
    print("REVERTED: %s removed (%d filters remain)." % (FILTER_ID, len(kept)))
    return 0


def main():
    ap = argparse.ArgumentParser()
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
