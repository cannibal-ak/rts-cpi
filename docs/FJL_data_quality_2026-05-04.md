# FJL data-quality issue — 2026-05-04 ingestion

**Status:** open · **Filed:** 2026-05-15 · **Affects:** `cfl_cpi_snapshot`
(and therefore `vw_cfl_cpi_fjl_snapshot`, the FJL dashboard's source)

## Summary

On the single capture date **2026-05-04**, the FJL ingestion landed **11
extra "routes" that never appear on any other date** in the snapshot.
The other 6 cap_dates in the dataset (2026-05-03, 05-05, 05-06, 05-07,
05-14) all consistently carry exactly **4 routes** — the real Color Line /
Fjord Line Norway↔Denmark corridors. The 2026-05-04 row also carries those
4 legitimate routes, plus 11 additional records that look like noise.

This caused the FJL "Routes Covered" KPI on the dashboard to read as **15**
when an across-all-dates aggregation was tried, even though FJL only
actually tracks 4 routes day-to-day.

The dashboard side has been fixed (Cap Date now defaults to the latest
date, where coverage is the real 4-route number).  This note documents the
underlying data-quality issue so it can be addressed at the ingestion /
view layer when there is time.

## What the data looks like

### The 4 legitimate routes (appear on every cap_date)

| Route |
| --- |
| Hirtshals → Kristiansand |
| Hirtshals → Larvik |
| Kristiansand → Hirtshals |
| Larvik → Hirtshals |

Stable row counts per cap_date: ~3,000 + ~1,350 + ~3,000 + ~1,350 ≈ 9,000
records/day.

### The 11 extras that appear only on 2026-05-04

#### a) 5 same-city pairs — these cannot be ferry routes

| "Route" | Rows |
| --- | --- |
| Bergen → Bergen | 365 |
| Copenhagen → Copenhagen | 365 |
| Kiel → Kiel | 241 |
| Oslo → Oslo | 606 |
| Stavanger → Stavanger | 365 |

Ferries don't sail from a port to itself.  Either the upstream feed
emitted these as placeholders, or `org` and `dest` got the same value
through a mapping bug.  Three of them are exactly **365** rows, which is
suspicious (= days in a year, smells like generated/test data).

#### b) 6 plausible-looking routes that appear once and vanish

| "Route" | Rows |
| --- | --- |
| Bergen → Hirtshals | 750 |
| Hirtshals → Bergen | 711 |
| Hirtshals → Stavanger | 711 |
| Stavanger → Hirtshals | 750 |
| Kiel → Oslo | 744 |
| Oslo → Kiel | 744 |

These reference real ports.  Bergen, Stavanger, Kiel, Oslo are not in any
other cap_date's data.  Either a one-off broader scrape ran that day and
was never repeated, or the records are bad but happen to have
ferry-plausible origin/destination values.  The round numbers (744, 750,
~711) are also a hint of synthetic data.

## SQL to reproduce

```sql
-- 1. Confirm the day-by-day route count
SELECT cap_date,
       COUNT(DISTINCT org || ' → ' || dest) AS routes
FROM cfl_cpi_snapshot
GROUP BY cap_date
ORDER BY cap_date;
-- expected: 4, 15, 4, 4, 4, 4

-- 2. List the 5 same-city pairs on 2026-05-04
SELECT cap_date, org, dest, COUNT(*) AS rows
FROM cfl_cpi_snapshot
WHERE cap_date = '2026-05-04'
  AND org = dest
GROUP BY cap_date, org, dest
ORDER BY org;
-- expected: 5 rows (Bergen→Bergen, Copenhagen→Copenhagen, Kiel→Kiel,
--                    Oslo→Oslo, Stavanger→Stavanger)

-- 3. List the 6 one-off real-port routes (= appear on 2026-05-04 only,
--    are NOT same-city, are NOT one of the 4 standard corridors)
SELECT cap_date, org, dest, COUNT(*) AS rows
FROM cfl_cpi_snapshot
WHERE cap_date = '2026-05-04'
  AND org <> dest
  AND (org, dest) NOT IN (
      ('Hirtshals','Kristiansand'),
      ('Hirtshals','Larvik'),
      ('Kristiansand','Hirtshals'),
      ('Larvik','Hirtshals')
  )
GROUP BY cap_date, org, dest
ORDER BY org, dest;
-- expected: 6 rows
```

## Recommended follow-ups (not done in this task)

1. **Quarantine 2026-05-04 extras.**  Add a defensive `WHERE org <> dest`
   clause to `vw_cfl_cpi_fjl_snapshot` so same-city pairs are dropped from
   every downstream chart automatically.  Proper migration, not a hot-patch.
2. **Investigate the ingestion run** that produced 2026-05-04.  Was it a
   one-time wider scrape, a test run that hit prod, or a parser bug?  The
   audit log (`ingestion_audit_log` table) should have the import batch.
3. **Add an ingestion validation rule**: reject any row where `org = dest`
   on cruise/ferry sources.  Cheap, catches this class of bug for free.
4. **Decide on the historical row treatment**: leave the 2026-05-04 noise
   in place (currently hidden from the dashboard via the latest-date
   filter default), or delete it from `cfl_cpi_snapshot` with a one-shot
   cleanup migration.  Either is fine; deleting is cleaner long-term.

## Why the dashboard fix alone was the right scope

The KPI audit task (2026-05-15) explicitly excluded base-view and base-table
changes.  Defaulting the Cap Date filter to the latest date is a complete
fix for the **user-visible KPI mismatch** — every cap_date except 05-04
shows the truthful 4-route coverage, and the latest date is always one of
those.  The 05-04 anomaly stays in the underlying data until the ingestion
team handles it.

## Related artifacts

- Backups taken before the KPI fix:
  `/home/ankitprajapati/CPI/backups/kpi_audit_20260515_094348/dashboard_{1,2,3}.json`
- Superset SQLite snapshot inside the container:
  `/app/superset_home/superset.db.bak_kpi_audit_20260515_094349`
- Dashboard change applied: `defaultDataMask.filterState.value` of each
  dashboard's Cap Date filter set to `['2026-05-14']` (JY id=1, FJL id=2,
  PW id=3).
