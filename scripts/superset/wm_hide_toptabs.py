#!/usr/bin/env python3
"""Hide Superset's own top-level tab row on the WM dashboard (id 6), EMBEDDED view only.

The CPI app renders WinAir's five sections as its own tab bar (WinairTabBar) and
deep-links each one with a minted permalink (``activeTabs``), so Superset's outer
tab row inside the iframe is a second, competing navigation for the same thing.
This appends a marked CSS block to ``dashboards.css`` WHERE id=6. Idempotent.

  Apply:   docker exec cpi-superset-1 python3 /tmp/wm_hide_toptabs.py
  Revert:  docker exec cpi-superset-1 python3 /tmp/wm_hide_toptabs.py --revert
  Inspect: docker exec cpi-superset-1 python3 /tmp/wm_hide_toptabs.py --show

Companion to ``_wm_hide_filterbar.py`` (WM-EMBED-HIDE-FILTERBAR v1), and it uses
the same ``#app[data-bootstrap*=...]`` gate so the change is invisible in the
admin dashboard view. Lives in the repo rather than a home directory because the
filter-bar script exists on exactly one machine and cannot be undone anywhere else.

VERIFY BEFORE TRUSTING IT. In the Superset iframe's console:

    [...document.querySelectorAll('.ant-tabs-nav')]
      .map(n => [n.parentElement.id, getComputedStyle(n).display])

PASS  = exactly one entry reads ["TABS-wmTopNav", "none"], every other entry is
        NOT "none" (those are the Line/Bar/Table sub-tabs, which must survive).
FAIL  = any nested id shows "none" -> --revert immediately, then switch to
        VARIANT_STRUCTURAL below, which does not depend on the id at all.

ORDERING RULE: a code revert does NOT undo this. Reverting the app first would
leave WinAir with no tab navigation whatsoever. Roll back CSS FIRST, then code.

DURABILITY GAP: ``TABS-wmTopNav`` exists only as hand-applied layout state on the
dev host — ``grep -rn wmTopNav`` over this repo finds nothing but this file, and
``scripts/superset_provision_winair.py`` would flatten it back if re-run.
Production's dashboard 6 has no such node (its five sections sit directly in the
grid), so this block is INERT there — which is the safe direction, but also why
the tab bar cannot ship to production without restructuring that layout first.
"""
import argparse
import datetime
import sqlite3
import sys

DB = "/app/superset_home/superset.db"
DASH_ID = 6
MARKER = "WM-EMBED-HIDE-TOPTABS v1"

# Precise variant. Superset renders each TABS layout node's antd <Tabs> with
# id={component.id} (verified in the dashboard chunk: `(0,s.tZ)(g.cl,{id:t.id,`),
# so the outer strip is #TABS-wmTopNav. The `>` combinator makes reaching a
# nested sub-tab row structurally impossible: those live several levels deeper,
# inside .ant-tabs-content-holder > ... > .ant-tabs-tabpane, under their own ids.
VARIANT_ID = """
/* ==== WM-EMBED-HIDE-TOPTABS v1 (dash 6 ONLY -- do not copy to other dashboards) ====
   The CPI app draws this dashboard's five sections as its own tab bar, so
   Superset's outer tab row would duplicate it. EMBEDDED VIEW ONLY -- the
   #app[data-bootstrap*=...] prefix never matches the admin dashboard view.
   FRAGILE: that gate depends on json.dumps' default separators and on
   "dashboard_id" being the first key of the "embedded" dict in
   superset/embedded/view.py. A Superset upgrade changing either silently
   disables this block AND WM-EMBED-HIDE-FILTERBAR v1. It fails OPEN (the row
   comes back), which is the safe direction. Inert without #TABS-wmTopNav. */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] #TABS-wmTopNav > .ant-tabs-nav {
  display: none !important;
}
/* ==== end WM-EMBED-HIDE-TOPTABS v1 ==== */
"""

# Fallback that does not depend on the id reaching the DOM. Hides every
# dashboard tab row, then restores any that sits inside a tab pane -- which is
# precisely what makes a row a SUB-tab row. The second rule carries an extra
# ancestor, so it wins on specificity. Height rather than display, so restoring
# never has to guess what the original display value was.
VARIANT_STRUCTURAL = """
/* ==== WM-EMBED-HIDE-TOPTABS v1 (dash 6 ONLY -- structural variant) ==== */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] .dashboard-component-tabs > .ant-tabs > .ant-tabs-nav {
  height: 0 !important; overflow: hidden !important; visibility: hidden !important; margin: 0 !important;
}
#app[data-bootstrap*='"embedded": {"dashboard_id"'] .ant-tabs-tabpane .dashboard-component-tabs > .ant-tabs > .ant-tabs-nav {
  height: auto !important; overflow: visible !important; visibility: visible !important;
}
/* ==== end WM-EMBED-HIDE-TOPTABS v1 ==== */
"""


def _now() -> str:
    # Matches the format already stored in dashboards.changed_on.
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--revert", action="store_true", help="Remove the marked block.")
    ap.add_argument("--show", action="store_true", help="Print the dashboard's css and exit.")
    ap.add_argument(
        "--structural", action="store_true",
        help="Apply the id-independent variant instead (use if the id check FAILED).",
    )
    args = ap.parse_args()

    con = sqlite3.connect(DB, timeout=30)
    try:
        row = con.execute("SELECT css FROM dashboards WHERE id=?", (DASH_ID,)).fetchone()
        if row is None:
            print("ERROR: dashboard id %d not found" % DASH_ID)
            return 1
        css = row[0] or ""

        if args.show:
            print(css)
            return 0

        start = css.find("/* ==== " + MARKER)
        end_tag = "/* ==== end " + MARKER + " ==== */"
        end = css.find(end_tag)

        if args.revert:
            if start == -1 or end == -1:
                print("marker not present; nothing to revert. css_len=%d" % len(css))
                return 0
            new_css = css[:start] + css[end + len(end_tag):]
            con.execute(
                "UPDATE dashboards SET css=?, changed_on=? WHERE id=?",
                (new_css, _now(), DASH_ID),
            )
            con.commit()
            print("reverted. css_len %d -> %d" % (len(css), len(new_css)))
            return 0

        if start != -1:
            print("already applied (marker present); no-op. css_len=%d" % len(css))
            return 0

        block = VARIANT_STRUCTURAL if args.structural else VARIANT_ID
        new_css = css + block
        con.execute(
            "UPDATE dashboards SET css=?, changed_on=? WHERE id=?",
            (new_css, _now(), DASH_ID),
        )
        con.commit()
        print("applied %s variant. css_len %d -> %d"
              % ("structural" if args.structural else "id", len(css), len(new_css)))
        print("VERIFY NOW in the iframe console -- see this file's docstring.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
