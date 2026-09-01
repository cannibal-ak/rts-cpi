#!/usr/bin/env python3
"""READ-ONLY cross-tenant alert-settings inventory.

Dumps, for JY/PW/WM/DA: every alert_rule row (rule_key, is_active, severity,
condition_json — split into structural keys vs tuned numeric values), the
tenant_feature 'alerts' flags, and the code-side preset catalogue, so the
parity report can compare STRUCTURE across tenants while leaving per-tenant
tuned thresholds alone.

Run inside the api container (dev or prod):
    docker exec -i cpi-api-1 python3 - --env-label dev < parity_alerts_inventory.py > out.json

Uses the non-RLS SessionLocal (read-only SELECTs; the audit needs all four
tenants in one pass, and this session never writes).
"""
import argparse
import datetime
import json
import sys

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.alerts.presets import PRESET_ORDER, PRESETS

TENANT_SLUGS = ("jy", "pw", "wm", "da")

# Keys whose VALUES are per-tenant tuned by policy (2026-08-31 tuning) and are
# therefore reported separately, not compared for drift.
TUNED_VALUE_KEYS = {"move_pct", "min_abs_move", "value", "min_gap_pct", "max_rank"}


def split_condition(cond):
    cond = cond or {}
    structure = {}
    tuned = {}
    for key in sorted(cond):
        val = cond[key]
        if key in TUNED_VALUE_KEYS:
            tuned[key] = val
        elif isinstance(val, list):
            structure[key] = sorted(str(v) for v in val)
        else:
            structure[key] = val
    return structure, tuned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-label", default="unknown")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rules = db.execute(text(
            "SELECT t.slug AS tenant, r.rule_key, r.preset_key, r.is_active, "
            "       r.is_preset, r.severity_default, r.name, r.condition_json, "
            "       r.updated_at::text AS updated_at "
            "FROM alert_rule r JOIN tenant t ON t.id = r.tenant_id "
            "WHERE t.slug = ANY(:slugs) ORDER BY t.slug, r.rule_key"
        ), {"slugs": list(TENANT_SLUGS)}).mappings().all()

        features = db.execute(text(
            "SELECT t.slug AS tenant, f.code, f.enabled "
            "FROM tenant_feature f JOIN tenant t ON t.id = f.tenant_id "
            "WHERE f.code = 'alerts' AND t.slug = ANY(:slugs) ORDER BY t.slug"
        ), {"slugs": list(TENANT_SLUGS)}).mappings().all()
    finally:
        db.close()

    # "rules" holds preset rows only, so the cross-tenant structure diff stays
    # clean; user-created instances are per-tenant by nature and land under
    # "instances", visible to the audit without registering as drift.
    tenants = {slug: {"rules": {}, "instances": {}, "alerts_feature": None}
               for slug in TENANT_SLUGS}
    for row in rules:
        structure, tuned = split_condition(row["condition_json"])
        bucket = "rules" if row["is_preset"] else "instances"
        tenants[row["tenant"]][bucket][row["rule_key"]] = {
            "is_active": row["is_active"],
            "is_preset": row["is_preset"],
            "preset_key": row["preset_key"],
            "severity_default": row["severity_default"],
            "name": row["name"],
            "condition_structure": structure,
            "condition_tuned_values": tuned,
            "updated_at": row["updated_at"],
        }
    for row in features:
        tenants[row["tenant"]]["alerts_feature"] = row["enabled"]

    catalogue = []
    for key in PRESET_ORDER:
        p = PRESETS[key]
        catalogue.append({
            "rule_key": p.rule_key,
            "name": p.name,
            "severity_default": p.severity_default,
            "default_active": p.default_active,
            "requires_before_active": list(p.requires_before_active),
            "default_condition_keys": sorted(p.defaults().keys()),
            "tunable_keys": [t.key for t in p.tunables],
        })

    json.dump({
        "env_label": args.env_label,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "preset_catalogue": catalogue,
        "tenants": tenants,
    }, sys.stdout, indent=1, sort_keys=True, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
