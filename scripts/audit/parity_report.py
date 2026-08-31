#!/usr/bin/env python3
"""Cross-tenant parity comparator: consumes the parity_inventory /
parity_alerts_inventory JSON dumps and emits the parity matrix plus a
proposed-renames CSV for user review.

WM (Superset dash 6) is the canonical axis per the approved policy:
names standardize on WM's wherever a chart/filter is equivalent; brand
palettes and per-tenant tuned alert thresholds are NOT compared.

Usage (from the repo root, after running the inventories into audits/):
    python scripts/audit/parity_report.py
Writes audits/parity_matrix.md and audits/proposed_renames.csv.
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

AUDITS = Path(__file__).resolve().parents[2] / "audits"

CANON_DASH = "6"  # WM
TENANT_BY_DASH = {"1": "JY", "3": "PW", "6": "WM", "7": "DA"}
DASH_ORDER = ["6", "7", "1", "3"]  # WM, DA, JY, PW

# alert condition keys whose VALUES are per-tenant tuned by policy —
# windows/routes/competitors included: they were deliberate 2026-08-31 knobs.
ALERT_TUNED_KEYS = {"move_pct", "min_abs_move", "value", "min_gap_pct", "max_rank",
                    "windows", "routes", "competitors", "min_day_share", "min_days",
                    "min_stop_gap", "min_gap_days", "min_days_observed", "min_competitors"}

UNTOUCHABLE_SLICES = {43}


def norm(name):
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def load(name):
    path = AUDITS / name
    if not path.exists():
        sys.exit(f"missing {path} — run the inventory first")
    return json.loads(path.read_text(encoding="utf-8"))


def slice_rows(dash):
    """(tab_label, position-in-tab, slice) for every in-layout slice, layout order."""
    by_id = {s["id"]: s for s in dash["slices"]}
    rows = []
    for tab in dash["layout"]["tabs"]:
        for pos, c in enumerate(tab["charts"]):
            s = by_id.get(c["chart_id"])
            if s:
                rows.append((tab["label"], pos, s))
    return rows


def token_sim(a, b):
    ta, tb = set(norm(a).split()), set(norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def compare_slices(canon, other, tenant, renames, tab_matches):
    """Match other's slices to canonical; append rename proposals; return cell notes.

    tab_matches collects (canon_tab_label, other_tab_label) pairs for every
    slice-level match, as content evidence for tab-rename proposals.
    """
    canon_rows = slice_rows(canon)
    other_rows = slice_rows(other)
    canon_keys = {(norm(s["name"]), s["viz_type"]) for _, _, s in canon_rows}
    notes, matched_other = [], set()

    for tab_label, pos, cs in canon_rows:
        # exact (normalized name, viz) match anywhere
        hit = next((o for o in other_rows
                    if (norm(o[2]["name"]), o[2]["viz_type"]) == (norm(cs["name"]), cs["viz_type"])
                    and o[2]["id"] not in matched_other), None)
        conf = "HIGH"
        if hit is None:
            # name match, any viz (viz divergence noted, not renamed)
            hit = next((o for o in other_rows
                        if norm(o[2]["name"]) == norm(cs["name"]) and o[2]["id"] not in matched_other), None)
            if hit:
                matched_other.add(hit[2]["id"])
                tab_matches.append((tab_label, hit[0]))
                notes.append(f"VIZ-DIFF: '{cs['name']}' is {hit[2]['viz_type']} (canonical {cs['viz_type']})")
                continue
            # same viz + name containment or token similarity >= 0.7 — both MEDIUM:
            # a wording change can change the metric's meaning, so a human confirms.
            candidates = [o for o in other_rows
                          if o[2]["viz_type"] == cs["viz_type"] and o[2]["id"] not in matched_other]
            contain = next((o for o in candidates
                            if norm(cs["name"]) in norm(o[2]["name"])
                            or norm(o[2]["name"]) in norm(cs["name"])), None)
            if contain is not None:
                hit, conf = contain, "MEDIUM"
            else:
                scored = sorted(((token_sim(o[2]["name"], cs["name"]), o) for o in candidates),
                                key=lambda x: -x[0])
                if scored and scored[0][0] >= 0.7:
                    hit, conf = scored[0][1], "MEDIUM"
        if hit is None:
            notes.append(f"MISSING: '{cs['name']}' [{cs['viz_type']}]")
            continue
        matched_other.add(hit[2]["id"])
        tab_matches.append((tab_label, hit[0]))
        if hit[2]["name"] != cs["name"]:
            locked = hit[2]["id"] in UNTOUCHABLE_SLICES
            renames.append({
                "tenant": tenant, "superset_dash": other["id"], "object_type": "slice",
                "object_id": hit[2]["id"], "current_name": hit[2]["name"],
                "proposed_name": cs["name"],
                "confidence": "LOCKED-NEEDS-APPROVAL" if locked else conf,
                "evidence": f"viz={hit[2]['viz_type']} tab='{hit[0]}' pos={hit[1]}",
                "notes": ("slice 43 is on the UNTOUCHABLE list" if locked else
                          ("metric wording differs — confirm chart semantics before rename"
                           if conf == "MEDIUM" else "")),
            })
    for o in other_rows:
        if o[2]["id"] not in matched_other and (norm(o[2]["name"]), o[2]["viz_type"]) not in canon_keys:
            notes.append(f"EXTRA (no canonical counterpart): '{o[2]['name']}' [{o[2]['viz_type']}]")
    return notes


def compare_tabs(canon, other, tenant, renames, tab_matches):
    """A differently-named tab is only a rename candidate when slice-level
    matching tied its CONTENT to the canonical tab — otherwise it is a
    missing/extra tab, and renaming would mislabel different content."""
    ct = [t["label"] for t in canon["layout"]["tabs"]]
    ot = [t["label"] for t in other["layout"]["tabs"]]
    evidence = set(tab_matches)
    notes = []
    proposed_from = set()
    for i, label in enumerate(ct):
        if i < len(ot) and ot[i] != label:
            if (label, ot[i]) in evidence:
                node = other["layout"]["tabs"][i]["node"]
                proposed_from.add(ot[i])
                renames.append({
                    "tenant": tenant, "superset_dash": other["id"], "object_type": "tab",
                    "object_id": node, "current_name": ot[i], "proposed_name": label,
                    "confidence": "MEDIUM", "evidence": f"tab position {i+1}, content matches",
                    "notes": "tab label only — node id untouched",
                })
            else:
                notes.append(f"MISSING TAB: '{label}' (position {i+1} holds unrelated '{ot[i]}')")
        elif i >= len(ot):
            notes.append(f"MISSING TAB: '{label}'")
    for label in ot:
        if label not in ct and label not in proposed_from:
            notes.append(f"EXTRA TAB: '{label}'")
    return notes


def compare_filters(canon, other, tenant, renames):
    cf = {f["column"]: f for f in canon["native_filters"]}
    of = {f["column"]: f for f in other["native_filters"]}
    notes = []
    for col, f in cf.items():
        o = of.get(col)
        if o is None:
            notes.append(f"MISSING FILTER: '{f['name']}' (col={col})")
            continue
        if o["name"] != f["name"]:
            renames.append({
                "tenant": tenant, "superset_dash": other["id"], "object_type": "filter",
                "object_id": o["id"], "current_name": o["name"], "proposed_name": f["name"],
                "confidence": "HIGH", "evidence": f"column={col}", "notes": "display name only",
            })
        if o["multi_select"] != f["multi_select"]:
            notes.append(f"FILTER '{f['name']}': multi_select {o['multi_select']} vs canonical {f['multi_select']}")
    for col, o in of.items():
        if col not in cf:
            notes.append(f"EXTRA FILTER: '{o['name']}' (col={col})")
    return notes


def css_check(dash):
    markers = set(dash["css_markers"])
    ok_top = any("HIDE-TOPTABS" in m for m in markers)
    ok_fb = any("HIDE-FILTERBAR" in m for m in markers)
    return ("MATCH" if ok_top and ok_fb else
            "DRIFT: missing " + "/".join(x for x, ok in
                                         [("toptabs", ok_top), ("filterbar", ok_fb)] if not ok))


def alerts_matrix(alerts, out):
    cat = [p["rule_key"] for p in alerts["preset_catalogue"]]
    tenants = sorted(alerts["tenants"])
    out.write("\n### Alert rules — enabled state (policy: same everywhere)\n\n")
    out.write("| rule_key | " + " | ".join(t.upper() for t in tenants) + " |\n")
    out.write("|---" * (len(tenants) + 1) + "|\n")
    drift = []
    for rk in cat:
        cells = []
        states = {}
        for t in tenants:
            r = alerts["tenants"][t]["rules"].get(rk)
            state = "—" if r is None else ("ON" if r["is_active"] else "off")
            states[t] = state
            cells.append(state)
        out.write(f"| {rk} | " + " | ".join(cells) + " |\n")
        if len(set(states.values())) > 1:
            drift.append((rk, states))
    out.write("\n### Alert rules — structural drift (tuned values excluded)\n\n")
    base_t = "wm"
    any_struct = False
    for rk in cat:
        base = alerts["tenants"][base_t]["rules"].get(rk, {})
        base_s = {k: v for k, v in (base.get("condition_structure") or {}).items()
                  if k not in ALERT_TUNED_KEYS}
        for t in tenants:
            r = alerts["tenants"][t]["rules"].get(rk)
            if r is None:
                out.write(f"- {t.upper()} {rk}: row MISSING\n"); any_struct = True; continue
            s = {k: v for k, v in (r.get("condition_structure") or {}).items()
                 if k not in ALERT_TUNED_KEYS}
            if s != base_s:
                out.write(f"- {t.upper()} {rk}: structure {s} != WM {base_s}\n"); any_struct = True
    if not any_struct:
        out.write("- none — all four tenants structurally identical\n")
    return drift


def main():
    sup = {env: load(f"superset_{env}.json") for env in ("dev", "prod")}
    alerts = {env: load(f"alerts_{env}.json") for env in ("dev", "prod")}
    renames = []
    out = io.StringIO()
    out.write("# Tenant parity matrix — JY / PW / WM / DA\n")
    out.write(f"\nGenerated from: superset_dev/prod.json ({sup['dev']['generated_at_utc']} / "
              f"{sup['prod']['generated_at_utc']}), alerts_dev/prod.json.\n")
    out.write("\nCanonical axis: WM (dash 6). Cells compare each tenant to WM on DEV; "
              "a separate section compares dev↔prod per tenant.\n")

    canon = sup["dev"]["dashboards"][CANON_DASH]
    for did in DASH_ORDER:
        tenant = TENANT_BY_DASH[did]
        dash = sup["dev"]["dashboards"][did]
        out.write(f"\n## {tenant} (Superset dash {did}) vs canonical\n\n")
        if did == CANON_DASH:
            out.write("- CANONICAL reference\n")
            out.write(f"- css: {css_check(dash)}\n")
            continue
        tab_matches = []
        slice_notes = compare_slices(canon, dash, tenant, renames, tab_matches)
        for label, notes in (("Tabs", compare_tabs(canon, dash, tenant, renames, tab_matches)),
                             ("Slices", slice_notes),
                             ("Filters", compare_filters(canon, dash, tenant, renames))):
            out.write(f"- **{label}**: " + ("MATCH (after proposed renames)\n" if not notes else "\n"))
            for n in notes:
                out.write(f"  - {n}\n")
        out.write(f"- **Embed CSS**: {css_check(dash)}\n")

    out.write("\n## Dev ↔ prod drift per tenant\n\n")
    for did in DASH_ORDER:
        tenant = TENANT_BY_DASH[did]
        d, p = sup["dev"]["dashboards"][did], sup["prod"]["dashboards"][did]
        rows = []
        if set(d["label_colors_keys"]) != set(p["label_colors_keys"]):
            rows.append(f"label_colors: dev {len(d['label_colors_keys'])} keys vs prod "
                        f"{len(p['label_colors_keys'])} — dev-only: "
                        f"{sorted(set(d['label_colors_keys']) - set(p['label_colors_keys']))[:12]}")
        dd = {x["id"]: x for x in d["datasets"]}
        pdd = {x["id"]: x for x in p["datasets"]}
        for i in sorted(set(dd) | set(pdd)):
            a, b = dd.get(i), pdd.get(i)
            if not a or not b:
                rows.append(f"dataset {i}: only in {'dev' if a else 'prod'}")
            elif a["sql_norm_md5"] != b["sql_norm_md5"]:
                rows.append(f"dataset {i} ({a['table_name']}): SQL DIFFERS dev↔prod")
        if [t["label"] for t in d["layout"]["tabs"]] != [t["label"] for t in p["layout"]["tabs"]]:
            rows.append("tab labels differ dev↔prod")
        dn = {(s["name"], s["viz_type"]) for s in d["slices"]}
        pn = {(s["name"], s["viz_type"]) for s in p["slices"]}
        if dn != pn:
            rows.append(f"slice sets differ: dev-only {dn - pn}, prod-only {pn - dn}")
        stale = [s["id"] for s in d["slices"] if s["layout_slice_name_stale"]]
        if stale:
            rows.append(f"stale position_json sliceName copies (dev): slices {stale}")
        out.write(f"- **{tenant}**: " + ("in sync\n" if not rows else "\n"))
        for r in rows:
            out.write(f"  - {r}\n")

    out.write("\n## Alerts (dev)\n")
    enabled_drift = alerts_matrix(alerts["dev"], out)
    out.write("\n### Alerts dev ↔ prod\n\n")
    diff = []
    for t in sorted(alerts["dev"]["tenants"]):
        for rk, r in alerts["dev"]["tenants"][t]["rules"].items():
            pr = alerts["prod"]["tenants"].get(t, {}).get("rules", {}).get(rk)
            if pr is None:
                diff.append(f"{t.upper()} {rk}: missing on prod"); continue
            for field in ("is_active", "severity_default", "condition_structure",
                          "condition_tuned_values"):
                if r[field] != pr[field]:
                    diff.append(f"{t.upper()} {rk}.{field}: dev={r[field]} prod={pr[field]}")
    if diff:
        for x in diff:
            out.write(f"- {x}\n")
    else:
        out.write("- fully in sync\n")

    (AUDITS / "parity_matrix.md").write_text(out.getvalue(), encoding="utf-8")

    with open(AUDITS / "proposed_renames.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["tenant", "superset_dash", "object_type", "object_id",
                                           "current_name", "proposed_name", "confidence",
                                           "evidence", "notes"])
        w.writeheader()
        w.writerows(renames)

    print(f"wrote {AUDITS / 'parity_matrix.md'} and proposed_renames.csv "
          f"({len(renames)} rename proposals, {len(enabled_drift)} alert enabled-state drifts)")


if __name__ == "__main__":
    main()
