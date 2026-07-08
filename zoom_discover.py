#!/usr/bin/env python
"""READ-ONLY discovery of Data Zoom (zoomable) state across dashboard charts.
Makes NO writes. Opens superset.db read-only.
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


def zoomable_state(params_raw):
    """Return ('true'|'false'|'absent'|'invalid', parsed_or_None)."""
    if params_raw is None or str(params_raw).strip() == "":
        return "absent", None
    try:
        p = json.loads(params_raw)
    except (ValueError, TypeError):
        return "invalid", None
    if not isinstance(p, dict):
        return "invalid", None
    if "zoomable" not in p:
        return "absent", p
    return ("true" if p.get("zoomable") is True else "false"), p


def main():
    # read-only connection
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    cur = conn.cursor()

    grand = {"total": 0, "supported": 0, "already": 0, "tobe": 0, "unsupported": 0}

    for dash_id in DASHBOARD_IDS:
        cur.execute(
            "SELECT d.dashboard_title, d.id FROM dashboards d WHERE d.id=?",
            (dash_id,),
        )
        drow = cur.fetchone()
        dtitle = drow[0] if drow else "(dashboard not found)"
        print("=" * 92)
        print("DASHBOARD %s : %s" % (dash_id, dtitle))
        print("=" * 92)
        cur.execute(
            """
            SELECT s.id, s.slice_name, s.viz_type, s.params
            FROM dashboard_slices ds
            JOIN slices s ON s.id = ds.slice_id
            WHERE ds.dashboard_id = ?
            ORDER BY s.id
            """,
            (dash_id,),
        )
        rows = cur.fetchall()
        print(
            "%-9s | %-40s | %-26s | %-9s | %s"
            % ("slice_id", "slice_name", "viz_type", "zoom_sup", "zoomable_now")
        )
        print("-" * 92)
        for sid, sname, viz, params in rows:
            supported = viz in ZOOM_SUPPORTED
            state, _ = zoomable_state(params)
            grand["total"] += 1
            if supported:
                grand["supported"] += 1
                if state == "true":
                    grand["already"] += 1
                else:
                    grand["tobe"] += 1
            else:
                grand["unsupported"] += 1
            nm = (sname or "")[:40]
            print(
                "%-9s | %-40s | %-26s | %-9s | %s"
                % (sid, nm, viz, "Y" if supported else "N", state)
            )
        print("")

    print("=" * 92)
    print("SUMMARY (dashboards %s)" % DASHBOARD_IDS)
    print("-" * 92)
    print("  total charts        : %d" % grand["total"])
    print("  zoom-supported      : %d" % grand["supported"])
    print("  already enabled     : %d" % grand["already"])
    print("  to-be-enabled       : %d" % grand["tobe"])
    print("  unsupported (skip)  : %d" % grand["unsupported"])
    print("=" * 92)
    conn.close()


if __name__ == "__main__":
    main()
