/**
 * In-memory mock API client — for offline demos without a backend.
 */
import type { CpiApiClient, SnapshotQuery, JobQuery } from './client';
import type {
  Paginated,
  AlertRule,
  IngestionJob,
  IngestionUploadResponse,
  IngestionValidationResult,
  IngestionCommitResult,
  IngestionAuditLog,
  IngestionPreview,
} from '../types';
import {
  mockAirlineSnapshots, mockCflSnapshots,
  mockAlertRules, mockAlertEvents,
  mockTenantFeatures,
  mockFilterMetadata,
} from './mockData';

function paginate<T>(items: T[], page = 1, size = 20): Paginated<T> {
  const start = (page - 1) * size;
  const slice = items.slice(start, start + size);
  return {
    items: slice,
    page_info: { total: items.length, page, page_size: size, has_next: start + size < items.length },
  };
}

function delay<T>(val: T, ms = 120): Promise<T> {
  return new Promise(r => setTimeout(() => r(val), ms));
}

export const mockClient: CpiApiClient = {
  airline: {
    listSnapshots: (q?: SnapshotQuery) =>
      delay(paginate(mockAirlineSnapshots, q?.page as number, q?.page_size as number)),
    getFilterMetadata: (_tenant?: string) => delay(mockFilterMetadata.airline),
    exportSnapshots: (_q?: Record<string, string>) => delay(undefined),
    velocity: {
      listSnapshots: (q?: SnapshotQuery) =>
        delay(paginate([], q?.page as number, q?.page_size as number)),
      getFilterMetadata: (_tenant?: string) => delay([]),
      exportSnapshots: (_q?: Record<string, string>) => delay(undefined),
    },
  },
  cfl: {
    listSnapshots: (q?: SnapshotQuery) =>
      delay(paginate(mockCflSnapshots, q?.page as number, q?.page_size as number)),
    getFilterMetadata: (_tenant?: string) => delay(mockFilterMetadata.cfl),
    exportSnapshots: (_q?: Record<string, string>) => delay(undefined),
  },
  ingestion: {
    // Phase A overhaul — no realistic in-memory simulation of staged uploads;
    // the mock client returns empty/no-op results so the offline-demo build
    // still type-checks. Live development uses the real httpClient.
    listJobs: (q?: JobQuery) =>
      delay(paginate([] as IngestionJob[], q?.page, q?.page_size)),
    getJob: (_id: string) => delay(null),
    upload: (_files: File[]) =>
      delay({ files: [], summary: { accepted: 0, duplicate: 0, conflict: 0, rejected: 0 } } as IngestionUploadResponse),
    validate: (_id: string) => Promise.reject(new Error('Mock client does not implement ingestion.validate')) as Promise<IngestionValidationResult>,
    commit: (_id: string, _replace: boolean) => Promise.reject(new Error('Mock client does not implement ingestion.commit')) as Promise<IngestionCommitResult>,
    cancel: (_id: string) => Promise.reject(new Error('Mock client does not implement ingestion.cancel')) as Promise<IngestionJob>,
    getAudit: (id: string) => delay({ job_id: id, entries: [] } as IngestionAuditLog),
    getPreview: (id: string) => delay({ job_id: id, sample_valid: [], sample_rejected: [] } as IngestionPreview),
  },
  alerts: {
    listRules: () => delay([...mockAlertRules]),
    createRule: (rule) => delay({ ...rule, id: `rule-${Date.now()}`, created_at: new Date().toISOString() } as AlertRule),
    listEvents: () => delay([...mockAlertEvents]),
  },
  admin: {
    getTenantFeatures: () => delay([...mockTenantFeatures]),
    setTenantFeature: (code, enabled) => {
      const f = mockTenantFeatures.find(tf => tf.code === code);
      if (f) f.enabled = enabled;
      return delay(f || { code, label: code, category: 'module' as const, enabled });
    },
  },
  stats: {
    getFreshnessMetrics: () => delay([
      { domain: 'Airline CPI', last_capture_at: '2026-03-05T08:30:00Z', last_import_at: '2026-03-05T09:15:00Z', record_count: 245890, status: 'fresh' },
      { domain: 'Cruise/Ferry CPI', last_capture_at: '2026-03-04T22:00:00Z', last_import_at: '2026-03-05T01:30:00Z', record_count: 18432, status: 'stale' },
    ]),
  },
  tenant: {
    getUserRoles: () => delay({ roles: ['TENANT_ADMIN'] }),
    updateUserRoles: (roles, _tenant_id) => delay({ roles }),
  },
  superset: {
    getGuestToken: (dashboardId: string) => delay({
        token: `mock-token-${dashboardId}-${Date.now()}`,
        dashboard_uuid: `00000000-0000-0000-0000-00000000000${dashboardId}`,
        embedded_uuid: `11111111-1111-1111-1111-11111111111${dashboardId}`,
        dashboard_title: dashboardId === '1' ? 'Airline CPI JY Dashboard'
                       : dashboardId === '2' ? 'Airline CPI PW Dashboard'
                       : 'Cruise/Ferry CPI Dashboard',
    }),
  },
};
