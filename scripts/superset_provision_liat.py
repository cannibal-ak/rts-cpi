#!/usr/bin/env python3
"""Provision the Liat Air Superset dashboard by cloning DreamAir's dashboard 7.

Run inside the superset container:
    docker exec cpi-superset-1 python3 /tmp/superset_provision_liat.py

BACK UP superset.db FIRST. This writes the metadata database directly, the same
way superset_provision_dreamair.py does; there is no REST equivalent for
cloning a dashboard wholesale.

WHAT IS CLONED
--------------
  datasets  39 -> 45  vw_airline_cpi_5l_snapshot          (physical)
            40 -> 46  liat_all_airlines_fares             (virtual)
            41 -> 47  liat_pricing_recommendations        (virtual)
            42 -> 48  liat_velocity_normalized            (virtual)
            43 -> 49  liat_all_airlines_fares_availability (virtual)
            44 -> 50  liat_deployed_capacity              (virtual)
  slices    113,114,115,116,117,118,119,120,121,123,124 -> 125..135
  dashboard 7 -> 8, with position_json, json_metadata, css and an
            embedded_dashboards row

The slice list is dashboard 7's LIVE membership, not DreamAir's full clone
set: slice 122 (Deployed Capacity) was detached from dashboard 7 on
2026-08-20 and stays detached here — "like DreamAir" means DreamAir's current
state. Its dataset ds44 IS still cloned (-> 50, liat_deployed_capacity) so the
tenants keep dataset parity and the chart can be re-attached later without a
second provisioning pass.

Virtual-dataset names are `liat_*`, not `5l_*`: an identifier starting with a
digit is not a legal unquoted SQL name. For the same reason the own-fare
column alias becomes `liat_price` where DreamAir has `da_price`.

SQL substitution is mechanical and asserted, never assumed:
  vw_airline_cpi_da_snapshot -> vw_airline_cpi_5l_snapshot
  vw_velocity_da_snapshot    -> vw_velocity_5l_snapshot
  'DA' AS airline            -> '5L' AS airline
  da_price                   -> liat_price  (a column name, so table_columns too)

label_colors: CARRIER KEYS ARE NOT WRITTEN HERE. The Liat data has not been
ingested, so slots 2-8 of Palette A cannot be assigned (assignment is by
descending competitor row volume — docs/liat-palette.md §2). This script
writes every key that is carrier-independent (the 5L brand keys, measures,
recommendation traffic light, fare-composition metrics, 5L markers); run
scripts/superset/liat_dash8_carrier_keys.py AFTER the first ingest commits to
assign slots and add the competitor keys additively. Until then competitor
series fall through to the scheme domain, whose slot hues are the same
palette — acceptable for an empty tenant, wrong once real carriers land.
"""
import sqlite3
import json
import uuid
import datetime

DB = "/app/superset_home/superset.db"

SRC_DASH = 7
NEW_DASH = 8

# old DA dataset id -> new 5L dataset id
DSMAP = {39: 45, 40: 46, 41: 47, 42: 48, 43: 49, 44: 50}
DSNAME = {
    45: "vw_airline_cpi_5l_snapshot",
    46: "liat_all_airlines_fares",
    47: "liat_pricing_recommendations",
    48: "liat_velocity_normalized",
    49: "liat_all_airlines_fares_availability",
    50: "liat_deployed_capacity",
}

# Dashboard 7's live membership (122 detached 2026-08-20, see docstring).
LIAT_SLICES = [113, 114, 115, 116, 117, 118, 119, 120, 121, 123, 124]
SLICEMAP = {old: 125 + i for i, old in enumerate(LIAT_SLICES)}

# ── Palette A, docs/liat-palette.md section 2 — brand slot only ──
# Competitor slots 2-8 are assigned by liat_dash8_carrier_keys.py once data
# exists; adding them here would freeze an assignment no data supports yet.
DA_CODE = "5L"
CARRIER_COLORS = {
    "5L": "#D02127",   # slot 1 — brand red, the logo A-mark gradient midpoint
}
# The fixed 10-slot scheme domain (slots 2-8 + the two neutral fallbacks are
# hue-stable regardless of which carrier lands in which slot). Slots 2-4 are
# the logo's own colours — swoosh azure, gold, wordmark blue.
LIAT_DOMAIN = ["#D02127", "#0375B4", "#C08A00", "#275AA1", "#2E7D32",
               "#D6208F", "#A05A2C", "#9B4FD8", "#64748B", "#0F766E"]

# Palette B — measures (velocity chart), docs/liat-palette.md §3. The " (1)"
# suffix on the rate pair is not decoration: mixed_timeseries appends it to
# every query-B series name, and the colour lookup uses the suffixed form
# while the legend shows the bare one.
MEASURE_COLORS = {
    "Capacity":                 "#DE8078",
    "Current Booking":          "#D02127",
    "Actual Seat Factor (1)":   "#0375B4",
    "Forecasted SF (1)":        "#8B5CF6",
    "Actual Seat Factor":       "#0375B4",
    "Forecasted SF":            "#8B5CF6",
}

# Availability markers — semantic, carried over unchanged.
SOLD_OUT = "#F39C12"
NOT_ON_SALE = "#9E9E9E"

# Palette C — recommendation traffic light. As on WinAir, Reduce reuses the
# brand red: on that chart red means Reduce, not 5L — the scopes never meet
# (the reco chart has no carrier series). One palette per chart.
RECO_COLORS = {
    "Reduce": "#D02127",
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
    """Every carrier-independent key spelling, plus the 5L brand keys."""
    out = {}
    out.update(CARRIER_COLORS)
    for pfx in COMPOSITE_PREFIXES:
        for code, hexv in CARRIER_COLORS.items():
            out[f"{pfx}, {code}"] = hexv
    for code in CARRIER_COLORS:
        out[f"Sold out, {code}"] = SOLD_OUT
        out[f"Not on sale, {code}"] = NOT_ON_SALE
        out[f"Sold out, {code} (1)"] = SOLD_OUT
        out[f"Not on sale, {code} (1)"] = NOT_ON_SALE
    out.update(MEASURE_COLORS)
    out.update(RECO_COLORS)
    # Fare Composition (dist_bar): series are the METRIC labels, not carriers
    out["Base"] = "#D02127"
    out["Tax"] = "#C08A00"
    out["YQ"] = "#0375B4"
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
    """DA -> 5L in a virtual dataset's SQL. Asserts, never assumes."""
    if not sql:
        return None
    out = (sql.replace("vw_airline_cpi_da_snapshot", "vw_airline_cpi_5l_snapshot")
              .replace("vw_velocity_da_snapshot", "vw_velocity_5l_snapshot")
              .replace("'DA' AS airline", "'5L' AS airline")
              .replace("da_price", "liat_price"))
    assert "vw_airline_cpi_da_snapshot" not in out, "airline view not substituted"
    assert "vw_velocity_da_snapshot" not in out, "velocity view not substituted"
    assert "'DA'" not in out, "DA literal survived"
    assert "da_price" not in out, "da_price survived"
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
    if c.execute("SELECT 1 FROM tables WHERE table_name='liat_all_airlines_fares'").fetchone():
        print("ABORT: Liat datasets already exist. Restore superset.db from backup to re-run.")
        return
    if c.execute("SELECT 1 FROM dashboards WHERE id=?", (NEW_DASH,)).fetchone():
        print("ABORT: dashboard %d already exists." % NEW_DASH)
        return
    # ids 45..50 / 125..135 must be free — a livelier database means renumbering
    assert (c.execute("SELECT max(id) FROM tables").fetchone()[0] or 0) < 45, "dataset ids not free"
    assert (c.execute("SELECT max(id) FROM slices").fetchone()[0] or 0) < 125, "slice ids not free"

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
            if d["column_name"] == "da_price":
                d["column_name"] = "liat_price"
            if d.get("expression"):
                d["expression"] = d["expression"].replace("da_price", "liat_price")
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
                d["expression"] = d["expression"].replace("da_price", "liat_price")
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
        "dashboard_title": "Airline CPI 5L Dashboard",
        "slug": "airline-cpi-5l",
        "uuid": dash_uuid.bytes,
        "published": 1,
    })

    # ── 4. slices ──
    slice_uuid_str = {}
    for old in LIAT_SLICES:
        new = SLICEMAP[old]
        src = dict(c.execute("SELECT * FROM slices WHERE id=?", (old,)).fetchone())
        oldds = src["datasource_id"]
        newds = DSMAP[oldds]
        newname = DSNAME[newds]
        su = uuid.uuid4()
        slice_uuid_str[old] = str(su)

        params = json.loads(src["params"])
        remap(params, new)
        params_s = json.dumps(params).replace("da_price", "liat_price")

        qc_s = None
        if src["query_context"]:
            qc = json.loads(src["query_context"])
            remap(qc, new)
            qc_s = json.dumps(qc).replace("da_price", "liat_price")

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
    for old in LIAT_SLICES:
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
            node["meta"]["text"] = "Airline CPI 5L Dashboard"
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
    jm["color_scheme_domain"] = LIAT_DOMAIN
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
    print("\nAFTER the first Liat ingest commits, run")
    print("scripts/superset/liat_dash8_carrier_keys.py to assign competitor")
    print("colour slots and write their label_colors keys.")


if __name__ == "__main__":
    main()
    con.close()
