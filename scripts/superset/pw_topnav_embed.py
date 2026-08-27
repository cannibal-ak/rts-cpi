#!/usr/bin/env python3
"""Give PW (dashboard 3) the WinAir-style embedded-dashboard treatment.

Two stages, both idempotent, both against ``dashboards`` WHERE id=--dash-id:

  wrap  position_json: wrap the eight grid-level rows in one top-level nav
        TABS node (``TABS-pwTopNav`` + ``TAB-pwNav1..4``), exactly the shape
        WinAir's ``TABS-wmTopNav`` has on dash 6, so the API's
        ``_tabs_are_navigation`` turns true and the CPI app's tab bar (the
        WinairTabBar rendered for any chrome tenant) can drive sections via
        minted permalinks. Dash 3's grid is flat ROWs (no section TABS
        containers), so each nav tab adopts a LIST of rows as its children.
        Sets the inert ``show_native_filters: false`` for metadata parity
        with dashes 6/7/8.
  css   append PW-EMBED-HIDE-FILTERBAR v1 + PW-EMBED-HIDE-TOPTABS v1, the PW
        adaptations of the WM blocks on dash 6 (``_wm_hide_filterbar.py`` and
        ``scripts/superset/wm_hide_toptabs.py``). Embedded view ONLY — the
        ``#app[data-bootstrap*=...]`` gate never matches the admin view. No
        ink-bar override: dash 3's green css IS the native PW sheet.

Run INSIDE cpi-superset-1 (plain sqlite3, stdlib only), streaming from the
repo so the file never needs a docker cp:

  Recon:   docker exec -i cpi-superset-1 python3 - --show    < scripts/superset/pw_topnav_embed.py
  Dry-run: docker exec -i cpi-superset-1 python3 - --dry-run < scripts/superset/pw_topnav_embed.py
  Wrap:    docker exec -i cpi-superset-1 python3 - --stage wrap < scripts/superset/pw_topnav_embed.py
  CSS:     docker exec -i cpi-superset-1 python3 - --stage css  < scripts/superset/pw_topnav_embed.py
  Revert:  docker exec -i cpi-superset-1 python3 - --revert  < scripts/superset/pw_topnav_embed.py

Before the first write it takes TWO backups: a full DB copy via the sqlite3
backup API (WAL-safe — never ``cp`` a live DB) named
``superset.db.bak.<YYYYMMDDTHHMMSS>_IST.pwtopnav``, and an in-DB snapshot of
the three edited columns in ``_pw_topnav_backup`` (also the revert source and
the applied-sentinel). ``--revert`` is the surgical inverse — rows back
under GRID in their recorded order, nav nodes deleted, css markers stripped,
``show_native_filters`` removed. The full .bak stays behind as the nuclear
option.

Verification contract (from the WM scripts, adapted):
  * layout: this script's validate() must print 0 problems pre- and
    post-commit; then GET /api/v1/superset/dashboards/2/tabs (the CPI app
    registry id for this dashboard is "2") must flip to
    tabs_are_navigation: true with the four TAB-pwNav ids.
  * admin view /superset/dashboard/3/ must still show everything (nav row
    VISIBLE there — the embed gate must not match).
  * in the EMBEDDED iframe's console:
      [...document.querySelectorAll('.ant-tabs-nav')]
        .map(n => [n.parentElement.id, getComputedStyle(n).display])
    PASS = exactly one entry ["TABS-pwTopNav", "none"], every other entry NOT
    "none" (Line/Bar/Table sub-tabs must survive). FAIL -> --revert, then
    re-apply --stage css --structural (id-independent variant).

ORDERING RULE (inherited from wm_hide_toptabs.py): an app-code revert does NOT
undo the css. If the PW tab bar is ever rolled back in the app, revert the
css stage FIRST (else embedded PW has no top-level navigation at all).

PROD LATER: everything is keyed off --dash-id; run --show first and update
EXPECTED_GRID_CHILDREN if prod's dash 3 drifted. Guards abort on drift rather
than "fixing" it.
"""
# Derived from scripts/superset/jy_topnav_embed.py (the JY dash 1 build).
import argparse
import datetime
import json
import sqlite3
import sys

DB = "/app/superset_home/superset.db"

TOPNAV = "TABS-pwTopNav"

# Mirrors WM's semantic numbering (TAB-wmNav1..5): the id suffix identifies the
# section, the children array order is what renders. Unlike dashes 1/6, dash 3
# has no section TABS containers — the grid is flat ROWs — so the third element
# is a LIST of the grid rows each nav tab adopts, in render order.
NAV_TABS = [
    ("TAB-pwNav1", "Avg_Fare", ["ROW-1", "ROW-2"]),
    ("TAB-pwNav2", "Min/Max_Fare", ["ROW-3", "ROW-4", "ROW-5", "ROW-6"]),
    ("TAB-pwNav3", "Booking & Seat Factor", ["ROW-7"]),
    ("TAB-pwNav4", "Lowest_Fares", ["ROW-8"]),
]

# The surveyed dev state (2026-08-27). A guard, not a target: any drift aborts.
EXPECTED_GRID_CHILDREN = ["ROW-1", "ROW-2", "ROW-3", "ROW-4", "ROW-5", "ROW-6", "ROW-7", "ROW-8"]
EXPECTED_BASE_CSS_LEN = 11594  # warn-only

MARKER_FB = "PW-EMBED-HIDE-FILTERBAR v1"
MARKER_TT = "PW-EMBED-HIDE-TOPTABS v1"

CSS_FILTERBAR = """
/* ==== PW-EMBED-HIDE-FILTERBAR v1 (dash 3 ONLY -- do not copy to other dashboards) ====
   Hides the native vertical filter bar in the EMBEDDED view only. The PW
   top filter bar in the CPI app drives the same native filters via the
   native_filters urlParam; they keep applying through redux dataMask -- only
   the panel UI is hidden. Adapted from WM-EMBED-HIDE-FILTERBAR v1 on dash 6.
   FRAGILE: the #app[data-bootstrap*=...] gate depends on json.dumps' default
   separators and on "dashboard_id" being the first key of the "embedded"
   dict in superset/embedded/view.py. A Superset upgrade changing either
   silently disables this block AND the TOPTABS block below. It fails OPEN
   (the panel comes back), which is the safe direction. */
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
/* ==== end PW-EMBED-HIDE-FILTERBAR v1 ==== */
"""

CSS_TOPTABS_ID = """
/* ==== PW-EMBED-HIDE-TOPTABS v1 (dash 3 ONLY -- do not copy to other dashboards) ====
   The CPI app draws this dashboard's four sections as its own tab bar, so
   Superset's outer tab row would duplicate it. EMBEDDED VIEW ONLY -- same
   fragile-but-fails-open gate as PW-EMBED-HIDE-FILTERBAR v1 above. Inert
   without #TABS-pwTopNav (see pw_topnav_embed.py --stage wrap). */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] #TABS-pwTopNav > .ant-tabs-nav {
  display: none !important;
}
/* ==== end PW-EMBED-HIDE-TOPTABS v1 ==== */
"""

# Fallback that does not depend on the id reaching the DOM (from
# wm_hide_toptabs.py). Hides every dashboard tab row, then restores any that
# sits inside a tab pane -- which is precisely what makes a row a SUB-tab row.
CSS_TOPTABS_STRUCTURAL = """
/* ==== PW-EMBED-HIDE-TOPTABS v1 (dash 3 ONLY -- structural variant) ==== */
#app[data-bootstrap*='"embedded": {"dashboard_id"'] .dashboard-component-tabs > .ant-tabs > .ant-tabs-nav {
  height: 0 !important; overflow: hidden !important; visibility: hidden !important; margin: 0 !important;
}
#app[data-bootstrap*='"embedded": {"dashboard_id"'] .ant-tabs-tabpane .dashboard-component-tabs > .ant-tabs > .ant-tabs-nav {
  height: auto !important; overflow: visible !important; visibility: visible !important;
}
/* ==== end PW-EMBED-HIDE-TOPTABS v1 ==== */
"""


def _now() -> str:
    # Matches the format already stored in dashboards.changed_on.
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _ist_stamp() -> str:
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).strftime("%Y%m%dT%H%M%S")


def nav_tab_meta(label):
    # Nav tabs on dash 6 keep the stock defaultText/placeholder; only sub-tabs
    # use the all-three-identical convention. Mirrored exactly — TAB meta is
    # the one genuine render-crash path (Tab.jsx dereferences it unguarded).
    return {"text": label, "defaultText": "Tab title", "placeholder": "Tab title"}


def validate(pos):
    """Structural validation (ported from s1_subtabs.py). [] == good."""
    problems = []
    nodes = {k: v for k, v in pos.items() if isinstance(v, dict)}

    for k, v in nodes.items():
        for child in v.get("children", []) or []:
            if child not in nodes:
                problems.append("dangling child ref: %s -> %s" % (k, child))

    seen = {}
    for k, v in nodes.items():
        for child in v.get("children", []) or []:
            if child in seen:
                problems.append("node %s referenced by both %s and %s" % (child, seen[child], k))
            seen[child] = k

    reached, stack = set(), [("ROOT_ID", [])]
    while stack:
        nid, chain = stack.pop()
        if nid not in nodes:
            continue
        if nid in reached:
            problems.append("cycle or re-entry at %s" % nid)
            continue
        reached.add(nid)
        if nid != "ROOT_ID":
            stored = nodes[nid].get("parents")
            if stored != chain:
                problems.append("parents mismatch %s: stored=%s computed=%s" % (nid, stored, chain))
        for child in nodes[nid].get("children", []) or []:
            stack.append((child, chain + [nid]))

    unreachable = set(nodes) - reached - {"HEADER_ID"}
    if unreachable:
        problems.append("unreachable nodes: %s" % sorted(unreachable))

    for k, v in nodes.items():
        if v.get("type") == "TAB" and not isinstance(v.get("meta"), dict):
            problems.append("TAB %s has non-dict meta: %r" % (k, v.get("meta")))

    for k, v in nodes.items():
        if v.get("type") == "ROW":
            w = sum(nodes[c]["meta"].get("width", 0) for c in v.get("children", []) or []
                    if c in nodes and nodes[c].get("type") == "CHART")
            if w > 12:
                problems.append("ROW %s children width sum %d > 12" % (k, w))
    return problems


def rewrite_parents(pos):
    """Recompute every reachable node's parents by a fresh BFS from ROOT_ID.

    Separate code from validate()'s DFS on purpose: the check must not be the
    writer run twice. HEADER_ID (parentless, unreachable) is untouched.
    """
    nodes = {k: v for k, v in pos.items() if isinstance(v, dict)}
    queue = [("ROOT_ID", [])]
    while queue:
        nid, chain = queue.pop(0)
        if nid not in nodes:
            continue
        if nid != "ROOT_ID":
            nodes[nid]["parents"] = chain
        for child in nodes[nid].get("children", []) or []:
            queue.append((child, chain + [nid]))


def snapshot_exists(con, dash_id):
    have = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_pw_topnav_backup'"
    ).fetchone()
    if not have:
        return False
    return con.execute(
        "SELECT dash_id FROM _pw_topnav_backup WHERE dash_id=?", (dash_id,)
    ).fetchone() is not None


def take_file_backup(con):
    """Full-DB .bak via the online backup API (WAL-safe — never a bare file
    copy of a live DB). Called OUTSIDE the write transaction."""
    bak = DB + ".bak." + _ist_stamp() + "_IST.pwtopnav"
    dst = sqlite3.connect(bak)
    try:
        con.backup(dst)
    finally:
        dst.close()
    print("full DB backup: %s" % bak)


def ensure_snapshot(cur, dash_id):
    """Column snapshot into _pw_topnav_backup, inside the write transaction —
    it commits (or rolls back) atomically with the stage edits. Also the
    applied-sentinel: present means a backup pair already exists."""
    cur.execute(
        "CREATE TABLE IF NOT EXISTS _pw_topnav_backup ("
        " dash_id INTEGER PRIMARY KEY, position_json TEXT, css TEXT,"
        " json_metadata TEXT, grid_children TEXT, created TEXT)"
    )
    if cur.execute("SELECT dash_id FROM _pw_topnav_backup WHERE dash_id=?", (dash_id,)).fetchone():
        print("column snapshot already present for dash %d" % dash_id)
        return
    pos_raw, css, jm_raw = cur.execute(
        "SELECT position_json, css, json_metadata FROM dashboards WHERE id=?", (dash_id,)
    ).fetchone()
    grid_children = json.dumps(json.loads(pos_raw)["GRID_ID"]["children"])
    cur.execute(
        "INSERT INTO _pw_topnav_backup VALUES (?,?,?,?,?,?)",
        (dash_id, pos_raw, css or "", jm_raw or "", grid_children, _now()),
    )
    print("column snapshot stored in _pw_topnav_backup (grid order %s)" % grid_children)


def stage_wrap(cur, dash_id):
    pos_raw, jm_raw = cur.execute(
        "SELECT position_json, json_metadata FROM dashboards WHERE id=?", (dash_id,)
    ).fetchone()
    pos = json.loads(pos_raw)
    jm = json.loads(jm_raw or "{}")

    if TOPNAV in pos:
        print("wrap: %s already present - nothing to do" % TOPNAV)
        return False

    # ---- pre-flight guards: the layout must be exactly what was surveyed ----
    grid = pos["GRID_ID"]["children"]
    if grid != EXPECTED_GRID_CHILDREN:
        raise RuntimeError("GRID children drifted: %s (expected %s)" % (grid, EXPECTED_GRID_CHILDREN))
    for tab_id, _label, sections in NAV_TABS:
        if tab_id in pos:
            raise RuntimeError("%s already exists - clean up first" % tab_id)
        for section in sections:
            if section not in pos or not isinstance(pos[section], dict):
                raise RuntimeError("section %s missing or not a node" % section)

    pre = validate(pos)
    if pre:
        raise RuntimeError("layout invalid before edit: %s" % pre)
    print("pre-flight: guards passed; pre-validate: clean")

    # ---- the wrap ----
    pos[TOPNAV] = {
        "children": [t[0] for t in NAV_TABS],
        "id": TOPNAV,
        "meta": {},
        "parents": ["ROOT_ID", "GRID_ID"],
        "type": "TABS",
    }
    for tab_id, label, sections in NAV_TABS:
        pos[tab_id] = {
            "children": list(sections),
            "id": tab_id,
            "meta": nav_tab_meta(label),
            "parents": ["ROOT_ID", "GRID_ID", TOPNAV],
            "type": "TAB",
        }
    pos["GRID_ID"]["children"] = [TOPNAV]

    rewrite_parents(pos)

    problems = validate(pos)
    if problems:
        raise RuntimeError("post-edit layout INVALID: %s" % problems)
    print("post-edit validation: 0 problems")
    for tab_id, label, sections in NAV_TABS:
        print("  %-11s %-24r -> %s" % (tab_id, label, sections))
    print("preserved: DASHBOARD_VERSION_KEY=%r, HEADER_ID present=%s"
          % (pos.get("DASHBOARD_VERSION_KEY"), "HEADER_ID" in pos))

    # Inert on 3.1 (schemas.py strips it on any UI save; nothing reads it) —
    # set purely for metadata parity with dashboards 6/7/8.
    jm["show_native_filters"] = False

    cur.execute(
        "UPDATE dashboards SET position_json=?, json_metadata=?, changed_on=? WHERE id=?",
        (json.dumps(pos), json.dumps(jm), _now(), dash_id),
    )
    if cur.rowcount != 1:
        raise RuntimeError("dashboards update rowcount %d" % cur.rowcount)
    return True


def _has_block(css, marker):
    # Match the BLOCK START, not the bare marker: prose inside one block may
    # name another block's marker (the dry-run caught exactly that).
    return ("/* ==== " + marker) in css


def stage_css(cur, dash_id, structural):
    css = (cur.execute("SELECT css FROM dashboards WHERE id=?", (dash_id,)).fetchone()[0]) or ""
    if _has_block(css, MARKER_FB) and _has_block(css, MARKER_TT):
        print("css: both markers already present - nothing to do")
        return False
    if len(css) != EXPECTED_BASE_CSS_LEN and not _has_block(css, MARKER_FB):
        print("WARN: base css length %d != surveyed %d (sheet drifted; appending anyway)"
              % (len(css), EXPECTED_BASE_CSS_LEN))

    new_css = css
    if not _has_block(new_css, MARKER_FB):
        new_css += "\n" + CSS_FILTERBAR
        print("css: appended %s" % MARKER_FB)
    if not _has_block(new_css, MARKER_TT):
        new_css += (CSS_TOPTABS_STRUCTURAL if structural else CSS_TOPTABS_ID)
        print("css: appended %s (%s variant)" % (MARKER_TT, "structural" if structural else "id"))

    cur.execute(
        "UPDATE dashboards SET css=?, changed_on=? WHERE id=?", (new_css, _now(), dash_id)
    )
    if cur.rowcount != 1:
        raise RuntimeError("dashboards update rowcount %d" % cur.rowcount)
    print("css_len %d -> %d" % (len(css), len(new_css)))
    return True


def strip_marked(css, marker):
    start = css.find("\n/* ==== " + marker)
    if start == -1:
        start = css.find("/* ==== " + marker)
    end_tag = "/* ==== end " + marker + " ==== */"
    end = css.find(end_tag)
    if start == -1 or end == -1:
        return css, False
    return css[:start] + css[end + len(end_tag):], True


def do_revert(cur, dash_id):
    row = cur.execute(
        "SELECT grid_children FROM _pw_topnav_backup WHERE dash_id=?", (dash_id,)
    ).fetchone() if cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_pw_topnav_backup'"
    ).fetchone() else None
    original_grid = json.loads(row[0]) if row else EXPECTED_GRID_CHILDREN

    pos_raw, css, jm_raw = cur.execute(
        "SELECT position_json, css, json_metadata FROM dashboards WHERE id=?", (dash_id,)
    ).fetchone()
    pos, css, jm = json.loads(pos_raw), css or "", json.loads(jm_raw or "{}")

    changed = False
    if TOPNAV in pos:
        sections = [s for t in NAV_TABS for s in t[2]]
        pos["GRID_ID"]["children"] = [s for s in original_grid if s in pos] or sections
        for tab_id, _l, _s in NAV_TABS:
            pos.pop(tab_id, None)
        pos.pop(TOPNAV, None)
        rewrite_parents(pos)
        problems = validate(pos)
        if problems:
            raise RuntimeError("revert produced INVALID layout: %s" % problems)
        print("revert: sections back under GRID as %s; validation 0 problems"
              % pos["GRID_ID"]["children"])
        changed = True
    else:
        print("revert: %s not present, layout untouched" % TOPNAV)

    for marker in (MARKER_FB, MARKER_TT):
        css, stripped = strip_marked(css, marker)
        if stripped:
            print("revert: stripped %s" % marker)
            changed = True

    if "show_native_filters" in jm:
        del jm["show_native_filters"]
        print("revert: removed show_native_filters")
        changed = True

    if not changed:
        print("revert: nothing to do")
        return False

    cur.execute(
        "UPDATE dashboards SET position_json=?, css=?, json_metadata=?, changed_on=? WHERE id=?",
        (json.dumps(pos), css, json.dumps(jm), _now(), dash_id),
    )
    if cur.rowcount != 1:
        raise RuntimeError("dashboards update rowcount %d" % cur.rowcount)
    cur.execute("DELETE FROM _pw_topnav_backup WHERE dash_id=?", (dash_id,))
    return True


def show(con, dash_id):
    pos_raw, css, jm_raw = con.execute(
        "SELECT position_json, css, json_metadata FROM dashboards WHERE id=?", (dash_id,)
    ).fetchone()
    pos, css, jm = json.loads(pos_raw), css or "", json.loads(jm_raw or "{}")
    print("dash %d" % dash_id)
    print("  GRID children: %s" % pos["GRID_ID"]["children"])
    print("  %s present: %s" % (TOPNAV, TOPNAV in pos))
    print("  css len: %d | %s: %s | %s: %s"
          % (len(css), MARKER_FB, _has_block(css, MARKER_FB), MARKER_TT, _has_block(css, MARKER_TT)))
    print("  show_native_filters: %r | filter_bar_orientation: %r"
          % (jm.get("show_native_filters", "<absent>"), jm.get("filter_bar_orientation")))
    print("  validate: %s" % (validate(pos) or "0 problems"))


def main():
    ap = argparse.ArgumentParser(description="PW dash top-nav wrap + embed css")
    ap.add_argument("--dash-id", type=int, default=3)
    ap.add_argument("--stage", choices=["wrap", "css", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--structural", action="store_true",
                    help="css: use the id-independent TOPTABS variant")
    args = ap.parse_args()

    con = sqlite3.connect(DB, isolation_level=None, timeout=30)
    cur = con.cursor()
    try:
        if args.show:
            show(con, args.dash_id)
            return 0

        # Full-DB .bak before the lock: it captures committed pre-change state
        # either way, and the backup API must not run mid-transaction. Skipped
        # on dry-run (nothing will be written) and once the sentinel exists.
        if not args.revert and not args.dry_run and not snapshot_exists(con, args.dash_id):
            take_file_backup(con)

        cur.execute("BEGIN IMMEDIATE")  # all reads below happen under the write lock

        if args.revert:
            do_revert(cur, args.dash_id)
        else:
            if not args.dry_run:
                ensure_snapshot(cur, args.dash_id)
            if args.stage in ("wrap", "all"):
                stage_wrap(cur, args.dash_id)
            if args.stage in ("css", "all"):
                stage_css(cur, args.dash_id, args.structural)

        if args.dry_run:
            con.rollback()
            print("DRY-RUN: all changes ROLLED BACK")
            return 0
        con.commit()
        print("COMMITTED")

        after = json.loads(cur.execute(
            "SELECT position_json FROM dashboards WHERE id=?", (args.dash_id,)
        ).fetchone()[0])
        post = validate(after)
        if post:
            raise RuntimeError("POST-COMMIT VALIDATION FAILED: %s" % post)
        print("post-commit: re-read from DB and re-validated, 0 problems")
        return 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("pw_topnav_embed FAILED (rolled back): %s" % e)
        sys.exit(1)
