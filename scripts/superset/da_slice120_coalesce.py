#!/usr/bin/env python3
"""Fix slice 120 (DreamAir 'Fare Composition — Base / Tax / YQ', dist_bar).

BUG. The three metrics are ROUND(AVG(NULLIF(<col>, 0))::numeric, 2). On any
cap_date where every airline's yq is 0/NULL (172 of DA's 291 cap dates,
including the latest, 2026-08-12), AVG returns NULL for every group, pandas
pivot_table(dropna=True) drops the all-NaN 'YQ' column, and viz.py:1333
`pt = pt[metrics]` raises KeyError "['YQ'] not in index" — the dashboard shows
"Unexpected error". Reproduced 2026-08-20 in-container via viz.get_payload().

FIX. Wrap each metric in COALESCE(<old>, 0) so the result column is always
numeric and survives the pivot. A group with no YQ renders a 0-height segment
(nvd3 stacked draws nothing for 0), same visual as before. All three metrics
are wrapped symmetrically so no filter combination can crash on Base/Tax.

Revert is metric-level: the backup table stores each metric's prior
sqlExpression keyed by optionName, in both params and query_context.

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
SLICE_ID = int(__import__("os").environ.get("SLICE_ID", "120"))
BACKUP_TABLE = "_da_slice%d_coalesce_backup" % SLICE_ID
LABELS = ("Base", "Tax", "YQ")


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def wrap(expr):
    return "COALESCE(%s, 0)" % expr


def is_wrapped(expr):
    return expr.strip().upper().startswith("COALESCE(")


def iter_metrics(container):
    for m in container.get("metrics") or []:
        if isinstance(m, dict) and m.get("label") in LABELS \
                and m.get("expressionType") == "SQL":
            yield m


def show(con):
    p, qc = con.execute(
        "SELECT params, query_context FROM slices WHERE id=?", (SLICE_ID,)).fetchone()
    for tag, blob, path in (("params", p, None), ("query_context", qc, "form_data")):
        if not blob:
            print("%s: EMPTY" % tag)
            continue
        d = json.loads(blob)
        if path:
            d = d.get(path) or {}
        for m in iter_metrics(d):
            print("%s  %-4s wrapped=%s  %s"
                  % (tag, m["label"], is_wrapped(m["sqlExpression"]), m["sqlExpression"]))


def apply(con):
    if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                   (BACKUP_TABLE,)).fetchone():
        print("backup table %s exists -- already applied. --revert first." % BACKUP_TABLE)
        return 1
    con.execute("CREATE TABLE %s (target TEXT, option_name TEXT, old_expr TEXT)"
                % BACKUP_TABLE)

    p, qc = con.execute(
        "SELECT params, query_context FROM slices WHERE id=?", (SLICE_ID,)).fetchone()
    n = 0

    params = json.loads(p)
    for m in iter_metrics(params):
        if is_wrapped(m["sqlExpression"]):
            continue
        con.execute("INSERT INTO %s VALUES (?,?,?)" % BACKUP_TABLE,
                    ("params", m.get("optionName", m["label"]), m["sqlExpression"]))
        m["sqlExpression"] = wrap(m["sqlExpression"])
        n += 1
    con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                (json.dumps(params), _now(), SLICE_ID))

    if qc:
        try:
            q = json.loads(qc)
        except ValueError:
            q = None
            print("query_context not JSON -- params-only fix")
        if q is not None:
            targets = [q.get("form_data") or {}]
            targets += q.get("queries") or []
            for t in targets:
                for m in iter_metrics(t):
                    if is_wrapped(m["sqlExpression"]):
                        continue
                    con.execute("INSERT INTO %s VALUES (?,?,?)" % BACKUP_TABLE,
                                ("query_context", m.get("optionName", m["label"]),
                                 m["sqlExpression"]))
                    m["sqlExpression"] = wrap(m["sqlExpression"])
                    n += 1
            con.execute("UPDATE slices SET query_context=? WHERE id=?",
                        (json.dumps(q), SLICE_ID))

    con.commit()
    print("APPLIED: %d metric expressions wrapped on slice %d." % (n, SLICE_ID))
    return 0


def revert(con):
    if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (BACKUP_TABLE,)).fetchone():
        print("no backup table %s -- nothing to revert." % BACKUP_TABLE)
        return 1
    rows = list(con.execute("SELECT target, option_name, old_expr FROM %s" % BACKUP_TABLE))
    by_target = {}
    for target, opt, old in rows:
        by_target.setdefault(target, {})[opt] = old

    p, qc = con.execute(
        "SELECT params, query_context FROM slices WHERE id=?", (SLICE_ID,)).fetchone()

    if "params" in by_target:
        params = json.loads(p)
        for m in iter_metrics(params):
            key = m.get("optionName", m["label"])
            if key in by_target["params"]:
                m["sqlExpression"] = by_target["params"][key]
        con.execute("UPDATE slices SET params=?, changed_on=? WHERE id=?",
                    (json.dumps(params), _now(), SLICE_ID))

    if "query_context" in by_target and qc:
        q = json.loads(qc)
        targets = [q.get("form_data") or {}]
        targets += q.get("queries") or []
        for t in targets:
            for m in iter_metrics(t):
                key = m.get("optionName", m["label"])
                if key in by_target["query_context"]:
                    m["sqlExpression"] = by_target["query_context"][key]
        con.execute("UPDATE slices SET query_context=? WHERE id=?",
                    (json.dumps(q), SLICE_ID))

    con.execute("DROP TABLE %s" % BACKUP_TABLE)
    con.commit()
    print("REVERTED slice %d (%d expressions restored, table dropped)."
          % (SLICE_ID, len(rows)))
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
