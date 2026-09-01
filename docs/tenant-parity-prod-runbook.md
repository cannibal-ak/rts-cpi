# Tenant-parity prod deploy runbook (Phase 5)

Run only after Gate 2 (dev verified + user sign-off). Prod = root@187.127.130.130,
repo /opt/cpi, baked images, superset container `cpi-superset-1`, postgres
`cpi-postgres-1`. Prod cannot fetch GitHub — code travels by git bundle.
Slice/dashboard ids verified IDENTICAL dev↔prod for dashes 1/3/6/7 (2026-08-31
audit), but every script asserts current state and aborts on drift anyway.

**Standing prod rules (never freehand):**
- every compose command carries `--env-file .env.prod`
- never plain `up -d` (pg healthcheck landmine) — always `up -d --no-deps <services>`
- fresh prod inventory BEFORE any Superset write; timestamped superset.db
  backup before the first write of the day

## 0. Fresh prod inventory

    ssh root@187.127.130.130 "docker exec -i cpi-superset-1 python3 - --dashboards 1,3,6,7 --env-label prod" < scripts/superset/parity_inventory.py > audits/superset_prod.json
    ssh root@187.127.130.130 "docker exec -i -e PYTHONPATH=/app cpi-api-1 python3 - --env-label prod" < scripts/alerts/parity_alerts_inventory.py > audits/alerts_prod.json

Diff against dev expectations; any prod-only drift beyond the four known
items below stops the deploy for investigation.

## 1. Superset metadata (scripts, dash-by-dash, --dry-run reviewed before each --apply)

Each script takes its own full superset.db backup on apply. Order:

1. **JY ds13 fare fix (Gate 1 D4d, explicit approval)** — sync prod dataset
   13's SQL to dev's COALESCE form. One targeted UPDATE via a marked script
   with expected-old-SQL assertion + backup table (write it from dev's
   `SELECT sql FROM tables WHERE id=13`).
2. **JY renames**: `parity_rename.py --dry-run` then `--apply` (asserts prod's
   pre-rename titles; ids identical).
3. **JY backfill**: `parity_jy_backfill.py --dry-run` / `--apply`.
   NOTE: new slice/dataset ids on prod may differ from dev's (max(id)+1 on a
   different DB) — that is fine; nothing downstream hardcodes them.
4. **PW rebuild**: `parity_pw_rebuild.py --dry-run` / `--apply` (same note).
5. **WM slice 107 COALESCE**: external backup, then
   `SLICE_ID=107 da_slice120_coalesce.py` (same as dev).
6. **DA re-attach 122**: `parity_da_reattach.py --dry-run` / `--apply`.
7. **DA Exp colors (Gate 1 D4c)**: run `scripts/superset/da_dash7_exp_keys.py`
   on prod (dev already has the 9 keys; prod is at 94 vs dev 103).

## 2. Code deploy (api + web)

    # laptop
    git bundle create parity-<date>.bundle master..deploy/parity-<date>
    scp parity-<date>.bundle root@187.127.130.130:/opt/cpi/
    # prod
    cd /opt/cpi && git fetch parity-<date>.bundle deploy/parity-<date>:deploy/parity-<date>
    # BEFORE checkout: diff the prod-only files list (see liat deploy notes) —
    # especially any prod-only Chart-view date-overlay code in
    # DashboardViewerPage.tsx; merge, never overwrite.
    git checkout deploy/parity-<date>
    docker compose --env-file .env.prod build api web
    docker compose --env-file .env.prod up -d --no-deps api web worker beat

Changed code: superset.py (PW hidden_filter_columns → canonical 7),
tenantCarrierColors.ts (DA table), AirlineCpiPage.tsx (labels),
theme files + WinairTopFilterBar (skeleton count), new scripts/docs.
No alembic migration in this branch (confirm before deploy; if one appears,
remember the api entrypoint runs `alembic upgrade head` on boot).

## 3. Alerts (prod Postgres)

    # backup first
    docker exec cpi-postgres-1 psql -U cpi -d cpi_db -c "CREATE TABLE alert_rule_backup_parity_<date> AS SELECT * FROM alert_rule"

1. **DA tuning** (Gate 1 D4a): copy `da_alert_driver.py` + `da_apply_spec.json`
   into prod cpi-api-1, run with PYTHONPATH=/app. Same measured values as dev
   (DA's data is identical on both).
2. **WM cosmetic**: normalize `undercut_position.condition_json.routes` from
   `[]` to null via PATCH (or leave — semantically identical; do it for a
   clean matrix).
3. Targeted restart: `docker compose --env-file .env.prod up -d --no-deps worker beat`.

## 4. Verify prod (same suite as Gate 2)

    ssh root@…: docker cp mint_guest_tokens.py + verify_dashboard_colors.py into containers
    mint tokens (prod api) → verify dashes 1, 3, 6, 7 → expect 4× PASS
    re-run step-0 inventories → `python scripts/audit/parity_report.py` → all
    MATCH / documented EXCEPTION, alerts matrix all-ON, dev↔prod section clean

## 5. Land the branch

Host (canonical pusher): fetch + rebase + push `deploy/parity-<date>` and the
parity branch; merge to master per house flow.
