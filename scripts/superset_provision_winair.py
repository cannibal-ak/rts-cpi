#!/usr/bin/env python
"""Provision the WinAir (WM) Superset dashboard by cloning JY — PRICING ONLY.

Adapted from scripts/superset_provision_altitude.py. WM has NO velocity data,
so this clone:
  * DROPS slice 47 (velocity mixed_timeseries) + dataset 14 (jy_velocity_normalized)
  * STRIPS the velocity CTE/LEFT JOIN from the pricing-recommendations dataset
    (ds 15 -> 33): recommendations become price-gap-only; the velocity-derived
    columns (load_factor, load_bucket, current_booking, capacity) are removed
  * clones the remaining 9 JY slices -> WM slices 94..102
  * clones 3 datasets: ds 3->31 (physical vw_airline_cpi_wm_snapshot),
    13->32 (wm_all_airlines_fares), 15->33 (wm_pricing_recommendations)
  * builds WM dashboard id 6 (slug airline-cpi-wm), rts_cpi_palette + WM colors
  * inserts a fresh embedded_dashboards row

Idempotent guard: aborts if a 'wm_all_airlines_fares' dataset already exists.
One transaction; commit only if every assertion passes.
"""
import sqlite3
import json
import uuid
import datetime

DB = "/app/superset_home/superset.db"

# ── Explicit new ids (current maxima: dash 5, tables 30, slices 93) ──
DSMAP = {3: 31, 13: 32, 15: 33}                 # old JY dataset id -> new WM id (NO 14)
DSNAME = {
    31: "vw_airline_cpi_wm_snapshot",
    32: "wm_all_airlines_fares",
    33: "wm_pricing_recommendations",
}
NEWDASH = 6
WM_SLICES = [43, 46, 48, 49, 50, 51, 52, 53, 55]            # NO 47
SLICEMAP = {old: 94 + i for i, old in enumerate(WM_SLICES)}  # -> 94..102
SLICE_DS = {43: 13, 46: 13, 48: 15, 49: 13, 50: 13,
            51: 13, 52: 13, 53: 15, 55: 13}

JY_CARRIERS = {"JY", "BW", "WM", "9Q", "5L", "PY", "DO", "S6", "7Z", "DM"}
# WM host in WinAir brand red + competitors spaced around it (CVD-validated,
# 2026-08-17 rebrand). MUST match KNOWN_AIRLINE_COLORS in
# apps/web/src/components/dashboard/winair/priceChartTheme.ts — the native
# Latest Prices chart and these Superset charts share the palette.
WM_COLORS = {"WM": "#CD1F25", "5L": "#1BAF7A", "7Z": "#8B5CF6", "BW": "#C08A00",
             "DM": "#0891B2", "Exp": "#A05A2C", "Expedia": "#A05A2C",
             "JY": "#2A78D6", "S6": "#D6208F"}
WM_DOMAIN = ["#CD1F25", "#1BAF7A", "#8B5CF6", "#C08A00", "#0891B2", "#A05A2C",
             "#2A78D6", "#D6208F", "#64748B", "#0070C0"]

# velocity-derived columns dropped from the reco dataset + reco slices
DROP_COLS = {"load_factor", "load_bucket", "current_booking", "capacity"}

# ── velocity-stripped pricing-recommendations SQL (ds 33) ──
RECO_SQL_WM = """WITH ranked_competitors AS (
  SELECT
    CONCAT(ref_org, ' → ', ref_dst) AS route,
    ref_org AS origin, ref_dst AS destination,
    ref_dep_date, cap_date, trip_type,
    ref_via AS via, ref_tot_fare AS wm_price,
    comp_al, comp_tot_fare,
    ROW_NUMBER() OVER (
      PARTITION BY ref_org, ref_dst, ref_dep_date, trip_type, cap_date
      ORDER BY comp_tot_fare ASC
    ) AS rn
  FROM vw_airline_cpi_wm_snapshot WHERE comp_tot_fare > 0
),
lowest_comp AS (
  SELECT route, origin, destination, ref_dep_date, cap_date, trip_type, via,
         wm_price, comp_al AS lowest_competitor, comp_tot_fare AS lowest_comp_price,
         CASE WHEN comp_tot_fare > 0
              THEN ROUND(((wm_price - comp_tot_fare)/comp_tot_fare*100)::numeric, 1)
              ELSE 0 END AS price_gap_pct
  FROM ranked_competitors WHERE rn = 1
)
SELECT route, ref_dep_date, cap_date, trip_type, via, origin, destination,
  ROUND(wm_price::numeric, 2) AS wm_price,
  ROUND(lowest_comp_price::numeric, 2) AS lowest_comp_price,
  lowest_competitor, price_gap_pct,
  CASE WHEN price_gap_pct > 5 THEN 'Overpriced'
       WHEN price_gap_pct < -5 THEN 'Underpriced'
       ELSE 'Aligned' END AS price_status,
  CASE WHEN price_gap_pct > 15 THEN 'Reduce'
       WHEN price_gap_pct > 5 THEN 'Monitor'
       WHEN price_gap_pct >= -5 THEN 'No Change'
       ELSE 'Consider Increase' END AS recommendation,
  ROUND((lowest_comp_price - wm_price)::numeric, 2) AS recommended_change_usd
FROM lowest_comp"""

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
c = con.cursor()


def now():
    return datetime.datetime.utcnow().isoformat(sep=" ")


def fix_label_colors(d):
    out = {k: v for k, v in d.items() if k not in JY_CARRIERS}
    out.update(WM_COLORS)
    return out


def mapslices(lst):
    return [SLICEMAP[x] for x in lst if isinstance(x, int) and x in SLICEMAP]


def remap(o, newslice):
    if isinstance(o, dict):
        for k in list(o.keys()):
            v = o[k]
            if k == "datasource" and isinstance(v, str) and v.endswith("__table"):
                o[k] = "%d__table" % DSMAP[int(v.split("__")[0])]
            elif k == "datasource" and isinstance(v, dict) and "id" in v:
                v["id"] = DSMAP.get(v["id"], v["id"])
                remap(v, newslice)
            elif k == "dashboards" and isinstance(v, list):
                o[k] = [NEWDASH]
            elif k == "slice_id":
                o[k] = newslice
            elif k == "label_colors" and isinstance(v, dict):
                o[k] = fix_label_colors(v)
            else:
                remap(v, newslice)
    elif isinstance(o, list):
        for x in o:
            remap(x, newslice)


def strip_velocity_cols(fd):
    """Remove velocity-derived columns from a table/dist_bar form_data."""
    if isinstance(fd.get("all_columns"), list):
        fd["all_columns"] = [x for x in fd["all_columns"] if x not in DROP_COLS]
    if isinstance(fd.get("column_config"), dict):
        fd["column_config"] = {k: v for k, v in fd["column_config"].items() if k not in DROP_COLS}
    for key in ("columns", "groupby"):
        if isinstance(fd.get(key), list):
            fd[key] = [x for x in fd[key] if not (isinstance(x, str) and x in DROP_COLS)]


def clone_row(table, src_id, new_id, overrides):
    row = dict(c.execute("SELECT * FROM %s WHERE id=?" % table, (src_id,)).fetchone())
    row["id"] = new_id
    if "uuid" in row and "uuid" not in overrides:
        row["uuid"] = uuid.uuid4().bytes
    row.update(overrides)
    cols = list(row.keys())
    c.execute("INSERT INTO %s (%s) VALUES (%s)" % (
        table, ",".join(cols), ",".join(["?"] * len(cols))),
        [row[k] for k in cols])


def main():
    # ── idempotent guard ──
    if c.execute("SELECT 1 FROM tables WHERE table_name='wm_all_airlines_fares'").fetchone():
        print("ABORT: WM datasets already exist. Restore from backup to re-run.")
        return

    # ── build + PRINT the substituted virtual SQL (for review) ──
    sql13 = c.execute("SELECT sql FROM tables WHERE id=13").fetchone()[0]

    s32 = sql13.replace("'JY' AS airline", "'WM' AS airline") \
               .replace("vw_airline_cpi_jy_snapshot", "vw_airline_cpi_wm_snapshot")
    assert "'WM' AS airline" in s32 and s32.count("vw_airline_cpi_wm_snapshot") == 2 \
        and "vw_airline_cpi_jy_snapshot" not in s32, "fares SQL substitution failed"

    s33 = RECO_SQL_WM
    assert "vw_airline_cpi_wm_snapshot" in s33 and "vw_velocity" not in s33 \
        and "jy_price" not in s33 and "wm_price" in s33 and "_jy_" not in s33 \
        and "load_factor" not in s33 and "current_booking" not in s33, "reco SQL build failed"

    print("=" * 72)
    print("SUBSTITUTED SQL -> wm_all_airlines_fares (id 32):\n" + s32)
    print("-" * 72)
    print("VELOCITY-STRIPPED SQL -> wm_pricing_recommendations (id 33):\n" + s33)
    print("=" * 72)

    SQLBY = {32: s32, 33: s33}

    # ── 1. datasets (tables) ──
    for old, new in DSMAP.items():
        name = DSNAME[new]
        ov = {"table_name": name,
              "perm": "[CPI PostgreSQL].[%s](id:%d)" % (name, new),
              "schema_perm": "[CPI PostgreSQL].[public]",
              "sql": None if new == 31 else SQLBY[new]}
        clone_row("tables", old, new, ov)

    # ── 2. table_columns + sql_metrics for each dataset ──
    tc_id = c.execute("SELECT max(id) FROM table_columns").fetchone()[0]
    m_id = c.execute("SELECT max(id) FROM sql_metrics").fetchone()[0]
    for old, new in DSMAP.items():
        for col in c.execute("SELECT * FROM table_columns WHERE table_id=?", (old,)).fetchall():
            d = dict(col)
            cname = d["column_name"]
            if old == 15:
                if cname in DROP_COLS:
                    continue                       # drop velocity columns from reco
                if cname == "jy_price":
                    d["column_name"] = "wm_price"
            tc_id += 1
            d["id"] = tc_id
            d["table_id"] = new
            d["uuid"] = uuid.uuid4().bytes
            cols = list(d.keys())
            c.execute("INSERT INTO table_columns (%s) VALUES (%s)" % (
                ",".join(cols), ",".join(["?"] * len(cols))), [d[k] for k in cols])
        for met in c.execute("SELECT * FROM sql_metrics WHERE table_id=?", (old,)).fetchall():
            m_id += 1
            d = dict(met)
            d["id"] = m_id
            d["table_id"] = new
            d["uuid"] = uuid.uuid4().bytes
            cols = list(d.keys())
            c.execute("INSERT INTO sql_metrics (%s) VALUES (%s)" % (
                ",".join(cols), ",".join(["?"] * len(cols))), [d[k] for k in cols])

    # ── 3. dashboard (insert now; position/json_metadata updated after slices) ──
    dash_uuid = uuid.uuid4()
    clone_row("dashboards", 1, NEWDASH, {
        "dashboard_title": "Airline CPI WM Dashboard",
        "slug": "airline-cpi-wm",
        "uuid": dash_uuid.bytes,
        "published": 1,
    })

    # ── 4. slices ──
    slice_uuid_str = {}
    for old in WM_SLICES:
        new = SLICEMAP[old]
        newds = DSMAP[SLICE_DS[old]]
        newname = DSNAME[newds]
        su = uuid.uuid4()
        slice_uuid_str[old] = str(su)
        src = dict(c.execute("SELECT * FROM slices WHERE id=?", (old,)).fetchone())
        params = json.loads(src["params"])
        remap(params, new)
        if SLICE_DS[old] == 15:
            strip_velocity_cols(params)
        params_s = json.dumps(params).replace("jy_price", "wm_price").replace("ic_branded", "rts_cpi_palette")
        qc_s = None
        if src["query_context"]:
            qc = json.loads(src["query_context"])
            remap(qc, new)
            if SLICE_DS[old] == 15:
                if isinstance(qc.get("form_data"), dict):
                    strip_velocity_cols(qc["form_data"])
                for qd in qc.get("queries", []):
                    if isinstance(qd.get("columns"), list):
                        qd["columns"] = [x for x in qd["columns"]
                                         if not (isinstance(x, str) and x in DROP_COLS)]
            qc_s = json.dumps(qc).replace("jy_price", "wm_price").replace("ic_branded", "rts_cpi_palette")
        clone_row("slices", old, new, {
            "uuid": su.bytes,
            "datasource_id": newds,
            "datasource_name": "public.%s" % newname,
            "perm": "[CPI PostgreSQL].[%s](id:%d)" % (newname, newds),
            "schema_perm": "[CPI PostgreSQL].[public]",
            "params": params_s,
            "query_context": qc_s,
        })

    # ── 5. dashboard_slices links ──
    for old in WM_SLICES:
        c.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                  (NEWDASH, SLICEMAP[old]))

    # ── 6. position_json: drop the velocity row+chart, remap the rest ──
    pos = json.loads(c.execute("SELECT position_json FROM dashboards WHERE id=1").fetchone()[0])
    pos.pop("CHART-jy-47", None)
    pos.pop("ROW-velocity", None)
    if "GRID_ID" in pos and isinstance(pos["GRID_ID"].get("children"), list):
        pos["GRID_ID"]["children"] = [x for x in pos["GRID_ID"]["children"] if x != "ROW-velocity"]
    for k, node in pos.items():
        if isinstance(node, dict) and node.get("type") == "CHART":
            m = node["meta"]
            old = m["chartId"]
            m["chartId"] = SLICEMAP[old]
            m["uuid"] = slice_uuid_str[old]
        if k == "HEADER_ID":
            node["meta"]["text"] = "Airline CPI WM Dashboard"
    assert "CHART-jy-47" not in pos and "ROW-velocity" not in pos, "velocity layout not removed"

    # ── 7. json_metadata remap ──
    jm = json.loads(c.execute("SELECT json_metadata FROM dashboards WHERE id=1").fetchone()[0])
    jm["label_colors"] = fix_label_colors(jm.get("label_colors", {}))
    jm["shared_label_colors"] = {}
    jm["color_scheme"] = "rts_cpi_palette"
    jm["color_scheme_domain"] = WM_DOMAIN
    for f in jm.get("native_filter_configuration", []):
        for t in f.get("targets", []):
            if "datasetId" in t:
                t["datasetId"] = DSMAP.get(t["datasetId"], t["datasetId"])
        if "chartsInScope" in f:
            f["chartsInScope"] = mapslices(f["chartsInScope"])
        sc = f.get("scope", {})
        if "excluded" in sc:
            sc["excluded"] = mapslices(sc["excluded"])
    gc = jm.get("global_chart_configuration", {})
    if "chartsInScope" in gc:
        gc["chartsInScope"] = mapslices(gc["chartsInScope"])
    if "scope" in gc and "excluded" in gc["scope"]:
        gc["scope"]["excluded"] = mapslices(gc["scope"]["excluded"])
    cc = jm.get("chart_configuration", {})
    newcc = {}
    for k, v in cc.items():
        if int(k) not in SLICEMAP:                 # drops slice 47's config
            continue
        if "id" in v:
            v["id"] = SLICEMAP[v["id"]]
        cf = v.get("crossFilters", {})
        if isinstance(cf.get("chartsInScope"), list):
            cf["chartsInScope"] = mapslices(cf["chartsInScope"])
        newcc[str(SLICEMAP[int(k)])] = v
    jm["chart_configuration"] = newcc

    c.execute("UPDATE dashboards SET position_json=?, json_metadata=? WHERE id=?",
              (json.dumps(pos), json.dumps(jm), NEWDASH))

    # ── 8. embedded_dashboards ──
    emb_uuid = uuid.uuid4()
    c.execute("INSERT INTO embedded_dashboards "
              "(created_on, changed_on, allow_domain_list, uuid, dashboard_id, created_by_fk, changed_by_fk) "
              "VALUES (?,?,?,?,?,?,?)",
              (now(), now(), "", emb_uuid.bytes, NEWDASH, 1, 1))

    con.commit()
    print("\n=== PROVISIONED ===")
    print("dashboard id:        ", NEWDASH)
    print("dashboard uuid:      ", str(dash_uuid))
    print("embedded_uuid:       ", str(emb_uuid))
    print("dataset ids:         ", DSMAP, "->", DSNAME)
    print("slice ids:           ", SLICEMAP)
    print("slice uuids:         ", slice_uuid_str)


if __name__ == "__main__":
    main()
    con.close()
