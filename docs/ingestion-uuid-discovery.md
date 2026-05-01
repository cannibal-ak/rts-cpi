# Phase 1 — Ingestion UUID Discovery (Read-Only)

**Date:** 2026-04-30
**Scope:** Confirm whether the existing folder-watch ingest writes JY data under the **Skywave** tenant UUID (bug) or the **JY** tenant UUID (by design). No code or data was modified during this discovery.

---

## TL;DR

- **Bug confirmed.** `apps/api/scripts/ingest_daily.py` hardcodes JY's tenant UUID as `a0000000-...` (Skywave's UUID) instead of `dd000000-...` (JY's canonical UUID).
- **PW and FJL are correct.** Only JY is affected.
- **Reads aren't broken** because the entire read path filters by `tenant_code = 'JY'` (string), not by `tenant_id` (uuid). The wrong UUID is invisible to the running app — but the audit trail and any future RLS-driven query will be wrong.
- **Recommended fix:** Phase 4's new ingestion service should look up tenant UUIDs from the `tenant` table by slug, eliminating the hardcode entirely. A one-time data-correction `UPDATE` will re-tag the misattributed rows.

---

## Canonical tenants (DB ground truth)

Query: `SELECT id, slug, display_name FROM tenant ORDER BY slug;`

| slug    | id (uuid)                              | display_name           |
| ------- | -------------------------------------- | ---------------------- |
| fjl     | `cc000000-0000-0000-0000-000000000001` | Baltic Ferries - FJL   |
| jy      | `dd000000-0000-0000-0000-000000000001` | Skywave - JY           |
| pw      | `bb000000-0000-0000-0000-000000000001` | Skybound - PW          |
| skywave | `a0000000-0000-0000-0000-000000000001` | Skywave Platform Admin |

Note: the table is named `tenant` (singular), not `tenants`. The schema in Phase 2 of the overhaul prompt assumes plural — FK references must use `tenant(id)`.

---

## Hardcoded UUIDs in `apps/api/scripts/ingest_daily.py`

The `TENANTS` dict (lines 45–89) hardcodes one UUID per tenant code:

| code | hardcoded id                           | matches DB?  | verdict   |
| ---- | -------------------------------------- | ------------ | --------- |
| JY   | `a0000000-0000-0000-0000-000000000001` | NO (Skywave) | **WRONG** |
| PW   | `bb000000-0000-0000-0000-000000000001` | yes (pw)     | correct   |
| FJL  | `cc000000-0000-0000-0000-000000000001` | yes (fjl)    | correct   |

The JY hardcode at `apps/api/scripts/ingest_daily.py:47` is the root cause.

Helpfully, `main()` (line 838-842) does:

```python
INSERT INTO tenant (id, slug, display_name)
VALUES (:tid, :slug, :name)
```

…only when the row does not exist. Since the canonical `jy` row already exists in `tenant` with `id=dd000000-...`, the script never inserts a duplicate — but every JY ingest then attaches its data rows to the wrong UUID anyway.

---

## Data impact (current row counts)

### `airline_cpi_snapshot`

| tenant_id (uuid prefix)   | tenant_code | rows   | report_date |
| ------------------------- | ----------- | ------ | ----------- |
| `a0000000-...` (Skywave!) | JY          | 7,022  | 2026-04-02  |
| `bb000000-...` (PW)       | PW          | 16,103 | 2026-02-21  |

### `cfl_cpi_snapshot`

| tenant_id (uuid prefix) | tenant_code | rows  | report_date |
| ----------------------- | ----------- | ----- | ----------- |
| `cc000000-...` (FJL)    | FJL         | 9,519 | 2026-02-21  |

### `jy_velocity_snapshot`

| tenant_id (uuid prefix)   | tenant_code | rows  |
| ------------------------- | ----------- | ----- |
| `a0000000-...` (Skywave!) | JY          | 6,155 |

### `import_job`

| tenant_id      | data_owner | domain   | status    |
| -------------- | ---------- | -------- | --------- |
| `a0000000-...` | FJL        | cfl      | committed |
| `a0000000-...` | JY         | airline  | committed |
| `a0000000-...` | JY         | velocity | committed |
| `a0000000-...` | PW         | airline  | committed |

**Wait — every `import_job` row has `tenant_id = a0000000-...`?** Yes. Looking at the script's INSERT (line 224-228), `import_job.tenant_id` is always set to whatever `cfg["id"]` is for the tenant being ingested. PW and FJL data tables get the right UUID, but their `import_job` rows… also use `a0000000`? That doesn't match the script's logic. Likely explanation: the 4 import_job rows are old artefacts from before PW/FJL UUIDs were corrected. Either way, the **only mis-attributed *data* is JY**.

---

## How is the read side filtered? (Why nothing is visibly broken)

### `vw_airline_cpi_jy_snapshot` definition (excerpt)

```sql
SELECT … FROM airline_cpi_snapshot
WHERE tenant_code::text = 'JY'::text;
```

### `vw_jy_velocity_snapshot` definition (excerpt)

```sql
SELECT … FROM jy_velocity_snapshot
WHERE tenant_code::text = 'JY'::text;
```

### `apps/api/app/routers/airline.py:36` (excerpt)

```python
AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot",
                    "PW": "vw_airline_cpi_pw_snapshot"}
```

The router selects the view by **tenant CODE** (string `"JY"`), not UUID. The view filters by **`tenant_code`**, not `tenant_id`. So the wrong `tenant_id` is never consulted on the read path.

### RLS state on the snapshot tables

- `airline_cpi_snapshot` / `cfl_cpi_snapshot`: tenant-isolation policy enforces `tenant_id = current_setting('app.current_tenant')`. But this policy targets the `public` role and the connection user is `cpi`, which has a separate `…_superuser_bypass` policy with `USING (true)`.
- `jy_velocity_snapshot`: isolation policy targets the `cpi_app` role, not `public` — and `cpi` bypasses it too.

**Net effect:** RLS would catch the misattribution if the API connected as a `public` or `cpi_app` role and read the base tables, but it currently does neither. Combined with the `tenant_code` filtering in views, the bug is silent.

---

## RLS visibility check for `jy@airline.com`

When `jy@airline.com` logs in, `get_user_identity` returns `"JY"`, `is_platform_admin()` returns false, and the airline router locks `effective_tenant = "JY"`. They can only see rows the views surface, which filter by `tenant_code = 'JY'` — so they DO see all JY data, even though it is incorrectly attributed.

If we ever switch reads to enforce `tenant_id`-based RLS (e.g. make the API connect as `cpi_app` or remove the bypass policy), JY data would suddenly become invisible to JY users until the data-correction step runs. The fix must therefore land **together with** the data correction.

---

## Recommended fix (for Phase 4)

### Code fix

In the **new** `app/ingestion/service.py`, do not hardcode a tenant UUID. Look it up from the `tenant` table at runtime, keyed by slug:

```python
def _resolve_tenant_id(db, slug: str) -> uuid.UUID:
    tid = db.execute(
        text("SELECT id FROM tenant WHERE slug = :slug"),
        {"slug": slug.lower()},
    ).scalar()
    if not tid:
        raise ValueError(f"Unknown tenant slug: {slug}")
    return tid
```

Use `slug = airline_code.lower()` (`'jy'`, `'pw'`, `'fjl'`).

### Old script

`scripts/ingest_daily.py` is being **removed** in Phase 6, so we do not need to fix line 47 directly — but the `TENANTS` dict's UUID values are reusable test fixtures, so document the canonical mapping in the new code.

### Data correction (one-time, runs as part of Phase 4 commit logic OR a separate migration step)

```sql
-- Re-tag mis-attributed JY rows to the correct tenant_id
UPDATE airline_cpi_snapshot
   SET tenant_id = 'dd000000-0000-0000-0000-000000000001'
 WHERE tenant_code = 'JY'
   AND tenant_id = 'a0000000-0000-0000-0000-000000000001';

UPDATE jy_velocity_snapshot
   SET tenant_id = 'dd000000-0000-0000-0000-000000000001'
 WHERE tenant_code = 'JY'
   AND tenant_id = 'a0000000-0000-0000-0000-000000000001';

UPDATE import_job
   SET tenant_id = 'dd000000-0000-0000-0000-000000000001'
 WHERE data_owner = 'JY'
   AND tenant_id = 'a0000000-0000-0000-0000-000000000001';

UPDATE import_batch
   SET tenant_id = 'dd000000-0000-0000-0000-000000000001'
 WHERE tenant_id = 'a0000000-0000-0000-0000-000000000001'
   AND import_job_id IN (
       SELECT id FROM import_job WHERE data_owner = 'JY'
   );
```

PW and FJL `import_job` rows are also tagged with `a0000000-...` — those are stale and should be re-tagged similarly, or left alone if considered historical noise. Worth confirming.

---

## Open questions for the user (raised at Phase 1 HALT)

1. **Naming convention for the new `ingestion_jobs` table.** The prompt says `airline_code VARCHAR(8)`. Existing fact tables use `tenant_code` and `data_owner`. FJL is a cruise/ferry tenant, not an airline — so `airline_code` is a misnomer. Three options:
   - **A)** Use `tenant_code` (matches existing schema convention).
   - **B)** Use `airline_code` as the prompt literally says.
   - **C)** Rename to `data_owner` (matches the existing index name pattern).

2. **Branch base for Phase 2 onward.** Host's `master` is just an initial commit. All current code (auth, UI, current ingestion router) lives on `feat/ingestion-super-admin-only`. Branching from `master` would lose ~60 files of merged work. Branching from `feat/ingestion-super-admin-only` is what was almost certainly intended.

3. **Stale PW/FJL `import_job` rows.** Their `tenant_id = a0000000-...` too — fix in the same data-correction step or leave as legacy?

4. **Migration number.** `017_global_email_unique_constraint.py` already exists. New migration will be `018_ingestion_overhaul.py`.
