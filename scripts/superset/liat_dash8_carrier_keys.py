#!/usr/bin/env python3
"""Assign Liat (5L) competitor colour slots and write their label_colors keys.

Run inside the superset container AFTER the first Liat ingest commits:
    docker exec cpi-superset-1 python3 /tmp/liat_dash8_carrier_keys.py          # dry run
    docker exec cpi-superset-1 python3 /tmp/liat_dash8_carrier_keys.py --apply
    docker exec cpi-superset-1 python3 /tmp/liat_dash8_carrier_keys.py --revert <backup.json>

superset_provision_liat.py deliberately writes no competitor keys: slots 2-8
of Palette A are assigned by DESCENDING ROW VOLUME in the ingested data
(docs/liat-palette.md §2), which does not exist at provisioning time. This
script closes that gap additively, the way da_dash7_exp_keys.py did for Exp:

  1. reads competitor volumes from vw_airline_cpi_5l_snapshot (postgres),
  2. assigns slots 2-8 in descending volume (ties broken alphabetically so
     the run is reproducible), overflow taking the neutral fallbacks in list
     order — never a ninth hue,
  3. builds the nine key spellings per carrier that Superset can produce
     (bare code, four "<metric>, <code>" composites, and the four
     sold-out / not-on-sale marker keys incl. the query-B " (1)" suffix),
  4. MERGES them into dashboard 8's json_metadata.label_colors and every
     dash-8 slice's params/query_context label_colors. Existing keys are
     never overwritten (additive-only); a key-level JSON backup is written
     first and --revert restores exactly those keys.

After --apply, three follow-ups:
  1. paste the printed volume/slot table into docs/liat-palette.md §2;
  2. mirror the same assignment into LIAT_CARRIERS.known in
     apps/web/src/components/dashboard/tenantCarrierColors.ts — the native
     Latest Prices panel and the embedded dashboard must colour each carrier
     identically;
  3. verify with an UNSCOPED guest token — a cap_date-scoped PASS can hide a
     carrier whose rows sit outside the tested date (the DreamAir Exp lesson).
"""
import json
import os
import sqlite3
import sys
import datetime

DB = "/app/superset_home/superset.db"
DASH = 8

# postgres DSN: compose-default credentials, overridable.
PG_DSN = os.environ.get("CPI_PG_DSN", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")

# docs/liat-palette.md §2 — slots 2..8 then the neutral fallbacks, fixed
# order. Slots 2-4 are the logo's own colours (swoosh azure, gold, wordmark
# blue), so the three busiest competitors wear logo colours. Only the two
# neutral fallbacks: overflow past them folds into "Other", never a new hue.
SLOT_HEXES = ["#0375B4", "#C08A00", "#275AA1", "#2E7D32",
              "#D6208F", "#A05A2C", "#9B4FD8"]
FALLBACKS = ["#64748B", "#0F766E"]

SOLD_OUT = "#F39C12"
NOT_ON_SALE = "#9E9E9E"
COMPOSITE_PREFIXES = ["Min Fare", "Max Fare", "Lowest Available Fare", "Avg Fare"]


def carrier_volumes():
    import psycopg2
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT comp_al, count(*) AS n
        FROM vw_airline_cpi_5l_snapshot
        WHERE comp_al IS NOT NULL AND comp_al <> '' AND comp_al <> '5L'
        GROUP BY comp_al
        ORDER BY n DESC, comp_al ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def assign_slots(volumes):
    hexes = SLOT_HEXES + FALLBACKS
    if len(volumes) > len(hexes):
        print(f"WARNING: {len(volumes)} competitors but only {len(hexes)} "
              f"slots+fallbacks; the smallest {len(volumes) - len(hexes)} get no key "
              f"and will fall through to the scheme — fold them into 'Other' instead.")
    return {code: hexes[i] for i, (code, _n) in enumerate(volumes) if i < len(hexes)}


def build_keys(assignment):
    out = {}
    for code, hexv in assignment.items():
        out[code] = hexv
        for pfx in COMPOSITE_PREFIXES:
            out[f"{pfx}, {code}"] = hexv
        out[f"Sold out, {code}"] = SOLD_OUT
        out[f"Not on sale, {code}"] = NOT_ON_SALE
        out[f"Sold out, {code} (1)"] = SOLD_OUT
        out[f"Not on sale, {code} (1)"] = NOT_ON_SALE
    return out


def merge_into(obj_label_colors, new_keys, added, where):
    """Additive merge: existing keys win, and each add is recorded."""
    for k, v in new_keys.items():
        if k not in obj_label_colors:
            obj_label_colors[k] = v
            added.setdefault(where, []).append(k)


def main():
    apply_ = "--apply" in sys.argv
    if "--revert" in sys.argv:
        return revert(sys.argv[sys.argv.index("--revert") + 1])

    volumes = carrier_volumes()
    if not volumes:
        print("ABORT: vw_airline_cpi_5l_snapshot has no competitor rows — "
              "ingest the Liat data first.")
        return
    assignment = assign_slots(volumes)
    print(f"{'carrier':<10}{'rows':>12}  slot hex")
    for i, (code, n) in enumerate(volumes):
        hexv = assignment.get(code, "(none — overflow)")
        tag = f"slot {i + 2}" if i < len(SLOT_HEXES) else f"fallback {i - len(SLOT_HEXES) + 1}"
        print(f"{code:<10}{n:>12}  {hexv}  ({tag})")
    new_keys = build_keys(assignment)
    print(f"\n{len(new_keys)} keys to merge into dashboard {DASH} + its slices.")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    jm_row = c.execute("SELECT json_metadata FROM dashboards WHERE id=?", (DASH,)).fetchone()
    assert jm_row, f"dashboard {DASH} does not exist — run superset_provision_liat.py first"
    slices = c.execute(
        "SELECT s.id, s.params, s.query_context FROM slices s "
        "JOIN dashboard_slices ds ON ds.slice_id = s.id WHERE ds.dashboard_id=?",
        (DASH,)).fetchall()

    if not apply_:
        print("\nDRY RUN — pass --apply to write. No changes made.")
        con.close()
        return

    # key-level backup: exactly what to delete on revert
    added = {}
    jm = json.loads(jm_row["json_metadata"])
    jm.setdefault("label_colors", {})
    merge_into(jm["label_colors"], new_keys, added, "dashboard")

    slice_updates = []
    for s in slices:
        params = json.loads(s["params"]) if s["params"] else {}
        if isinstance(params.get("label_colors"), dict):
            merge_into(params["label_colors"], new_keys, added, f"slice:{s['id']}:params")
        qc = None
        if s["query_context"]:
            qc = json.loads(s["query_context"])
            fd = qc.get("form_data")
            if isinstance(fd, dict) and isinstance(fd.get("label_colors"), dict):
                merge_into(fd["label_colors"], new_keys, added, f"slice:{s['id']}:qc")
        slice_updates.append((json.dumps(params),
                              json.dumps(qc) if qc is not None else s["query_context"],
                              s["id"]))

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"/app/superset_home/liat_carrier_keys_backup_{stamp}.json"
    with open(backup_path, "w") as f:
        json.dump({"dashboard": DASH, "added": added, "keys": new_keys}, f, indent=1)
    print("backup:", backup_path)

    c.execute("UPDATE dashboards SET json_metadata=? WHERE id=?", (json.dumps(jm), DASH))
    for params_s, qc_s, sid in slice_updates:
        c.execute("UPDATE slices SET params=?, query_context=? WHERE id=?",
                  (params_s, qc_s, sid))
    con.commit()
    con.close()
    print(f"APPLIED: {sum(len(v) for v in added.values())} key writes across "
          f"{len(added)} objects.")
    print("Now update docs/liat-palette.md §2 with the table above, and verify "
          "with an UNSCOPED guest token.")


def revert(backup_path):
    with open(backup_path) as f:
        b = json.load(f)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    c = con.cursor()
    for where, keys in b["added"].items():
        if where == "dashboard":
            jm = json.loads(c.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                                      (b["dashboard"],)).fetchone()[0])
            for k in keys:
                jm.get("label_colors", {}).pop(k, None)
            c.execute("UPDATE dashboards SET json_metadata=? WHERE id=?",
                      (json.dumps(jm), b["dashboard"]))
        else:
            _, sid, field = where.split(":")
            row = c.execute("SELECT params, query_context FROM slices WHERE id=?",
                            (int(sid),)).fetchone()
            if field == "params":
                params = json.loads(row["params"])
                for k in keys:
                    params.get("label_colors", {}).pop(k, None)
                c.execute("UPDATE slices SET params=? WHERE id=?",
                          (json.dumps(params), int(sid)))
            else:
                qc = json.loads(row["query_context"])
                for k in keys:
                    qc.get("form_data", {}).get("label_colors", {}).pop(k, None)
                c.execute("UPDATE slices SET query_context=? WHERE id=?",
                          (json.dumps(qc), int(sid)))
    con.commit()
    con.close()
    print("REVERTED", backup_path)


if __name__ == "__main__":
    main()
