# Roadmap & Recommended Next Phases

## Phase 3: Stabilization & Test Coverage (Priority: High)
- **Objective**: Implement comprehensive API tests and fix the JY ingestion UUID bug.
- **Pre-requisites**: None.
- **Estimated Prompts**: 5-7.
- **Smoke-test gate criteria**: All `pytest` tests pass successfully in CI/CD or local dev environment.
- **Pre-phase backup plan**: `tar -czf cpi_project.tar.gz ./CPI` and `pg_dump` of `cpi_db`.
- **Rollback procedure**: Restore snapshot database from `.sql` file, git checkout `master`.

## Phase 4: Frontend Admin Completeness (Priority: Medium)
- **Objective**: Implement the missing tenant and user management UIs.
- **Pre-requisites**: Phase 3.
- **Estimated Prompts**: 3-5.
- **Smoke-test gate criteria**: A platform admin can successfully create a new user via the UI.
- **Pre-phase backup plan**: Same as Phase 3.
- **Rollback procedure**: `git checkout` to pre-phase state.

## Phase 5: Superset UI Polish (Priority: Low)
- **Objective**: Implement the vertical filter bar and refine dashboards.
- **Pre-requisites**: None.
- **Estimated Prompts**: 1.
- **Smoke-test gate criteria**: Superset JSON metadata shows `filter_bar_orientation: VERTICAL`.
- **Pre-phase backup plan**: Backup `superset.db`.
- **Rollback procedure**: Restore `superset.db`.

## Recommended Course Corrections
1. **Immediate P0 Fix**: Correct the `TENANTS["JY"]["id"]` hardcoded UUID in `ingest_daily.py` before any further data ingestions occur, otherwise JY data will be siloed into Skywave.
2. **Explicit Pinning**: Update `requirements.txt` to explicitly include `bcrypt>=4.0,<4.1`.
