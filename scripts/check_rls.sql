-- ═══════════════════════════════════════════════════════════════════
-- RLS Validation Script — check_rls.sql
-- ═══════════════════════════════════════════════════════════════════
-- Run with:  docker compose exec postgres psql -U cpi -d cpi_db -f /scripts/check_rls.sql
--
-- This script validates:
--   1. RLS is enabled on all tenant-owned tables
--   2. Correct policies exist
--   3. Cross-tenant reads return zero rows
-- ═══════════════════════════════════════════════════════════════════

\echo '══════════════════════════════════════════════════'
\echo '  1. RLS ENABLED CHECK'
\echo '══════════════════════════════════════════════════'

SELECT
    tablename,
    rowsecurity AS rls_enabled,
    forcerowsecurity AS rls_forced,
    CASE
        WHEN rowsecurity AND forcerowsecurity THEN '✓ OK'
        ELSE '✗ FAIL'
    END AS status
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'app_user', 'role_binding', 'tenant_feature',
    'source_system', 'source_connection', 'source_file',
    'import_job', 'import_batch', 'ingest_error',
    'provider_contract', 'alert_rule', 'alert_event',
    'audit_event', 'saved_view', 'export_job',
    'airline_cpi_snapshot', 'cfl_cpi_snapshot'
  )
ORDER BY tablename;

\echo ''
\echo '══════════════════════════════════════════════════'
\echo '  2. RLS POLICIES CHECK'
\echo '══════════════════════════════════════════════════'

SELECT
    schemaname,
    tablename,
    policyname,
    roles,
    cmd
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;

\echo ''
\echo '══════════════════════════════════════════════════'
\echo '  3. CROSS-TENANT ISOLATION PROOF'
\echo '══════════════════════════════════════════════════'

-- Use the cpi_app role (non-superuser, subject to RLS)
SET ROLE cpi_app;

-- Set context to Tenant A (Acme Airways)
SET app.current_tenant = 'a0000000-0000-0000-0000-000000000001';

\echo ''
\echo '--- As Tenant A: airline snapshots ---'
SELECT count(*) AS tenant_a_airline_rows FROM airline_cpi_snapshot;

\echo '--- As Tenant A: CFL snapshots (should be 0 — belongs to Tenant B) ---'
SELECT count(*) AS tenant_a_cfl_rows FROM cfl_cpi_snapshot;

\echo '--- As Tenant A: import jobs ---'
SELECT count(*) AS tenant_a_jobs FROM import_job;

\echo '--- As Tenant A: alert rules ---'
SELECT count(*) AS tenant_a_alerts FROM alert_rule;

-- Switch to Tenant B (Baltic Ferries)
SET app.current_tenant = 'b0000000-0000-0000-0000-000000000002';

\echo ''
\echo '--- As Tenant B: airline snapshots (should be 0 — belongs to Tenant A) ---'
SELECT count(*) AS tenant_b_airline_rows FROM airline_cpi_snapshot;

\echo '--- As Tenant B: CFL snapshots ---'
SELECT count(*) AS tenant_b_cfl_rows FROM cfl_cpi_snapshot;

\echo '--- As Tenant B: import jobs ---'
SELECT count(*) AS tenant_b_jobs FROM import_job;

\echo '--- As Tenant B: alert rules ---'
SELECT count(*) AS tenant_b_alerts FROM alert_rule;

-- No tenant set — should return 0 rows for everything
RESET app.current_tenant;

\echo ''
\echo '--- No tenant set: airline snapshots (should be 0) ---'
SELECT count(*) AS no_tenant_airline FROM airline_cpi_snapshot;

\echo '--- No tenant set: CFL snapshots (should be 0) ---'
SELECT count(*) AS no_tenant_cfl FROM cfl_cpi_snapshot;

-- Reset role
RESET ROLE;

\echo ''
\echo '══════════════════════════════════════════════════'
\echo '  4. SUPERSET VIEWS CHECK'
\echo '══════════════════════════════════════════════════'

SELECT viewname FROM pg_views
WHERE schemaname = 'public' AND viewname LIKE 'vw_%'
ORDER BY viewname;

\echo ''
\echo '══════════════════════════════════════════════════'
\echo '  VALIDATION COMPLETE'
\echo '══════════════════════════════════════════════════'
