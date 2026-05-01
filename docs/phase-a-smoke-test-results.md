# Phase A — Smoke Test Results

**Run date:** 2026-04-30
**Branch:** `feat/ingestion-overhaul-phase-a`
**Stack:** RTS CPI on `IN1PSDOCKER` (192.168.101.10), API at `http://localhost:8000`

**Test files used:**

| Path                          |  Size  | Purpose                                  |
| ----------------------------- | -----: | ---------------------------------------- |
| `/tmp/JY_010426.xlsx`         | 1.7 MB | Primary upload (copy of archived JY xlsx) |
| `/tmp/JY_010426_edited.xlsx` | 938 KB | Same filename, modified one cell → different SHA-256 |
| `/tmp/FOO_BAR.txt`            |    8 B | Bogus file for parser-rejection test      |

---

## Result summary

| # | Test                                            | Expected                          | Actual              | Pass |
| - | ----------------------------------------------- | --------------------------------- | ------------------- | ---- |
| 1 | Upload without JWT                              | 401                               | 401                 | ✓    |
| 2 | Upload as `jy@airline.com`                      | 403                               | 403                 | ✓    |
| 3 | Upload as `admin@skywave.com`                   | 200, status=STAGED                | 200, STAGED         | ✓    |
| 4 | Validate that job                               | VALIDATED with row counts         | VALIDATED, 7022/0   | ✓    |
| 5 | Commit that job                                 | COMMITTED, rows visible to JY     | 7022 rows, JY sees them | ✓ |
| 6 | Re-upload same file                             | duplicate=true, returns existing  | duplicate=true      | ✓    |
| 7 | Upload edited file (same name, different hash)  | conflict + existing_job_id        | conflict=true       | ✓    |
| 8 | Commit with `replace_existing=true`            | old=REPLACED, new=COMMITTED       | both states correct | ✓    |
| 9 | GET audit log                                   | all actions, correct actors       | 4 + 3 entries       | ✓    |
| 10| Upload bogus `FOO_BAR.txt`                      | parser rejection                  | 200 w/ per-file 400 | ✓    |

**Overall: 10 / 10 PASS**

---

## T1 — Upload without JWT → 401

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/upload \
       -F 'files=@/tmp/JY_010426.xlsx'
HTTP 401
{"detail":"Not authenticated"}
```

---

## T2 — Upload as `jy@airline.com` → 403

After adding `dependencies=[Depends(RequirePlatformAdmin())]` to the `/upload` route (so non-admin requests fail at the route level rather than per-file), this returns the expected HTTP 403:

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/upload \
       -H "Authorization: Bearer $JY_TOKEN" \
       -F 'files=@/tmp/JY_010426.xlsx'
HTTP 403
{"detail":"Forbidden: platform administrator access required"}
```

---

## T3 — Upload as `admin@skywave.com` → 200, STAGED

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/upload \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -F 'files=@/tmp/JY_010426.xlsx'
HTTP 200
```

Selected response fields:

```json
{
  "id":            "148dbc32-f446-4851-ac20-e1d9b28bf476",
  "tenant_id":     "dd000000-0000-0000-0000-000000000001",
  "tenant_code":   "JY",
  "domain":        "AIRLINE",
  "filename":      "JY_010426.xlsx",
  "file_hash":     "81a47a420d37b7ac5108f8da5feb71df231bd7fc8081a77df17f2a02d67f82ed",
  "file_size_bytes": 1762293,
  "file_date":     "2026-04-01",
  "status":        "STAGED",
  "uploaded_by_user_id": "11111111-0000-0000-0000-000000000001"
}
```

**Phase 1 fix verified live**: `tenant_id = dd000000-...` (JY's canonical UUID), **NOT** `a0000000-...` (Skywave's UUID).

---

## T4 — Validate the staged job → VALIDATED + counts

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/jobs/148dbc32.../validate \
       -H "Authorization: Bearer $ADMIN_TOKEN"
status:        VALIDATED
total:         7022
valid:         7022
rejected:      0
date_field:    CapDate
```

---

## T5 — Commit + verify rows visible to `jy@airline.com`

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/jobs/148dbc32.../commit \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -d '{"replace_existing":false}'
status:           COMMITTED
rows_inserted:    7022
tenant_id_used:   dd000000-0000-0000-0000-000000000001
```

DB-level verification — rows ended up with the **correct** tenant UUID:

```
SELECT tenant_id, tenant_code, COUNT(*) FROM airline_cpi_snapshot
 WHERE source_file = 'JY_010426.xlsx'
 GROUP BY tenant_id, tenant_code;

              tenant_id               | tenant_code | count
--------------------------------------+-------------+-------
 dd000000-0000-0000-0000-000000000001 | JY          |  7022
```

`jy@airline.com` view (no date filter) — 14,044 rows total visible:
- 7,022 newly committed JY rows under correct `tenant_id = dd000000-...`
- 7,022 pre-existing JY rows (legacy mis-attributed `tenant_id = a0000000-...`) — view filters by `tenant_code='JY'` so they're still surfaced; a one-time data correction is documented in `docs/ingestion-uuid-discovery.md` and is **not** auto-applied (see "Open follow-ups" below).

---

## T6 — Re-upload SAME bytes → duplicate=true (no new job)

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/upload \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -F 'files=@/tmp/JY_010426.xlsx'
duplicate:        True
existing_job_id:  148dbc32-f446-4851-ac20-e1d9b28bf476
summary:          {'accepted': 0, 'duplicate': 1, 'conflict': 0, 'rejected': 0}
```

Idempotency check working: identical SHA-256 + already-COMMITTED job → returns existing job, no new staging dir created.

---

## T7 — Upload EDITED file (same filename, different hash) → conflict

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/upload \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -F 'files=@/tmp/JY_010426_edited.xlsx;filename=JY_010426.xlsx'
duplicate:         False
conflict:          True
existing_job_id:   148dbc32-f446-4851-ac20-e1d9b28bf476
new_job_id:        29f8cea4-6eae-4357-ba7e-c5b848f77e9e
new_status:        STAGED
```

Conflict signal returned with `existing_job_id` — client now has enough info to choose between cancel-this and replace-existing.

---

## T8 — Commit with `replace_existing=true`

```
$ curl -X POST http://localhost:8000/api/v1/ingestion/jobs/29f8cea4.../validate ...
$ curl -X POST http://localhost:8000/api/v1/ingestion/jobs/29f8cea4.../commit \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -d '{"replace_existing":true}'
new_status:         COMMITTED
rows_inserted:      7022
replaced_job_id:    148dbc32-f446-4851-ac20-e1d9b28bf476
```

Old job state after replace:

```
$ curl http://localhost:8000/api/v1/ingestion/jobs/148dbc32... \
       -H "Authorization: Bearer $ADMIN_TOKEN"
old_status:    REPLACED
replaced_by:   29f8cea4-6eae-4357-ba7e-c5b848f77e9e
```

The replace flow: marked T5's job as `REPLACED`, set the `replaced_by_job_id` pointer, deleted T5's fact rows for `(tenant_code='JY', report_date=2026-04-01)`, inserted T8's 7,022 fresh rows, audit-logged a `REPLACED` entry on the old job and a `COMMITTED` on the new.

---

## T9 — Audit log — all actions, correct actors

```
$ curl http://localhost:8000/api/v1/ingestion/jobs/148dbc32.../audit \
       -H "Authorization: Bearer $ADMIN_TOKEN"

job1 entries: 4
  REPLACED   actor=11111111... ip=172.21.0.1 ts=2026-04-30T12:33:06.129642Z
  COMMITTED  actor=11111111... ip=172.21.0.1 ts=2026-04-30T12:33:01.938739Z
  VALIDATED  actor=11111111... ip=172.21.0.1 ts=2026-04-30T12:33:00.448539Z
  UPLOADED   actor=11111111... ip=172.21.0.1 ts=2026-04-30T12:33:00.393457Z

job2 entries: 3
  COMMITTED  actor=11111111... ip=172.21.0.1
  VALIDATED  actor=11111111... ip=172.21.0.1
  UPLOADED   actor=11111111... ip=172.21.0.1
```

All actions present, all from the same admin actor (`11111111-...` is `admin@skywave.com`'s `app_user.id`), client IP captured from `X-Forwarded-For`/`request.client`.

---

## T10 — Upload bogus `FOO_BAR.txt` → parser rejection

```
$ echo 'garbage' > /tmp/FOO_BAR.txt
$ curl -X POST http://localhost:8000/api/v1/ingestion/upload \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -F 'files=@/tmp/FOO_BAR.txt'
error_code:    ingestion_filename_invalid
message:       unknown tenant prefix 'FOO'
job:           None
```

The HTTP status is 200 (per-file error pattern in multi-file upload), with the file-level result correctly carrying `error_code` and `error_message`. Summary: `{accepted: 0, rejected: 1}`.

---

## Open follow-ups (not blockers for Phase A merge)

1. **Legacy mis-attributed JY rows in `airline_cpi_snapshot` and `jy_velocity_snapshot`** still carry `tenant_id = a0000000-...` (Skywave). The discovery doc (`docs/ingestion-uuid-discovery.md`) includes the SQL `UPDATE` statements to re-tag them. Apply as a follow-up data-correction step (separate alembic migration) once you confirm scope.
2. **Frontend break — Phase B:** the existing "Ingestion Jobs" page calls `/jobs` and `/jobs/{id}/batches` and expects the legacy schema. Now `/jobs` returns the new `ingestion_jobs` rows and `/batches` is 404. Phase B (frontend overhaul) updates the UI types to the new shape.
3. **`POST /api/v1/ingestion/ingest` returns 410 Gone** — the "Ingest All" button surfaces this. Acceptable per the prompt; Phase B replaces the button with the new upload flow.
4. **pytest is now baked into `requirements.txt`** so `docker compose up --build` will preserve it. `docker exec cpi-api-1 python -m pytest tests/ingestion/ -v` runs all 33 unit tests in ~0.4s.
