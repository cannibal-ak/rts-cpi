#!/usr/bin/env python3
"""Backfill dashboard 1 (interCaribbean / JY) to the canonical WinAir shape.

Dashboard 6 (WM) is the canonical tenant dashboard. After the Gate-1 rename
pass (parity_rename.py) dash 1 already matches its 5-tab shape and titles.
This script closes the remaining structural gaps, WM-template-faithfully but
with JY's brand palette KEPT (ic_branded + dash 1's existing carrier hexes):

NEW CHARTS (3), each with a purpose-built JY dataset:
  A1 'Lowest Available Fare & Availability by Travel_Date' [mixed_timeseries]
     cloned from WM slice 109 / dataset 37. Dataset 36 (the 2026-08 JY
     availability experiment) is NOT reusable: slice 109's metrics_b reference
     `availability_status`, which ds36 lacks (it has `status_label` with
     different semantics) -- verified 2026-09-01, guarded at plan time.
     A NEW dataset `jy_all_airlines_fares_availability` is created from ds37's
     SQL with vw_airline_cpi_wm_snapshot->vw_airline_cpi_jy_snapshot and
     'WM'->'JY', PLUS three deliberate deviations so dash 1's ds13-sourced
     native filters (which bind by column NAME and match by VALUE) still hit:
       stops        ds13's bucketed strings ('Nonstop'/'1 stop'/...), not raw int
       flt_num      ds13's COALESCE(...,'(unspecified)') form
       fare_family  added (ds13's ref_bkg_class expression; ds37 has no JY
                    FareFamily filter to serve)
     and dtd_bucket as ds13's CALCULATED column (labels '0-7'/'8-14'/... --
     ds37's inline '00-07' style would silently miss JY's filter values).
     Placed as the FIRST chart in the Avg_Fare '📈 Line' sub-tab, ABOVE
     chart 43, which stays (approved exception; 43 and ds13 are untouchable).
  A2 'Fare Composition — Base / Tax / YQ' [dist_bar] cloned from WM slice 107,
     but with the METRIC definitions from DA slice 120 -- the COALESCE(...,0)
     wrapping that stops the pandas-pivot "not in index" crash on all-NULL YQ
     (JY's ref_yq is 100% NULL/0, so without COALESCE the WM-107 latent bug
     would be a LIVE bug here). New dataset `jy_fare_composition` = ds32's SQL
     with wm->jy substitutions (base_fare/tax/yq verified present on
     vw_airline_cpi_jy_snapshot). New '🧾 Composition' sub-tab in the
     Competitor Breakdown tab, cloning dash 6's node shape.
  A3 'Deployed Capacity — Flights Operated by Airline' [echarts_timeseries_bar]
     cloned from WM slice 110 / dataset 38. New dataset `jy_deployed_capacity`
     = ds38's SQL with wm->jy substitutions (unnests '/'-joined flt_num
     itineraries; JY has 33,979 ref + 443,803 comp multi-leg rows, so the
     unnest is real work here; blank flt_num = no flight, excluded). The
     Velocity tab is restructured to dash 6's nested sub-tab shape:
     '📊 Booking & Seat Factor' (existing chart 47 moves inside, node
     untouched) + '🛫 Deployed Capacity' (the new chart).

CHART-TYPE SWAPS (2), the wm_carrier_consistency.py 97->111 way -- old slice
parked intact off-dashboard, every by-id reference repointed
(dashboard_slices, position_json node meta, every native filter's
chartsInScope AND scope.excluded, global_chart_configuration,
chart_configuration crossFilters):
  B1 slice 49 'Competitor Breakdown' [dist_bar] -> clone modeled on WM 111
     (echarts_timeseries_bar, airline as SERIES so carriers are colourable),
     datasource ds13 (columns airline/fare/travel_date/cap_date verified).
  B2 slice 53 'Pricing Recommendations — Summary' [dist_bar] -> clone modeled
     on WM 112, datasource ds15 (recommendation/cap_date/ref_dep_date
     verified; NB ds15 emits ELEVEN load-factor-aware categories where WM's
     ds33 emits four -- the series set is JY's own).

FILTER SCOPING of the new charts mirrors dash 6 exactly: the availability
chart joins every list chart 43 is in (WM has 109 scoped like that); the
composition and deployed-capacity charts stay OUT of every native filter list
(on dash 6, 107 and 110 are in neither chartsInScope nor excluded -- absence
is the canonical state, not an oversight). Pre-existing stale refs to slices
54/106 in dash 1's filter lists are left untouched (additive-only).

LABEL_COLORS (additive; the cross-tenant rts_cpi_palette scheme is never
touched; existing keys always win):
  carriers      discovered by volume from vw_airline_cpi_jy_snapshot; each
                keeps its EXISTING dash-1 hex; genuinely new carriers take the
                jy-palette fallbacks (#A05A2C, #0F766E) in volume order, and
                more than two new carriers aborts (never a ninth hue).
  per carrier   bare code, 'Lowest Available Fare, <C>', and the four marker
                spellings 'Sold out, <C>' / 'Not on sale, <C>' (+' (1)'
                query-B variants) at the cross-surface amber/grey
                (docs/winair-palette.md §6).
  Base/Tax/YQ   the JY-brand translation of WM's family-pair + contrast-hue
                structure, all ic_branded scheme hexes: Base #049CFC (ocean
                anchor), Tax #04049C (deep-blue family pair), YQ #E4049C
                (magenta contrast). Cross-chart hue reuse with carrier slots
                (9Q, BW) is accepted per the one-palette-per-chart rule --
                WM itself reuses DM's cyan for YQ.
  reco cats     slice 53's existing 11-category traffic-light, promoted from
                its (dead, dist_bar) params to keys that actually bind.
Keys are written to dashboard json_metadata.label_colors AND each new slice's
params.label_colors and query_context.form_data.label_colors.

HOUSE PATTERN
  --show     read-only state survey.
  --dry-run  full plan + in-memory build of every payload (datasets, slices,
             position_json, json_metadata) + structural validation + Postgres
             feasibility probes. Executes NO DML whatsoever.
  --apply    full-DB backup via the sqlite3 backup API to
             superset.db.bak.<YYYYMMDDTHHMMSS>_IST.jybackfill, then ONE
             BEGIN IMMEDIATE transaction: in-DB backup table
             _parity_jy_backfill_backup (pre-change dash-1 row, removed
             dashboard_slices rows, ids of every created row), all writes,
             post-edit layout validation, commit, post-commit re-validation.
             Refuses if the backup table already exists.
  --revert   exact inverse from the backup table: created rows deleted,
             removed links re-inserted, dash-1 position_json/json_metadata
             restored blob-for-blob, backup table dropped. NB blob restore
             discards any dash-1 metadata edits made after --apply.
Every touched object is asserted to be in its surveyed state first (titles
are the POST-rename ones); any drift aborts before a single write.
Slice 43 and dataset 13 are never modified (ds13 is only used, read-only, as
the datasource of the new Competitor Breakdown slice). Only dashboard 1 is
written; dashboards 2/5/8 are never read or written.

Run INSIDE cpi-superset-1 (stdlib sqlite3 + the container's psycopg2):
  Recon:    docker exec -i cpi-superset-1 python3 - --show    < scripts/superset/parity_jy_backfill.py
  Dry-run:  docker exec -i cpi-superset-1 python3 - --dry-run < scripts/superset/parity_jy_backfill.py
  Apply:    docker exec -i cpi-superset-1 python3 - --apply   < scripts/superset/parity_jy_backfill.py
  Revert:   docker exec -i cpi-superset-1 python3 - --revert  < scripts/superset/parity_jy_backfill.py
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

DASH_ID = 1
WM_DASH_ID = 6          # read-only template source
BACKUP_TABLE = "_parity_jy_backfill_backup"
BAK_TAG = "jybackfill"

UNTOUCHABLE_SLICES = {43}
UNTOUCHABLE_DATASETS = {13}

# WM/DA template slices (read-only)
TPL_AVAIL, TPL_COMP, TPL_DEPCAP, TPL_COMP_BAR, TPL_RECO = 109, 107, 110, 111, 112
DA_COALESCE_SLICE = 120
OLD_COMP_BAR, OLD_RECO = 49, 53

JY_SNAPSHOT_VIEW = "vw_airline_cpi_jy_snapshot"

# ---------------------------------------------------------------- palette --
# dash 1's live label_colors / docs/jy-palette.md §3 -- the KEPT JY palette.
JY_CARRIERS = {
    "JY": "#049CFC", "BW": "#E4049C", "WM": "#8CD404", "9Q": "#04049C",
    "5L": "#F59E0B", "PY": "#06B6D4", "DO": "#8B5CF6", "S6": "#64748B",
}
JY_FALLBACKS = ["#A05A2C", "#0F766E"]   # jy-palette.md §3; never a new hue
SOLD_OUT = "#F39C12"                    # cross-surface marker pair
NOT_ON_SALE = "#9E9E9E"                 # (winair-palette.md §6)
COMPOSITION_COLORS = {"Base": "#049CFC", "Tax": "#04049C", "YQ": "#E4049C"}
# ds15's 11 categories; hexes must match slice 53's current (dead) keys --
# asserted at plan time so a palette edit elsewhere aborts rather than forks.
RECO_COLORS = {
    "Aggressive Decrease": "#DC2626", "Decrease": "#EF4444",
    "Slight Decrease": "#F87171", "Reduce": "#F87171",
    "Monitor": "#A78BFA", "Match Market": "#64748B", "No Change": "#94A3B8",
    "Slight Increase": "#4ADE80", "Increase": "#22C55E",
    "Strong Increase": "#15803D", "Consider Increase": "#16A34A",
}

# ------------------------------------------------------------- new slices --
AVAIL_SLICE_NAME = "Lowest Available Fare & Availability by Travel_Date"
COMP_SLICE_NAME = "Fare Composition — Base / Tax / YQ"
DEPCAP_SLICE_NAME = "Deployed Capacity — Flights Operated by Airline"
DEPCAP_NAME_OVERRIDE = "Flights Operated by Airline"
COMP_BAR_SLICE_NAME = "Competitor Breakdown"
RECO_SLICE_NAME = "Pricing Recommendations — Summary"

# optionName / filterOptionName hygiene renames applied to cloned payloads
# (values are per-slice tokens; labels -- which drive series naming -- are
# never changed).
RENAMES = {
    "metric_00cf3606b85c": "metric_jyavail_lowest",
    "metric_wmavail_sold_out": "metric_jyavail_sold_out",
    "metric_wmavail_not_on_sale": "metric_jyavail_not_on_sale",
    "filter_travel_date_04d6c9aa": "filter_travel_date_jyavail1",
    "filter_cap_date_006d1bba": "filter_cap_date_jyavail2",
    "metric_depcap_flights": "metric_jydepcap_flights",
    "filter_travel_date_depcap01": "filter_travel_date_jydepcap1",
    "filter_cap_date_depcap02": "filter_cap_date_jydepcap2",
    "metric_wm_base_1e": "metric_jy_base_1e",
    "metric_wm_tax_1e": "metric_jy_tax_1e",
    "metric_wm_yq_1e": "metric_jy_yq_1e",
    "filter_cap_date_04633bf6": "filter_cap_date_jyfc1",
    "filter_travel_date_031ccea9": "filter_travel_date_jyfc2",
    "metric_avg_fare_comp97": "metric_avg_fare_jy49",
    "filter_cap_date_comp97a": "filter_cap_date_jy49a",
    "filter_travel_date_comp97b": "filter_travel_date_jy49b",
}

# ----------------------------------------------------------- new datasets --
AVAIL_DS_NAME = "jy_all_airlines_fares_availability"
COMP_DS_NAME = "jy_fare_composition"
DEPCAP_DS_NAME = "jy_deployed_capacity"

# ds13's calculated dtd_bucket -- copied verbatim so JY's DTDBucket filter
# values ('0-7', '8-14', ...) keep matching.
DTD_EXPR = ("CASE WHEN (travel_date - cap_date) < 0 THEN '(past)' "
            "WHEN (travel_date - cap_date) <= 7 THEN '0-7' "
            "WHEN (travel_date - cap_date) <= 14 THEN '8-14' "
            "WHEN (travel_date - cap_date) <= 30 THEN '15-30' "
            "WHEN (travel_date - cap_date) <= 45 THEN '31-45' "
            "ELSE '46+' END")

# ds37's SQL, wm->jy, with the three filter-compat deviations documented in
# the header (stops/flt_num/fare_family) and no inline dtd_bucket (it becomes
# the ds13-style calculated column above). availability_status semantics are
# ds37's verbatim: ref side keys off raw ref_stops, comp side off comp_flt_num.
AVAIL_SQL = """SELECT ref_dep_date AS travel_date, 'JY' AS airline, ref_tot_fare AS fare,
       CONCAT(ref_org, ' → ', ref_dst) AS route, ref_org AS origin, ref_dst AS destination,
       trip_type, ref_via AS via, cap_date, 'reference' AS role,
       COALESCE(NULLIF(ref_flt_num, ''), '(unspecified)') AS flt_num,
       ref_base_fare AS base_fare, ref_tax AS tax, ref_yq AS yq,
       CASE WHEN ref_stops IS NULL THEN '(unspecified)' WHEN ref_stops = 0 THEN 'Nonstop' WHEN ref_stops = 1 THEN '1 stop' ELSE '2+ stops' END AS stops,
       CASE WHEN ref_bkg_class IS NULL OR btrim(ref_bkg_class) = '' THEN '(unspecified)' ELSE upper(btrim(ref_bkg_class)) END AS fare_family,
       ref_dep_time AS dep_time, NULL::integer AS duration_min,
       CASE WHEN ref_tot_fare > 0 THEN 'on_sale' WHEN ref_stops IS NULL THEN 'not_on_sale' ELSE 'sold_out' END AS availability_status
FROM vw_airline_cpi_jy_snapshot
UNION ALL
SELECT ref_dep_date, comp_al, comp_tot_fare,
       CONCAT(ref_org, ' → ', ref_dst), ref_org, ref_dst,
       trip_type, comp_via, cap_date, 'competitor',
       COALESCE(NULLIF(ref_flt_num, ''), '(unspecified)'),
       comp_base_fare, comp_tax, comp_yq,
       CASE WHEN comp_stops IS NULL THEN '(unspecified)' WHEN comp_stops = 0 THEN 'Nonstop' WHEN comp_stops = 1 THEN '1 stop' ELSE '2+ stops' END,
       CASE WHEN ref_bkg_class IS NULL OR btrim(ref_bkg_class) = '' THEN '(unspecified)' ELSE upper(btrim(ref_bkg_class)) END,
       comp_dep_time, NULL::integer,
       CASE WHEN comp_tot_fare > 0 THEN 'on_sale' WHEN COALESCE(comp_flt_num, '') <> '' THEN 'sold_out' ELSE 'not_on_sale' END
FROM vw_airline_cpi_jy_snapshot"""

# (name, type, is_dttm, expression) -- explicit because the avail SQL is a
# documented hybrid, not a straight ds37 clone.
AVAIL_COLUMNS = [
    ("travel_date", "DATE", 1, None),
    ("airline", "STRING", 0, None),
    ("fare", "DECIMAL", 0, None),
    ("route", "STRING", 0, None),
    ("origin", "STRING", 0, None),
    ("destination", "STRING", 0, None),
    ("trip_type", "STRING", 0, None),
    ("via", "STRING", 0, None),
    ("cap_date", "DATE", 1, None),
    ("role", "STRING", 0, None),
    ("flt_num", "STRING", 0, None),
    ("base_fare", "NUMERIC", 0, None),
    ("tax", "NUMERIC", 0, None),
    ("yq", "NUMERIC", 0, None),
    ("stops", "STRING", 0, None),
    ("fare_family", "STRING", 0, None),
    ("dep_time", "VARCHAR", 0, None),
    ("duration_min", "INTEGER", 0, None),
    ("availability_status", "STRING", 0, None),
    ("dtd_bucket", "STRING", 0, DTD_EXPR),
]

AVAIL_DS_DESCRIPTION = (
    "Fares + availability_status source for interCaribbean (JY), cloned from "
    "wm_all_airlines_fares_availability (ds 37) with jy substitutions. "
    "Deliberate deviations from the WM SQL: stops/flt_num/fare_family use "
    "jy_all_airlines_fares (ds 13) value conventions and dtd_bucket is the "
    "ds13-style calculated column, so dashboard 1's native filters keep "
    "matching. Built by parity_jy_backfill.py.")
COMP_DS_DESCRIPTION = (
    "Fare composition source for interCaribbean (JY) - clone of "
    "wm_all_airlines_fares (ds 32) with jy substitutions, created for the "
    "'Fare Composition — Base / Tax / YQ' chart on dashboard 1. "
    "Built by parity_jy_backfill.py.")

# ------------------------------------------------------- layout node ids --
N_ROW_AVAIL = "ROW-jy-avail"
N_CHART_AVAIL = "CHART-jy-avail"
N_TAB_COMP3 = "TAB-comp-3"
N_ROW_COMP3 = "ROW-comp-3"
N_CHART_FC = "CHART-jy-fc"
N_TABS_VEL = "TABS-jyvel"
N_TAB_VEL0 = "TAB-jyvel-0"
N_TAB_VEL1 = "TAB-jyvel-1"
N_ROW_VEL1 = "ROW-jy-vel-1"
N_CHART_DEPCAP = "CHART-jy-depcap"
NEW_NODE_IDS = [N_ROW_AVAIL, N_CHART_AVAIL, N_TAB_COMP3, N_ROW_COMP3,
                N_CHART_FC, N_TABS_VEL, N_TAB_VEL0, N_TAB_VEL1, N_ROW_VEL1,
                N_CHART_DEPCAP]

TAB_VEL0_LABEL = "\U0001F4CA Booking & Seat Factor"   # 📊
TAB_VEL1_LABEL = "\U0001F6EB Deployed Capacity"        # 🛫
TAB_COMP3_LABEL = "\U0001F9FE Composition"             # 🧾

# surveyed state (2026-09-01, post-rename) -- guards, not targets
EXPECTED_TITLES = {
    43: "Avg Fare by Travel Date",
    46: "Min/Max_Fare by Travel_Date",
    47: "Booking, Seat Factor, Capacity",
    48: "Pricing Recommendations",
    49: "Competitor Breakdown",
    50: "Lowest Available Avg_Fare by Travel_Date",
    51: "Lowest Available Avg_Fare by Travel_Date",
    52: "Min/Max_Fare by Travel_Date",
    53: "Pricing Recommendations — Summary",
}
EXPECTED_NAV5_LABEL = "Velocity"


# ---------------------------------------------------------------- helpers --
def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")


def _ist_stamp():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).strftime("%Y%m%dT%H%M%S")


def die(msg):
    sys.exit("ABORT (nothing committed): %s" % msg)


def deep_rename(obj, mapping):
    """Replace string VALUES that exactly match a mapping key, in place."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v in mapping:
                obj[k] = mapping[v]
            else:
                deep_rename(v, mapping)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and v in mapping:
                obj[i] = mapping[v]
            else:
                deep_rename(v, mapping)


def validate(pos):
    """Structural layout validation (ported from jy_topnav_embed.py)."""
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
                problems.append("node %s referenced by both %s and %s"
                                % (child, seen[child], k))
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
                problems.append("parents mismatch %s: stored=%s computed=%s"
                                % (nid, stored, chain))
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
            w = sum(nodes[c]["meta"].get("width", 0)
                    for c in v.get("children", []) or []
                    if c in nodes and nodes[c].get("type") == "CHART")
            if w > 12:
                problems.append("ROW %s children width sum %d > 12" % (k, w))
    return problems


def rewrite_parents(pos):
    """Recompute parents by BFS from ROOT_ID (writer kept separate from the
    validator on purpose -- the check must not be the writer run twice)."""
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


def sub_tab_meta(label):
    # dash 6 sub-tab convention: all three fields identical
    return {"text": label, "defaultText": label, "placeholder": label}


def backup_exists(con):
    return con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (BACKUP_TABLE,)).fetchone() is not None


def fetch_slice(cur, sid):
    row = cur.execute(
        "SELECT id, slice_name, viz_type, datasource_id, datasource_type, "
        "params, query_context FROM slices WHERE id=?", (sid,)).fetchone()
    if row is None:
        die("slice %d not found" % sid)
    d = dict(zip(["id", "slice_name", "viz_type", "datasource_id",
                  "datasource_type", "params", "query_context"], row))
    d["params_obj"] = json.loads(d["params"]) if d["params"] else {}
    d["qc_obj"] = json.loads(d["query_context"]) if d["query_context"] else None
    return d


def fetch_dataset(cur, ds_id):
    tcols = [r[1] for r in cur.execute("PRAGMA table_info(tables)")]
    row = cur.execute("SELECT %s FROM tables WHERE id=?" % ",".join(tcols),
                      (ds_id,)).fetchone()
    if row is None:
        die("dataset %d not found" % ds_id)
    d = dict(zip(tcols, row))
    ccols = [r[1] for r in cur.execute("PRAGMA table_info(table_columns)")]
    d["columns"] = [dict(zip(ccols, r)) for r in cur.execute(
        "SELECT %s FROM table_columns WHERE table_id=? ORDER BY id"
        % ",".join(ccols), (ds_id,))]
    return d


def dataset_column_names(cur, ds_id):
    return {r[0] for r in cur.execute(
        "SELECT column_name FROM table_columns WHERE table_id=?", (ds_id,))}


# --------------------------------------------------------------- postgres --
def pg_probes(specs):
    """READ-ONLY feasibility probes. Returns (volumes, source_cols)."""
    try:
        import psycopg2
    except ImportError:
        die("psycopg2 not importable in this container -- cannot probe "
            "postgres for carrier volumes / dataset feasibility")
    conn = psycopg2.connect(PG_DSN)
    try:
        cur = conn.cursor()
        need = ["ref_base_fare", "ref_tax", "ref_yq", "comp_base_fare",
                "comp_tax", "comp_yq", "ref_flt_num", "comp_flt_num",
                "ref_stops", "comp_stops", "ref_dep_time", "comp_dep_time",
                "ref_bkg_class", "ref_tot_fare", "comp_tot_fare"]
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=%s AND column_name = ANY(%s)",
            (JY_SNAPSHOT_VIEW, need))
        have = {r[0] for r in cur.fetchall()}
        missing = sorted(set(need) - have)
        if missing:
            die("BLOCKED: %s lacks source columns %s -- the composition/"
                "availability datasets cannot be built" %
                (JY_SNAPSHOT_VIEW, missing))
        cur.execute(
            "SELECT comp_al, count(*) FROM " + JY_SNAPSHOT_VIEW +
            " WHERE comp_tot_fare > 0 AND comp_al IS NOT NULL AND comp_al <> ''"
            " GROUP BY 1 ORDER BY 2 DESC, 1 ASC")
        volumes = cur.fetchall()
        for name, sql in specs:
            cur.execute("SELECT 1 FROM (" + sql + ") q LIMIT 1")
            if cur.fetchone() is None:
                die("BLOCKED: dataset SQL for %s returned zero rows" % name)
        conn.rollback()  # close the read txn
        return volumes, sorted(have)
    finally:
        conn.close()


def build_carrier_assignment(volumes):
    """Existing dash-1 hexes win; new carriers take fallbacks by volume."""
    assignment = {"JY": JY_CARRIERS["JY"]}
    fallbacks = list(JY_FALLBACKS)
    new_carriers = []
    for code, _n in volumes:
        if code in assignment:
            continue
        if code in JY_CARRIERS:
            assignment[code] = JY_CARRIERS[code]
        else:
            if not fallbacks:
                die("more new carriers than fallback slots (%r) -- never a "
                    "new hue; fold the tail into 'Other' instead"
                    % [c for c, _ in volumes])
            assignment[code] = fallbacks.pop(0)
            new_carriers.append(code)
    return assignment, new_carriers


# ----------------------------------------------------------- label colors --
def marker_keys(assignment):
    out = {}
    for c in assignment:
        out["Sold out, %s" % c] = SOLD_OUT
        out["Sold out, %s (1)" % c] = SOLD_OUT
        out["Not on sale, %s" % c] = NOT_ON_SALE
        out["Not on sale, %s (1)" % c] = NOT_ON_SALE
    return out


def laf_keys(assignment):
    return {"Lowest Available Fare, %s" % c: h for c, h in assignment.items()}


def dash_new_keys(assignment):
    keys = dict(assignment)
    keys.update(laf_keys(assignment))
    keys.update(marker_keys(assignment))
    keys.update(COMPOSITION_COLORS)
    keys.update(RECO_COLORS)
    return keys


# ------------------------------------------------------------ plan (read) --
def plan(cur, volumes=None):
    """Read + assert everything; return the state dict. NO writes.
    volumes: pass a previous probe's carrier volumes to skip the postgres
    round-trip (used for the re-assert pass under the write lock)."""
    st = {}
    if backup_exists(cur.connection if hasattr(cur, "connection") else cur):
        die("backup table %s already exists -- applied before (--revert "
            "first)" % BACKUP_TABLE)

    # --- dash 1 current state ---
    row = cur.execute(
        "SELECT position_json, json_metadata FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()
    if row is None:
        die("dashboard %d not found" % DASH_ID)
    st["pos_raw"], st["jm_raw"] = row
    pos = json.loads(st["pos_raw"])
    jm = json.loads(st["jm_raw"] or "{}")
    st["pos"], st["jm"] = pos, jm

    pre = validate(pos)
    if pre:
        die("dash %d layout invalid before edit: %s" % (DASH_ID, pre))

    for sid, want in sorted(EXPECTED_TITLES.items()):
        r = cur.execute("SELECT slice_name FROM slices WHERE id=?",
                        (sid,)).fetchone()
        if r is None:
            die("slice %d missing" % sid)
        if r[0] != want:
            die("slice %d is %r, expected %r -- survey stale" % (sid, r[0], want))

    linked = [r[0] for r in cur.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=?",
        (DASH_ID,))]
    st["linked"] = sorted(linked)
    for sid in (OLD_COMP_BAR, OLD_RECO):
        if sid not in linked:
            die("slice %d not linked to dashboard %d" % (sid, DASH_ID))

    old49 = fetch_slice(cur, OLD_COMP_BAR)
    old53 = fetch_slice(cur, OLD_RECO)
    if old49["viz_type"] != "dist_bar" or old49["datasource_id"] != 13:
        die("slice 49 is %s/ds%s, expected dist_bar/ds13"
            % (old49["viz_type"], old49["datasource_id"]))
    if old53["viz_type"] != "dist_bar" or old53["datasource_id"] != 15:
        die("slice 53 is %s/ds%s, expected dist_bar/ds15"
            % (old53["viz_type"], old53["datasource_id"]))
    st["old49"], st["old53"] = old49, old53
    lc53 = (old53["params_obj"].get("label_colors") or {})
    for cat, hexv in RECO_COLORS.items():
        if lc53.get(cat) != hexv:
            die("slice 53 label_colors[%r]=%r, expected %r -- survey stale"
                % (cat, lc53.get(cat), hexv))

    # --- layout guards ---
    def node(key):
        n = pos.get(key)
        if not isinstance(n, dict):
            die("layout node %s missing on dash %d" % (key, DASH_ID))
        return n

    if node("TAB-jyNav5")["meta"].get("text") != EXPECTED_NAV5_LABEL:
        die("TAB-jyNav5 label is %r, expected %r"
            % (node("TAB-jyNav5")["meta"].get("text"), EXPECTED_NAV5_LABEL))
    if node("TAB-jyNav5")["children"] != ["ROW-velocity"]:
        die("TAB-jyNav5 children drifted: %r" % node("TAB-jyNav5")["children"])
    if node("ROW-velocity")["children"] != ["CHART-jy-47"]:
        die("ROW-velocity children drifted: %r" % node("ROW-velocity")["children"])
    if node("TAB-avgfare-0")["children"] != ["ROW-avgfare-0"]:
        die("TAB-avgfare-0 children drifted: %r" % node("TAB-avgfare-0")["children"])
    if node("TABS-comp")["children"] != ["TAB-comp-0", "TAB-comp-2"]:
        die("TABS-comp children drifted: %r" % node("TABS-comp")["children"])
    for key, sid, header in (("CHART-jy-49", 49, "Competitor Breakdown — Bar"),
                             ("CHART-jy-53", 53, RECO_SLICE_NAME)):
        m = node(key)["meta"]
        if m.get("chartId") != sid:
            die("%s chartId is %r, expected %d" % (key, m.get("chartId"), sid))
        if m.get("sliceName") != header:
            die("%s header is %r, expected %r" % (key, m.get("sliceName"), header))
    for nid in NEW_NODE_IDS:
        if nid in pos:
            die("planned layout node id %s already exists" % nid)

    # --- metadata guards ---
    cc = jm.get("chart_configuration") or {}
    for sid in (OLD_COMP_BAR, OLD_RECO):
        if str(sid) in cc:
            die("chart_configuration unexpectedly has an entry for %d" % sid)
    gcc = jm.get("global_chart_configuration") or {}
    for sid in (OLD_COMP_BAR, OLD_RECO):
        if sid not in (gcc.get("chartsInScope") or []):
            die("global_chart_configuration lacks %d -- survey stale" % sid)

    # --- templates (read-only, dash 6 / DA) ---
    tpl = {}
    for key, sid, viz, ds in (("avail", TPL_AVAIL, "mixed_timeseries", 37),
                              ("comp", TPL_COMP, "dist_bar", 32),
                              ("depcap", TPL_DEPCAP, "echarts_timeseries_bar", 38),
                              ("comp_bar", TPL_COMP_BAR, "echarts_timeseries_bar", 32),
                              ("reco", TPL_RECO, "echarts_timeseries_bar", 33)):
        s = fetch_slice(cur, sid)
        if s["viz_type"] != viz or s["datasource_id"] != ds:
            die("template slice %d is %s/ds%s, expected %s/ds%s"
                % (sid, s["viz_type"], s["datasource_id"], viz, ds))
        if not s["qc_obj"] or not isinstance(s["qc_obj"].get("form_data"), dict):
            die("template slice %d has no usable query_context" % sid)
        tpl[key] = s
    st["tpl"] = tpl
    if "availability_status" not in json.dumps(tpl["avail"]["params_obj"]):
        die("template slice 109 no longer references availability_status -- "
            "assumptions changed, re-survey")

    da = fetch_slice(cur, DA_COALESCE_SLICE)
    da_metrics = [m for m in (da["params_obj"].get("metrics") or [])
                  if isinstance(m, dict) and m.get("label") in ("Base", "Tax", "YQ")]
    if len(da_metrics) != 3:
        die("DA slice 120 does not carry the 3 Base/Tax/YQ metrics")
    for m in da_metrics:
        if not m.get("sqlExpression", "").strip().upper().startswith("COALESCE("):
            die("DA slice 120 metric %r is not COALESCE-wrapped -- the crash "
                "fix has been reverted?" % m.get("label"))
    st["da_metrics"] = copy.deepcopy(da_metrics)

    # --- ds36 reuse decision guard ---
    ds36_cols = dataset_column_names(cur, 36)
    if "availability_status" in ds36_cols:
        die("dataset 36 now HAS availability_status -- the create-new-dataset "
            "decision no longer holds; re-survey and decide reuse instead")
    st["ds36_cols"] = sorted(ds36_cols)

    # --- referenced-column checks on the swap datasources ---
    ds13_cols = dataset_column_names(cur, 13)
    for c in ("airline", "fare", "travel_date", "cap_date"):
        if c not in ds13_cols:
            die("ds13 lacks column %r needed by the Competitor Breakdown clone" % c)
    ds15_cols = dataset_column_names(cur, 15)
    for c in ("recommendation", "cap_date", "ref_dep_date"):
        if c not in ds15_cols:
            die("ds15 lacks column %r needed by the Pricing Recommendations "
                "Summary clone" % c)

    # --- dataset templates + wm->jy SQL substitution ---
    ds32 = fetch_dataset(cur, 32)
    ds37 = fetch_dataset(cur, 37)
    ds38 = fetch_dataset(cur, 38)
    st["ds37_row"], st["ds32_row"], st["ds38_row"] = ds37, ds32, ds38

    def wm_to_jy(sql):
        if "vw_airline_cpi_wm_snapshot" not in sql or "'WM'" not in sql:
            die("template dataset SQL no longer matches the wm-snapshot "
                "pattern -- substitution would be a no-op")
        out = sql.replace("vw_airline_cpi_wm_snapshot", JY_SNAPSHOT_VIEW)
        out = out.replace("'WM'", "'JY'")
        return out

    st["comp_sql"] = wm_to_jy(ds32["sql"])
    st["depcap_sql"] = wm_to_jy(ds38["sql"])
    st["avail_sql"] = AVAIL_SQL
    for want in ("base_fare", "tax", "yq"):
        if want not in {c["column_name"] for c in ds32["columns"]}:
            die("ds32 lacks column %r -- composition clone impossible" % want)
    for want in ("operating_flight", "travel_date", "airline", "cap_date"):
        if want not in {c["column_name"] for c in ds38["columns"]}:
            die("ds38 lacks column %r -- deployed capacity clone impossible" % want)
    avail_names = {c[0] for c in AVAIL_COLUMNS}
    for c in ("travel_date", "cap_date", "airline", "fare", "availability_status"):
        if c not in avail_names:
            die("availability column plan lacks %r" % c)

    for name in (AVAIL_DS_NAME, COMP_DS_NAME, DEPCAP_DS_NAME):
        if cur.execute("SELECT id FROM tables WHERE table_name=?",
                       (name,)).fetchone():
            die("dataset name %r already taken" % name)

    perm_row = cur.execute(
        "SELECT id FROM ab_permission WHERE name='datasource_access'").fetchone()
    if perm_row is None:
        die("ab_permission 'datasource_access' not found")
    st["perm_id"] = perm_row[0]

    st["max_slice_id"] = cur.execute("SELECT MAX(id) FROM slices").fetchone()[0]
    st["max_table_id"] = cur.execute("SELECT MAX(id) FROM tables").fetchone()[0]

    # --- postgres feasibility ---
    if volumes is None:
        volumes, have_cols = pg_probes([
            (AVAIL_DS_NAME, st["avail_sql"]),
            (COMP_DS_NAME, st["comp_sql"]),
            (DEPCAP_DS_NAME, st["depcap_sql"])])
        st["source_cols"] = have_cols
    st["volumes"] = volumes
    assignment, new_carriers = build_carrier_assignment(volumes)
    st["assignment"], st["new_carriers"] = assignment, new_carriers
    return st


# ------------------------------------------------------------- builders --
def adapt_params(tpl_params, ds_id, label_colors, extra=None):
    p = copy.deepcopy(tpl_params)
    p["datasource"] = "%d__table" % ds_id
    p["dashboards"] = [DASH_ID]
    p["color_scheme"] = "ic_branded"
    p["label_colors"] = dict(label_colors)
    p.pop("slice_id", None)
    if extra:
        p.update(copy.deepcopy(extra))
    deep_rename(p, RENAMES)
    return p


def adapt_qc(tpl_qc, ds_id, params, slice_id, metric_override=None):
    q = copy.deepcopy(tpl_qc)
    q["datasource"] = {"id": ds_id, "type": "table"}
    if metric_override:
        by_label = {m["label"]: m for m in metric_override}
        for query in q.get("queries") or []:
            query["metrics"] = [
                copy.deepcopy(by_label.get(m.get("label"), m))
                if isinstance(m, dict) else m
                for m in (query.get("metrics") or [])]
            new_ob = []
            for entry in (query.get("orderby") or []):
                m, asc = entry
                if isinstance(m, dict) and m.get("label") in by_label:
                    m = copy.deepcopy(by_label[m["label"]])
                new_ob.append([m, asc])
            query["orderby"] = new_ob
    deep_rename(q, RENAMES)
    fd = copy.deepcopy(params)
    fd["slice_id"] = slice_id
    tpl_fd = tpl_qc.get("form_data") or {}
    for k in ("result_format", "result_type", "force"):
        if k in tpl_fd:
            fd[k] = tpl_fd[k]
    q["form_data"] = fd
    return q


def build_slice_payloads(st, ds_ids):
    """Five (key, base_slice_id, name, viz, ds_id, params) tuples.
    query_context is built later, once the slice id is known."""
    a = st["assignment"]
    bare = dict(a)
    avail_lc = dict(bare)
    avail_lc.update(laf_keys(a))
    avail_lc.update(marker_keys(a))
    comp_lc = dict(bare)
    comp_lc.update(COMPOSITION_COLORS)
    tpl = st["tpl"]
    return [
        ("avail", TPL_AVAIL, AVAIL_SLICE_NAME, "mixed_timeseries",
         ds_ids["avail"],
         adapt_params(tpl["avail"]["params_obj"], ds_ids["avail"], avail_lc)),
        ("comp", TPL_COMP, COMP_SLICE_NAME, "dist_bar",
         ds_ids["comp"],
         adapt_params(tpl["comp"]["params_obj"], ds_ids["comp"], comp_lc,
                      extra={"metrics": st["da_metrics"]})),
        ("depcap", TPL_DEPCAP, DEPCAP_SLICE_NAME, "echarts_timeseries_bar",
         ds_ids["depcap"],
         adapt_params(tpl["depcap"]["params_obj"], ds_ids["depcap"], bare)),
        ("new49", OLD_COMP_BAR, COMP_BAR_SLICE_NAME, "echarts_timeseries_bar",
         13,
         adapt_params(tpl["comp_bar"]["params_obj"], 13, bare)),
        ("new53", OLD_RECO, RECO_SLICE_NAME, "echarts_timeseries_bar",
         15,
         adapt_params(tpl["reco"]["params_obj"], 15, dict(RECO_COLORS))),
    ]


def qc_for(key, st, ds_ids, params, slice_id):
    tpl = st["tpl"]
    tpl_qc = {"avail": tpl["avail"], "comp": tpl["comp"],
              "depcap": tpl["depcap"], "new49": tpl["comp_bar"],
              "new53": tpl["reco"]}[key]["qc_obj"]
    ds_id = {"avail": ds_ids["avail"], "comp": ds_ids["comp"],
             "depcap": ds_ids["depcap"], "new49": 13, "new53": 15}[key]
    metric_override = st["da_metrics"] if key == "comp" else None
    return adapt_qc(tpl_qc, ds_id, params, slice_id,
                    metric_override=metric_override)


def build_position(st, ids):
    """ids: {key: (slice_id, uuid_str)}. Returns the new position_json dict."""
    pos = copy.deepcopy(st["pos"])

    def chart_node(nid, key, height, slice_name, extra_meta=None):
        sid, u = ids[key]
        meta = {"chartId": sid, "height": height, "sliceName": slice_name,
                "uuid": u, "width": 12}
        if extra_meta:
            meta.update(extra_meta)
        return {"children": [], "id": nid, "meta": meta, "parents": [],
                "type": "CHART"}

    # A1: availability above chart 43
    pos[N_CHART_AVAIL] = chart_node(N_CHART_AVAIL, "avail", 50, AVAIL_SLICE_NAME)
    pos[N_ROW_AVAIL] = {"children": [N_CHART_AVAIL], "id": N_ROW_AVAIL,
                        "meta": {"background": "BACKGROUND_TRANSPARENT"},
                        "parents": [], "type": "ROW"}
    pos["TAB-avgfare-0"]["children"] = [N_ROW_AVAIL, "ROW-avgfare-0"]

    # A2: composition sub-tab
    pos[N_CHART_FC] = chart_node(N_CHART_FC, "comp", 50, COMP_SLICE_NAME)
    pos[N_ROW_COMP3] = {"children": [N_CHART_FC], "id": N_ROW_COMP3,
                        "meta": {"background": "BACKGROUND_TRANSPARENT"},
                        "parents": [], "type": "ROW"}
    pos[N_TAB_COMP3] = {"children": [N_ROW_COMP3], "id": N_TAB_COMP3,
                        "meta": sub_tab_meta(TAB_COMP3_LABEL),
                        "parents": [], "type": "TAB"}
    pos["TABS-comp"]["children"] = ["TAB-comp-0", "TAB-comp-2", N_TAB_COMP3]

    # A3: velocity nested sub-tabs; chart 47's ROW-velocity moves, untouched
    pos[N_CHART_DEPCAP] = chart_node(
        N_CHART_DEPCAP, "depcap", 60, DEPCAP_SLICE_NAME,
        extra_meta={"sliceNameOverride": DEPCAP_NAME_OVERRIDE})
    pos[N_ROW_VEL1] = {"children": [N_CHART_DEPCAP], "id": N_ROW_VEL1,
                       "meta": {"background": "BACKGROUND_TRANSPARENT"},
                       "parents": [], "type": "ROW"}
    pos[N_TAB_VEL0] = {"children": ["ROW-velocity"], "id": N_TAB_VEL0,
                       "meta": sub_tab_meta(TAB_VEL0_LABEL),
                       "parents": [], "type": "TAB"}
    pos[N_TAB_VEL1] = {"children": [N_ROW_VEL1], "id": N_TAB_VEL1,
                       "meta": sub_tab_meta(TAB_VEL1_LABEL),
                       "parents": [], "type": "TAB"}
    pos[N_TABS_VEL] = {"children": [N_TAB_VEL0, N_TAB_VEL1], "id": N_TABS_VEL,
                       "meta": {}, "parents": [], "type": "TABS"}
    pos["TAB-jyNav5"]["children"] = [N_TABS_VEL]

    # B: swaps -- same nodes, chartId/uuid updated (headers already canonical)
    pos["CHART-jy-49"]["meta"]["chartId"] = ids["new49"][0]
    pos["CHART-jy-49"]["meta"]["uuid"] = ids["new49"][1]
    pos["CHART-jy-53"]["meta"]["chartId"] = ids["new53"][0]
    pos["CHART-jy-53"]["meta"]["uuid"] = ids["new53"][1]

    rewrite_parents(pos)
    return pos


def build_metadata(st, ids):
    jm = copy.deepcopy(st["jm"])
    swap = {OLD_COMP_BAR: ids["new49"][0], OLD_RECO: ids["new53"][0]}
    avail_id = ids["avail"][0]

    def swapped(lst):
        return [swap.get(x, x) for x in (lst or [])]

    for f in jm.get("native_filter_configuration") or []:
        cis = swapped(f.get("chartsInScope"))
        exc = swapped((f.get("scope") or {}).get("excluded"))
        # availability chart mirrors chart 43's memberships (dash-6 pattern)
        if 43 in cis:
            cis.append(avail_id)
        elif 43 in exc:
            exc.append(avail_id)
        if f.get("chartsInScope") is not None:
            f["chartsInScope"] = cis
        if f.get("scope") is not None:
            f["scope"]["excluded"] = exc

    gcc = jm.get("global_chart_configuration")
    if gcc:
        gcc["chartsInScope"] = swapped(gcc.get("chartsInScope")) + [
            ids["avail"][0], ids["comp"][0], ids["depcap"][0]]

    cc = jm.get("chart_configuration") or {}
    for entry in cc.values():
        xf = entry.get("crossFilters") if isinstance(entry, dict) else None
        if isinstance(xf, dict):
            xf["chartsInScope"] = swapped(xf.get("chartsInScope"))
    linked_after = sorted(
        (set(st["linked"]) - {OLD_COMP_BAR, OLD_RECO})
        | {ids[k][0] for k in ("avail", "comp", "depcap", "new49", "new53")})
    # dash 6 carries cross-filter entries for its availability + composition
    # charts (109/107) but not deployed capacity (110) -- mirrored here
    for key in ("avail", "comp"):
        sid = ids[key][0]
        cc[str(sid)] = {"id": sid, "crossFilters": {
            "scope": "global",
            "chartsInScope": [x for x in linked_after if x != sid]}}
    jm["chart_configuration"] = cc

    lc = jm.get("label_colors") or {}
    added = []
    for k, v in dash_new_keys(st["assignment"]).items():
        if k not in lc:          # additive: existing keys always win
            lc[k] = v
            added.append(k)
    jm["label_colors"] = lc
    return jm, added


def dataset_specs(st):
    """(key, name, sql, main_dttm_col, description, column_plan, add_count)"""
    def clone_cols(ds):
        return [(c["column_name"], c["type"], c["is_dttm"],
                 c.get("expression") or None, c.get("description") or None)
                for c in ds["columns"]]
    ds38_desc = st["ds38_row"].get("description")
    depcap_desc = (ds38_desc.replace("WinAir", "interCaribbean")
                   if ds38_desc else None)
    return [
        ("avail", AVAIL_DS_NAME, st["avail_sql"], "travel_date",
         AVAIL_DS_DESCRIPTION,
         [(n, t, d, e, None) for n, t, d, e in AVAIL_COLUMNS], False),
        ("comp", COMP_DS_NAME, st["comp_sql"], "travel_date",
         COMP_DS_DESCRIPTION, clone_cols(st["ds32_row"]), True),
        ("depcap", DEPCAP_DS_NAME, st["depcap_sql"], "travel_date",
         depcap_desc, clone_cols(st["ds38_row"]), False),
    ]


# ------------------------------------------------------------------ show --
def show(con):
    cur = con.cursor()
    print("dashboard %d survey (%s UTC)" % (DASH_ID, _now()))
    print("backup table %s present: %s" % (BACKUP_TABLE, backup_exists(con)))
    row = cur.execute(
        "SELECT position_json, json_metadata FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()
    pos, jm = json.loads(row[0]), json.loads(row[1] or "{}")
    print("layout validate: %s" % (validate(pos) or "0 problems"))
    for tab in pos.get("TABS-jyTopNav", {}).get("children", []):
        n = pos.get(tab) or {}
        print("  %s %r children=%s" % (tab, (n.get("meta") or {}).get("text"),
                                       n.get("children")))
    print("  TAB-avgfare-0 children: %s" % pos.get("TAB-avgfare-0", {}).get("children"))
    print("  TABS-comp children:     %s" % pos.get("TABS-comp", {}).get("children"))
    print("  TAB-jyNav5 children:    %s" % pos.get("TAB-jyNav5", {}).get("children"))
    linked = sorted(r[0] for r in cur.execute(
        "SELECT slice_id FROM dashboard_slices WHERE dashboard_id=?", (DASH_ID,)))
    print("linked slices: %s" % linked)
    for sid in sorted(EXPECTED_TITLES):
        r = cur.execute("SELECT slice_name, viz_type, datasource_id FROM slices "
                        "WHERE id=?", (sid,)).fetchone()
        ok = "OK " if (r and r[0] == EXPECTED_TITLES[sid]) else "DRIFT"
        print("  %s slice %-3d %-45r viz=%-24s ds=%s" % (ok, sid, r and r[0],
                                                         r and r[1], r and r[2]))
    print("label_colors keys on dash %d: %d"
          % (DASH_ID, len(jm.get("label_colors") or {})))
    for name in (AVAIL_DS_NAME, COMP_DS_NAME, DEPCAP_DS_NAME):
        taken = cur.execute("SELECT id FROM tables WHERE table_name=?",
                            (name,)).fetchone()
        print("dataset name %-36s %s" % (name, "TAKEN id=%s" % taken[0]
                                         if taken else "free"))
    ds36 = dataset_column_names(cur, 36)
    print("ds36 has availability_status: %s  (False => create new dataset)"
          % ("availability_status" in ds36))
    # pre-existing quirk, deliberately untouched
    stale = set()
    for f in jm.get("native_filter_configuration") or []:
        for lst in (f.get("chartsInScope") or [],
                    (f.get("scope") or {}).get("excluded") or []):
            stale |= {x for x in lst if x not in linked}
    if stale:
        print("note: filter lists reference off-dashboard slice ids %s "
              "(pre-existing; left untouched)" % sorted(stale))


# --------------------------------------------------------------- dry-run --
def print_plan(st, ds_ids, ids, slice_payloads, new_pos, new_jm, added_keys):
    print("PLAN (WM-canonical backfill of dashboard %d)" % DASH_ID)
    print("- carriers by volume (comp_tot_fare>0):")
    for code, n in st["volumes"]:
        tag = "existing hex" if code in JY_CARRIERS else "NEW -> fallback"
        print("    %-4s %10d rows  %s (%s)"
              % (code, n, st["assignment"].get(code), tag))
    if st["new_carriers"]:
        print("    new carriers taking fallback slots: %s" % st["new_carriers"])
    print("- datasets to create:")
    for key, name, sql, dttm, _desc, cols, add_count in dataset_specs(st):
        print("    ds %-3s %-36s cols=%d main_dttm=%s count_metric=%s"
              % (ds_ids[key], name, len(cols), dttm, add_count))
    print("- slices to create:")
    for key, base, name, viz, ds_id, params in slice_payloads:
        print("    slice %-3s %-52r viz=%-24s ds=%-3s (template base slice %d)"
              % (ids[key][0], name, viz, ds_id, base))
    print("- swaps: 49 -> %d, 53 -> %d (old slices parked intact, unlinked)"
          % (ids["new49"][0], ids["new53"][0]))
    print("- layout: +%s above chart 43; +%s sub-tab; Velocity tab -> nested "
          "sub-tabs %r / %r" % (N_CHART_AVAIL, N_TAB_COMP3,
                                TAB_VEL0_LABEL, TAB_VEL1_LABEL))
    print("- label_colors: %d new keys added to dash metadata (additive)"
          % len(added_keys))
    print("- post-edit layout validation: %s" % (validate(new_pos) or "0 problems"))
    # metadata sanity
    fcount = sum(1 for f in new_jm.get("native_filter_configuration") or []
                 if ids["avail"][0] in (f.get("chartsInScope") or []))
    xcount = sum(1 for f in new_jm.get("native_filter_configuration") or []
                 if ids["avail"][0] in ((f.get("scope") or {}).get("excluded") or []))
    print("- availability chart joins %d filter scopes (+%d excluded), "
          "mirroring chart 43" % (fcount, xcount))
    leftovers = []
    for f in new_jm.get("native_filter_configuration") or []:
        if OLD_COMP_BAR in (f.get("chartsInScope") or []) or \
           OLD_RECO in (f.get("chartsInScope") or []) or \
           OLD_COMP_BAR in ((f.get("scope") or {}).get("excluded") or []) or \
           OLD_RECO in ((f.get("scope") or {}).get("excluded") or []):
            leftovers.append(f.get("id"))
    print("- filters still referencing 49/53 after swap: %s"
          % (leftovers or "none"))
    print("- gcc chartsInScope after: %s"
          % (new_jm.get("global_chart_configuration") or {}).get("chartsInScope"))
    # every payload must serialize
    for key, _b, _n, _v, _d, params in slice_payloads:
        json.dumps(params)
        json.dumps(qc_for(key, st, ds_ids, params, ids[key][0]))
    json.dumps(new_pos)
    json.dumps(new_jm)
    print("- all params/query_context/position/metadata payloads serialize OK")


def dry_run(con):
    cur = con.cursor()
    st = plan(cur)
    # provisional ids (autoincrement will assign the real ones on --apply)
    ds_ids = {"avail": st["max_table_id"] + 1, "comp": st["max_table_id"] + 2,
              "depcap": st["max_table_id"] + 3}
    order = ["avail", "comp", "depcap", "new49", "new53"]
    ids = {k: (st["max_slice_id"] + 1 + i, str(uuidlib.uuid4()))
           for i, k in enumerate(order)}
    slice_payloads = build_slice_payloads(st, ds_ids)
    new_pos = build_position(st, ids)
    problems = validate(new_pos)
    new_jm, added_keys = build_metadata(st, ids)
    print_plan(st, ds_ids, ids, slice_payloads, new_pos, new_jm, added_keys)
    if problems:
        die("post-edit layout validation FAILED: %s" % problems)
    print("DRY-RUN COMPLETE: no DML executed, nothing written. Ids shown are "
          "provisional (max+1..); --apply assigns real ones and re-asserts "
          "state under the write lock.")
    return 0


# ----------------------------------------------------------------- apply --
def take_file_backup(con):
    bak = "%s.bak.%s_IST.%s" % (DB, _ist_stamp(), BAK_TAG)
    dst = sqlite3.connect(bak)
    try:
        con.backup(dst)
    finally:
        dst.close()
    print("full DB backup: %s" % bak)


def _bk(cur, kind, ref, payload):
    cur.execute("INSERT INTO %s VALUES (?,?,?)" % BACKUP_TABLE,
                (kind, str(ref), json.dumps(payload)))


def insert_dataset(cur, st, name, sql, main_dttm, description, cols, add_count):
    tpl = st["ds37_row"]
    now = _now()
    row = {
        "created_on": now, "changed_on": now, "table_name": name,
        "main_dttm_col": main_dttm, "default_endpoint": None,
        "database_id": tpl["database_id"], "created_by_fk": 1,
        "changed_by_fk": 1, "offset": 0, "description": description,
        "is_featured": 0, "cache_timeout": None, "schema": tpl["schema"],
        "sql": sql, "params": None, "perm": None,
        "filter_select_enabled": 1, "fetch_values_predicate": None,
        "is_sqllab_view": 0, "template_params": None,
        "schema_perm": tpl["schema_perm"], "extra": None,
        "uuid": uuidlib.uuid4().bytes, "is_managed_externally": 0,
        "external_url": None, "normalize_columns": 0,
        "always_filter_main_dttm": 0,
    }
    keys = list(row)
    cur.execute("INSERT INTO tables (%s) VALUES (%s)"
                % (",".join(keys), ",".join("?" * len(keys))),
                [row[k] for k in keys])
    ds_id = cur.lastrowid
    perm = "[CPI PostgreSQL].[%s](id:%d)" % (name, ds_id)
    cur.execute("UPDATE tables SET perm=? WHERE id=?", (perm, ds_id))
    _bk(cur, "created_dataset", ds_id, {"name": name})
    for cname, ctype, is_dttm, expression, cdesc in cols:
        crow = {
            "created_on": now, "changed_on": now, "table_id": ds_id,
            "column_name": cname, "is_dttm": is_dttm, "is_active": 1,
            "type": ctype, "groupby": 1, "filterable": 1,
            "description": cdesc, "created_by_fk": 1, "changed_by_fk": 1,
            "expression": expression, "verbose_name": None,
            "python_date_format": None, "uuid": uuidlib.uuid4().bytes,
            "extra": None, "advanced_data_type": None,
        }
        ck = list(crow)
        cur.execute("INSERT INTO table_columns (%s) VALUES (%s)"
                    % (",".join(ck), ",".join("?" * len(ck))),
                    [crow[k] for k in ck])
        _bk(cur, "created_column", cur.lastrowid, {"table_id": ds_id,
                                                   "name": cname})
    if add_count:
        mrow = {
            "created_on": now, "changed_on": now, "metric_name": "count",
            "verbose_name": "COUNT(*)", "metric_type": "count",
            "table_id": ds_id, "expression": "COUNT(*)", "description": None,
            "created_by_fk": 1, "changed_by_fk": 1, "d3format": None,
            "warning_text": None, "extra": None,
            "uuid": uuidlib.uuid4().bytes, "currency": None,
        }
        mk = list(mrow)
        cur.execute("INSERT INTO sql_metrics (%s) VALUES (%s)"
                    % (",".join(mk), ",".join("?" * len(mk))),
                    [mrow[k] for k in mk])
        _bk(cur, "created_metric", cur.lastrowid, {"table_id": ds_id})
    cur.execute("INSERT INTO ab_view_menu (name) VALUES (?)", (perm,))
    vm_id = cur.lastrowid
    _bk(cur, "created_view_menu", vm_id, {"name": perm})
    cur.execute("INSERT INTO ab_permission_view (permission_id, view_menu_id) "
                "VALUES (?,?)", (st["perm_id"], vm_id))
    _bk(cur, "created_permission_view", cur.lastrowid, {"view_menu": perm})
    print("  dataset %d %s (%d columns%s)"
          % (ds_id, name, len(cols), ", +count metric" if add_count else ""))
    return ds_id, perm


def insert_slice(cur, base_slice_id, name, viz, ds_id, ds_perm, params):
    cols = [r[1] for r in cur.execute("PRAGMA table_info(slices)")]
    src = dict(zip(cols, cur.execute(
        "SELECT %s FROM slices WHERE id=?" % ",".join(cols),
        (base_slice_id,)).fetchone()))
    new_uuid = uuidlib.uuid4()
    row = dict(src)
    row.pop("id")
    now = _now()
    row.update({
        "slice_name": name, "viz_type": viz,
        "datasource_id": ds_id, "datasource_type": "table",
        "params": json.dumps(params), "query_context": None,
        "uuid": new_uuid.bytes, "created_on": now, "changed_on": now,
        "last_saved_at": None, "last_saved_by_fk": None,
        "description": None,
    })
    if ds_perm is not None:
        row["perm"] = ds_perm
        row["datasource_name"] = "public.%s" % ds_perm.split("[")[2].split("]")[0]
    keys = list(row)
    cur.execute("INSERT INTO slices (%s) VALUES (%s)"
                % (",".join(keys), ",".join("?" * len(keys))),
                [row[k] for k in keys])
    return cur.lastrowid, str(new_uuid)


def apply(con):
    cur = con.cursor()
    # plan + pg probes BEFORE the lock (round-trips must not hold it) ...
    st0 = plan(cur)
    # ... file backup outside any transaction (backup API requirement) ...
    take_file_backup(con)
    # ... then re-read + re-assert EVERYTHING under the write lock.
    cur.execute("BEGIN IMMEDIATE")
    st = plan(cur, volumes=st0["volumes"])

    cur.execute("CREATE TABLE %s (kind TEXT, ref TEXT, payload TEXT)"
                % BACKUP_TABLE)
    _bk(cur, "dash_row", DASH_ID,
        {"position_json": st["pos_raw"], "json_metadata": st["jm_raw"]})

    print("creating datasets:")
    ds_ids, ds_perms = {}, {}
    for key, name, sql, dttm, desc, cols, add_count in dataset_specs(st):
        ds_ids[key], ds_perms[key] = insert_dataset(
            cur, st, name, sql, dttm, desc, cols, add_count)

    print("creating slices:")
    ids = {}
    for key, base, name, viz, ds_id, params in build_slice_payloads(st, ds_ids):
        perm = ds_perms.get(key)  # swaps keep the base slice's own perm fields
        sid, u = insert_slice(cur, base, name, viz, ds_id, perm, params)
        p = dict(params)
        p["slice_id"] = sid
        qc = qc_for(key, st, ds_ids, params, sid)
        qc["form_data"]["slice_id"] = sid
        cur.execute("UPDATE slices SET params=?, query_context=? WHERE id=?",
                    (json.dumps(p), json.dumps(qc), sid))
        ids[key] = (sid, u)
        _bk(cur, "created_slice", sid, {"name": name})
        print("  slice %d %r viz=%s ds=%s" % (sid, name, viz, ds_id))

    # dashboard_slices: unlink the two old dist_bars, link the five new charts
    for old in (OLD_COMP_BAR, OLD_RECO):
        cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND "
                    "slice_id=?", (DASH_ID, old))
        _bk(cur, "removed_link", old, {"dashboard_id": DASH_ID, "slice_id": old})
    for key in ("avail", "comp", "depcap", "new49", "new53"):
        cur.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) "
                    "VALUES (?,?)", (DASH_ID, ids[key][0]))
        _bk(cur, "added_link", ids[key][0], {})
    print("dashboard_slices: %d/%d out, %s in"
          % (OLD_COMP_BAR, OLD_RECO, sorted(v[0] for v in ids.values())))

    new_pos = build_position(st, ids)
    problems = validate(new_pos)
    if problems:
        raise RuntimeError("post-edit layout INVALID (rolling back): %s"
                           % problems)
    new_jm, added_keys = build_metadata(st, ids)
    cur.execute("UPDATE dashboards SET position_json=?, json_metadata=?, "
                "changed_on=? WHERE id=?",
                (json.dumps(new_pos), json.dumps(new_jm), _now(), DASH_ID))
    if cur.rowcount != 1:
        raise RuntimeError("dashboards update rowcount %d" % cur.rowcount)
    print("layout: validated, 0 problems; label_colors: %d keys added"
          % len(added_keys))

    con.commit()
    print("COMMITTED")

    after = json.loads(cur.execute(
        "SELECT position_json FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()[0])
    post = validate(after)
    if post:
        raise RuntimeError("POST-COMMIT VALIDATION FAILED: %s -- run --revert"
                           % post)
    print("post-commit: re-read and re-validated, 0 problems")
    print("APPLIED. New: avail=%d comp=%d depcap=%d; swaps 49->%d 53->%d; "
          "old 49/53 parked intact." % (ids["avail"][0], ids["comp"][0],
                                        ids["depcap"][0], ids["new49"][0],
                                        ids["new53"][0]))
    return 0


# ---------------------------------------------------------------- revert --
def revert(con):
    if not backup_exists(con):
        print("no backup table %s -- nothing to revert." % BACKUP_TABLE)
        return 1
    cur = con.cursor()
    cur.execute("BEGIN IMMEDIATE")
    rows = list(cur.execute("SELECT kind, ref, payload FROM %s" % BACKUP_TABLE))
    by_kind = {}
    for kind, ref, payload in rows:
        by_kind.setdefault(kind, []).append((ref, json.loads(payload)))

    for ref, _p in by_kind.get("created_permission_view", []):
        cur.execute("DELETE FROM ab_permission_view WHERE id=?", (int(ref),))
    for ref, _p in by_kind.get("created_view_menu", []):
        cur.execute("DELETE FROM ab_view_menu WHERE id=?", (int(ref),))
    for ref, _p in by_kind.get("added_link", []):
        cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id=? AND "
                    "slice_id=?", (DASH_ID, int(ref)))
    for ref, _p in by_kind.get("created_slice", []):
        if int(ref) in UNTOUCHABLE_SLICES:
            raise RuntimeError("refusing to delete untouchable slice %s" % ref)
        cur.execute("DELETE FROM slices WHERE id=?", (int(ref),))
    for ref, _p in by_kind.get("created_metric", []):
        cur.execute("DELETE FROM sql_metrics WHERE id=?", (int(ref),))
    for ref, _p in by_kind.get("created_column", []):
        cur.execute("DELETE FROM table_columns WHERE id=?", (int(ref),))
    for ref, _p in by_kind.get("created_dataset", []):
        if int(ref) in UNTOUCHABLE_DATASETS:
            raise RuntimeError("refusing to delete untouchable dataset %s" % ref)
        cur.execute("DELETE FROM tables WHERE id=?", (int(ref),))
    for _ref, p in by_kind.get("removed_link", []):
        cur.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) "
                    "VALUES (?,?)", (p["dashboard_id"], p["slice_id"]))
    for _ref, p in by_kind.get("dash_row", []):
        cur.execute("UPDATE dashboards SET position_json=?, json_metadata=?, "
                    "changed_on=? WHERE id=?",
                    (p["position_json"], p["json_metadata"], _now(), DASH_ID))
    cur.execute("DROP TABLE %s" % BACKUP_TABLE)
    con.commit()

    pos = json.loads(cur.execute(
        "SELECT position_json FROM dashboards WHERE id=?",
        (DASH_ID,)).fetchone()[0])
    print("reverted %d backup entries; layout validate: %s"
          % (len(rows), validate(pos) or "0 problems"))
    print("(the full .bak file from --apply is untouched -- nuclear option)")
    return 0


# ------------------------------------------------------------------ main --
def main():
    ap = argparse.ArgumentParser(
        description="Backfill JY dashboard 1 to the canonical WinAir shape")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--show", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.show or args.dry_run:
        # genuinely read-only modes get a genuinely read-only connection
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)
    else:
        con = sqlite3.connect(DB, isolation_level=None, timeout=30)
    try:
        if args.show:
            show(con)
            return 0
        if args.dry_run:
            return dry_run(con)
        if args.revert:
            return revert(con)
        return apply(con)
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("parity_jy_backfill FAILED (rolled back): %s" % e)
        sys.exit(1)
