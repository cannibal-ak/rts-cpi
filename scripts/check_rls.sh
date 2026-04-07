#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# check_rls.sh — CI/dev script to validate RLS is active
# on all tenant-owned tables and cross-tenant isolation works.
#
# Usage:
#   docker compose exec postgres bash /sample_data/scripts/check_rls.sh
#   OR
#   bash scripts/check_rls.sh  (from host, if psql is available)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-cpi_db}"
DB_SUPER="${DB_SUPER:-cpi}"
DB_APP_USER="${DB_APP_USER:-cpi_app}"

TENANT_A="a0000000-0000-0000-0000-000000000001"
TENANT_B="b0000000-0000-0000-0000-000000000002"

REQUIRED_RLS_TABLES=(
  app_user role_binding tenant_feature
  source_system source_connection source_file
  import_job import_batch ingest_error
  provider_contract
  alert_rule alert_event audit_event saved_view export_job
  airline_cpi_snapshot cfl_cpi_snapshot
)

REQUIRED_VIEWS=(
  vw_airline_cpi_jy_snapshot
  vw_airline_cpi_pw_snapshot
  vw_cfl_cpi_fjl_snapshot
  vw_import_jobs
  vw_alert_events
)

PASS=0
FAIL=0

ok()   { PASS=$((PASS+1)); echo "  ✅  $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌  $1"; }

psql_super() { psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_SUPER" -d "$DB_NAME" -t -A -c "$1"; }
psql_app()   { psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_APP_USER" -d "$DB_NAME" -t -A -c "$1"; }

echo ""
echo "═══════════════════════════════════════════════════"
echo "  RLS Validation Check"
echo "═══════════════════════════════════════════════════"

# ── 1. Check RLS is enabled ──────────────────────
echo ""
echo "1. Checking RLS enabled on required tables..."
for tbl in "${REQUIRED_RLS_TABLES[@]}"; do
  rls=$(psql_super "SELECT rowsecurity FROM pg_tables WHERE tablename='$tbl' AND schemaname='public';")
  if [[ "$rls" == "t" ]]; then
    ok "$tbl — RLS enabled"
  else
    fail "$tbl — RLS NOT enabled (got: $rls)"
  fi
done

# ── 2. Check Superset views exist ────────────────
echo ""
echo "2. Checking Superset views exist..."
for vw in "${REQUIRED_VIEWS[@]}"; do
  exists=$(psql_super "SELECT COUNT(*) FROM pg_views WHERE viewname='$vw' AND schemaname='public';")
  if [[ "$exists" == "1" ]]; then
    ok "$vw — exists"
  else
    fail "$vw — MISSING"
  fi
done

# ── 3. Cross-tenant isolation proof ──────────────
echo ""
echo "3. Cross-tenant isolation proof..."

# Tenant A should see airline data but NOT CFL data
a_airline=$(psql_app "SET app.current_tenant = '$TENANT_A'; SELECT COUNT(*) FROM airline_cpi_snapshot;")
a_cfl=$(psql_app "SET app.current_tenant = '$TENANT_A'; SELECT COUNT(*) FROM cfl_cpi_snapshot;")

if [[ "$a_airline" -gt 0 ]]; then
  ok "Tenant A sees $a_airline airline rows (own data)"
else
  fail "Tenant A sees 0 airline rows (expected >0)"
fi

if [[ "$a_cfl" -eq 0 ]]; then
  ok "Tenant A sees 0 CFL rows (correct isolation)"
else
  fail "Tenant A sees $a_cfl CFL rows (should be 0)"
fi

# Tenant B should see CFL data but NOT airline data
b_airline=$(psql_app "SET app.current_tenant = '$TENANT_B'; SELECT COUNT(*) FROM airline_cpi_snapshot;")
b_cfl=$(psql_app "SET app.current_tenant = '$TENANT_B'; SELECT COUNT(*) FROM cfl_cpi_snapshot;")

if [[ "$b_airline" -eq 0 ]]; then
  ok "Tenant B sees 0 airline rows (correct isolation)"
else
  fail "Tenant B sees $b_airline airline rows (should be 0)"
fi

if [[ "$b_cfl" -gt 0 ]]; then
  ok "Tenant B sees $b_cfl CFL rows (own data)"
else
  fail "Tenant B sees 0 CFL rows (expected >0)"
fi

# ── 4. Unset tenant sees nothing ─────────────────
echo ""
echo "4. Checking unset tenant returns zero rows..."
no_tenant=$(psql_app "SELECT COUNT(*) FROM airline_cpi_snapshot;")
if [[ "$no_tenant" -eq 0 ]]; then
  ok "No tenant context → 0 airline rows (safe default)"
else
  fail "No tenant context → $no_tenant airline rows (should be 0!)"
fi

# ── Summary ──────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════════"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
