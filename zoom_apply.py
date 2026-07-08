#!/usr/bin/env python
"""APPLY Data Zoom (zoomable=true) to eligible charts on the target dashboards.
Idempotent: only modifies whitelisted charts whose zoomable is not already true.
Preserves every other key in params; only the one flag is added/changed.
Does NOT touch query_context.
"""
import json
import sqlite3

DB_PATH = "/app/superset_home/superset.db"
DASHBOARD_IDS = [1, 2, 3]  # JY=1, FJL=2, PW=3

ZOOM_SUPPORTED = {
    "echarts_timeseries",
    "echarts_timeseries_line",
    "echarts_timeseries_bar",
    "echarts_timeseries_smooth",
    "echarts_timeseries_step",
    "echarts_timeseries_scatter",
    "echarts_area",
    "mixed_timeseries",
}


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Collect distinct slice_ids attached to target dashboards.
    placeholders = ",".join("?" for _ in DASHBOARD_IDS)
    cur.execute(
        """
        SELECT DISTINCT s.id, s.slice_name, s.viz_type, s.params
        FROM dashboard_slices ds
        JOIN slices s ON s.id = ds.slice_id
        WHERE ds.dashboard_id IN (%s)
        ORDER BY s.id
        """ % placeholders,
        DASHBOARD_IDS,
    )
    rows = cur.fetchall()

    changed = []
    skipped_unsupported = 0
    skipped_already = 0
    skipped_bad = 0

    for sid, sname, viz, params in rows:
        if viz not in ZOOM_SUPPORTED:
            skipped_unsupported += 1
            continue
        if params is None or str(params).strip() == "":
            skipped_bad += 1
            print("SKIP (empty params) slice %s : %s" % (sid, sname))
            continue
        try:
            p = json.loads(params)
        except (ValueError, TypeError):
            skipped_bad += 1
            print("SKIP (invalid JSON) slice %s : %s" % (sid, sname))
            continue
        if not isinstance(p, dict):
            skipped_bad += 1
            print("SKIP (params not object) slice %s : %s" % (sid, sname))
            continue
        if p.get("zoomable") is True:
            skipped_already += 1
            continue
        p["zoomable"] = True
        new_params = json.dumps(p)
        cur.execute("UPDATE slices SET params = ? WHERE id = ?", (new_params, sid))
        changed.append((sid, sname, viz))
        print("CHANGED slice %s : %s [%s]  zoomable -> true" % (sid, sname, viz))

    conn.commit()

    print("-" * 70)
    print("APPLY SUMMARY")
    print("  changed             : %d" % len(changed))
    print("  skipped already-true: %d" % skipped_already)
    print("  skipped unsupported : %d" % skipped_unsupported)
    print("  skipped bad params  : %d" % skipped_bad)
    if changed:
        print("  changed ids         : %s" % ", ".join(str(c[0]) for c in changed))
    print("-" * 70)
    conn.close()


if __name__ == "__main__":
    main()
