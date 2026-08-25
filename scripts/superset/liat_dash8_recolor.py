#!/usr/bin/env python3
"""Recolour the provisioned Liat dashboard 8 from blue-anchored to red-anchored.

Run inside the superset container (BACK UP superset.db FIRST):
    docker exec cpi-superset-1 python3 /tmp/liat_dash8_recolor.py          # dry run
    docker exec cpi-superset-1 python3 /tmp/liat_dash8_recolor.py --apply
    docker exec cpi-superset-1 python3 /tmp/liat_dash8_recolor.py --revert <backup.json>

superset_provision_liat.py originally wrote the blue-anchored label_colors
(5L = ocean #1B5FA8, teal-green/violet measures). The palette was re-anchored
on the logo red (docs/liat-palette.md, 2026-08-25) and the provisioning
script now carries the red values — but dashboard 8 already exists, so this
script retargets it in place rather than re-provisioning.

It SETS the value of each key below on dashboard 8's
json_metadata.label_colors and on every dash-8 slice's params /
query_context.form_data label_colors (all three places bind, per the palette
doc §6), plus json_metadata.color_scheme_domain. Keys it does not name —
including any carrier keys liat_dash8_carrier_keys.py adds later — are left
untouched. A key-level JSON backup of every prior value is written first and
--revert restores exactly those values.
"""
import json
import sqlite3
import sys
import datetime

DB = "/app/superset_home/superset.db"
DASH = 8

# key -> new value. The 5L brand keys, both measure families, the
# recommendation traffic light and the fare-composition metrics. The
# availability-marker keys (Sold out / Not on sale) are semantic, not brand,
# and are deliberately absent — they keep their amber/grey.
NEW_VALUES = {
    # ── 5L brand identity (Palette A slot 1) ──
    "5L": "#D02127",
    "Min Fare, 5L": "#D02127",
    "Max Fare, 5L": "#D02127",
    "Lowest Available Fare, 5L": "#D02127",
    "Avg Fare, 5L": "#D02127",
    # ── Palette B (velocity measures) ──
    "Capacity": "#DE8078",
    "Current Booking": "#D02127",
    "Actual Seat Factor (1)": "#0375B4",
    "Forecasted SF (1)": "#8B5CF6",
    "Actual Seat Factor": "#0375B4",
    "Forecasted SF": "#8B5CF6",
    # ── Palette C (recommendations; Reduce = brand red, WinAir scope rule) ──
    "Reduce": "#D02127",
    "Monitor": "#C08A00",
    "No Change": "#64748B",
    "Consider Increase": "#1BAF7A",
    # ── Fare Composition metrics — all three logo families ──
    "Base": "#D02127",
    "Tax": "#C08A00",
    "YQ": "#0375B4",
}

NEW_DOMAIN = ["#D02127", "#0375B4", "#C08A00", "#275AA1", "#2E7D32",
              "#D6208F", "#A05A2C", "#9B4FD8", "#64748B", "#0F766E"]


def set_values(label_colors, prior, where):
    """Set each NEW_VALUES key that exists (or is missing) and record priors."""
    touched = 0
    for k, v in NEW_VALUES.items():
        old = label_colors.get(k)
        if old == v:
            continue
        prior.setdefault(where, {})[k] = old  # None = key did not exist
        label_colors[k] = v
        touched += 1
    return touched


def main():
    apply_ = "--apply" in sys.argv
    if "--revert" in sys.argv:
        return revert(sys.argv[sys.argv.index("--revert") + 1])

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    jm_row = c.execute("SELECT json_metadata FROM dashboards WHERE id=?", (DASH,)).fetchone()
    assert jm_row, f"dashboard {DASH} does not exist"
    jm = json.loads(jm_row["json_metadata"])
    slices = c.execute(
        "SELECT s.id, s.params, s.query_context FROM slices s "
        "JOIN dashboard_slices ds ON ds.slice_id = s.id WHERE ds.dashboard_id=?",
        (DASH,)).fetchall()

    prior = {}
    total = 0
    jm.setdefault("label_colors", {})
    total += set_values(jm["label_colors"], prior, "dashboard")
    old_domain = jm.get("color_scheme_domain")
    domain_changes = old_domain != NEW_DOMAIN

    slice_updates = []
    for s in slices:
        params = json.loads(s["params"]) if s["params"] else {}
        if isinstance(params.get("label_colors"), dict):
            total += set_values(params["label_colors"], prior, f"slice:{s['id']}:params")
        qc = None
        if s["query_context"]:
            qc = json.loads(s["query_context"])
            fd = qc.get("form_data")
            if isinstance(fd, dict) and isinstance(fd.get("label_colors"), dict):
                total += set_values(fd["label_colors"], prior, f"slice:{s['id']}:qc")
        slice_updates.append((json.dumps(params),
                              json.dumps(qc) if qc is not None else s["query_context"],
                              s["id"]))

    print(f"{total} key-value changes across {len(prior)} objects"
          f"{'; color_scheme_domain updated' if domain_changes else ''}.")
    if not apply_:
        for where, keys in sorted(prior.items()):
            print(f"  {where}: {sorted(keys)}")
        print("\nDRY RUN — pass --apply to write. No changes made.")
        con.close()
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"/app/superset_home/liat_recolor_backup_{stamp}.json"
    with open(backup_path, "w") as f:
        json.dump({"dashboard": DASH, "prior": prior,
                   "prior_domain": old_domain}, f, indent=1)
    print("backup:", backup_path)

    if domain_changes:
        jm["color_scheme_domain"] = NEW_DOMAIN
    c.execute("UPDATE dashboards SET json_metadata=? WHERE id=?", (json.dumps(jm), DASH))
    for params_s, qc_s, sid in slice_updates:
        c.execute("UPDATE slices SET params=?, query_context=? WHERE id=?",
                  (params_s, qc_s, sid))
    con.commit()
    con.close()
    print("APPLIED.")


def revert(backup_path):
    with open(backup_path) as f:
        b = json.load(f)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    def restore(label_colors, priors):
        for k, old in priors.items():
            if old is None:
                label_colors.pop(k, None)
            else:
                label_colors[k] = old

    for where, priors in b["prior"].items():
        if where == "dashboard":
            jm = json.loads(c.execute("SELECT json_metadata FROM dashboards WHERE id=?",
                                      (b["dashboard"],)).fetchone()[0])
            restore(jm.get("label_colors", {}), priors)
            jm["color_scheme_domain"] = b["prior_domain"]
            c.execute("UPDATE dashboards SET json_metadata=? WHERE id=?",
                      (json.dumps(jm), b["dashboard"]))
        else:
            _, sid, field = where.split(":")
            row = c.execute("SELECT params, query_context FROM slices WHERE id=?",
                            (int(sid),)).fetchone()
            if field == "params":
                params = json.loads(row["params"])
                restore(params.get("label_colors", {}), priors)
                c.execute("UPDATE slices SET params=? WHERE id=?",
                          (json.dumps(params), int(sid)))
            else:
                qc = json.loads(row["query_context"])
                restore(qc.get("form_data", {}).get("label_colors", {}), priors)
                c.execute("UPDATE slices SET query_context=? WHERE id=?",
                          (json.dumps(qc), int(sid)))
    con.commit()
    con.close()
    print("REVERTED", backup_path)


if __name__ == "__main__":
    main()
