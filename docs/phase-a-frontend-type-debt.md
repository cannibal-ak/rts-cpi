# Phase A Frontend Type Debt

**Status:** Filed for Phase 5 housekeeping. Out of Phase 4 scope. Discovered May 4 2026 during Phase 4.1b setup.

**Symptom:** `apps/web/tsconfig.json` had no `moduleResolution` set, defaulting to `"classic"` with `module: "ESNext"`, which caused `tsc` to error on `resolveJsonModule` and silently bypass project-wide type-checking. When fixed (added `moduleResolution: "bundler"`), 25 pre-existing dormant errors surfaced.

## Category A (15 errors) — auto-fixable

`TS6133`/`TS6192` unused imports / declarations across:

- `App.tsx`
- `api/httpClient.ts`
- `components/common/DataFreshnessIndicator.tsx`, `KpiTiles.tsx`, `StatusChip.tsx`, `StatusTimeline.tsx`
- `components/layout/AppBar.tsx`, `MainLayout.tsx`, `Sidebar.tsx`
- `context/AuthContext.tsx`, `ThemeContext.tsx`
- `hooks/useAccess.ts`
- `pages/NotAuthorizedPage.tsx`, `NotFoundPage.tsx`
- `pages/ingestion/UploadPage.tsx`
- `pages/login/LoginPage.tsx`
- `pages/superset/DashboardViewerPage.tsx`

Currently silenced via `noUnusedLocals: false` + `noUnusedParameters: false` in `apps/web/tsconfig.json`. Re-enable both flags and run `tsc --noEmit` to surface; fix by removing the dead imports.

## Category B (12 errors) — real type-reference breaks

| Location | Symptom |
|---|---|
| `api/index.ts:7` | imports `ErrorQuery`, `AuditQuery` from `./client` (don't exist) |
| `api/mockData.ts:2` | imports `ValidationError` from `../types` (doesn't exist) |
| `api/mockData.ts:4` | imports `JobTimelineEntry` from `../types` (doesn't exist) |
| `api/mockData.ts:163` | `IngestionJob[]` mock missing 16+ required fields (`tenant_id`, `filename`, `file_hash`, `file_size_bytes`, …) |
| `api/mockClient.ts:83` | `DataFreshness[]` missing `report_date` |
| `components/common/StatusTimeline.tsx:4` | imports `JobTimelineEntry`, `JobStatus` from `../../types` (don't exist) |
| `mock/session.ts:1` | imports `SourceConfig` from `../types` (doesn't exist) |
| `mock/session.ts:14` | `"contracts"` not assignable to `Capability` (`Capability = 'alerts' \| 'exports' \| 'saved_views'`) |
| `mock/session.ts:49` | `DataFreshness` mock entry missing `report_date` |
| `mock/session.ts:50` | `DataFreshness` mock entry missing `report_date` |

Likely root cause: a refactor of `types/index.ts` (probably the Phase A → Phase B transition) removed exports that consumers still reference. The tsconfig bug masked it.

## Recommended Phase 5 fix

1. Add the missing type exports back (`ValidationError`, `JobTimelineEntry`, `JobStatus`, `SourceConfig`, `ErrorQuery`, `AuditQuery`), or refactor consumers to use current types.
2. Update the `IngestionJob` mock to match the current schema.
3. Decide whether `'contracts'` belongs in the `Capability` enum or `mock/session.ts` is wrong.
4. Add `report_date` to all `DataFreshness` mock entries.
5. Re-enable `noUnusedLocals` + `noUnusedParameters` in `apps/web/tsconfig.json`.
6. Run `tsc --noEmit` and confirm zero errors.

## Diagnostic record

Phase 4.1b chat session, May 4 2026. Baseline = 12 errors after `noUnusedLocals`/`noUnusedParameters` relaxed; do not let new edits push the count higher without an explanation.
