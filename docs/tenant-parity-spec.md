# Tenant parity spec — JY / PW / WM / DA

Approved 2026-08-31 (Gate 1). WM (Superset dash 6) is the canonical reference.
All four airline tenants present the same UI/UX, the same Superset chart & tab
names, and the same alert settings; only the data differs. Brand palettes are
deliberately per-tenant and are NOT synced.

Re-run the audit any time (read-only; also the regression gate for new tenants):

    ssh docker-host  "docker exec -i cpi-superset-1 python3 - --dashboards 1,3,6,7 --env-label dev"  < scripts/superset/parity_inventory.py  > audits/superset_dev.json
    ssh root@187.127.130.130 "docker exec -i cpi-superset-1 python3 - --dashboards 1,3,6,7 --env-label prod" < scripts/superset/parity_inventory.py > audits/superset_prod.json
    ssh docker-host  "docker exec -i -e PYTHONPATH=/app cpi-api-1 python3 - --env-label dev"  < scripts/alerts/parity_alerts_inventory.py > audits/alerts_dev.json
    ssh root@187.127.130.130 "docker exec -i -e PYTHONPATH=/app cpi-api-1 python3 - --env-label prod" < scripts/alerts/parity_alerts_inventory.py > audits/alerts_prod.json
    python scripts/audit/parity_report.py

## Canonical dashboard shape (WM, dash 6)

Tabs, in order, with their charts (slice titles are canon — every tenant uses
these exact titles):

| Tab | Charts (viz) |
|---|---|
| Avg_Fare | Lowest Available Fare & Availability by Travel_Date (mixed_timeseries) · Lowest Available Avg_Fare by Travel_Date (echarts_timeseries_bar) · Lowest Available Avg_Fare by Travel_Date (table) |
| Min/Max_Fare | Min/Max_Fare by Travel_Date (echarts_timeseries_line) · Min/Max_Fare by Travel_Date (table) |
| Competitor Breakdown | Competitor Breakdown (echarts_timeseries_bar) · Competitor Breakdown (table) · Fare Composition — Base / Tax / YQ (dist_bar) |
| Pricing Recommendations | Pricing Recommendations (table) · Pricing Recommendations — Summary (echarts_timeseries_bar) |
| Velocity | Booking, Seat Factor, Capacity (mixed_timeseries) · Deployed Capacity — Flights Operated by Airline (echarts_timeseries_bar) |

Canonical native filters (display names): Airline, Route (O&D), Flight Number,
Days to Departure, Price Position, Pricing Action, Cheapest Competitor,
Days Left, Aircraft, Leg/Segment, Stops, Trip Type.

Visible in the app's top filter bar (the rest are suppressed via
`hidden_filter_columns` in `apps/api/app/routers/superset.py`):
**Route (O&D), Flight Number, Days Left, Stops, Trip Type** — plus the
tenant's own-carrier column always hidden (`airline`, or `carrier` on PW).

Embed CSS: every dashboard carries a `*-EMBED-HIDE-TOPTABS` and a
`*-EMBED-HIDE-FILTERBAR` marked block (embedded view only). Revert CSS
BEFORE reverting app code, never after.

## Approved exceptions

| Item | Tenant | Reason |
|---|---|---|
| Slice 43 "Avg Fare by Travel Date" (line) stays as-is | JY | Untouchable list; no canonical counterpart (WM's first Avg_Fare chart is the availability mixed chart) |
| Fare Family filter (visible, 6th in bar) | JY | Data-driven: only JY carries fare families |
| Hidden filters Price Position / Pricing Action / Cheapest Competitor absent | JY | Invisible to users (suppressed everywhere); backfill optional |
| Own-carrier filter column is `carrier`, not `airline` | PW | Dataset schema; both are hidden from the bar, behavior identical |
| Old PW slices 76–83 detached but kept in Superset | PW | Superseded by the canonical rebuild (Gate 1 D2) |
| Trip Type filter effectively single-valued | DA, PW (OW-only feeds) | Data, not config |
| Velocity chart series differ (no forecast on JY) | JY | Data availability; chart name and shape are canonical |

## Alert policy

Catalogue (code, `apps/api/app/services/alerts/presets.py`): comp_price_move,
undercut_position, comp_price_threshold, stops_disadvantage, service_gap.

- Enabled-state: ALL FIVE active for every parity tenant (Gate 1 D4 turned on
  DA's remaining three).
- Structure (keys, grain, metric, notify flags): identical everywhere —
  structural drift is a defect.
- Tuned values (thresholds, move sizes, windows, routes, competitors): per
  tenant, measured from that tenant's data. Never copy numbers across tenants.
  Tuning provenance: JY/PW/WM 2026-08-31 harnesses under `scripts/alerts/`;
  DA tuned as part of the parity sync (PW harness re-pointed — DA data is
  PW-shaped).
- Gates that must list all four tenants: `ALERTS_MODULES`
  (`apps/web/src/alerts/alertsAccess.ts`) and `CPI_ALERTS_TENANT_CODES`
  (compose / .env.prod).

## Registry policy (frontend)

`CHROME_BY_TENANT` in `apps/web/src/components/dashboard/tenantChrome.ts` is
the single opt-in for the WinAir-family UX. Derived per-tenant sets (chart-view
retirement, carrier colors, labels) must be registries keyed the same way —
never re-keyed literals scattered per file.

## Traps (learned, do not relearn)

- `label_colors` keys bind to the SERIES names Superset builds and fail
  SILENTLY to `rts_cpi_palette[0]` forest green. Slice-title renames are safe;
  metric-label renames are NOT (dist_bar series = metric label;
  mixed_timeseries query-B keys get a literal `" (1)"` suffix). Verify with
  `scripts/superset/verify_dashboard_colors.py <dash> <unscoped-guest-token>`.
- Tab NODE ids are permalink anchors — rename labels (`meta.text`) only,
  never node ids.
- Dataset SQL does not travel with slice replication — md5-diff `tables.sql`
  dev↔prod after any Superset deploy (`parity_inventory.py` does this).
- Any newly VISIBLE filter column needs an index check first
  (EXPLAIN the distinct-values query; DA trip_type was 39s→3s).
- Superset mutations: sqlite3 direct, `--show/--dry-run/--apply/--revert`,
  timestamped IST superset.db backup before the first write, in-DB backup
  table, single transaction, dashboards allowlist {1,3,6,7}.
- Prod: every compose command carries `--env-file .env.prod`; never plain
  `up -d` (pg healthcheck) — `up -d --no-deps <services>`.

## Untouchables / out of scope

Slice 43 and dataset 13 (title/SQL frozen on dev; the one approved exception:
prod ds13 was synced to dev's COALESCE SQL per Gate 1 D4d). Dashboards 2 (FJL),
5 (SKY), 8 (5L) are never modified by parity work.
