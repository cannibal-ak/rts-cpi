/**
 * In-memory mock API client — for offline demos without a backend.
 */
import type { CpiApiClient, SnapshotQuery, JobQuery } from './client';
import type {
  Paginated,
  ImportBatch,
  AlertRule,
} from '../types';
import {
  mockAirlineSnapshots, mockCflSnapshots, mockIngestionJobs,
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
    listJobs: (q?: JobQuery) => {
      let jobs = [...mockIngestionJobs];
      if (q?.domain) jobs = jobs.filter(j => j.domain === q.domain);
      if (q?.status) jobs = jobs.filter(j => j.status === q.status);
      if (q?.tenant) jobs = jobs.filter(j => j.tenant_code === q.tenant);
      return delay(paginate(jobs, q?.page, q?.page_size));
    },
    getJob: (id: string) => delay(mockIngestionJobs.find(j => j.id === id) || null),
    listJobBatches: (_jobId: string) => delay([] as ImportBatch[]),
    triggerIngest: (_tenant?: string, _force?: boolean) => delay({ message: 'Mock ingestion triggered', results: [] }),
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
