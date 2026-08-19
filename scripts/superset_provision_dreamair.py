#!/usr/bin/env python3
"""Provision the DreamAir Superset dashboard by cloning WinAir's dashboard 6.

Run inside the superset container:
    docker exec cpi-superset-1 python3 /tmp/superset_provision_dreamair.py

BACK UP superset.db FIRST. This writes the metadata database directly, the same
way superset_provision_winair.py does; there is no REST equivalent for cloning a
dashboard wholesale.

WHY IT CLONES FROM THE LIVE DATABASE, NOT FROM A SCRIPT
-------------------------------------------------------
superset_provision_winair.py builds only datasets 31/32/33 and slices 94..102.
WinAir's velocity (34), availability (37) and deployed-capacity (38) datasets and
slices 103/105/107/109/110/111/112 were built out of band and exist nowhere in
the repo. They are recoverable because their SQL lives in `tables.sql`, so this
script reads the live metadata as its source. Running it is therefore the first
time the full WinAir chart set has been reproducible from a checked-in artefact.

WHAT IS CLONED
--------------
  datasets  31 -> 39  vw_airline_cpi_da_snapshot          (physical)
            32 -> 40  da_all_airlines_fares               (virtual)
            33 -> 41  da_pricing_recommendations          (virtual)
            34 -> 42  da_velocity_normalized              (virtual)
            37 -> 43  da_all_airlines_fares_availability  (virtual)
            38 -> 44  da_deployed_capacity                (virtual)
  slices    95,96,100,102,103,105,106,107,109,110,111,112 -> 113..124
  dashboard 6 -> 7, with position_json, json_metadata, css and an
            embedded_dashboards row

SQL substitution is mechanical and asserted, never assumed:
  vw_airline_cpi_wm_snapshot -> vw_airline_cpi_da_snapshot
  vw_velocity_wm_snapshot    -> vw_velocity_da_snapshot
  'WM' AS airline            -> 'DA' AS airline
  wm_price                   -> da_price   (a column name, so table_columns too)

label_colors is REBUILT rather than substituted. DreamAir's competitors
(TC, KQ, Fli, Aur, YS, Coa, UI, CQ) share nothing with WinAir's
(5L, 7Z, BW, DM, Exp, JY, S6), so a string swap would leave dead keys that
silently fall through to the scheme default. See docs/dreamair-palette.md for
why the key spellings below are what they are -- a key that does not match the
series name Superset builds is ignored without any error.
"""
import sqlite3
import json
import uuid
import datetime

DB = "/app/superset_home/superset.db"

SRC_DASH = 6
NEW_DASH = 7

# old WM dataset id -> new DA dataset id
DSMAP = {31: 39, 32: 40, 33: 41, 34: 42, 37: 43, 38: 44}
DSNAME = {
    39: "vw_airline_cpi_da_snapshot",
    40: "da_all_airlines_fares",
    41: "da_pricing_recommendations",
    42: "da_velocity_normalized",
    43: "da_all_airlines_fares_availability",
    44: "da_deployed_capacity",
}

DA_SLICES = [95, 96, 100, 102, 103, 105, 106, 107, 109, 110, 111, 112]
SLICEMAP = {old: 113 + i for i, old in enumerate(DA_SLICES)}

# ── Palette A, docs/dreamair-palette.md section 2 ──
# Slot order is fixed; competitors take slots 2..8 in descending row volume.
DA_CODE = "DA"
CARRIER_COLORS = {
    "DA":  "#1268E3",   # slot 1 — brand azure
    "TC":  "#E8632A",   # slot 2
    "KQ":  "#D6208F",   # slot 3
    "Fli": "#C08A00",   # slot 4
    "Aur": "#0E9DA8",   # slot 5
    "YS":  "#A05A2C",   # slot 6
    "Coa": "#9B4FD8",   # slot 7
    "UI":  "#2E7D32",   # slot 8
    "CQ":  "#64748B",   # overflow -> neutral fallback, see the doc
}
DA_DOMAIN = ["#1268E3", "#E8632A", "#D6208F", "#C08A00", "#0E9DA8",
             "#A05A2C", "#9B4FD8", "#2E7D32", "#64748B", "#0F766E"]

# Palette B — measures (velocity chart). The " (1)" suffix on the rate pair is
# not decoration: mixed_timeseries appends it to every query-B series name, and
# the colour lookup uses the suffixed form while the legend shows the bare one.
MEASURE_COLORS = {
    "Capacity":                 "#7FB0F0",
    "Current Booking":          "#0D4FB5",
    "Actual Seat Factor (1)":   "#10996B",
    "Forecasted SF (1)":        "#9B4FD8",
    "Actual Seat Factor":       "#10996B",
    "Forecasted SF":            "#9B4FD8",
}

# Availability markers — semantic, carried over from WinAir unchanged.
SOLD_OUT = "#F39C12"
NOT_ON_SALE = "#9E9E9E"

# Palette C — recommendation traffic light. Red is free here because the brand
# is azure, so "Reduce" gets a true red rather than a stand-in.
RECO_COLORS = {
    "Reduce": "#C0392B",
    "Monitor": "#C08A00",
    "No Change": "#64748B",
    "Consider Increase": "#1BAF7A",
}

# Composite key prefixes Superset builds for "<metric>, <carrier>" series.
COMPOSITE_PREFIXES = ["Min Fare", "Max Fare", "Lowest Available Fare", "Avg Fare"]

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
c = con.cursor()


def now():
    return datetime.datetime.utcnow().isoformat(sep=" ")


def build_label_colors():
    """Every key spelling Superset might build, for DreamAir's carriers."""
    out = {}
    out.update(CARRIER_COLORS)
    for pfx in COMPOSITE_PREFIXES:
        for code, hexv in CARRIER_COLORS.items():
            out[f"{pfx}, {code}"] = hexv
    for code in CARRIER_COLORS:
        out[f"Sold out, {code}"] = SOLD_OUT
        out[f"Not on sale, {code}"] = NOT_ON_SALE
        # mixed_timeseries query-B suffix
        out[f"Sold out, {code} (1)"] = SOLD_OUT
        out[f"Not on sale, {code} (1)"] = NOT_ON_SALE
    out.update(MEASURE_COLORS)
    out.update(RECO_COLORS)
    # Fare Composition (dist_bar): series are the METRIC labels, not carriers
    out["Base"] = "#1268E3"
    out["Tax"] = "#7FB0F0"
    out["YQ"] = "#9B4FD8"
    return out


LABEL_COLORS = build_label_colors()


def mapslices(lst):
    return [SLICEMAP[x] for x in lst if isinstance(x, int) and x in SLICEMAP]


def remap(o, newslice):
    """Rewrite dataset ids, slice ids, dashboard refs and label_colors in place."""
    if isinstance(o, dict):
        for k in list(o.keys()):
            v = o[k]
            if k == "datasource" and isinstance(v, str) and v.endswith("__table"):
                o[k] = "%d__table" % DSMAP[int(v.split("__")[0])]
            elif k == "datasource" and isinstance(v, dict) and "id" in v:
                v["id"] = DSMAP.get(v["id"], v["id"])
                remap(v, newslice)
            elif k == "dashboards" and isinstance(v, list):
                o[k] = [NEW_DASH]
            elif k == "slice_id":
                o[k] = newslice
            elif k == "label_colors" and isinstance(v, dict):
                o[k] = dict(LABEL_COLORS)
            else:
                remap(v, newslice)
    elif isinstance(o, list):
        for x in o:
            remap(x, newslice)


def sub_sql(sql):
    """WM -> DA in a virtual dataset's SQL. Asserts, never assumes."""
    if not sql:
        return None
    out = (sql.replace("vw_airline_cpi_wm_snapshot", "vw_airline_cpi_da_snapshot")
              .replace("vw_velocity_wm_snapshot", "vw_velocity_da_snapshot")
              .replace("'WM' AS airline", "'DA' AS airline")
              .replace("wm_price", "da_price"))
    assert "vw_airline_cpi_wm_snapshot" not in out, "airline view not substituted"
    assert "vw_velocity_wm_snapshot" not in out, "velocity view not substituted"
    assert "'WM'" not in out, "WM literal survived"
    assert "wm_price" not in out, "wm_price survived"
    return out


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
    if c.execute("SELECT 1 FROM tables WHERE table_name='da_all_airlines_fares'").fetchone():
        print("ABORT: DA datasets already exist. Restore superset.db from backup to re-run.")
        return
    if c.execute("SELECT 1 FROM dashboards WHERE id=?", (NEW_DASH,)).fetchone():
        print("ABORT: dashboard %d already exists." % NEW_DASH)
        return

    # ── 1. datasets ──
    for old, new in DSMAP.items():
        src = c.execute("SELECT table_name, sql FROM tables WHERE id=?", (old,)).fetchone()
        name = DSNAME[new]
        newsql = sub_sql(src["sql"])
        clone_row("tables", old, new, {
            "table_name": name,
            "perm": "[CPI PostgreSQL].[%s](id:%d)" % (name, new),
            "schema_perm": "[CPI PostgreSQL].[public]",
            "sql": newsql,
        })
        print("dataset %d -> %d  %s  (virtual=%s)" % (old, new, name, bool(newsql)))

    # ── 2. table_columns + sql_metrics ──
    tc_id = c.execute("SELECT max(id) FROM table_columns").fetchone()[0]
    m_id = c.execute("SELECT max(id) FROM sql_metrics").fetchone()[0]
    for old, new in DSMAP.items():
        for col in c.execute("SELECT * FROM table_columns WHERE table_id=?", (old,)).fetchall():
            d = dict(col)
            if d["column_name"] == "wm_price":
                d["column_name"] = "da_price"
            if d.get("expression"):
                d["expression"] = d["expression"].replace("wm_price", "da_price")
            tc_id += 1
            d["id"] = tc_id
            d["table_id"] = new
            d["uuid"] = uuid.uuid4().bytes
            cols = list(d.keys())
            c.execute("INSERT INTO table_columns (%s) VALUES (%s)" % (
                ",".join(cols), ",".join(["?"] * len(cols))), [d[k] for k in cols])
        for met in c.execute("SELECT * FROM sql_metrics WHERE table_id=?", (old,)).fetchall():
            d = dict(met)
            if d.get("expression"):
                d["expression"] = d["expression"].replace("wm_price", "da_price")
            m_id += 1
            d["id"] = m_id
            d["table_id"] = new
            d["uuid"] = uuid.uuid4().bytes
            cols = list(d.keys())
            c.execute("INSERT INTO sql_metrics (%s) VALUES (%s)" % (
                ",".join(cols), ",".join(["?"] * len(cols))), [d[k] for k in cols])

    # ── 3. dashboard shell ──
    dash_uuid = uuid.uuid4()
    clone_row("dashboards", SRC_DASH, NEW_DASH, {
        "dashboard_title": "Airline CPI DA Dashboard",
        "slug": "airline-cpi-da",
        "uuid": dash_uuid.bytes,
        "published": 1,
    })

    # ── 4. slices ──
    slice_uuid_str = {}
    for old in DA_SLICES:
        new = SLICEMAP[old]
        src = dict(c.execute("SELECT * FROM slices WHERE id=?", (old,)).fetchone())
        oldds = src["datasource_id"]
        newds = DSMAP[oldds]
        newname = DSNAME[newds]
        su = uuid.uuid4()
        slice_uuid_str[old] = str(su)

        params = json.loads(src["params"])
        remap(params, new)
        params_s = json.dumps(params).replace("wm_price", "da_price")

        qc_s = None
        if src["query_context"]:
            qc = json.loads(src["query_context"])
            remap(qc, new)
            qc_s = json.dumps(qc).replace("wm_price", "da_price")

        clone_row("slices", old, new, {
            "uuid": su.bytes,
            "datasource_id": newds,
            "datasource_name": "public.%s" % newname,
            "perm": "[CPI PostgreSQL].[%s](id:%d)" % (newname, newds),
            "schema_perm": "[CPI PostgreSQL].[public]",
            "params": params_s,
            "query_context": qc_s,
        })
        print("slice %d -> %d  ds %d -> %d  %s" % (old, new, oldds, newds, src["slice_name"]))

    # ── 5. dashboard_slices ──
    for old in DA_SLICES:
        c.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                  (NEW_DASH, SLICEMAP[old]))

    # ── 6. position_json ──
    pos = json.loads(c.execute("SELECT position_json FROM dashboards WHERE id=?",
                               (SRC_DASH,)).fetchone()[0])
    for k, node in pos.items():
        if isinstance(node, dict) and node.get("type") == "CHART":
            m = node["meta"]
            old = m["chartId"]
            assert old in SLICEMAP, "position_json references unmapped chart %r" % old
            m["chartId"] = SLICEMAP[old]
            m["uuid"] = slice_uuid_str[old]
        if k == "HEADER_ID":
            node["meta"]["text"] = "Airline CPI DA Dashboard"
    # every cloned slice must appear in the layout, or the tab row loses a chart
    laid_out = {n["meta"]["chartId"] for n in pos.values()
                if isinstance(n, dict) and n.get("type") == "CHART"}
    missing = set(SLICEMAP.values()) - laid_out
    assert not missing, "slices cloned but absent from position_json: %s" % sorted(missing)

    # ── 7. json_metadata ──
    jm = json.loads(c.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                              (SRC_DASH,)).fetchone()[0])
    jm["label_colors"] = dict(LABEL_COLORS)
    jm["shared_label_colors"] = {}
    jm["color_scheme"] = "rts_cpi_palette"
    jm["color_scheme_domain"] = DA_DOMAIN
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
    newcc = {}
    for k, v in (jm.get("chart_configuration") or {}).items():
        if int(k) not in SLICEMAP:
            continue
        if "id" in v:
            v["id"] = SLICEMAP[v["id"]]
        cf = v.get("crossFilters", {})
        if isinstance(cf.get("chartsInScope"), list):
            cf["chartsInScope"] = mapslices(cf["chartsInScope"])
        newcc[str(SLICEMAP[int(k)])] = v
    jm["chart_configuration"] = newcc
    for key in ("expanded_slices", "timed_refresh_immune_slices"):
        val = jm.get(key)
        if isinstance(val, list):
            jm[key] = mapslices(val)
        elif isinstance(val, dict):
            jm[key] = {str(SLICEMAP[int(k)]): v for k, v in val.items()
                       if int(k) in SLICEMAP}

    c.execute("UPDATE dashboards SET position_json=?, json_metadata=? WHERE id=?",
              (json.dumps(pos), json.dumps(jm), NEW_DASH))

    # ── 8. embedded_dashboards ──
    emb_uuid = uuid.uuid4()
    c.execute("INSERT INTO embedded_dashboards "
              "(created_on, changed_on, allow_domain_list, uuid, dashboard_id, "
              "created_by_fk, changed_by_fk) VALUES (?,?,?,?,?,?,?)",
              (now(), now(), "", emb_uuid.bytes, NEW_DASH, 1, 1))

    con.commit()
    print("\n=== PROVISIONED ===")
    print("dashboard id:   ", NEW_DASH)
    print("dashboard uuid: ", str(dash_uuid))
    print("embedded_uuid:  ", str(emb_uuid))
    print("datasets:       ", DSMAP)
    print("slices:         ", SLICEMAP)
    print("\nPut dashboard uuid and embedded_uuid into DASHBOARDS in")
    print("apps/api/app/routers/superset.py -- prod mints its own, they will differ.")


if __name__ == "__main__":
    main()
    con.close()
