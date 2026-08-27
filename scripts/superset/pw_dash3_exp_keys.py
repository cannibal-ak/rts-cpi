#!/usr/bin/env python3
"""Bind the Exp carrier on PW's dashboard 3.

THE GAP. Dashboard 3's json_metadata.label_colors carries 28 keys for the
carrier set the original PW provisioning produced. The historical data holds a
carrier `comp_al = 'Exp'` -- 32,557 rows -- that is absent from those 28 keys,
so any series Exp produces falls through to the palette default instead of a
pinned colour.

WHY IT LOOKS FINE TODAY. An unmatched key is silently ignored, and so is a
missing one: the series just falls through to the theme palette's first slot.
Exp only surfaces on requests that reach its historical cap_dates, so
date-scoped renders pass and the gap hides.

THE FIX -- ONE KEY, SLATE. This script appends exactly one key:

    "Exp": "#64748B"

#64748B (slate) is a neutral overflow hue with no collision against PW's
green/gold carrier set. Its low chroma is the point of a neutral fallback
slot -- do not saturate it.

Applied to the dashboard AND all dash-3 slices that carry a label_colors dict,
because that is the shape provisioning leaves behind: the dashboard's copy is
the one that binds when a chart renders inside a dashboard (Chart.jsx
overwrites each slice's copy); the slice copies keep Explore consistent.
Nothing but label_colors is touched.

IDEMPOTENCE / CONCURRENCY -- why revert is key-level, not payload-level.
Dashboard 3 may be edited by another session. Restoring a whole json_metadata
blob would silently discard that work, so this records only the key it
touches: whether it was absent or what it previously held (printed on apply,
and kept in the backup table for surgical revert). Running twice is a clean
abort: the backup table's existence marks "already applied". Revert deletes
what we added and restores what we overwrote, leaving every other key alone.
All writes run in one transaction and roll back together on any error.

  Apply:   docker exec cpi-superset-1 python3 /tmp/pw_dash3_exp_keys.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/pw_dash3_exp_keys.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/pw_dash3_exp_keys.py --show

Take the external timestamped-IST superset.db backup (suffix .pwexp) BEFORE
running, per the standing rule, e.g. inside the container:

  python3 -c "import sqlite3,datetime;\
src=sqlite3.connect('/app/superset_home/superset.db');\
ts=(datetime.datetime.utcnow()+datetime.timedelta(hours=5,minutes=30)).strftime('%Y%m%d-%H%M%S');\
dst=sqlite3.connect('/app/superset_home/superset.db.'+ts+'-IST.pwexp');\
src.backup(dst); dst.close(); src.close(); print('backup written', ts)"
"""
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 3
BACKUP_TABLE = "_pw_dash3_exp_keys_backup"

EXP = "#64748B"  # slate -- neutral overflow, no hue collision with PW green/gold

# Exactly one key. Exp is absent from dashboard 3's 28 existing keys.
EXP_KEYS = {
    "Exp": EXP,
}


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


def dash3_slice_ids(con):
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
    for sid in dash3_slice_ids(con):
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
            # Print the prior value so manual revert is possible even without
            # the backup table.
            print("  prior %s %s %-10s %s"
                  % (target, rid, key,
                     old if had else "-- ABSENT (delete on revert) --"))

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

    for sid in dash3_slice_ids(con):
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

    print("APPLIED. Reload dashboard 3 to see it.")
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
    global DASH_ID
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--dash-id", type=int, default=DASH_ID,
                    help="dashboard id (default %d)" % DASH_ID)
    args = ap.parse_args()
    DASH_ID = args.dash_id

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
