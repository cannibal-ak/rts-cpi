#!/usr/bin/env python3
"""READ-ONLY cross-tenant parity inventory of superset.db.

Dumps, for an allowlisted set of dashboards, everything the tenant-parity
audit compares: tab structure, slice names, native filters, css markers,
label_colors keys, and dataset SQL fingerprints. Never writes anything —
the database is opened with mode=ro&immutable=1.

Run inside the superset container (dev or prod):
    docker exec -i cpi-superset-1 python3 - --dashboards 1,3,6,7 < parity_inventory.py > out.json

Scope guard: refuses to include dashboards 2 (FJL), 5 (SKY) and 8 (5L) even
if asked — they are out of the JY/PW/WM/DA parity scope.
"""
import argparse
import datetime
import hashlib
import json
import re
import sqlite3
import sys
import uuid as uuidlib

DB = "/app/superset_home/superset.db"
FORBIDDEN = {2, 5, 8}  # FJL, SKY, 5L — out of scope, never inventoried
CSS_MARKER_RE = re.compile(r"([A-Z0-9]+-EMBED-[A-Z-]+ v\d+)")


def md5(text):
    return hashlib.md5((text or "").encode("utf-8", "replace")).hexdigest()


def norm_sql_md5(sql):
    # Whitespace/case-insensitive fingerprint so formatting-only diffs don't flag.
    norm = re.sub(r"\s+", " ", (sql or "").strip().lower())
    return hashlib.md5(norm.encode("utf-8", "replace")).hexdigest()


def decode_uuid(raw):
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            return str(uuidlib.UUID(bytes=raw))
        except Exception:
            return raw.hex()
    return str(raw)


def safe_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def walk_charts(nodes, node_id, acc, nested_tab_labels):
    """Depth-first collection of chartIds under a layout node, recording any
    nested TAB labels met on the way (e.g. WM's Velocity sub-tabs)."""
    node = nodes.get(node_id)
    if not isinstance(node, dict):
        return
    ntype = node.get("type")
    meta = node.get("meta") or {}
    if ntype == "CHART":
        acc.append({
            "chart_id": meta.get("chartId"),
            "layout_slice_name": meta.get("sliceName"),
            "layout_uuid": meta.get("uuid"),
            "node": node_id,
        })
    if ntype == "TAB":
        label = (meta.get("text") or "").strip()
        if label:
            nested_tab_labels.append(label)
    for child in node.get("children") or []:
        walk_charts(nodes, child, acc, nested_tab_labels)


def extract_layout(position_json):
    nodes = safe_json(position_json) or {}
    out = {"top_tabs_node": None, "tabs": [], "ungrouped_charts": []}
    grid = nodes.get("GRID_ID") or {}
    grid_children = grid.get("children") or []
    top_tabs_id = None
    for child in grid_children:
        node = nodes.get(child)
        if isinstance(node, dict) and node.get("type") == "TABS":
            top_tabs_id = child
            break
    if top_tabs_id:
        out["top_tabs_node"] = top_tabs_id
        for tab_id in (nodes.get(top_tabs_id) or {}).get("children") or []:
            tab = nodes.get(tab_id) or {}
            label = ((tab.get("meta") or {}).get("text") or "").strip()
            charts, nested = [], []
            for child in tab.get("children") or []:
                walk_charts(nodes, child, charts, nested)
            out["tabs"].append({
                "node": tab_id,
                "label": label,
                "charts": charts,
                "nested_tab_labels": nested,
            })
        # anything in the grid outside the TABS node
        for child in grid_children:
            if child == top_tabs_id:
                continue
            charts, nested = [], []
            walk_charts(nodes, child, charts, nested)
            out["ungrouped_charts"].extend(charts)
    else:
        charts, nested = [], []
        for child in grid_children:
            walk_charts(nodes, child, charts, nested)
        out["ungrouped_charts"] = charts
        if nested:
            out["flat_section_tab_labels"] = nested
    return out


def extract_native_filters(meta):
    filters = []
    for f in (meta or {}).get("native_filter_configuration") or []:
        targets = f.get("targets") or [{}]
        t0 = targets[0] if targets else {}
        column = (t0.get("column") or {}).get("name")
        control = f.get("controlValues") or {}
        scope = f.get("scope") or {}
        chart_scope = f.get("chartsInScope")
        default_mask = f.get("defaultDataMask") or {}
        has_default = bool((default_mask.get("filterState") or {}).get("value"))
        filters.append({
            "id": f.get("id"),
            "name": f.get("name"),
            "filter_type": f.get("filterType"),
            "column": column,
            "dataset_id": t0.get("datasetId"),
            "multi_select": control.get("multiSelect"),
            "charts_in_scope_count": len(chart_scope) if isinstance(chart_scope, list) else None,
            "scope_excluded": scope.get("excluded"),
            "has_default_value": has_default,
        })
    return filters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dashboards", required=True,
                    help="comma-separated Superset dashboard ids, e.g. 1,3,6,7")
    ap.add_argument("--env-label", default="unknown")
    args = ap.parse_args()

    wanted = {int(x) for x in args.dashboards.split(",") if x.strip()}
    blocked = wanted & FORBIDDEN
    if blocked:
        sys.stderr.write("REFUSED: dashboards %s are out of parity scope\n" % sorted(blocked))
        sys.exit(2)

    con = sqlite3.connect("file:%s?mode=ro&immutable=1" % DB, uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    result = {
        "env_label": args.env_label,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "db_path": DB,
        "all_dashboards": [],
        "dashboards": {},
    }

    for row in cur.execute("SELECT id, dashboard_title, slug FROM dashboards ORDER BY id"):
        result["all_dashboards"].append(
            {"id": row["id"], "title": row["dashboard_title"], "slug": row["slug"]})

    for dash_id in sorted(wanted):
        row = cur.execute(
            "SELECT id, dashboard_title, slug, uuid, css, json_metadata, position_json "
            "FROM dashboards WHERE id=?", (dash_id,)).fetchone()
        if row is None:
            result["dashboards"][str(dash_id)] = {"error": "dashboard id not found"}
            continue

        meta = safe_json(row["json_metadata"]) or {}
        css = row["css"] or ""

        emb = cur.execute(
            "SELECT uuid FROM embedded_dashboards WHERE dashboard_id=?", (dash_id,)).fetchone()

        d = {
            "id": row["id"],
            "title": row["dashboard_title"],
            "slug": row["slug"],
            "uuid": decode_uuid(row["uuid"]),
            "embedded_uuid": decode_uuid(emb["uuid"]) if emb else None,
            "css_markers": CSS_MARKER_RE.findall(css),
            "css_len": len(css),
            "metadata_keys": sorted(meta.keys()),
            "color_scheme": meta.get("color_scheme"),
            "color_scheme_domain_len": len(meta.get("color_scheme_domain") or []),
            "label_colors_keys": sorted((meta.get("label_colors") or {}).keys()),
            "show_native_filters": meta.get("show_native_filters"),
            "native_filters": extract_native_filters(meta),
            "layout": extract_layout(row["position_json"]),
        }

        slices = []
        dataset_ids = set()
        layout_names = {}
        for tab in d["layout"]["tabs"]:
            for c in tab["charts"]:
                layout_names[c["chart_id"]] = (c["layout_slice_name"], tab["label"])
        for c in d["layout"]["ungrouped_charts"]:
            layout_names[c["chart_id"]] = (c["layout_slice_name"], None)

        for s in cur.execute(
                "SELECT s.id, s.slice_name, s.viz_type, s.datasource_id, s.datasource_type, "
                "s.params, s.query_context, s.uuid "
                "FROM slices s JOIN dashboard_slices ds ON ds.slice_id = s.id "
                "WHERE ds.dashboard_id=? ORDER BY s.id", (dash_id,)):
            in_layout = s["id"] in layout_names
            layout_name, tab_label = layout_names.get(s["id"], (None, None))
            if s["datasource_type"] == "table" and s["datasource_id"]:
                dataset_ids.add(s["datasource_id"])
            slices.append({
                "id": s["id"],
                "name": s["slice_name"],
                "viz_type": s["viz_type"],
                "dataset_id": s["datasource_id"],
                "uuid": decode_uuid(s["uuid"]),
                "params_md5": md5(s["params"]),
                "query_context_md5": md5(s["query_context"]),
                "in_layout": in_layout,
                "tab_label": tab_label,
                "layout_header": layout_name,
                # meta.sliceName is the DISPLAYED header and legitimately carries
                # view-type suffixes ("<name> — Line/Bar/Table"); stale means the
                # header no longer starts with the slice's actual name.
                "layout_slice_name_stale": bool(
                    in_layout and layout_name
                    and not layout_name.startswith(s["slice_name"])),
            })
        d["slices"] = slices

        datasets = []
        for ds_id in sorted(dataset_ids):
            t = cur.execute(
                "SELECT id, table_name, sql FROM tables WHERE id=?", (ds_id,)).fetchone()
            if t is None:
                datasets.append({"id": ds_id, "error": "not found"})
                continue
            cols = [r["column_name"] for r in cur.execute(
                "SELECT column_name FROM table_columns WHERE table_id=? ORDER BY column_name",
                (ds_id,))]
            datasets.append({
                "id": t["id"],
                "table_name": t["table_name"],
                "is_virtual": bool(t["sql"]),
                "sql_md5": md5(t["sql"]),
                "sql_norm_md5": norm_sql_md5(t["sql"]),
                "columns": cols,
            })
        d["datasets"] = datasets

        result["dashboards"][str(dash_id)] = d

    con.close()
    json.dump(result, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
