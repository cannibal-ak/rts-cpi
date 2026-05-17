# Airline CPI Migration Plan — 2026-05-06

**Mode:** read-only discovery + planning. No DDL, DML, code edits, or container restarts performed.

**Scope:** align `airline_cpi_snapshot` with the *Airline Competitors' Price Data Dictionary* (canonical 77 dictionary columns + 11 infrastructure columns = 88 physical columns post-migration). Current physical: 41. Gap: 47 columns to add. All 4 layers (DB, ingestion, API, UI) covered.

**Locked-in decisions (recap):**
1. Drop dictionary column `RefArrDate` (PW-only). Not migrated.
2. Canonical equipment column = `ref_equip_code`. Mapper translates JY's `RefAircraft` and PW's `RefEquipCode` → same DB column.
3. `airline_cpi_snapshot` stays consolidated (no per-tenant split). JY and PW share the table.

---

## 0. Pre-flight

### 0.1 Git status — matches Round 2 baseline

```
On branch feat/ingestion-overhaul-phase-a
Modified (8): apps/web/src/{App.tsx, api/client.ts, api/httpClient.ts, api/mockClient.ts,
              components/common/StatusChip.tsx, mock/navigation.ts,
              pages/ingestion/IngestionJobsPage.tsx, types/index.ts}
Untracked (3): apps/web/src/pages/ingestion/UploadPage.tsx,
               docs/db-structure-discovery-20260506.md,
               ingestion-super-admin.patch
```

The plan file (this file) is the only addition.

### 0.2 Docker stack — all CPI services healthy/running

`cpi-postgres-1` (postgres:16-alpine, 3w, healthy) — verified.
`cpi-api-1`, `cpi-worker-1`, `cpi-redis-1`, `cpi-rabbitmq-1`, `cpi-superset-1` — all healthy.
`cpi-web-1` — unhealthy (pre-existing healthcheck quirk; acceptable per memory).

### 0.3 psql sanity

```
SELECT COUNT(*) FROM airline_cpi_snapshot;
 count
-------
 45515
```

---

## 1. Source file header inspection

### 1.1 JY file path

Newest JY airline source by mtime (live SFTP staging copies — same headers across all JY xlsx):

- `dev-sftp-mount/jy/JY_010126.xlsx` (mtime 2026-05-04, file_date 2026-01-01, 3 rows of data)
- staging copy `apps/api/data/staging/5682d4b2-…/JY_010426.xlsx` (the STAGED job's snapshot of `JY_010426.xlsx`, file_date 2026-04-01, 7,022 rows of data — used for header extraction below).

Both files share the same header schema.

### 1.2 PW file path

Single PW airline xlsx in repo: `dev-sftp-mount/pw/PW_010426.xlsx` (mtime 2026-05-05, file_date 2026-04-01, 15,365 rows). No CSV variant exists for AIRLINE domain (CSVs are velocity-only).

### 1.3 Header rows (verbatim)

**JY (72 columns):**
```
ID, CapDate, CapTime, RefAL, RefFltNum, RefRetFltNum, RefOrg, RefDst,
RefDepDate, RefRetDepDate, RefDepTime, RefRetDepTime, RefArrTime, RefRetArrTime,
RefStops, RefVia, RefRetVia, RefRetStops, RefFFCode, RefCur, RefBaseFare,
RefTax, RefYQ, RefYR, RefAncPrice, RefAncType, RefTotFare, RefCabName,
RefRetCabName, RefCabCode, RefRetCabCode, RefBkgClass, RefRetBkgClass,
RefSeats, RefRetSeats, RefAircraft, RefRetAircraft, TripType, CompAL,
CompFltNum, CompRetFltNum, CompOrg, CompDst, CompDepDate, CompRetDepDate,
CompDepTime, CompRetDepTime, CompArrTime, CompRetArrTime, CompStops,
CompVia, CompRetVia, CompRetStops, CompFFCode, CompCur, CompBaseFare,
CompTax, CompYQ, CompYR, CompAncPrice, CompAncType, CompTotFare,
CompCabName, CompRetCabName, CompCabCode, CompRetCabCode,
CompBkgClass, CompRetBkgClass, CompSeats, CompRetSeats,
CompAircraft, CompRetAircraft
```

**PW (46 columns):**
```
ID, CapDate, CapTime, RefAL, RefFltNum, RefOrg, RefDst, TripType,
RefDepDate, RefDepTime, RefArrTime, RefStops, RefBaseFare, RefCur,
RefTax, RefYQ, RefYR, RefTotFare, CompAL, CompFltNum, CompOrg, CompDst,
CompDepDate, CompDepTime, CompArrTime, CompStops, CompFFCode, CompCur,
CompBaseFare, CompTax, CompYQ, CompYR, CompAncPrice, CompAncType,
CompTotFare, POA, POD, POC, POS, CompCabName, CompCabCode,
CompBkgClass, CompSeats, RefCabName, RefCabCode, RefBkgClass
```

### 1.4 JY header diff

All 72 JY headers are listed in the JY dictionary sheet (no UNKNOWN headers). The four headers below are the only RENAMEs (per locked decision #2 and the snake_case naming convention):

| source_jy_header  | in_dictionary | dictionary_name (canonical db_col_name) | classification |
|-------------------|---------------|------------------------------------------|----------------|
| `RefAircraft`     | yes           | `ref_equip_code` (unified)               | RENAME         |
| `RefRetAircraft`  | yes           | `ref_ret_equip_code`                     | RENAME         |
| `CompAircraft`    | yes           | `comp_equip_code`                        | RENAME         |
| `CompRetAircraft` | yes           | `comp_ret_equip_code`                    | RENAME         |

The remaining 68 JY headers are direct MATCH (snake_case form of the dictionary name, e.g. `RefAL` → `ref_al`).

### 1.5 PW header diff

All 46 PW headers are in the PW dictionary sheet. None are RENAMEs (PW source uses no `Aircraft` header — note `RefEquipCode` is in PW *dictionary* but absent from the actual PW *file*; see 1.6). All 46 are direct MATCH.

### 1.6 Dictionary columns absent from sources

**Truly absent from BOTH source files (will be permanently NULL on ingest):**
- `Path` (Sr. No. 77, Alpha(50)). Required per dict but neither file emits it.

**Absent from JY source only (PW provides them):**
- `POA`, `POD`, `POC`, `POS` — JY file has no point-of-sale/origin/destination/commencement columns at all. PW file has all four.

**Absent from PW source only (JY provides them):**
- `RefEquipCode` — listed in PW dict (Sr. No. 47, "Yes"-required) but **the actual PW file omits the column**. JY's `RefAircraft` is the only practical source for `ref_equip_code` today.
- All 29 JY-only canonical columns (return-flight Ref/Comp variants, RefVia/CompVia, RefAncPrice/RefAncType, RefSeats, RefFFCode, plus the four Aircraft columns).

**Bottom line for ingestion:**
- 1 column NULL for everyone (`path`).
- 4 columns NULL for JY rows (`pod`, `poc`, plus `pos`/`poa` need the mapper hardcode removed — see Section 3).
- 1 column NULL for PW rows where the dict says it shouldn't be (`ref_equip_code`).
- 29 columns NULL for PW rows by design (return-flight + ancillaries — JY-only).

---

## 2. Master mapping table

Sorted by status (MISSING → PRESENT_MISMATCH → PRESENT_OK), then by canonical dictionary order.

Type-mapping rules applied:
- `Alpha (N)` → `varchar(N)` (with current DB minimum-length preserved where DB already has wider — see PRESENT_MISMATCH rows)
- `Alpha` (no length) → `varchar(32)`
- `AlphaNumeric` → `varchar(32)` default
- `Numeric` (fare/tax/charge/surcharge) → `numeric(12,2)`
- `Numeric` (stops/seats/count) → `integer`
- `Numeric (4)` for FltNum-like → `varchar(10)` (preserve current; JY `RefFltNum` carries values like `"PW0423/PW4"`)
- `YYYY-MM-DD` → `date`
- `HH:MM:SS` → `time without time zone`
- `HHMM` (4-digit clock) → `varchar(4)` (preserves leading zeros, matches the existing `velocity_snapshot.dep_time` convention)

Nullability rules:
- `tenants=BOTH` and dict required=Yes → NOT NULL on add (but see "open question Q5" in Section 7.4 — adding NOT NULL to an existing populated table without backfill needs a default)
- `tenants=BOTH` and required=No → nullable
- `tenants=JY` only → nullable
- POA/POD/POC/POS (PW-source-only) → nullable

> **Implementation guideline:** all 47 new columns are added as **nullable** in Phase 2A regardless of dict "required", because the existing 45,515 rows have no value to backfill. After backfill or replace-existing re-ingest (Phase 2D), a follow-up migration can tighten NOT NULL where appropriate.

### 2.1 MISSING (47 rows — to be added in Phase 2A)

| dict_name | dict_type | dict_len | required | tenants | source_jy | source_pw | db_col_name | db_col_type | db_nullable | orm_attr | api_field | ui_col_key | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RefRetFltNum | Numeric | 4 | Yes | JY | RefRetFltNum | n/a | ref_ret_flt_num | varchar(10) | true | ref_ret_flt_num | ref_ret_flt_num | ref_ret_flt_num | MISSING |
| RefRetDepDate | YYYY-MM-DD |  | Yes | JY | RefRetDepDate | n/a | ref_ret_dep_date | date | true | ref_ret_dep_date | ref_ret_dep_date | ref_ret_dep_date | MISSING |
| RefDepTime | HHMM |  | Yes | BOTH | RefDepTime | RefDepTime | ref_dep_time | varchar(4) | true | ref_dep_time | ref_dep_time | ref_dep_time | MISSING |
| RefRetDepTime | HHMM |  | Yes | JY | RefRetDepTime | n/a | ref_ret_dep_time | varchar(4) | true | ref_ret_dep_time | ref_ret_dep_time | ref_ret_dep_time | MISSING |
| RefArrTime | HHMM |  | Yes | BOTH | RefArrTime | RefArrTime | ref_arr_time | varchar(4) | true | ref_arr_time | ref_arr_time | ref_arr_time | MISSING |
| RefRetArrTime | HHMM |  | Yes | JY | RefRetArrTime | n/a | ref_ret_arr_time | varchar(4) | true | ref_ret_arr_time | ref_ret_arr_time | ref_ret_arr_time | MISSING |
| RefStops | Numeric |  | Yes | BOTH | RefStops | RefStops | ref_stops | integer | true | ref_stops | ref_stops | ref_stops | MISSING |
| RefVia | Alpha | 3 | Yes | JY | RefVia | n/a | ref_via | varchar(4) | true | ref_via | ref_via | ref_via | MISSING |
| RefRetVia | Alpha | 3 | Yes | JY | RefRetVia | n/a | ref_ret_via | varchar(4) | true | ref_ret_via | ref_ret_via | ref_ret_via | MISSING |
| RefRetStops | Numeric |  | Yes | JY | RefRetStops | n/a | ref_ret_stops | integer | true | ref_ret_stops | ref_ret_stops | ref_ret_stops | MISSING |
| RefFFCode | Alpha | 20 | Yes | JY | RefFFCode | n/a | ref_ff_code | varchar(20) | true | ref_ff_code | ref_ff_code | ref_ff_code | MISSING |
| RefYR | Numeric |  | No | BOTH | RefYR | RefYR | ref_yr | numeric(12,2) | true | ref_yr | ref_yr | ref_yr | MISSING |
| RefAncPrice | Numeric |  | No | JY | RefAncPrice | n/a | ref_anc_price | numeric(12,2) | true | ref_anc_price | ref_anc_price | ref_anc_price | MISSING |
| RefAncType | Alpha | 20 | No | JY | RefAncType | n/a | ref_anc_type | varchar(20) | true | ref_anc_type | ref_anc_type | ref_anc_type | MISSING |
| RefCabName | Alpha | 20 | Yes | BOTH | RefCabName | RefCabName | ref_cab_name | varchar(20) | true | ref_cab_name | ref_cab_name | ref_cab_name | MISSING |
| RefRetCabName | Alpha | 20 | Yes | JY | RefRetCabName | n/a | ref_ret_cab_name | varchar(20) | true | ref_ret_cab_name | ref_ret_cab_name | ref_ret_cab_name | MISSING |
| RefRetCabCode | Alpha | 1 | Yes | JY | RefRetCabCode | n/a | ref_ret_cab_code | varchar(4) | true | ref_ret_cab_code | ref_ret_cab_code | ref_ret_cab_code | MISSING |
| RefBkgClass | Alpha | 1 | Yes | BOTH | RefBkgClass | RefBkgClass | ref_bkg_class | varchar(4) | true | ref_bkg_class | ref_bkg_class | ref_bkg_class | MISSING |
| RefRetBkgClass | Alpha | 1 | Yes | JY | RefRetBkgClass | n/a | ref_ret_bkg_class | varchar(4) | true | ref_ret_bkg_class | ref_ret_bkg_class | ref_ret_bkg_class | MISSING |
| RefRetSeats | Numeric |  | No | JY | RefRetSeats | n/a | ref_ret_seats | integer | true | ref_ret_seats | ref_ret_seats | ref_ret_seats | MISSING |
| RefAircraft / RefEquipCode | AlphaNumeric |  | Yes | BOTH | RefAircraft | RefEquipCode | ref_equip_code | varchar(32) | true | ref_equip_code | ref_equip_code | ref_equip_code | MISSING (unification target) |
| RefRetAircraft | AlphaNumeric |  | No | JY | RefRetAircraft | n/a | ref_ret_equip_code | varchar(32) | true | ref_ret_equip_code | ref_ret_equip_code | ref_ret_equip_code | MISSING |
| CompRetFltNum | Numeric | 4 | Yes | JY | CompRetFltNum | n/a | comp_ret_flt_num | varchar(10) | true | comp_ret_flt_num | comp_ret_flt_num | comp_ret_flt_num | MISSING |
| CompRetDepDate | YYYY-MM-DD |  | Yes | JY | CompRetDepDate | n/a | comp_ret_dep_date | date | true | comp_ret_dep_date | comp_ret_dep_date | comp_ret_dep_date | MISSING |
| CompDepTime | HHMM |  | Yes | BOTH | CompDepTime | CompDepTime | comp_dep_time | varchar(4) | true | comp_dep_time | comp_dep_time | comp_dep_time | MISSING |
| CompRetDepTime | HHMM |  | Yes | JY | CompRetDepTime | n/a | comp_ret_dep_time | varchar(4) | true | comp_ret_dep_time | comp_ret_dep_time | comp_ret_dep_time | MISSING |
| CompArrTime | HHMM |  | Yes | BOTH | CompArrTime | CompArrTime | comp_arr_time | varchar(4) | true | comp_arr_time | comp_arr_time | comp_arr_time | MISSING |
| CompRetArrTime | HHMM |  | Yes | JY | CompRetArrTime | n/a | comp_ret_arr_time | varchar(4) | true | comp_ret_arr_time | comp_ret_arr_time | comp_ret_arr_time | MISSING |
| CompStops | Numeric |  | Yes | BOTH | CompStops | CompStops | comp_stops | integer | true | comp_stops | comp_stops | comp_stops | MISSING |
| CompVia | Alpha | 3 | Yes | JY | CompVia | n/a | comp_via | varchar(4) | true | comp_via | comp_via | comp_via | MISSING |
| CompRetVia | Alpha | 3 | Yes | JY | CompRetVia | n/a | comp_ret_via | varchar(4) | true | comp_ret_via | comp_ret_via | comp_ret_via | MISSING |
| CompRetStops | Numeric |  | Yes | JY | CompRetStops | n/a | comp_ret_stops | integer | true | comp_ret_stops | comp_ret_stops | comp_ret_stops | MISSING |
| CompFFCode | Alpha | 20 | Yes | BOTH | CompFFCode | CompFFCode | comp_ff_code | varchar(20) | true | comp_ff_code | comp_ff_code | comp_ff_code | MISSING |
| CompYR | Numeric |  | No | BOTH | CompYR | CompYR | comp_yr | numeric(12,2) | true | comp_yr | comp_yr | comp_yr | MISSING |
| CompAncPrice | Numeric |  | No | BOTH | CompAncPrice | CompAncPrice | comp_anc_price | numeric(12,2) | true | comp_anc_price | comp_anc_price | comp_anc_price | MISSING |
| CompAncType | Alpha | 20 | No | BOTH | CompAncType | CompAncType | comp_anc_type | varchar(20) | true | comp_anc_type | comp_anc_type | comp_anc_type | MISSING |
| POD | Alpha (untyped) |  | (untyped) | PW-src | n/a | POD | pod | varchar(4) | true | pod | pod | pod | MISSING |
| POC | Alpha (untyped) |  | (untyped) | PW-src | n/a | POC | poc | varchar(4) | true | poc | poc | poc | MISSING |
| CompCabName | Alpha | 20 | Yes | BOTH | CompCabName | CompCabName | comp_cab_name | varchar(20) | true | comp_cab_name | comp_cab_name | comp_cab_name | MISSING |
| CompRetCabName | Alpha | 20 | Yes | JY | CompRetCabName | n/a | comp_ret_cab_name | varchar(20) | true | comp_ret_cab_name | comp_ret_cab_name | comp_ret_cab_name | MISSING |
| CompRetCabCode | Alpha | 1 | Yes | JY | CompRetCabCode | n/a | comp_ret_cab_code | varchar(4) | true | comp_ret_cab_code | comp_ret_cab_code | comp_ret_cab_code | MISSING |
| CompBkgClass | Alpha | 1 | Yes | BOTH | CompBkgClass | CompBkgClass | comp_bkg_class | varchar(4) | true | comp_bkg_class | comp_bkg_class | comp_bkg_class | MISSING |
| CompRetBkgClass | Alpha | 1 | Yes | JY | CompRetBkgClass | n/a | comp_ret_bkg_class | varchar(4) | true | comp_ret_bkg_class | comp_ret_bkg_class | comp_ret_bkg_class | MISSING |
| CompRetSeats | Numeric |  | No | JY | CompRetSeats | n/a | comp_ret_seats | integer | true | comp_ret_seats | comp_ret_seats | comp_ret_seats | MISSING |
| CompAircraft | AlphaNumeric |  | No | JY | CompAircraft | n/a | comp_equip_code | varchar(32) | true | comp_equip_code | comp_equip_code | comp_equip_code | MISSING |
| CompRetAircraft | AlphaNumeric |  | No | JY | CompRetAircraft | n/a | comp_ret_equip_code | varchar(32) | true | comp_ret_equip_code | comp_ret_equip_code | comp_ret_equip_code | MISSING |
| Path | Alpha | 50 | Yes | (neither file) | n/a | n/a | path | varchar(50) | true | path | path | path | MISSING (no source — see open Q5) |

47 rows.

### 2.2 PRESENT_MISMATCH (13 rows — schema-correct but width/name divergence; not blockers)

| dict_name | dict_type | dict_len | required | tenants | db_col_name | db_col_type | mismatch_note | status |
|---|---|---|---|---|---|---|---|---|
| RefAL | Alpha | 2 | Yes | BOTH | ref_al | varchar(3) | DB width 3, dict says 2 (3 fits IATA codes; harmless) | PRESENT_MISMATCH |
| RefFltNum | Numeric | 4 | Yes | BOTH | ref_flt_num | varchar(10) | DB type varchar(10), dict says Numeric(4); JY data has alpha-prefixed values like `PW0423/PW4` — keep varchar(10) | PRESENT_MISMATCH |
| RefOrg | Alpha | 3 | Yes | BOTH | ref_org | varchar(4) | DB 4, dict 3 (harmless) | PRESENT_MISMATCH |
| RefDst | Alpha | 3 | Yes | BOTH | ref_dst | varchar(4) | DB 4, dict 3 | PRESENT_MISMATCH |
| RefCur | Alpha | 3 | Yes | BOTH | ref_curr | varchar(4) | name `ref_curr` vs dict `RefCur`; DB has `_curr` suffix instead of dict snake `ref_cur`; default `'GBP'` matches | PRESENT_MISMATCH (name) |
| RefCabCode | Alpha | 1 | Yes | BOTH | ref_cab_code | varchar(4) | DB 4, dict 1 (room for codes like `TWIG`) | PRESENT_MISMATCH |
| TripType | Alpha | 2 | Yes | BOTH | trip_type | varchar(4) | DB 4, dict 2 (`OW`/`RT` fit) — but JY emits `One-way` style on CFL data; on AIRLINE both files emit `OW`/`RT` so 4 is fine | PRESENT_MISMATCH |
| CompAL | Alpha | 2 | Yes | BOTH | comp_al | varchar(3) | as RefAL | PRESENT_MISMATCH |
| CompFltNum | Numeric | 4 | Yes | BOTH | comp_flt_num | varchar(10) | as RefFltNum | PRESENT_MISMATCH |
| CompOrg | Alpha | 3 | Yes | BOTH | comp_org | varchar(4) | DB 4, dict 3 | PRESENT_MISMATCH |
| CompDst | Alpha | 3 | Yes | BOTH | comp_dst | varchar(4) | DB 4, dict 3 | PRESENT_MISMATCH |
| CompCur | Alpha | 3 | Yes | BOTH | comp_curr | varchar(4) | name & length as RefCur | PRESENT_MISMATCH (name) |
| CompCabCode | Alpha | 1 | Yes | BOTH | comp_cab_code | varchar(4) | DB 4, dict 1 | PRESENT_MISMATCH |

13 rows.

> **Recommendation:** treat all 13 PRESENT_MISMATCH as ACCEPTABLE-AS-IS. Renaming `ref_curr`/`comp_curr` to `ref_cur`/`comp_cur` would be churn for no functional gain and would invalidate Superset/Grafana saved views. Width tightening would risk truncating live data.

### 2.3 PRESENT_OK (17 rows — DB column matches dict semantics)

ID, CapDate, CapTime, RefDepDate, RefBaseFare, RefTax, RefYQ, RefTotFare, RefSeats, CompDepDate, CompBaseFare, CompTax, CompYQ, CompTotFare, POA, POS, CompSeats.

Notes:
- `pos`/`poa`: schema present, but **mapper hardcodes both to `'US'`** for every row (Section 3) — not a schema bug, a behavior bug to fix in Phase 2C.
- `ref_seats`/`comp_seats`: NOT NULL with mapper default `9` when source omits the field (PW source has neither `RefSeats` nor `CompSeats` — every PW row has `seats=9`).
- `ref_tax`, `ref_yq`, `comp_yq` are NOT NULL in DB but optional in dict — mapper writes `0.0` when source is blank. Acceptable.

### 2.4 Special-case row (per prompt confirmation)

| dict_name | source_jy_header | source_pw_header | db_col_name | tenants | status |
|---|---|---|---|---|---|
| RefAircraft / RefEquipCode | RefAircraft | RefEquipCode | ref_equip_code | BOTH | MISSING (unification target) |

`RefArrDate` is **omitted** from this plan entirely (locked decision #1).

---

## 3. Ingestion mapper inspection

### 3.1 Mapper file paths

- [apps/api/app/ingestion/parsers.py](apps/api/app/ingestion/parsers.py) — shared helpers: `parse_date`, `parse_time`, `safe_float`, `safe_int`, `read_data_file`. Lenient: bad/missing values return `0`/`None`.
- [apps/api/app/ingestion/service.py:557-626](apps/api/app/ingestion/service.py:557) — `_insert_airline_rows` (the airline mapper). Single function used for **both JY and PW** — no per-tenant branching.
- [apps/api/app/ingestion/service.py:507](apps/api/app/ingestion/service.py:507) — replace-existing path for AIRLINE: `DELETE FROM airline_cpi_snapshot WHERE tenant_code = … AND report_date = …`.
- [apps/api/app/ingestion/service.py:515](apps/api/app/ingestion/service.py:515) — VELOCITY replace-existing path **still references legacy `jy_velocity_snapshot`** (broken reference; covered by separate Round-2 finding).

### 3.2 Current mapper coverage

The INSERT (lines 562-583) writes 35 columns. Of those, the data-driven ones (read from source `row.get(...)`) cover only **22 dictionary headers**: CapDate, CapTime, TripType, RefAL, RefFltNum, RefOrg, RefDst, RefDepDate, RefCabCode, RefTotFare, RefBaseFare, RefTax, RefYQ, RefSeats, CompAL, CompFltNum, CompOrg, CompDst, CompDepDate, CompCabCode, CompTotFare, CompBaseFare, CompTax, CompYQ, CompSeats.

Behaviorally hardcoded (NOT read from source):
- `pos = 'US'` (literal)
- `poa = 'US'` (literal)
- `data_owner`, `tenant_code`, `business_type`, `report_date`, `source_file` — derived from the IngestionJob, not the row.

> **Phase 5 implication:** PW data DOES carry POA/POD/POC/POS values in source, but the mapper discards them. The "POS" column in the UI shows `US` for every row regardless of tenant or source.

### 3.3 Missing-column mapping gaps (cross-ref to Section 2)

Per row in 2.1 (47 MISSING columns), every one needs a new line in `_insert_airline_rows`. Specifically:

- **20 columns BOTH-tenants** (mapper reads same header for JY+PW): RefDepTime, RefArrTime, RefStops, RefYR, RefCabName, RefBkgClass, CompDepTime, CompArrTime, CompStops, CompFFCode, CompYR, CompAncPrice, CompAncType, CompCabName, CompBkgClass, plus POA/POS (un-hardcode), POD, POC.
  - Net new mapping lines: 18 (POA/POS already have target columns, just need to remove `'US'` literals).
- **27 JY-only columns** (mapper reads only when row originated from JY): all the Ret-variants (16), RefVia/CompVia (2), RefAncPrice/RefAncType (2), RefRetSeats/CompRetSeats (2), RefFFCode (1), RefAircraft/RefRetAircraft/CompAircraft/CompRetAircraft (4 — including the unified ref_equip_code).
  - These rows need NULL when ingesting from a PW file. The mapper already uses `row.get(...)` (lenient), so missing keys naturally return None — no per-tenant branching strictly needed, just `row.get("RefVia")` etc. The unified `ref_equip_code` does need 2-source logic: `row.get("RefAircraft") or row.get("RefEquipCode")`.

### 3.4 Unknown/unmapped source headers

JY 72 source headers, PW 46 source headers. All are covered by the canonical 77 dictionary. **No unknown headers — no key-error risk.** The mapper currently silently ignores 50 headers in JY (72 read - 22 used) and 24 in PW (46 - 22).

---

## 4. API endpoint inspection

### 4.1 Endpoints

- [apps/api/app/routers/airline.py:24](apps/api/app/routers/airline.py:24) — `GET /api/v1/airline/snapshots` (paginated list).
- [apps/api/app/routers/airline.py:80](apps/api/app/routers/airline.py:80) — `GET /api/v1/airline/filter-metadata`.
- Pydantic response model: [apps/api/app/schemas/airline.py:9](apps/api/app/schemas/airline.py:9) `AirlineSnapshotOut`.

### 4.2 Tenant-scoping mechanism

`/snapshots` resolves `effective_tenant` from `user_identity` (or query param `tenant=` for platform admin), then dispatches to one of two **views**:
- `JY` → `vw_airline_cpi_jy_snapshot`
- `PW` → `vw_airline_cpi_pw_snapshot`

Tenant isolation is enforced at the **view-WHERE-clause** level (`WHERE tenant_code = 'JY'`/`'PW'`) plus the RLS policy on the underlying table. The endpoint runs raw SQL `SELECT * FROM <view>` — so any column the view exposes is in the response, regardless of what `AirlineSnapshotOut` declares.

Filter params: `file_date`, `airline`. Pagination: `page`, `page_size` (≤100). Sort: hardcoded `ORDER BY cap_date DESC, cap_time DESC`.

### 4.3 API response field comparison vs master table

| Field | In view `vw_airline_cpi_jy_snapshot`? | In `AirlineSnapshotOut` Pydantic? | Comment |
|---|---|---|---|
| `id` | yes | yes | OK |
| `tenant_id` | yes | NO | view exposes, schema hides |
| `cap_date`, `cap_time`, `trip_type`, `ref_al`, `ref_flt_num`, `ref_org`, `ref_dst`, `ref_dep_date`, `ref_cab_code`, `ref_tot_fare`, `ref_base_fare`, `ref_tax`, `ref_yq`, `ref_seats`, `comp_al`, `comp_flt_num`, `comp_org`, `comp_dst`, `comp_dep_date`, `comp_cab_code`, `comp_tot_fare`, `comp_base_fare`, `comp_tax`, `comp_yq`, `comp_seats`, `pos`, `poa` | yes | yes | OK |
| `ref_curr`, `comp_curr` | yes | NO | view exposes the currency, schema **omits** it — so frontend cannot read it |
| `fare_delta`, `fare_delta_pct` | yes (computed) | yes | OK |
| `ingested_at`, `import_batch_id`, `source_file_id`, `tenant_code`, `business_type`, `report_date`, `file_date` (alias of `report_date`), `source_file`, `loaded_at` | yes | NO | view exposes, schema hides |

**FastAPI behavior:** the endpoint returns `rows` directly without re-validating through the Pydantic model (it uses `response_model=PaginatedResponse[AirlineSnapshotOut]` which DOES coerce). With `from_attributes=True`, fields not declared in the schema are dropped. **So `ref_curr`/`comp_curr` are silently dropped before reaching the client** — confirming Section 5's hypothesis about the hardcoded `$` symbol on the frontend.

**Aliases (Python attr ≠ JSON key):** none — Pydantic uses attribute names directly.

**Fields in response promised by schema but missing from DB:** none after migration; `fare_delta` and `fare_delta_pct` are computed in the view, so they remain.

**Post-Phase-2A action for the schema (Phase 2B):** add the 47 new fields, plus add the 9 currently-dropped fields (`ref_curr`, `comp_curr`, `tenant_code`, `report_date`, `file_date`, `source_file`, `business_type`, `loaded_at`, `ingested_at`).

---

## 5. Frontend column-key inspection

### 5.1 Files

- [apps/web/src/pages/airline/AirlineCpiPage.tsx](apps/web/src/pages/airline/AirlineCpiPage.tsx) — page shell (89 lines) with a tabs container.
- [apps/web/src/pages/airline/AirlineCpiPricingTab.tsx](apps/web/src/pages/airline/AirlineCpiPricingTab.tsx) — pricing table (209 lines).
- [apps/web/src/pages/airline/AirlineCpiVelocityTab.tsx](apps/web/src/pages/airline/AirlineCpiVelocityTab.tsx) — velocity table (219 lines).
- [apps/web/src/utils/format.ts](apps/web/src/utils/format.ts) — `formatCurrency(value)` hardcoded `currency: 'USD'`.

There is **no separate column-config file** — columns are inlined as JSX `<TableCell>` elements in each tab.

### 5.2 Pricing tab columns rendered

[apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:144-186](apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:144) — fixed 11-column table:

| ui_col_label | ui_col_key (read from row) | formatter |
|---|---|---|
| Route | `row.ref_org`–`row.ref_dst` | string concat |
| Trip | `row.trip_type` | Chip |
| Ref Airline | `row.ref_al` (tooltip `row.ref_flt_num`) | Chip |
| Cabin | `row.ref_cab_code` | Chip |
| Ref Fare | `row.ref_tot_fare` | `formatCurrency(...)` (hardcoded `$`) |
| Comp Airline | `row.comp_al` (tooltip `row.comp_flt_num`) | Chip |
| Comp Fare | `row.comp_tot_fare` | `formatCurrency(...)` |
| Delta | computed `(comp_tot_fare - ref_tot_fare) / ref_tot_fare * 100` | `.toFixed(1)%` |
| POS | `row.pos` | text |
| Cap Date | `row.cap_date` | text |
| Dep Date | `row.ref_dep_date` | text |

### 5.3 UI key-vs-API gaps (root-cause of $0.00 / NaN%)

For the keys read by the pricing tab, every key resolves on the API response **today** — there is no `ref_fare`/`comp_fare` typo. So $0.00 / NaN% is NOT a key-mismatch problem; it is one of three real problems:

| Problem | Detail | Resolution phase |
|---|---|---|
| Currency formatter | `formatCurrency(val)` always emits `$` (USD). PW data stores `GBP`; JY airline data stores `GBP`/`KES`; UI mis-labels currency. Numeric value is correct, only the symbol is wrong. | Phase 2F |
| Currency value missing from response | `ref_curr`/`comp_curr` are stripped by Pydantic (Section 4.3), so even a tenant-aware formatter can't see them. | Phase 2B |
| Delta NaN% on free flights | `comp_tot_fare === 0 && ref_tot_fare === 0` → `(0-0)/0 * 100 = NaN`. Computation should guard against `ref_tot_fare === 0`. | Phase 2F |

**Fields the API returns that the UI ignores today:** all of `data_owner`, `tenant_code`, `business_type`, `report_date`, `file_date`, `source_file`, `ingested_at`, `loaded_at`, `import_batch_id` — none are referenced in the pricing-tab JSX. Phase 2F decides which become column-picker options (cf. open question Q3).

**Fields the UI reads that the API DOESN'T return:** none today (with current 11-column config). After Phase 2A+2B, all 47 new fields will be available; Phase 2F adds them to the table.

### 5.4 Filter-panel title strings — actual vs desired

| Tab | Component file:line | Current string | User-requested string |
|---|---|---|---|
| Airline / Pricing | [AirlineCpiPricingTab.tsx:121](apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:121) | `${tenantCode} Filters` → `JY Filters`/`PW Filters` | `JY Pricing Filters` / `PW Pricing Filters` |
| Airline / Velocity | [AirlineCpiVelocityTab.tsx:121](apps/web/src/pages/airline/AirlineCpiVelocityTab.tsx:121) | hardcoded literal `"JY Velocity Filters"` (NOT tenant-aware!) | `${tenantCode} Velocity Filters` → `JY Velocity Filters` / `PW Velocity Filters` |
| CFL | [CflCpiPage.tsx:130](apps/web/src/pages/cfl/CflCpiPage.tsx:130) | `${tenantCode} Filters` → `FJL Filters` | `FJL Pricing Filters` (only one tab today) |

The PW tab on Velocity currently displays "JY Velocity Filters" because the title string is hardcoded — independent of the active tenant. This is an existing bug surfaced by the multi-tenant audit and should be fixed in Phase 2F.

---

## 6. Multi-tenant isolation & view recreation

### 6.1 RLS policies on `airline_cpi_snapshot`

Unchanged since Round 1 (no migration since alembic 019). Two policies:
- `rls_airline_cpi_snapshot_superuser_bypass` — `TO cpi`, USING `true`, WITH CHECK `true`.
- `rls_airline_cpi_snapshot_tenant_isolation` — no `TO` clause (applies to all roles), USING and WITH CHECK both: `((tenant_id)::text = COALESCE(NULLIF(current_setting('app.current_tenant', true), ''), '00000000-0000-0000-0000-000000000000'))`.

Both policies operate on `tenant_id` only. **Adding columns to the table cannot affect RLS row visibility** — column-level changes are policy-neutral. ✅ Phase 2A is RLS-safe.

### 6.2 View definitions (current)

#### `vw_airline_cpi_jy_snapshot` (44 columns out)

```sql
SELECT id, tenant_id,
       cap_date, cap_time, trip_type,
       ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date, ref_cab_code,
       ref_tot_fare, ref_base_fare, ref_tax, ref_yq, ref_seats, ref_curr,
       comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
       comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats, comp_curr,
       pos, poa,
       (comp_tot_fare - ref_tot_fare) AS fare_delta,
       CASE WHEN ref_tot_fare > 0
            THEN round(((comp_tot_fare - ref_tot_fare) / ref_tot_fare) * 100, 2)
            ELSE NULL END AS fare_delta_pct,
       ingested_at, import_batch_id, source_file_id,
       tenant_code, business_type, report_date,
       report_date AS file_date,
       source_file, loaded_at
FROM airline_cpi_snapshot
WHERE tenant_code = 'JY';
```

#### `vw_airline_cpi_pw_snapshot`

Identical structure to `vw_airline_cpi_jy_snapshot` except `WHERE tenant_code = 'PW'`.

#### `vw_jy_fare_vs_load` (cross-domain join, JY-only)

JOIN of `airline_cpi_snapshot` (filtered `tenant_code='JY'`) with `velocity_snapshot` (filtered `airline_code='JY' AND legseg_type='Segment' AND leg_seg_order=1`) on `(origin, destination, dep_date, 'JY' || dep_code = ref_flt_num)`. Projects 21 columns including computed `fare_delta`, `fare_delta_pct`, `seats_available`, `booking_pct`. Used by analytics screens.

### 6.3 Phase 2A view recreation requirement

After ALTER TABLE adds the 47 columns:

- **`vw_airline_cpi_jy_snapshot`** and **`vw_airline_cpi_pw_snapshot`**: replace via `CREATE OR REPLACE VIEW` with the 47 new columns appended after the existing list (preserve `fare_delta`/`fare_delta_pct` computed fields and the `report_date AS file_date` alias).
- **`vw_jy_fare_vs_load`**: needs `CREATE OR REPLACE`. Since Postgres only accepts `CREATE OR REPLACE` when the existing column list is a strict prefix of the new one, and this view explicitly aliases columns (e.g. `a.id AS pricing_id`), **the alembic migration must DROP and CREATE this view, not REPLACE.** Wrap in a single transaction so it appears atomic.
- All three views can remain unchanged in their WHERE clauses — RLS does not need adjustment.

---

## 7. Migration plan

### 7.1 Column clusters (for Alembic migration readability)

The 47 new columns group logically as:

1. **Schedule-time fields** (4): `ref_dep_time`, `ref_arr_time`, `comp_dep_time`, `comp_arr_time` — BOTH tenants.
2. **Stops counts** (2): `ref_stops`, `comp_stops` — BOTH.
3. **Return-flight core** (8): `ref_ret_flt_num`, `ref_ret_dep_date`, `ref_ret_dep_time`, `ref_ret_arr_time`, `comp_ret_flt_num`, `comp_ret_dep_date`, `comp_ret_dep_time`, `comp_ret_arr_time` — JY-only.
4. **Via-stop fields** (4): `ref_via`, `ref_ret_via`, `comp_via`, `comp_ret_via` — JY-only (RefVia/CompVia originally listed `Yes`-required for JY; left nullable per migration safety rule).
5. **Return-flight stops** (2): `ref_ret_stops`, `comp_ret_stops` — JY-only.
6. **Fare-family codes** (2): `ref_ff_code` (JY-only), `comp_ff_code` (BOTH).
7. **Fare components** (4): `ref_yr`, `comp_yr` — BOTH; `ref_anc_price`, `ref_anc_type` — JY-only.
8. **Comp-side ancillaries** (2): `comp_anc_price`, `comp_anc_type` — BOTH.
9. **Cabin-class names** (4): `ref_cab_name`, `ref_ret_cab_name`, `comp_cab_name`, `comp_ret_cab_name` — BOTH/JY mixed.
10. **Booking class codes** (4): `ref_bkg_class`, `ref_ret_bkg_class`, `comp_bkg_class`, `comp_ret_bkg_class` — BOTH/JY mixed.
11. **Return cabin codes** (2): `ref_ret_cab_code`, `comp_ret_cab_code` — JY-only.
12. **Return seats** (2): `ref_ret_seats`, `comp_ret_seats` — JY-only.
13. **Equipment unification** (4): `ref_equip_code` (BOTH, target of unification), `ref_ret_equip_code`, `comp_equip_code`, `comp_ret_equip_code` — JY-only for the latter three.
14. **Point-of fields completion** (2): `pod`, `poc` — PW-source-only.
15. **Path** (1): `path` — neither source carries it; nullable (open Q5).

Total: 4+2+8+4+2+2+4+2+4+4+2+2+4+2+1 = 47 ✅

### 7.2 Execution phases (proposed)

#### Phase 2A — Alembic migration (DB schema + view recreation)

- New file: `apps/api/alembic/versions/<rev>_airline_cpi_dict_align.py`
- `upgrade()`:
  - 47 × `ALTER TABLE airline_cpi_snapshot ADD COLUMN <name> <type>` — all nullable, no defaults.
  - `CREATE OR REPLACE VIEW vw_airline_cpi_jy_snapshot ...` (with 47 new columns appended).
  - `CREATE OR REPLACE VIEW vw_airline_cpi_pw_snapshot ...` (same).
  - `DROP VIEW vw_jy_fare_vs_load; CREATE VIEW vw_jy_fare_vs_load ...` (the join view, since column-aliasing changes prevent `CREATE OR REPLACE` from working cleanly).
- `downgrade()`:
  - Reverse-order `DROP COLUMN`.
  - Recreate the three views with original SELECT-lists (captured verbatim in Section 6.2).
- Files modified: 1 new alembic file.
- Tests: `alembic upgrade head` then `alembic downgrade -1` round-trip in a docker-compose-up fresh DB.
- Risk: **low** (additive ALTERs, no data loss; views are recreated from verbatim source).
- Rollback: `alembic downgrade -1`.
- Estimated size: ~250 lines.

#### Phase 2B + 2E — ORM model + Pydantic response schema (combined)

- [apps/api/app/models/airline.py](apps/api/app/models/airline.py): add 47 new attributes (one `Column(...)` line each).
- [apps/api/app/schemas/airline.py](apps/api/app/schemas/airline.py): add 47 new fields plus the 9 currently-dropped fields (`ref_curr`, `comp_curr`, `tenant_code`, `report_date`, `file_date`, `source_file`, `business_type`, `ingested_at`, `loaded_at`) — all `Optional` with sensible defaults.
- [apps/api/app/routers/airline.py](apps/api/app/routers/airline.py): no change needed (already `SELECT * FROM <view>` returning a `RowMapping`).
- Files modified: 2.
- Tests: `GET /api/v1/airline/snapshots?tenant=JY` returns the new fields (NULL for existing rows; populated post-Phase-2D backfill); same for PW.
- Risk: low (additive, no removal of existing fields).
- Rollback: git revert.
- Estimated size: ~120 lines diff.

#### Phase 2C — Ingestion mapper

- [apps/api/app/ingestion/service.py:557-626](apps/api/app/ingestion/service.py:557): rewrite `_insert_airline_rows` INSERT/VALUES list and parameter mapping to include all 77 dict columns.
- Remove `pos='US'`/`poa='US'` literals; read from source.
- Add `ref_equip_code` unification: `(row.get("RefAircraft") or row.get("RefEquipCode"))[:32]`.
- Per-column type coercion using existing `safe_float`/`safe_int`/`parse_date`/`parse_time` helpers; HHMM clock fields stored as 4-char strings preserving leading zeros.
- No per-tenant branching needed (lenient `row.get()` returns None for absent JY/PW headers).
- Files modified: 1.
- Tests: re-run latest `JY_010426.xlsx` and `PW_010426.xlsx` through the mapper in a docker exec; confirm 7,022 JY rows + 15,365 PW rows insert with all 77 dict columns populated where source allows.
- Risk: **medium** (parsing edge cases; need to verify `safe_int(None)` returns 0 vs None semantics for nullable integer columns — currently always returns 0).
- Rollback: git revert.
- Estimated size: ~150 lines diff.

#### Phase 2D — Backfill (decision point — see open question Q1)

Two options:
- **(a) Re-ingest** the most recent JY+PW source files through the new mapper using the existing replace-existing path (DELETE WHERE `tenant_code` AND `report_date`, then INSERT). Source files are present in the repo at `dev-sftp-mount/{jy,pw}/` and in `apps/api/data/staging/` — easily re-runnable.
- **(b) Accept NULLs on history**; only future ingestions populate the new columns.

Recommendation: **(a)** — files exist locally, the replace-existing path is already in production use, and the alternative leaves 45,515 historical rows with most columns NULL forever. Deferred to user decision.

#### Phase 2F — Frontend

- [apps/web/src/pages/airline/AirlineCpiPricingTab.tsx](apps/web/src/pages/airline/AirlineCpiPricingTab.tsx): expand the 11-column table to expose the 47 new columns. Default visible subset = open Q3.
- [apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:121](apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:121): change FilterPanel title to `${tenantCode} Pricing Filters`.
- [apps/web/src/pages/airline/AirlineCpiVelocityTab.tsx:121](apps/web/src/pages/airline/AirlineCpiVelocityTab.tsx:121): replace hardcoded `"JY Velocity Filters"` with `${tenantCode} Velocity Filters`.
- [apps/web/src/pages/cfl/CflCpiPage.tsx:130](apps/web/src/pages/cfl/CflCpiPage.tsx:130): change to `${tenantCode} Pricing Filters`.
- [apps/web/src/utils/format.ts](apps/web/src/utils/format.ts): add second `formatCurrency(value, currencyCode)` overload that respects the row's `ref_curr`/`comp_curr`. Existing calls keep USD as fallback. Or — switch all call sites to the row-aware variant.
- [apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:159](apps/web/src/pages/airline/AirlineCpiPricingTab.tsx:159): guard delta-pct against `ref_tot_fare === 0` to avoid `NaN%`.
- [apps/web/src/types/index.ts](apps/web/src/types/index.ts): extend `AirlineSnapshot` interface with the 47 new fields plus 9 newly-exposed ones.
- Files modified: 4-6.
- Tests: browser smoke test for `jy@airline.com`, `pw@airline.com`, `admin@skywave.com` — fares render non-zero, currency symbol matches the row's `ref_curr`/`comp_curr`, all new columns visible (or available via column-picker per Q3), filter panel title matches the active tab.
- Risk: medium (UI regression on column widths; horizontal scrollbar; possible default-visibility user disagreement).
- Rollback: git revert.
- Estimated size: ~250 lines diff (depends on column-picker scope).

### 7.3 Per-phase risk / rollback summary

| phase | files_modified | risk   | rollback                   | est_size |
|-------|----------------|--------|----------------------------|----------|
| 2A    | 1 new alembic  | low    | `alembic downgrade -1`     | ~250 LoC |
| 2B+2E | 2 (model+schema) | low  | git revert                 | ~120 LoC |
| 2C    | 1 (mapper)     | medium | git revert                 | ~150 LoC |
| 2D    | 0 code; runs ingestion CLI | low | re-ingest old file (if backed up) | n/a |
| 2F    | 4-6 (frontend) | medium | git revert                 | ~250 LoC |

### 7.4 Open questions for user (must answer before Phase 2A)

#### Q1. Backfill strategy (Phase 2D)

(a) Re-ingest the most recent JY+PW source files through the new mapper to populate new columns on existing rows.
(b) Accept NULLs on history; only new ingestions populate the new columns.

Recommendation: **(a)** — source files are present in the repo and the replace-existing path is already production-tested.

#### Q2. Validation strictness for Phase 2C

- **STRICT** — reject row if any dict-required column is missing/empty for that row's tenant.
- **LENIENT** — current behavior; warn-and-proceed, leave NULL.

Recommendation: **LENIENT** for first pass (current behavior). Tightening to STRICT later requires deciding what "required" means when the dict says Yes but the source physically doesn't carry the column (e.g. `RefEquipCode` for PW).

#### Q3. Default column visibility for Phase 2F

- **All 77 visible by default** (very wide table, lots of horizontal scroll).
- **Curated default subset** (~12-15 columns matching today's view), rest behind a column-picker dropdown.

Recommendation: **curated subset**. Suggested default: today's 11 columns + `ref_equip_code` + `comp_equip_code` + `ref_ff_code` + `comp_ff_code` (15 total). Everything else available via column-picker.

#### Q4. Currency conversion

Source files carry fares in their own currency (PW=GBP/KES, JY=GBP). Display:
- **As-is** — show the row's `ref_curr` and `comp_curr` symbols verbatim.
- **Convert** — pick a tenant-preferred display currency at API time (requires FX rate table — out of scope today).

Recommendation: **as-is**. Adds zero new infrastructure; matches the data semantics.

#### Q5. `path` column treatment

Dictionary marks `Path` (Sr. No. 77) as Yes-required, but neither source file emits it. Options:
- Add `path` as nullable; mapper writes NULL forever (until source files are extended).
- Defer adding `path` to a later migration once the source teams confirm whether they will add the column.
- Synthesize `path` from `source_file` (i.e., copy the filename into `path`) — meets the dict letter, but the value is not what the dict description suggests ("Data extraction path identifier").

Recommendation: **add as nullable; do not synthesize.** Surface to source teams (PW, JY) as a data-quality follow-up.

---

## 8. Locked-in decisions (recap)

1. **Drop `RefArrDate`** (PW-only). Not migrated. The PW source file already omits it (per Section 1.5), so this is a no-op for ingestion.
2. **Canonical equipment column = `ref_equip_code`.** Mapper translates JY's `RefAircraft` → `ref_equip_code` and PW's `RefEquipCode` → `ref_equip_code`. Three sibling columns follow the `_equip_code` naming convention: `ref_ret_equip_code`, `comp_equip_code`, `comp_ret_equip_code`.
3. **`airline_cpi_snapshot` stays consolidated.** No per-tenant split. Round-2 audit confirmed JY/PW columns are functionally symmetric (38/41 shared, 1 skewed, 2 sparse-both). Adding 47 nullable columns preserves that property.

Final shape post-migration:
- 30 dict columns currently in DB (17 PRESENT_OK + 13 PRESENT_MISMATCH)
- + 47 new dict columns (Phase 2A)
- + 11 infra columns (`tenant_id, import_batch_id, source_file_id, record_hash, ingested_at, data_owner, tenant_code, business_type, report_date, source_file, loaded_at`)
- = **88 physical columns, matching the locked target.**
