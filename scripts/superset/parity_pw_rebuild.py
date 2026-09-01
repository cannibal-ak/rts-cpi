#!/usr/bin/env python3
"""Rebuild Superset dashboard 3 (Precision Air / PW) to the canonical WinAir shape.

Dashboard 6 (WinAir) is the canonical reference: five top tabs under
``TABS-wmTopNav``, nested viz sub-tabs, 12 slices over 5 virtual datasets,
12 native filters. Dashboard 3 is an older-generation build (8 per-carrier
charts over datasets 4/25/26, 8 filters). This script clones the canonical
shape onto dash 3 while KEEPING:

  * the top-nav node ids ``TABS-pwTopNav`` / ``TAB-pwNav1..4`` (permalinks
    bind to node ids) -- they are relabelled to the canonical tab names and a
    new ``TAB-pwNav5`` 'Velocity' is appended;
  * dash 3's css EXACTLY as is (never touched);
  * ``color_scheme`` 'precisionAir' + its domain -- PW keeps its brand;
  * the old slices 76-83 in the DB (detached from the dashboard, not deleted).

WHAT IT CREATES (single transaction)
------------------------------------
  datasets  32 -> pw_all_airlines_fares
            33 -> pw_pricing_recommendations
            34 -> pw_velocity_canonical            (see VELOCITY DECISION)
            37 -> pw_all_airlines_fares_availability
            38 -> pw_deployed_capacity
            (ids = max(tables.id)+1.., cloned rows + table_columns +
             sql_metrics, fresh uuid blobs, SQL substituted and ASSERTED:
             vw_airline_cpi_wm_snapshot -> vw_airline_cpi_pw_snapshot
             vw_velocity_wm_snapshot    -> vw_velocity_pw_snapshot
             'WM' AS airline            -> 'PW' AS airline
             wm_price                   -> pw_price)
  slices    109,105,106,95,100,111,102,107,96,112,103,110 -> max(id)+1..
            (titles kept canonical; datasource remapped; label_colors rebuilt
             for PW's carriers; three-place rule observed)
  dashboard 3: position_json rewritten (canonical nested sub-tab subtrees
            cloned from dash 6 with '-pw' suffixed node ids), json_metadata
            rewritten (12 canonical filters with fresh 'NATIVE_FILTER-PW-*'
            ids, chart/global chart configuration remapped, label_colors
            merged additively -- existing keys always win), dashboard_slices
            swapped 76-83 -> the 12 new slices.

VELOCITY DECISION (evidence-based, 2026-09-01 dev)
--------------------------------------------------
The task rule was: reuse ds26 pw_velocity_normalized if it exposes every
column slice 103 references. By NAME that test PASSES (slice 103 needs only
dep_date / current_booking / capacity / actual_seat_factor /
forecasted_seat_factor, all present in ds26). It is rejected on SEMANTICS:
the canonical Route (O&D) filter includes the velocity chart in its scope and
emits values like 'DAR -> JRO' (from the fares dataset's
``CONCAT(ref_org, ' `` + arrow + `` ', ref_dst)``); ds26's ``route`` is the raw
6-char city_pair ('DARJRO' -- probed live), so reusing it would silently blank
the velocity chart whenever a route is selected. WM's ds34 exists precisely to
normalise that (``CONCAT(LEFT(city_pair,3), ..., RIGHT(city_pair,3))``), and
ds26 cannot be widened (additive-only standing rule). Hence
pw_velocity_canonical. The comparison is re-run and printed on every
--show/--dry-run; ds26 and slice 82 are untouched.

HOUSE PATTERN
-------------
  --show     recon only: current dash 3 + canonical dash 6 + the full plan.
  --dry-run  executes the ENTIRE plan against an in-memory COPY of
             superset.db (sqlite backup API), commits there, re-validates,
             then discards. The live DB is opened mode=ro only -- zero risk.
  --apply    full-DB backup first via the sqlite3 backup API to
             /app/superset_home/superset.db.bak.<YYYYMMDDTHHMMSS>_IST.pwrebuild
             then BEGIN IMMEDIATE, in-DB backup table
             ``_parity_pw_rebuild_backup`` (pre-change dash row, removed
             dashboard_slices rows, every created row id), plan, commit,
             post-commit re-validation. REFUSES to run if the backup table
             already exists.
  --revert   surgical inverse from ``_parity_pw_rebuild_backup``: restores the
             dash 3 row, deletes every created row, re-links slices 76-83,
             drops the backup table. The .bak file stays as nuclear option.

Every expectation about the current state is asserted before writing --
current tab labels, slice titles, dataset names, substitution counts. Drift
aborts the run; nothing is ever "fixed" silently.

Run INSIDE cpi-superset-1 (stdlib + psycopg2, both present), streaming from
the repo so the file never needs a docker cp:

  ssh docker-host "docker exec -i cpi-superset-1 python3 - --show"    < scripts/superset/parity_pw_rebuild.py
  ssh docker-host "docker exec -i cpi-superset-1 python3 - --dry-run" < scripts/superset/parity_pw_rebuild.py
  ssh docker-host "docker exec -i cpi-superset-1 python3 - --apply"   < scripts/superset/parity_pw_rebuild.py
  ssh docker-host "docker exec -i cpi-superset-1 python3 - --revert"  < scripts/superset/parity_pw_rebuild.py

Postgres (carrier volume discovery) uses CPI_PG_DSN, defaulting to the
compose-internal DSN, exactly like liat_dash8_carrier_keys.py.

FOLLOW-UPS AFTER --apply (not done by this script)
--------------------------------------------------
  * The CPI app's PW top filter bar binds columns of the OLD datasets
    (e.g. ``carrier``@ds25); the canonical filter set uses ``airline``@fares.
    The app-side PW filter-bar config must be re-pointed in the same deploy.
  * PW's snapshot table has no index coverage for the new filter columns
    (the DA Trip Type lesson: ix_air_snap_da_triptype was REQUIRED);
    filter-value SELECT DISTINCTs over ~4.2M rows may be slow until indexed.
  * Verify colours with an UNSCOPED guest token (the DreamAir Exp lesson).
"""
import argparse
import copy
import datetime
import json
import os
import sqlite3
import sys
import uuid as uuidlib

DB = "/app/superset_home/superset.db"
PG_DSN = os.environ.get("CPI_PG_DSN", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")

DASH = 3          # rebuilt
SRC_DASH = 6      # canonical
BACKUP_TABLE = "_parity_pw_rebuild_backup"

EMDASH = "—"
ARROW = "→"

# ---------------------------------------------------------------------------
# Canonical expectations (surveyed on dev 2026-09-01). Guards, not targets:
# any drift ABORTS the run.
# ---------------------------------------------------------------------------

# WM dataset id -> new PW dataset name (creation order == this order)
DS_SRC_ORDER = [32, 33, 34, 37, 38]
DS_NEW_NAME = {
    32: "pw_all_airlines_fares",
    33: "pw_pricing_recommendations",
    34: "pw_velocity_canonical",
    37: "pw_all_airlines_fares_availability",
    38: "pw_deployed_capacity",
}
EXPECTED_WM_DS_NAME = {
    32: "wm_all_airlines_fares",
    33: "wm_pricing_recommendations",
    34: "wm_velocity_normalized",
    37: "wm_all_airlines_fares_availability",
    38: "wm_deployed_capacity",
}
# exact substitution occurrence counts in each WM dataset's SQL
EXPECTED_SUBS = {  # (view_fares, view_vel, "'WM' AS airline", wm_price)
    32: (2, 0, 1, 0),
    33: (1, 0, 0, 6),
    34: (0, 1, 0, 0),
    37: (2, 0, 1, 0),
    38: (2, 0, 1, 0),
}

# canonical slices in tab order; new ids are max(slices.id)+1.. in this order
WM_SLICE_ORDER = [109, 105, 106, 95, 100, 111, 102, 107, 96, 112, 103, 110]
EXPECTED_WM_SLICES = {  # id -> (title, viz_type, datasource_id)
    109: ("Lowest Available Fare & Availability by Travel_Date", "mixed_timeseries", 37),
    105: ("Lowest Available Avg_Fare by Travel_Date", "echarts_timeseries_bar", 32),
    106: ("Lowest Available Avg_Fare by Travel_Date", "table", 32),
    95:  ("Min/Max_Fare by Travel_Date", "echarts_timeseries_line", 32),
    100: ("Min/Max_Fare by Travel_Date", "table", 32),
    111: ("Competitor Breakdown", "echarts_timeseries_bar", 32),
    102: ("Competitor Breakdown", "table", 32),
    107: ("Fare Composition %s Base / Tax / YQ" % EMDASH, "dist_bar", 32),
    96:  ("Pricing Recommendations", "table", 33),
    112: ("Pricing Recommendations %s Summary" % EMDASH, "echarts_timeseries_bar", 33),
    103: ("Booking, Seat Factor, Capacity", "mixed_timeseries", 34),
    110: ("Deployed Capacity %s Flights Operated by Airline" % EMDASH, "echarts_timeseries_bar", 38),
}

# dash 6 nav: children order of TABS-wmTopNav with labels
EXPECTED_WM_NAV = [
    ("TAB-wmNav1", "Avg_Fare"),
    ("TAB-wmNav4", "Min/Max_Fare"),
    ("TAB-wmNav3", "Competitor Breakdown"),
    ("TAB-wmNav2", "Pricing Recommendations"),
    ("TAB-wmNav5", "Velocity"),
]
# dash 3 today: children order of TABS-pwTopNav with labels
EXPECTED_PW_NAV_OLD = [
    ("TAB-pwNav1", "Avg_Fare"),
    ("TAB-pwNav2", "Min/Max_Fare"),
    ("TAB-pwNav3", "Booking & Seat Factor"),
    ("TAB-pwNav4", "Lowest_Fares"),
]
# kept PW nav tab -> (canonical label, WM nav tab whose subtree is cloned)
PW_NAV_PLAN = [
    ("TAB-pwNav1", "Avg_Fare", "TAB-wmNav1"),
    ("TAB-pwNav2", "Min/Max_Fare", "TAB-wmNav4"),
    ("TAB-pwNav3", "Competitor Breakdown", "TAB-wmNav3"),
    ("TAB-pwNav4", "Pricing Recommendations", "TAB-wmNav2"),
    ("TAB-pwNav5", "Velocity", "TAB-wmNav5"),   # NEW tab
]
NODE_SUFFIX = "-pw"

# dash 3's old grid content (ROW -> its single CHART), removed entirely
EXPECTED_OLD_TAB_CHILDREN = {
    "TAB-pwNav1": ["ROW-1", "ROW-2"],
    "TAB-pwNav2": ["ROW-3", "ROW-4", "ROW-5", "ROW-6"],
    "TAB-pwNav3": ["ROW-7"],
    "TAB-pwNav4": ["ROW-8"],
}
EXPECTED_OLD_ROW_CHART = {("ROW-%d" % i): ("CHART-%d" % (75 + i)) for i in range(1, 9)}
OLD_PW_SLICES = [76, 77, 78, 79, 80, 81, 82, 83]

# canonical native filters on dash 6: (id, name, dataset_id, column)
EXPECTED_WM_FILTERS = [
    ("NATIVE_FILTER-Airline", "Airline", 32, "airline"),
    ("NATIVE_FILTER-Route", "Route (O&D)", 32, "route"),
    ("NATIVE_FILTER-FlightNum", "Flight Number", 32, "flt_num"),
    ("NATIVE_FILTER-DtD", "Days to Departure", 32, "dtd_bucket"),
    ("NATIVE_FILTER-PricePos", "Price Position", 33, "price_status"),
    ("NATIVE_FILTER-PriceAction", "Pricing Action", 33, "recommendation"),
    ("NATIVE_FILTER-CheapComp", "Cheapest Competitor", 33, "lowest_competitor"),
    ("NATIVE_FILTER-DaysLeft", "Days Left", 34, "days_left"),
    ("NATIVE_FILTER-Aircraft", "Aircraft", 34, "eqp"),
    ("NATIVE_FILTER-LegSeg", "Leg/Segment", 34, "legseg_type"),
    ("NATIVE_FILTER-Stops", "Stops", 32, "stops"),
    ("NATIVE_FILTER-TripType", "Trip Type", 32, "trip_type"),
]
FILTER_ID_PREFIX_OLD = "NATIVE_FILTER-"
FILTER_ID_PREFIX_NEW = "NATIVE_FILTER-PW-"

# columns slice 103 references (the ds26-reuse name test, printed as evidence)
SLICE103_COLUMNS = ["dep_date", "current_booking", "capacity",
                    "actual_seat_factor", "forecasted_seat_factor"]

# ---------------------------------------------------------------------------
# PW colours. Carrier hexes come from dash 3's EXISTING label_colors (all ten
# carriers already have keys there; palette-slot assignment below only fires
# for a carrier that appears in the data later without a key). Measure /
# reco / composition defaults follow the WM/DA pattern re-expressed in PW's
# precisionAir greens+golds; wherever dash 3 already binds the same key, the
# existing hex WINS (additive-only).
# ---------------------------------------------------------------------------
PW_CODE = "PW"
FALLBACK_HEXES = ["#64748B", "#0F766E"]   # never a new brand hue (house rule)
SOLD_OUT = "#F39C12"       # semantic, cross-surface (winair-palette.md section 6)
NOT_ON_SALE = "#9E9E9E"
COMPOSITE_PREFIXES = ["Min Fare", "Max Fare", "Lowest Available Fare", "Avg Fare"]

MEASURE_DEFAULTS = {           # slice-103 twin (mixed_timeseries A/B queries)
    "Current Booking": "#3C5414",         # existing dash-3 key, same hex
    "Capacity": "#6E9930",                # existing dash-3 key, same hex
    "Actual Seat Factor": "#C5981B",      # derived from AVG(actual_seat_factor)
    "Actual Seat Factor (1)": "#C5981B",  # query-B " (1)" suffix binds
    "Forecasted SF": "#FBC31C",           # derived from 'Forecasted Seat Factor'
    "Forecasted SF (1)": "#FBC31C",
}
RECO_DEFAULTS = {              # traffic light; PW brand is green so red is free
    "Reduce": "#C0392B",
    "Monitor": "#C08A00",
    "No Change": "#64748B",
    "Consider Increase": "#1BAF7A",
}
COMPOSITION_DEFAULTS = {       # dist_bar series are the METRIC labels
    "Base": "#3C5414",         # brand dark green
    "Tax": "#6E9930",          # brand mid green (sharing with Capacity is the
    "YQ": "#FBC31C",           #   WM precedent: Tax==Capacity there too)
}


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _ist_stamp():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).strftime("%Y%m%dT%H%M%S")


def expect(cond, msg):
    if not cond:
        raise RuntimeError("EXPECTATION FAILED (state drifted; aborting): %s" % msg)


# ---------------------------------------------------------------------------
# layout validation (ported from jy_topnav_embed.py -- checker and writer are
# deliberately separate traversals)
# ---------------------------------------------------------------------------

def validate(pos):
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


# ---------------------------------------------------------------------------
# SQL substitution -- asserted, never assumed
# ---------------------------------------------------------------------------

def sub_sql(sql, src_id):
    exp = EXPECTED_SUBS[src_id]
    got = (sql.count("vw_airline_cpi_wm_snapshot"), sql.count("vw_velocity_wm_snapshot"),
           sql.count("'WM' AS airline"), sql.count("wm_price"))
    expect(got == exp,
           "WM dataset %d SQL substitution census drifted: expected %s got %s" % (src_id, exp, got))
    out = (sql.replace("vw_airline_cpi_wm_snapshot", "vw_airline_cpi_pw_snapshot")
              .replace("vw_velocity_wm_snapshot", "vw_velocity_pw_snapshot")
              .replace("'WM' AS airline", "'PW' AS airline")
              .replace("wm_price", "pw_price"))
    assert "vw_airline_cpi_wm_snapshot" not in out, "airline view not substituted"
    assert "vw_velocity_wm_snapshot" not in out, "velocity view not substituted"
    assert "'WM'" not in out, "WM literal survived"
    assert "wm_price" not in out, "wm_price survived"
    return out, got


# ---------------------------------------------------------------------------
# carriers + label_colors
# ---------------------------------------------------------------------------

def carrier_volumes():
    import psycopg2
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT comp_al, count(*) AS n
        FROM vw_airline_cpi_pw_snapshot
        WHERE comp_al IS NOT NULL AND comp_al <> '' AND comp_al <> 'PW'
              AND comp_tot_fare > 0
        GROUP BY comp_al
        ORDER BY n DESC, comp_al ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def assign_carrier_colors(volumes, existing_lc, scheme_domain):
    """PW first, then competitors by descending volume. A carrier that already
    has a bare-code key in dash 3's label_colors keeps that hex (additive-only
    standing rule); only keyless carriers draw palette-slot colours from the
    precisionAir domain (unused ones first), then the neutral fallbacks."""
    ordered = [PW_CODE] + [code for code, _n in volumes]
    used = {existing_lc[c] for c in ordered if c in existing_lc}
    pool = [h for h in list(scheme_domain) + FALLBACK_HEXES if h not in used]
    out, src = {}, {}
    for code in ordered:
        if code in existing_lc:
            out[code], src[code] = existing_lc[code], "existing"
        elif pool:
            out[code], src[code] = pool.pop(0), "palette-slot"
        else:
            out[code], src[code] = FALLBACK_HEXES[-1], "fallback-exhausted"
    return ordered, out, src


def build_label_colors(carrier_colors, existing_lc):
    """Every key spelling Superset can build for the canonical charts, in the
    exact spellings liat_dash8_carrier_keys.py generates (nine per carrier),
    plus measure / reco / composition keys. Existing dash-3 hexes win."""
    out = {}
    for code, hexv in carrier_colors.items():
        out[code] = hexv
        for pfx in COMPOSITE_PREFIXES:
            out["%s, %s" % (pfx, code)] = hexv
        out["Sold out, %s" % code] = SOLD_OUT
        out["Not on sale, %s" % code] = NOT_ON_SALE
        out["Sold out, %s (1)" % code] = SOLD_OUT
        out["Not on sale, %s (1)" % code] = NOT_ON_SALE
    out.update(MEASURE_DEFAULTS)
    out.update(RECO_DEFAULTS)
    out.update(COMPOSITION_DEFAULTS)
    for k in list(out):                       # existing assignment always wins
        if k in existing_lc:
            out[k] = existing_lc[k]
    return out


# ---------------------------------------------------------------------------
# generic row cloning
# ---------------------------------------------------------------------------

def table_cols(cur, table):
    return [r[1] for r in cur.execute("PRAGMA table_info(%s)" % table)]


def fetch_row(cur, table, rid):
    cols = table_cols(cur, table)
    row = cur.execute("SELECT %s FROM %s WHERE id=?" % (",".join(cols), table), (rid,)).fetchone()
    expect(row is not None, "%s id %s missing" % (table, rid))
    return dict(zip(cols, row))


def insert_row(cur, table, row):
    cols = list(row.keys())
    cur.execute("INSERT INTO %s (%s) VALUES (%s)" % (
        table, ",".join(cols), ",".join(["?"] * len(cols))), [row[k] for k in cols])


# ---------------------------------------------------------------------------
# slice params / query_context remapping (DA-script pattern)
# ---------------------------------------------------------------------------

def remap_json(o, dsmap, new_slice_id, label_colors):
    if isinstance(o, dict):
        for k in list(o.keys()):
            v = o[k]
            if k == "datasource" and isinstance(v, str) and v.endswith("__table"):
                o[k] = "%d__table" % dsmap[int(v.split("__")[0])]
            elif k == "datasource" and isinstance(v, dict) and "id" in v:
                v["id"] = dsmap.get(v["id"], v["id"])
                remap_json(v, dsmap, new_slice_id, label_colors)
            elif k == "dashboards" and isinstance(v, list):
                o[k] = [DASH]
            elif k == "slice_id":
                o[k] = new_slice_id
            elif k == "label_colors" and isinstance(v, dict):
                o[k] = dict(label_colors)
            else:
                remap_json(v, dsmap, new_slice_id, label_colors)
    elif isinstance(o, list):
        for x in o:
            remap_json(x, dsmap, new_slice_id, label_colors)


def assert_clean_blob(blob, what):
    for bad in ('"32__table"', '"33__table"', '"34__table"', '"37__table"', '"38__table"',
                "wm_price", '"WM"', ", WM\"", '"dashboards": [6]'):
        assert bad not in blob, "%s still contains %r after remap" % (what, bad)


# ---------------------------------------------------------------------------
# layout subtree cloning
# ---------------------------------------------------------------------------

def clone_subtree(pos_src, root_id, slicemap, slice_uuid_str):
    """Deep-copy the node subtree rooted at root_id, suffixing every node id,
    repointing CHART meta to the new slices. parents are rewritten later by
    rewrite_parents(); validate() must then come back clean."""
    out = {}

    def walk(nid):
        node = copy.deepcopy(pos_src[nid])
        node["id"] = nid + NODE_SUFFIX
        kids = node.get("children", []) or []
        node["children"] = [c + NODE_SUFFIX for c in kids]
        if node.get("type") == "CHART":
            meta = node["meta"]
            old = meta["chartId"]
            expect(old in slicemap, "subtree CHART %s references unmapped slice %s" % (nid, old))
            meta["chartId"] = slicemap[old]
            meta["uuid"] = slice_uuid_str[old]
            # meta.sliceName / sliceNameOverride / width / height cloned verbatim
        out[node["id"]] = node
        for c in kids:
            walk(c)

    walk(root_id)
    return root_id + NODE_SUFFIX, out


# ---------------------------------------------------------------------------
# in-DB backup helpers
# ---------------------------------------------------------------------------

def backup_exists(cur):
    return cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (BACKUP_TABLE,)).fetchone() is not None


def bk(cur, kind, ref, payload):
    cur.execute("INSERT INTO %s VALUES (?,?,?)" % BACKUP_TABLE,
                (kind, str(ref), json.dumps(payload)))


# ---------------------------------------------------------------------------
# recon / preflight
# ---------------------------------------------------------------------------

def preflight(cur):
    """Assert the world is exactly as surveyed; return the loaded state."""
    st = {}
    # dash 3
    row = cur.execute("SELECT position_json, json_metadata, css FROM dashboards WHERE id=?",
                      (DASH,)).fetchone()
    expect(row is not None, "dashboard %d missing" % DASH)
    st["pos3"] = json.loads(row[0])
    st["jm3"] = json.loads(row[1])
    st["css3"] = row[2] or ""
    pos3 = st["pos3"]
    expect(pos3.get("TABS-pwTopNav", {}).get("children") == [t for t, _l in EXPECTED_PW_NAV_OLD],
           "TABS-pwTopNav children drifted: %s" % pos3.get("TABS-pwTopNav", {}).get("children"))
    for tid, label in EXPECTED_PW_NAV_OLD:
        got = pos3[tid]["meta"].get("text")
        expect(got == label, "dash 3 tab %s label %r != expected %r" % (tid, got, label))
    for tid, kids in EXPECTED_OLD_TAB_CHILDREN.items():
        expect(pos3[tid].get("children") == kids,
               "dash 3 %s children drifted: %s" % (tid, pos3[tid].get("children")))
    for rid, cid in EXPECTED_OLD_ROW_CHART.items():
        expect(pos3.get(rid, {}).get("children") == [cid],
               "dash 3 %s children drifted" % rid)
        expect(pos3.get(cid, {}).get("meta", {}).get("chartId") == int(cid.split("-")[1]),
               "dash 3 %s chartId drifted" % cid)
    v3 = validate(pos3)
    expect(v3 == [], "dash 3 layout invalid before edit: %s" % v3)
    links3 = [r[0] for r in cur.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=? ORDER BY slice_id", (DASH,))]
    expect(links3 == OLD_PW_SLICES, "dash 3 dashboard_slices drifted: %s" % links3)
    expect(st["jm3"].get("color_scheme") == "precisionAir", "dash 3 color_scheme drifted")
    lc3 = st["jm3"].get("label_colors") or {}
    expect(len(lc3) == 29, "dash 3 label_colors key count drifted: %d" % len(lc3))
    expect(st["jm3"].get("show_native_filters") is False, "dash 3 show_native_filters drifted")

    # dash 6
    row = cur.execute("SELECT position_json, json_metadata FROM dashboards WHERE id=?",
                      (SRC_DASH,)).fetchone()
    expect(row is not None, "dashboard %d missing" % SRC_DASH)
    st["pos6"] = json.loads(row[0])
    st["jm6"] = json.loads(row[1])
    pos6 = st["pos6"]
    expect(pos6.get("TABS-wmTopNav", {}).get("children") == [t for t, _l in EXPECTED_WM_NAV],
           "TABS-wmTopNav children drifted")
    for tid, label in EXPECTED_WM_NAV:
        expect(pos6[tid]["meta"].get("text") == label,
               "dash 6 tab %s label drifted" % tid)
        expect(len(pos6[tid].get("children", [])) == 1,
               "dash 6 tab %s has %d children (expected the one sub-TABS node)"
               % (tid, len(pos6[tid].get("children", []))))
    v6 = validate(pos6)
    expect(v6 == [], "dash 6 layout invalid: %s" % v6)
    chart_ids_6 = sorted(n["meta"]["chartId"] for n in pos6.values()
                         if isinstance(n, dict) and n.get("type") == "CHART")
    expect(chart_ids_6 == sorted(WM_SLICE_ORDER),
           "dash 6 laid-out charts drifted: %s" % chart_ids_6)

    # WM slices
    for sid, (title, viz, dsid) in EXPECTED_WM_SLICES.items():
        r = cur.execute("SELECT slice_name, viz_type, datasource_id, datasource_type "
                        "FROM slices WHERE id=?", (sid,)).fetchone()
        expect(r is not None, "WM slice %d missing" % sid)
        expect(r[0] == title, "slice %d title %r != %r" % (sid, r[0], title))
        expect(r[1] == viz, "slice %d viz %r != %r" % (sid, r[1], viz))
        expect(r[2] == dsid and r[3] == "table", "slice %d datasource drifted" % sid)

    # WM datasets
    for dsid, name in EXPECTED_WM_DS_NAME.items():
        r = cur.execute("SELECT table_name, sql FROM tables WHERE id=?", (dsid,)).fetchone()
        expect(r is not None and r[0] == name, "dataset %d name drifted" % dsid)
        expect(r[1], "dataset %d is not virtual" % dsid)

    # new names must not exist yet
    for name in DS_NEW_NAME.values():
        expect(cur.execute("SELECT 1 FROM tables WHERE table_name=?", (name,)).fetchone() is None,
               "dataset %r already exists -- applied before? (--revert first)" % name)

    # canonical filters
    nf6 = st["jm6"].get("native_filter_configuration") or []
    got = [(f.get("id"), f.get("name"), f["targets"][0].get("datasetId"),
            f["targets"][0].get("column", {}).get("name")) for f in nf6]
    expect(got == EXPECTED_WM_FILTERS, "dash 6 native filters drifted: %s" % got)

    # ds26 reuse evidence (velocity decision, printed by caller)
    r = cur.execute("SELECT sql FROM tables WHERE id=26 AND table_name='pw_velocity_normalized'").fetchone()
    expect(r is not None, "dataset 26 pw_velocity_normalized missing")
    st["ds26_sql"] = r[0]
    st["ds26_cols"] = [x[0] for x in cur.execute(
        "SELECT column_name FROM table_columns WHERE table_id=26")]
    return st


def print_velocity_decision(st):
    print("\n-- VELOCITY DECISION -----------------------------------------")
    missing = [c for c in SLICE103_COLUMNS if c not in st["ds26_cols"]]
    print("  ds26 name test (slice 103 columns %s): %s"
          % (SLICE103_COLUMNS, "PASS" if not missing else "FAIL missing %s" % missing))
    raw_route = "city_pair AS route" in st["ds26_sql"]
    print("  ds26 route semantics: %s"
          % ("RAW city_pair (e.g. 'DARJRO') -- canonical Route filter emits "
             "'DAR %s JRO' style values and its scope includes the velocity "
             "chart, so reuse would blank that chart under any Route selection"
             % ARROW if raw_route else "unexpectedly already formatted"))
    print("  DECISION: create pw_velocity_canonical from WM ds34's SQL "
          "(route formatted to match the fares dataset); ds26 + slice 82 untouched.")


# ---------------------------------------------------------------------------
# the plan (runs against any connection: in-memory copy on --dry-run,
# the live DB inside BEGIN IMMEDIATE on --apply)
# ---------------------------------------------------------------------------

def plan(cur, st, record_backup):
    # ---- id allotment ----
    base_ds = cur.execute("SELECT max(id) FROM tables").fetchone()[0] + 1
    dsmap = {src: base_ds + i for i, src in enumerate(DS_SRC_ORDER)}
    base_sl = cur.execute("SELECT max(id) FROM slices").fetchone()[0] + 1
    slicemap = {src: base_sl + i for i, src in enumerate(WM_SLICE_ORDER)}
    print("\n-- ID ALLOTMENT ----------------------------------------------")
    for src in DS_SRC_ORDER:
        print("  dataset %d %-38s -> %d %s"
              % (src, EXPECTED_WM_DS_NAME[src], dsmap[src], DS_NEW_NAME[src]))
    for src in WM_SLICE_ORDER:
        print("  slice %3d -> %3d  %s" % (src, slicemap[src],
              ascii(EXPECTED_WM_SLICES[src][0])))

    # ---- carriers + label colours ----
    volumes = carrier_volumes()
    expect(volumes, "vw_airline_cpi_pw_snapshot returned no competitor rows")
    lc3 = st["jm3"].get("label_colors") or {}
    domain = st["jm3"].get("color_scheme_domain") or []
    ordered, carrier_colors, src_of = assign_carrier_colors(volumes, lc3, domain)
    print("\n-- CARRIERS (volume-ordered) ---------------------------------")
    print("  %-8s %12s  %-9s %s" % ("carrier", "rows", "hex", "source"))
    volmap = dict(volumes)
    for code in ordered:
        print("  %-8s %12s  %-9s %s" % (code, volmap.get(code, "(reference)"),
                                        carrier_colors[code], src_of[code]))
    label_colors = build_label_colors(carrier_colors, lc3)
    print("  built %d canonical label_colors keys (9 per carrier + measures"
          " + reco + composition); existing dash-3 hexes won on %d overlaps"
          % (len(label_colors), sum(1 for k in label_colors if k in lc3)))

    # ---- 1. datasets ----
    print("\n-- DATASETS --------------------------------------------------")
    created = {"tables": [], "table_columns": [], "sql_metrics": [],
               "slices": [], "dashboard_slices": []}
    tc_id = cur.execute("SELECT max(id) FROM table_columns").fetchone()[0]
    m_id = cur.execute("SELECT max(id) FROM sql_metrics").fetchone()[0]
    for src in DS_SRC_ORDER:
        new = dsmap[src]
        name = DS_NEW_NAME[src]
        row = fetch_row(cur, "tables", src)
        newsql, counts = sub_sql(row["sql"], src)
        row.update({
            "id": new,
            "table_name": name,
            "sql": newsql,
            "perm": "[CPI PostgreSQL].[%s](id:%d)" % (name, new),
            "schema_perm": "[CPI PostgreSQL].[public]",
            "uuid": uuidlib.uuid4().bytes,
            "created_on": _now(), "changed_on": _now(),
        })
        if row.get("description"):
            row["description"] = row["description"].replace("WinAir", "Precision Air")
        insert_row(cur, "tables", row)
        created["tables"].append(new)
        print("  %d -> %d  %-38s subs(view_fares=%d, view_vel=%d, 'WM' lit=%d, wm_price=%d)"
              % (src, new, name, counts[0], counts[1], counts[2], counts[3]))

        # table_columns + sql_metrics
        n_c = n_m = 0
        for cid in [r[0] for r in cur.execute(
                "SELECT id FROM table_columns WHERE table_id=? ORDER BY id", (src,))]:
            d = fetch_row(cur, "table_columns", cid)
            if d["column_name"] == "wm_price":
                d["column_name"] = "pw_price"
            if d.get("expression"):
                d["expression"] = d["expression"].replace("wm_price", "pw_price")
            tc_id += 1
            d.update({"id": tc_id, "table_id": new, "uuid": uuidlib.uuid4().bytes,
                      "created_on": _now(), "changed_on": _now()})
            insert_row(cur, "table_columns", d)
            created["table_columns"].append(tc_id)
            n_c += 1
        for mid in [r[0] for r in cur.execute(
                "SELECT id FROM sql_metrics WHERE table_id=? ORDER BY id", (src,))]:
            d = fetch_row(cur, "sql_metrics", mid)
            if d.get("expression"):
                d["expression"] = d["expression"].replace("wm_price", "pw_price")
            m_id += 1
            d.update({"id": m_id, "table_id": new, "uuid": uuidlib.uuid4().bytes,
                      "created_on": _now(), "changed_on": _now()})
            insert_row(cur, "sql_metrics", d)
            created["sql_metrics"].append(m_id)
            n_m += 1
        print("        + %d columns, %d metrics" % (n_c, n_m))

    # ---- 2. slices ----
    print("\n-- SLICES ----------------------------------------------------")
    slice_uuid_str = {}
    for src in WM_SLICE_ORDER:
        new = slicemap[src]
        row = fetch_row(cur, "slices", src)
        oldds = row["datasource_id"]
        newds = dsmap[oldds]
        name = DS_NEW_NAME[oldds]
        su = uuidlib.uuid4()
        slice_uuid_str[src] = str(su)

        params = json.loads(row["params"])
        remap_json(params, dsmap, new, label_colors)
        params_s = json.dumps(params).replace("wm_price", "pw_price")
        assert_clean_blob(params_s, "slice %d params" % new)

        qc_s = None
        if row["query_context"]:
            qc = json.loads(row["query_context"])
            remap_json(qc, dsmap, new, label_colors)
            qc_s = json.dumps(qc).replace("wm_price", "pw_price")
            assert_clean_blob(qc_s, "slice %d query_context" % new)

        row.update({
            "id": new,
            "uuid": su.bytes,
            "datasource_id": newds,
            "datasource_type": "table",
            "datasource_name": "public.%s" % name,
            "perm": "[CPI PostgreSQL].[%s](id:%d)" % (name, newds),
            "schema_perm": "[CPI PostgreSQL].[public]",
            "params": params_s,
            "query_context": qc_s,
            "created_on": _now(), "changed_on": _now(),
            "last_saved_at": None, "last_saved_by_fk": None,
        })
        insert_row(cur, "slices", row)
        created["slices"].append(new)
        print("  %3d -> %3d  ds %d -> %d  %s"
              % (src, new, oldds, newds, ascii(row["slice_name"])))

    # ---- 3. dashboard_slices ----
    print("\n-- DASHBOARD_SLICES ------------------------------------------")
    for sid in OLD_PW_SLICES:
        r = cur.execute("SELECT id FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                        (DASH, sid)).fetchone()
        expect(r is not None, "dashboard_slices link for slice %d vanished" % sid)
        if record_backup:
            bk(cur, "removed_link", sid, {"dashboard_id": DASH, "slice_id": sid})
        cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND slice_id=?",
                    (DASH, sid))
    for src in WM_SLICE_ORDER:
        c2 = cur.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                         (DASH, slicemap[src]))
        created["dashboard_slices"].append(c2.lastrowid)
    print("  unlinked %s; linked %s" % (OLD_PW_SLICES, sorted(slicemap.values())))

    # ---- 4. position_json ----
    print("\n-- POSITION_JSON ---------------------------------------------")
    pos3 = copy.deepcopy(st["pos3"])
    pos6 = st["pos6"]
    # remove old rows + charts
    for rid, cid in EXPECTED_OLD_ROW_CHART.items():
        del pos3[rid]
        del pos3[cid]
    # relabel kept nav tabs, create pwNav5, attach cloned subtrees
    for pw_tab, label, wm_tab in PW_NAV_PLAN:
        subtree_src = pos6[wm_tab]["children"][0]
        new_root, nodes = clone_subtree(pos6, subtree_src, slicemap, slice_uuid_str)
        for k in nodes:
            expect(k not in pos3, "node id collision: %s" % k)
        pos3.update(nodes)
        if pw_tab in pos3:
            pos3[pw_tab]["meta"]["text"] = label
            pos3[pw_tab]["children"] = [new_root]
        else:  # TAB-pwNav5
            pos3[pw_tab] = {
                "children": [new_root],
                "id": pw_tab,
                "meta": {"text": label, "defaultText": "Tab title",
                         "placeholder": "Tab title"},
                "parents": [],   # rewritten below
                "type": "TAB",
            }
        print("  %-11s %-24s <- dash-6 subtree %s (root %s)"
              % (pw_tab, ascii(label), wm_tab, new_root))
    pos3["TABS-pwTopNav"]["children"] = [t for t, _l, _w in PW_NAV_PLAN]
    rewrite_parents(pos3)
    problems = validate(pos3)
    expect(problems == [], "post-edit layout INVALID: %s" % problems)
    laid_out = {n["meta"]["chartId"] for n in pos3.values()
                if isinstance(n, dict) and n.get("type") == "CHART"}
    expect(laid_out == set(slicemap.values()),
           "layout charts %s != cloned slices" % sorted(laid_out))
    print("  validation: 0 problems; %d charts laid out; old nodes removed: %d"
          % (len(laid_out), 2 * len(EXPECTED_OLD_ROW_CHART)))

    # ---- 5. json_metadata ----
    print("\n-- JSON_METADATA ---------------------------------------------")
    jm3 = copy.deepcopy(st["jm3"])
    jm6 = st["jm6"]

    def mapslices(lst):
        return [slicemap[x] for x in (lst or []) if isinstance(x, int) and x in slicemap]

    # native filters: canonical 12, fresh ids, targets + scopes remapped.
    # NOTE the canonical scopes deliberately leave slices 107/110's twins in
    # NEITHER chartsInScope nor excluded -- dash 6 is like that; relative
    # semantics are preserved exactly, never "completed".
    new_nf = []
    expected_scopes = {}
    for f in jm6.get("native_filter_configuration") or []:
        nf = copy.deepcopy(f)
        expect(nf["id"].startswith(FILTER_ID_PREFIX_OLD), "unexpected filter id %r" % nf["id"])
        nf["id"] = FILTER_ID_PREFIX_NEW + nf["id"][len(FILTER_ID_PREFIX_OLD):]
        for t in nf.get("targets", []):
            if "datasetId" in t:
                expect(t["datasetId"] in dsmap, "filter %s targets unmapped dataset %s"
                       % (nf["id"], t["datasetId"]))
                t["datasetId"] = dsmap[t["datasetId"]]
        if "chartsInScope" in nf:
            nf["chartsInScope"] = mapslices(nf["chartsInScope"])
        sc = nf.get("scope") or {}
        if "excluded" in sc:
            sc["excluded"] = mapslices(sc["excluded"])
        if isinstance(nf.get("description"), str):
            nf["description"] = nf["description"].replace("WM", "PW")
        expected_scopes[nf["id"]] = (sorted(nf.get("chartsInScope") or []),
                                     sorted((nf.get("scope") or {}).get("excluded") or []))
        new_nf.append(nf)
        print("  filter %-32s -> ds %s col %-18s inScope=%d excluded=%d"
              % (nf["id"], nf["targets"][0]["datasetId"],
                 nf["targets"][0]["column"]["name"],
                 len(nf.get("chartsInScope") or []),
                 len((nf.get("scope") or {}).get("excluded") or [])))
    jm3["native_filter_configuration"] = new_nf

    # chart_configuration + global_chart_configuration cloned from dash 6
    newcc = {}
    for k, v in (jm6.get("chart_configuration") or {}).items():
        if int(k) not in slicemap:
            continue
        v = copy.deepcopy(v)
        if "id" in v:
            v["id"] = slicemap[v["id"]]
        cf = v.get("crossFilters", {})
        if isinstance(cf.get("chartsInScope"), list):
            cf["chartsInScope"] = mapslices(cf["chartsInScope"])
        newcc[str(slicemap[int(k)])] = v
    jm3["chart_configuration"] = newcc
    gcc = copy.deepcopy(jm6.get("global_chart_configuration") or {})
    if "chartsInScope" in gcc:
        gcc["chartsInScope"] = mapslices(gcc["chartsInScope"])
    if "scope" in gcc and "excluded" in gcc.get("scope", {}):
        gcc["scope"]["excluded"] = mapslices(gcc["scope"]["excluded"])
    jm3["global_chart_configuration"] = gcc

    # label_colors: additive merge, existing keys win; brand scheme kept
    merged = dict(label_colors)
    merged.update(st["jm3"].get("label_colors") or {})
    added = [k for k in merged if k not in (st["jm3"].get("label_colors") or {})]
    jm3["label_colors"] = merged
    expect(jm3.get("color_scheme") == "precisionAir", "color_scheme must stay precisionAir")
    print("  chart_configuration: %d entries; global chartsInScope: %d"
          % (len(newcc), len(gcc.get("chartsInScope") or [])))
    print("  label_colors: %d -> %d keys (+%d new, 0 overwritten)"
          % (len(st["jm3"].get("label_colors") or {}), len(merged), len(added)))
    print("  kept: color_scheme=precisionAir, css untouched (%d chars),"
          " show_native_filters=%r, filter_bar_orientation=%r"
          % (len(st["css3"]), jm3.get("show_native_filters"),
             jm3.get("filter_bar_orientation")))

    # ---- 6. dashboard row ----
    if record_backup:
        bk(cur, "dashboard", DASH, {
            "position_json": json.dumps(st["pos3"]),
            "json_metadata": json.dumps(st["jm3"]),
            "css": st["css3"],
        })
        bk(cur, "created", "ids", created)
    cur.execute("UPDATE dashboards SET position_json=?, json_metadata=?, changed_on=? WHERE id=?",
                (json.dumps(pos3), json.dumps(jm3), _now(), DASH))
    expect(cur.rowcount == 1, "dashboards update rowcount %d" % cur.rowcount)

    return {"dsmap": dsmap, "slicemap": slicemap, "created": created,
            "label_colors": label_colors, "expected_scopes": expected_scopes,
            "cc_keys": sorted(int(k) for k in newcc)}


# ---------------------------------------------------------------------------
# post-plan verification: the by-id reference checklist
# (dashboard_slices, position_json chartId+uuid, filter scopes,
#  global/chart configuration, three-place label_colors)
# ---------------------------------------------------------------------------

def verify(cur, ctx):
    print("\n-- VERIFICATION (re-read from DB) ----------------------------")
    slicemap, dsmap = ctx["slicemap"], ctx["dsmap"]
    new_slices = sorted(slicemap.values())
    new_ds = sorted(dsmap.values())
    probs = []

    links = sorted(r[0] for r in cur.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=?", (DASH,)))
    if links != new_slices:
        probs.append("dashboard_slices %s != %s" % (links, new_slices))

    pos = json.loads(cur.execute("SELECT position_json FROM dashboards WHERE id=?",
                                 (DASH,)).fetchone()[0])
    v = validate(pos)
    if v:
        probs.append("layout: %s" % v)
    uuid_by_slice = {}
    for sid in new_slices:
        b = cur.execute("SELECT uuid FROM slices WHERE id=?", (sid,)).fetchone()[0]
        uuid_by_slice[sid] = str(uuidlib.UUID(bytes=b))
    charted = {}
    for n in pos.values():
        if isinstance(n, dict) and n.get("type") == "CHART":
            charted[n["meta"]["chartId"]] = n["meta"].get("uuid")
    if sorted(charted) != new_slices:
        probs.append("layout chartIds %s != %s" % (sorted(charted), new_slices))
    for sid, u in charted.items():
        if uuid_by_slice.get(sid) != u:
            probs.append("layout uuid for slice %d != slices.uuid" % sid)

    jm = json.loads(cur.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                                (DASH,)).fetchone()[0])
    nf = jm.get("native_filter_configuration") or []
    if len(nf) != 12:
        probs.append("expected 12 native filters, found %d" % len(nf))
    for f in nf:
        for t in f.get("targets", []):
            if t.get("datasetId") not in new_ds:
                probs.append("filter %s targets foreign dataset %s" % (f["id"], t.get("datasetId")))
        cis = sorted(f.get("chartsInScope") or [])
        exc = sorted((f.get("scope") or {}).get("excluded") or [])
        if not set(cis) <= set(new_slices) or not set(exc) <= set(new_slices):
            probs.append("filter %s scope references non-new slices" % f["id"])
        if ctx["expected_scopes"].get(f["id"]) != (cis, exc):
            probs.append("filter %s scope != canonical remap" % f["id"])
    gcc = jm.get("global_chart_configuration") or {}
    if sorted(gcc.get("chartsInScope") or []) != new_slices:
        probs.append("global_chart_configuration.chartsInScope wrong")
    cc = jm.get("chart_configuration") or {}
    if sorted(int(k) for k in cc) != ctx["cc_keys"]:
        probs.append("chart_configuration keys %s != canonical remap %s"
                     % (sorted(int(k) for k in cc), ctx["cc_keys"]))

    lc = jm.get("label_colors") or {}
    for sid in new_slices:
        p, q = cur.execute("SELECT params, query_context FROM slices WHERE id=?",
                           (sid,)).fetchone()
        plc = (json.loads(p).get("label_colors") or {}) if p else {}
        qlc = {}
        if q:
            qlc = (json.loads(q).get("form_data") or {}).get("label_colors") or {}
        for k, vv in ctx["label_colors"].items():
            if plc and plc.get(k) != vv:
                probs.append("slice %d params.label_colors[%r] wrong" % (sid, k))
                break
        for k, vv in ctx["label_colors"].items():
            if qlc and qlc.get(k) != vv:
                probs.append("slice %d qc label_colors[%r] wrong" % (sid, k))
                break
        missing = [k for k in ctx["label_colors"] if k not in lc]
        if missing:
            probs.append("dashboard label_colors missing keys e.g. %s" % missing[:3])
            break

    for name in DS_NEW_NAME.values():
        r = cur.execute("SELECT sql FROM tables WHERE table_name=?", (name,)).fetchone()
        if not r or not r[0]:
            probs.append("dataset %s missing or not virtual" % name)
        elif "wm_" in r[0] or "'WM'" in r[0]:
            probs.append("dataset %s SQL retains WM tokens" % name)

    if probs:
        raise RuntimeError("POST-PLAN VERIFICATION FAILED: %s" % probs)
    print("  dashboard_slices, layout chartId+uuid, 12 filters (targets+scopes),")
    print("  global/chart configuration, three-place label_colors, dataset SQL: ALL OK")


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------

def open_ro():
    return sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)


def show():
    con = open_ro()
    cur = con.cursor()
    try:
        print("=== parity_pw_rebuild --show ===")
        st = preflight(cur)
        print("preflight: dash 3 and dash 6 match the surveyed state (0 drift)")
        print("\n-- CURRENT DASH 3 --------------------------------------------")
        for tid, label in EXPECTED_PW_NAV_OLD:
            kids = st["pos3"][tid]["children"]
            print("  %-11s %-22s children=%s" % (tid, ascii(label), kids))
        print("  slices linked: %s" % OLD_PW_SLICES)
        print("  filters: %d (targeting datasets 4/25/26)"
              % len(st["jm3"].get("native_filter_configuration") or []))
        print("  label_colors: %d keys | color_scheme: %s | css: %d chars"
              % (len(st["jm3"].get("label_colors") or {}),
                 st["jm3"].get("color_scheme"), len(st["css3"])))
        print("\n-- CANONICAL DASH 6 ------------------------------------------")
        for tid, label in EXPECTED_WM_NAV:
            sub = st["pos6"][tid]["children"][0]
            subkids = st["pos6"][sub]["children"]
            charts = []
            for tabk in subkids:
                for rowk in st["pos6"][tabk]["children"]:
                    for ck in st["pos6"][rowk]["children"]:
                        charts.append(st["pos6"][ck]["meta"]["chartId"])
            print("  %-11s %-24s sub-tabs=%d charts=%s"
                  % (tid, ascii(label), len(subkids), charts))
        print_velocity_decision(st)
        if backup_exists(cur):
            print("\nNOTE: %s EXISTS -- already applied; --apply will refuse." % BACKUP_TABLE)
        # plan preview without writes: dry-run covers the full rehearsal
        base_ds = cur.execute("SELECT max(id) FROM tables").fetchone()[0] + 1
        base_sl = cur.execute("SELECT max(id) FROM slices").fetchone()[0] + 1
        print("\n-- PLAN (preview) --------------------------------------------")
        for i, src in enumerate(DS_SRC_ORDER):
            print("  dataset %d -> %d %s" % (src, base_ds + i, DS_NEW_NAME[src]))
        for i, src in enumerate(WM_SLICE_ORDER):
            print("  slice %3d -> %3d %s" % (src, base_sl + i,
                  ascii(EXPECTED_WM_SLICES[src][0])))
        print("  12 filters NATIVE_FILTER-PW-*; TAB-pwNav1..4 relabelled + TAB-pwNav5 added")
        print("  run --dry-run for the full rehearsal against an in-memory copy")
        return 0
    finally:
        con.close()


def dry_run():
    src = open_ro()
    try:
        mem = sqlite3.connect(":memory:")
        src.backup(mem)
    finally:
        src.close()
    cur = mem.cursor()
    try:
        print("=== parity_pw_rebuild --dry-run (in-memory copy; live DB opened read-only) ===")
        if backup_exists(cur):
            print("REFUSING: %s already exists -- applied before. --revert first." % BACKUP_TABLE)
            return 1
        st = preflight(cur)
        print("preflight: 0 drift")
        print_velocity_decision(st)
        ctx = plan(cur, st, record_backup=False)
        mem.commit()
        verify(cur, ctx)
        print("\nDRY-RUN COMPLETE: full plan executed and verified on the in-memory")
        print("copy; the live superset.db was never opened for writing.")
        return 0
    finally:
        mem.close()


def apply_():
    con = sqlite3.connect(DB, isolation_level=None, timeout=30)
    cur = con.cursor()
    try:
        if backup_exists(cur):
            print("REFUSING: %s already exists -- applied before. --revert first." % BACKUP_TABLE)
            return 1
        # full-DB .bak BEFORE the write lock (WAL-safe backup API, never cp)
        bak = DB + ".bak." + _ist_stamp() + "_IST.pwrebuild"
        dst = sqlite3.connect(bak)
        try:
            con.backup(dst)
        finally:
            dst.close()
        print("full DB backup: %s" % bak)

        cur.execute("BEGIN IMMEDIATE")
        st = preflight(cur)
        print("preflight: 0 drift")
        print_velocity_decision(st)
        cur.execute("CREATE TABLE %s (kind TEXT, ref TEXT, payload TEXT)" % BACKUP_TABLE)
        ctx = plan(cur, st, record_backup=True)
        con.commit()
        print("\nCOMMITTED")
        verify(cur, ctx)
        print("\nAPPLIED. Old slices 76-83 remain in the DB, detached.")
        print("Revert with --revert; nuclear option: %s" % bak)
        return 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def revert():
    con = sqlite3.connect(DB, isolation_level=None, timeout=30)
    cur = con.cursor()
    try:
        if not backup_exists(cur):
            print("no %s -- nothing to revert." % BACKUP_TABLE)
            return 1
        cur.execute("BEGIN IMMEDIATE")
        rows = list(cur.execute("SELECT kind, ref, payload FROM %s" % BACKUP_TABLE))
        by_kind = {}
        for kind, ref, payload in rows:
            by_kind.setdefault(kind, []).append((ref, json.loads(payload)))

        for _ref, saved in by_kind.get("dashboard", []):
            cur.execute("UPDATE dashboards SET position_json=?, json_metadata=?, css=?, "
                        "changed_on=? WHERE id=?",
                        (saved["position_json"], saved["json_metadata"], saved["css"],
                         _now(), DASH))
            print("dashboard %d row restored" % DASH)
        created = dict(by_kind.get("created", [("ids", {})])[0][1])
        for rid in created.get("dashboard_slices", []):
            cur.execute("DELETE FROM dashboard_slices WHERE id=?", (rid,))
        for rid in created.get("slices", []):
            cur.execute("DELETE FROM slices WHERE id=?", (rid,))
        for rid in created.get("table_columns", []):
            cur.execute("DELETE FROM table_columns WHERE id=?", (rid,))
        for rid in created.get("sql_metrics", []):
            cur.execute("DELETE FROM sql_metrics WHERE id=?", (rid,))
        for rid in created.get("tables", []):
            cur.execute("DELETE FROM tables WHERE id=?", (rid,))
        print("created rows deleted: %s" % {k: len(v) for k, v in created.items()})
        for _ref, saved in by_kind.get("removed_link", []):
            cur.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                        (saved["dashboard_id"], saved["slice_id"]))
        print("old dashboard_slices links restored: %d" % len(by_kind.get("removed_link", [])))
        cur.execute("DROP TABLE %s" % BACKUP_TABLE)
        con.commit()
        print("REVERTED (backup table dropped; .bak file kept).")
        return 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description="Rebuild dashboard 3 (PW) to the canonical WinAir shape")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    if args.show:
        return show()
    if args.dry_run:
        return dry_run()
    if args.revert:
        return revert()
    return apply_()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("parity_pw_rebuild FAILED (no partial state committed): %s" % e)
        sys.exit(1)
