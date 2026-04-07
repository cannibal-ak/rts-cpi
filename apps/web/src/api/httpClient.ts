/**
 * HTTP-based API client — talks to the real FastAPI backend.
 * Activated when VITE_API_BASE_URL is set.
 */
import type { CpiApiClient, SnapshotQuery, JobQuery } from './client';
import type {
  Paginated, AirlineSnapshot, CflSnapshot, FilterMetadata,
  IngestionJob, ImportBatch, AlertRule, AlertEvent,
  TenantFeature, DataFreshness,
} from '../types';

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const TENANT_ID = import.meta.env.VITE_TENANT_ID || '';
const USER_ROLES = import.meta.env.VITE_USER_ROLES || 'TENANT_ADMIN,DATA_ENGINEER,ANALYST,AUDITOR';

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  
  try {
    const stored = localStorage.getItem('rts_cpi_auth');
    if (stored) {
      const payload = JSON.parse(atob(stored));
      if (payload.tenantId) h['X-Tenant-ID'] = payload.tenantId;
      else if (TENANT_ID) h['X-Tenant-ID'] = TENANT_ID;

      if (payload.name) {
        h['X-User-Identity'] = payload.name;
        
        // Map names to roles for demo RBAC enforcement
        if (payload.name === 'Alex Rivera' || payload.name === 'Tenant Admin') {
          h['X-User-Roles'] = 'TENANT_ADMIN';
        } else if (payload.name.includes('Airline')) {
          h['X-User-Roles'] = 'ANALYST,AIRLINE_USER';
        } else if (payload.name.includes('Cruise')) {
          h['X-User-Roles'] = 'ANALYST,CRUISE_USER';
        } else {
          h['X-User-Roles'] = 'ANALYST';
        }
      }
    } else if (TENANT_ID) {
      h['X-Tenant-ID'] = TENANT_ID;
      if (USER_ROLES) h['X-User-Roles'] = USER_ROLES;
    }
  } catch (e) {
    if (TENANT_ID) h['X-Tenant-ID'] = TENANT_ID;
    if (USER_ROLES) h['X-User-Roles'] = USER_ROLES;
  }
  
  return h;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = '';
    try {
      const errorData = await res.json();
      detail = errorData.detail?.message || errorData.detail || JSON.stringify(errorData);
    } catch {
      detail = res.statusText;
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    });
  }
  try {
    const res = await fetch(url.toString(), { headers: headers() });
    return handleResponse<T>(res);
  } catch (err: any) {
    if (err.message.startsWith('API ')) throw err;
    throw new Error(`Network Error: ${err.message}. Is the backend at ${BASE} reachable?`);
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res);
  } catch (err: any) {
    if (err.message.startsWith('API ')) throw err;
    throw new Error(`Network Error: ${err.message}`);
  }
}


async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

async function download(path: string, params?: Record<string, string | number | undefined>): Promise<void> {
  const url = new URL(path, BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), { headers: headers() });
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);

  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition');
  let filename = 'export.xlsx';
  if (disposition && disposition.includes('attachment')) {
    const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
    const matches = filenameRegex.exec(disposition);
    if (matches != null && matches[1]) {
      filename = matches[1].replace(/['"]/g, '');
    }
  }

  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}

export const httpClient: CpiApiClient = {
  airline: {
    listSnapshots: (q?: SnapshotQuery) =>
      get<Paginated<AirlineSnapshot>>('/api/v1/airline/snapshots', q as Record<string, string | number | undefined>),
    getFilterMetadata: (tenant?: string) =>
      get<FilterMetadata[]>('/api/v1/airline/filter-metadata', tenant ? { tenant } : undefined),
    exportSnapshots: (q?: Record<string, string>) =>
      download('/api/v1/airline/export', q),
  },
  cfl: {
    listSnapshots: (q?: SnapshotQuery) =>
      get<Paginated<CflSnapshot>>('/api/v1/cfl/snapshots', q as Record<string, string | number | undefined>),
    getFilterMetadata: (tenant?: string) =>
      get<FilterMetadata[]>('/api/v1/cfl/filter-metadata', tenant ? { tenant } : undefined),
    exportSnapshots: (q?: Record<string, string>) =>
      download('/api/v1/cfl/export', q),
  },
  ingestion: {
    listJobs: (q?: JobQuery) =>
      get<Paginated<IngestionJob>>('/api/v1/ingestion/jobs', q as Record<string, string | number | undefined>),
    getJob: (id: string) =>
      get<IngestionJob>(`/api/v1/ingestion/jobs/${id}`),
    listJobBatches: (jobId: string) =>
      get<ImportBatch[]>(`/api/v1/ingestion/jobs/${jobId}/batches`),
    triggerIngest: async (tenant?: string, force?: boolean) => {
      const params = new URLSearchParams();
      if (tenant) params.set('tenant', tenant);
      if (force) params.set('force', 'true');
      const qs = params.toString();
      const url = `${BASE}/api/v1/ingestion/ingest${qs ? '?' + qs : ''}`;
      const res = await fetch(url, { method: 'POST', headers: headers() });
      return handleResponse<{ message: string; results: any[] }>(res);
    },
  },
  alerts: {
    listRules: () => get<AlertRule[]>('/api/v1/alerts/rules'),
    createRule: (rule) => post<AlertRule>('/api/v1/alerts/rules', rule),
    listEvents: () => get<AlertEvent[]>('/api/v1/alerts/events'),
  },

  admin: {
    getTenantFeatures(): Promise<TenantFeature[]> { return get<TenantFeature[]>('/api/v1/admin/tenant/features'); },
    setTenantFeature(code: string, enabled: boolean): Promise<TenantFeature> {
      return patch<TenantFeature>(`/api/v1/admin/tenant/features/${code}`, { enabled });
    },
  },
  stats: {
    getFreshnessMetrics: () => get<DataFreshness[]>('/api/v1/stats/freshness'),
  },
  tenant: {
    getUserRoles: () => get<{ roles: string[] }>('/api/v1/tenant/user-roles'),
    updateUserRoles: (roles, tenant_id) => post<{ roles: string[] }>('/api/v1/tenant/update-roles', { tenant_id, roles }),
  },
  superset: {
    getGuestToken: (dashboardId: string) =>
      get<{
        token: string;
        dashboard_uuid: string;
        embedded_uuid: string;
        dashboard_title: string;
      }>(`/api/v1/superset/guest-token`, { dashboard_id: dashboardId }),
  },
};
