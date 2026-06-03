#!/usr/bin/env python3
"""Provision the Sky Airways (ALT) Superset dashboard by cloning JY.

Run inside the Superset container (writes the metadata SQLite DB):
    # back up first!
    docker exec cpi-superset-1 cp /app/superset_home/superset.db \
        /app/superset_home/superset.db.bak.<ts>
    docker cp scripts/superset_provision_altitude.py cpi-superset-1:/tmp/prov.py
    docker exec cpi-superset-1 python /tmp/prov.py

Clones JY dashboard 1 -> a new ALT dashboard:
  * 4 datasets (1 physical on vw_airline_cpi_alt_snapshot + 3 virtual repointed
    to the ALT views, with a careful JY->ALT substitution; jy_price->sky_price)
  * the 10 JY slices, repointed to the ALT datasets
  * the dashboard json_metadata/position_json (filters retargeted, chart ids
    remapped, label_colors set to the Sky palette)
  * an embedded_dashboards row (new embedded_uuid)

Idempotent guard: aborts if an 'alt_all_airlines_fares' dataset already exists.
All writes happen in one transaction; nothing commits if an assertion fails.
"""
import sqlite3
import json
import uuid
import datetime

DB = "/app/superset_home/superset.db"

# ── Explicit new ids (all above current maxima: tables 26, slices 83, dash 4) ──
DSMAP = {3: 27, 13: 28, 14: 29, 15: 30}       # old JY dataset id -> new ALT id
DSNAME = {
    27: "vw_airline_cpi_alt_snapshot",
    28: "alt_all_airlines_fares",
    29: "alt_velocity_normalized",
    30: "alt_pricing_recommendations",
}
NEWDASH = 5
JY_SLICES = [43, 46, 47, 48, 49, 50, 51, 52, 53, 55]
SLICEMAP = {old: 84 + i for i, old in enumerate(JY_SLICES)}   # -> 84..93
SLICE_DS = {43: 13, 46: 13, 47: 14, 48: 15, 49: 13, 50: 13,
            51: 13, 52: 13, 53: 15, 55: 13}

JY_CARRIERS = {"JY", "BW", "WM", "9Q", "5L", "PY", "DO", "S6"}
ALT_COLORS = {"SKY": "#3F4EA8", "MR": "#0E9AA7", "CD": "#3DC1D3",
              "VR": "#F2A03D", "SX": "#5B6C8A"}
ALT_DOMAIN = ["#3F4EA8", "#0E9AA7", "#3DC1D3", "#F2A03D", "#5B6C8A", "#CBD5E1"]

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
c = con.cursor()


def now():
    return datetime.datetime.utcnow().isoformat(sep=" ")


def fix_label_colors(d):
    out = {k: v for k, v in d.items() if k not in JY_CARRIERS}
    out.update(ALT_COLORS)
    return out


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
    if c.execute("SELECT 1 FROM tables WHERE table_name='alt_all_airlines_fares'").fetchone():
        print("ABORT: ALT datasets already exist. Restore from backup to re-run.")
        return

    # ── build + PRINT the substituted virtual SQL (for review) ──
    sql13 = c.execute("SELECT sql FROM tables WHERE id=13").fetchone()[0]
    sql14 = c.execute("SELECT sql FROM tables WHERE id=14").fetchone()[0]
    sql15 = c.execute("SELECT sql FROM tables WHERE id=15").fetchone()[0]

    s28 = sql13.replace("'JY' AS airline", "'SKY' AS airline") \
               .replace("vw_airline_cpi_jy_snapshot", "vw_airline_cpi_alt_snapshot")
    assert "'SKY' AS airline" in s28 and s28.count("vw_airline_cpi_alt_snapshot") == 2 \
        and "vw_airline_cpi_jy_snapshot" not in s28, "fares SQL substitution failed"

    s29 = sql14.replace("vw_velocity_jy_snapshot", "vw_velocity_alt_snapshot")
    assert s29.count("vw_velocity_alt_snapshot") == 1 \
        and "vw_velocity_jy_snapshot" not in s29, "velocity SQL substitution failed"

    s30 = sql15.replace("vw_airline_cpi_jy_snapshot", "vw_airline_cpi_alt_snapshot") \
               .replace("vw_velocity_jy_snapshot", "vw_velocity_alt_snapshot") \
               .replace("jy_price", "sky_price")
    assert "vw_airline_cpi_alt_snapshot" in s30 and "vw_velocity_alt_snapshot" in s30 \
        and "jy_price" not in s30 and "_jy_" not in s30, "reco SQL substitution failed"

    print("=" * 70)
    print("SUBSTITUTED SQL -> alt_all_airlines_fares (id 28):\n" + s28)
    print("-" * 70)
    print("SUBSTITUTED SQL -> alt_velocity_normalized (id 29):\n" + s29)
    print("-" * 70)
    print("SUBSTITUTED SQL -> alt_pricing_recommendations (id 30):\n" + s30)
    print("=" * 70)

    SQLBY = {28: s28, 29: s29, 30: s30}

    # ── 1. datasets (tables) ──
    for old, new in DSMAP.items():
        name = DSNAME[new]
        ov = {"table_name": name,
              "perm": "[CPI PostgreSQL].[%s](id:%d)" % (name, new),
              "schema_perm": "[CPI PostgreSQL].[public]",
              "sql": None if new == 27 else SQLBY[new]}
        clone_row("tables", old, new, ov)

    # ── 2. table_columns + sql_metrics for each dataset ──
    tc_id = c.execute("SELECT max(id) FROM table_columns").fetchone()[0]
    m_id = c.execute("SELECT max(id) FROM sql_metrics").fetchone()[0]
    for old, new in DSMAP.items():
        for col in c.execute("SELECT * FROM table_columns WHERE table_id=?", (old,)).fetchall():
            tc_id += 1
            d = dict(col)
            d["id"] = tc_id
            d["table_id"] = new
            d["uuid"] = uuid.uuid4().bytes
            if old == 15 and d["column_name"] == "jy_price":
                d["column_name"] = "sky_price"
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
        "dashboard_title": "Airline CPI SKY Dashboard",
        "slug": "airline-cpi-alt",
        "uuid": dash_uuid.bytes,
        "published": 1,
    })

    # ── 4. slices ──
    slice_uuid_str = {}
    for old in JY_SLICES:
        new = SLICEMAP[old]
        newds = DSMAP[SLICE_DS[old]]
        newname = DSNAME[newds]
        su = uuid.uuid4()
        slice_uuid_str[old] = str(su)
        src = dict(c.execute("SELECT * FROM slices WHERE id=?", (old,)).fetchone())
        params = json.loads(src["params"])
        remap(params, new)
        params_s = json.dumps(params).replace("jy_price", "sky_price")
        qc_s = None
        if src["query_context"]:
            qc = json.loads(src["query_context"])
            remap(qc, new)
            qc_s = json.dumps(qc).replace("jy_price", "sky_price")
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
    for old in JY_SLICES:
        c.execute("INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (?,?)",
                  (NEWDASH, SLICEMAP[old]))

    # ── 6. position_json + json_metadata remap ──
    pos = json.loads(c.execute("SELECT position_json FROM dashboards WHERE id=1").fetchone()[0])
    for k, node in pos.items():
        if isinstance(node, dict) and node.get("type") == "CHART":
            m = node["meta"]
            old = m["chartId"]
            m["chartId"] = SLICEMAP[old]
            m["uuid"] = slice_uuid_str[old]
        if k == "HEADER_ID":
            node["meta"]["text"] = "Airline CPI SKY Dashboard"

    jm = json.loads(c.execute("SELECT json_metadata FROM dashboards WHERE id=1").fetchone()[0])
    jm["label_colors"] = fix_label_colors(jm.get("label_colors", {}))
    jm["shared_label_colors"] = {}
    jm["color_scheme"] = "rts_cpi_palette"
    jm["color_scheme_domain"] = ALT_DOMAIN
    for f in jm.get("native_filter_configuration", []):
        for t in f.get("targets", []):
            if "datasetId" in t:
                t["datasetId"] = DSMAP.get(t["datasetId"], t["datasetId"])
        if "chartsInScope" in f:
            f["chartsInScope"] = [SLICEMAP.get(x, x) for x in f["chartsInScope"]]
        sc = f.get("scope", {})
        if "excluded" in sc:
            sc["excluded"] = [SLICEMAP.get(x, x) for x in sc["excluded"]]
    gc = jm.get("global_chart_configuration", {})
    if "chartsInScope" in gc:
        gc["chartsInScope"] = [SLICEMAP.get(x, x) for x in gc["chartsInScope"]]
    if "scope" in gc and "excluded" in gc["scope"]:
        gc["scope"]["excluded"] = [SLICEMAP.get(x, x) for x in gc["scope"]["excluded"]]
    cc = jm.get("chart_configuration", {})
    newcc = {}
    for k, v in cc.items():
        if "id" in v:
            v["id"] = SLICEMAP.get(v["id"], v["id"])
        cf = v.get("crossFilters", {})
        if "chartsInScope" in cf:
            cf["chartsInScope"] = [SLICEMAP.get(x, x) for x in cf["chartsInScope"]]
        newcc[str(SLICEMAP.get(int(k), int(k)))] = v
    jm["chart_configuration"] = newcc

    c.execute("UPDATE dashboards SET position_json=?, json_metadata=? WHERE id=?",
              (json.dumps(pos), json.dumps(jm), NEWDASH))

    # ── 7. embedded_dashboards ──
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
