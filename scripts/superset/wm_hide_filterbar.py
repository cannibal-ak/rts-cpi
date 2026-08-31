#!/usr/bin/env python3
"""Hide the Superset-native vertical filter bar on the WM dashboard (id 6),
EMBEDDED view only. The teal WinairTopFilterBar in the CPI app drives the same
11 native filters via the native_filters urlParam, so the in-iframe panel is a
duplicate. Appends a marked CSS block to dashboards.css WHERE id=6; idempotent.

Run inside the superset container:  python3 /tmp/_wm_hide_filterbar.py
Rollback: restore css from dashboard_meta_backups/dash6_hidefb1a_<TS>.json
(UPDATE dashboards SET css=?, changed_on=? WHERE id=6).
"""
import datetime
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 6
MARKER = "WM-EMBED-HIDE-FILTERBAR v1"

CSS = """
/* ==== WM-EMBED-HIDE-FILTERBAR v1 (dash 6 ONLY -- do not copy to other dashboards) ====
   Hides the native vertical filter bar in the EMBEDDED view only. The teal
   WinairTopFilterBar drives the same 11 native filters via the native_filters
   urlParam; they keep applying through redux dataMask -- only the panel UI is hidden. */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] [data-test="filter-bar"] {
  display: none !important;
}
/* FiltersPanel wrapper (emotion-hash-only class): collapse its `auto` grid column */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] div:has(> div > [data-test="filter-bar"]) {
  display: none !important;
}
/* Neutralize inline margin-left:-32px on the top-level tabs wrapper (would clip tabs) */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] div:has(> div > [data-test="filter-bar"]) ~ div > .dragdroppable.dragdroppable-column {
  margin-left: 0 !important;
}
/* Symmetric grid margins (stock collapsed layout is 32px both sides) */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] div:has(> div > [data-test="filter-bar"]) ~ div .grid-container {
  margin-left: 32px !important;
}
/* The 1px sidebar width-resizer hover strip */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] .sidebar-resizer {
  display: none !important;
}
/* ==== end WM-EMBED-HIDE-FILTERBAR v1 ==== */
"""


def main():
    con = sqlite3.connect(DB, timeout=30)
    try:
        row = con.execute(
            "SELECT css, length(css) FROM dashboards WHERE id=?", (DASH_ID,)
        ).fetchone()
        if row is None:
            print("ERROR: dashboard id %d not found" % DASH_ID)
            return 1
        css, old_len = row[0] or "", row[1] or 0
        if MARKER in css:
            print("already applied (marker present); no-op. css_len=%d" % old_len)
            return 0
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
        con.execute(
            "UPDATE dashboards SET css = css || ?, changed_on = ? WHERE id = ?",
            ("\n" + CSS, now, DASH_ID),
        )
        con.commit()
        new_len = con.execute(
            "SELECT length(css) FROM dashboards WHERE id=?", (DASH_ID,)
        ).fetchone()[0]
        print("applied: css_len %d -> %d, changed_on=%s" % (old_len, new_len, now))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
