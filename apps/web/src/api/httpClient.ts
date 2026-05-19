/**
 * HTTP-based API client — talks to the real FastAPI backend.
 * Uses JWT Bearer tokens for authentication (Phase 2).
 */
import type { CpiApiClient, SnapshotQuery, JobQuery, DashboardChartsResponse, DashboardDateFilter } from './client';
import type {
  Paginated, AirlineSnapshot, VelocitySnapshot, CflSnapshot, FilterMetadata,
  AlertRule, AlertEvent,
  TenantFeature, DataFreshness,
  SftpConnection, SftpConnectionCreate, SftpConnectionUpdate,
  SftpConnectionTestResult, SftpConnectionListQuery,
  IngestionSchedule, IngestionScheduleCreate, IngestionScheduleUpdate,
  IngestionScheduleListQuery, RunNowResult,
  IngestionRun, IngestionRunDetail, IngestionRunListQuery,
  AdminUserListResponse, AdminResetTokenListResponse,
  AdminGenerateResetCodeResponse, AdminForceResetResponse,
  PlatformHealthResponse, TenantSummaryResponse,
  IngestionJob, IngestionUploadResponse, IngestionValidationResult, IngestionCommitResult, IngestionAuditLog, IngestionPreview,
} from '../types';
import type {
  SmtpConfigRead, SmtpConfigUpdate, SmtpTestRequest, SmtpTestResponse,
} from '../types/smtpConfig';
import { authStorage } from '../utils/authStorage';

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Access token is stored here and managed by AuthContext
let _accessToken: string | null = null;

export function setHttpClientAccessToken(token: string | null) {
  _accessToken = token;
}

export function getHttpClientAccessToken(): string | null {
  return _accessToken;
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (_accessToken) {
    h['Authorization'] = `Bearer ${_accessToken}`;
  }
  return h;
}

async function attemptRefresh(): Promise<boolean> {
  const refreshToken = authStorage.getRefreshToken();
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (res.ok) {
      const data = await res.json();
      _accessToken = data.access_token;
      return true;
    }
  } catch {
    // Refresh failed
  }
  return false;
}

/**
 * Shape of the structured fields attached to thrown API errors. Cast via:
 *   const e = err as Error & ApiErrorShape;
 * to access status / errorCode / details from a caller's catch block. The
 * legacy ``err.message.startsWith('API ')`` check is preserved for code
 * that hasn't been migrated.
 */
export interface ApiErrorShape {
  status?: number;
  errorCode?: string;
  details?: Record<string, unknown>;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = '';
    let errorCode = '';
    let details: Record<string, unknown> = {};
    try {
      const data = await res.json();
      if (typeof data.detail === 'object' && data.detail !== null) {
        const d = data.detail as Record<string, unknown>;
        message = (d.message as string) || JSON.stringify(d);
        errorCode = (d.error_code as string) || (d.code as string) || '';
        details = (d.details as Record<string, unknown>) || {};
      } else {
        message = (data.detail as string) || JSON.stringify(data);
      }
    } catch {
      message = res.statusText;
    }

    // Handle forced password change
    if (res.status === 403 && errorCode === 'PASSWORD_CHANGE_REQUIRED') {
      window.location.href = '/change-password';
      throw new Error('Password change required');
    }

    const err = new Error(`API ${res.status}: ${message}`) as Error & ApiErrorShape;
    err.status = res.status;
    err.errorCode = errorCode;
    err.details = details;
    throw err;
  }
  // 204 No Content has no body — fetch's res.json() would throw
  // "Unexpected end of JSON input". Phase 3's DELETE endpoints return
  // 204; resolve with undefined so callers typed Promise<void> work.
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

async function fetchWithAuth<T>(url: string, init: RequestInit): Promise<T> {
  let res = await fetch(url, init);

  // On 401, attempt a single refresh then retry
  if (res.status === 401) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      // Update headers with new token
      const newInit = { ...init, headers: { ...headers() } };
      res = await fetch(url, newInit);
    } else {
      // Refresh failed — force logout by clearing state and redirecting
      authStorage.removeRefreshToken();
      _accessToken = null;
      window.location.href = '/login';
      throw new Error('Session expired');
    }
  }

  return handleResponse<T>(res);
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    });
  }
  try {
    return await fetchWithAuth<T>(url.toString(), { headers: headers() });
  } catch (err: any) {
    if (err.message.startsWith('API ') || err.message === 'Session expired' || err.message === 'Password change required') throw err;
    throw new Error(`Network Error: ${err.message}. Is the backend at ${BASE} reachable?`);
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  try {
    return await fetchWithAuth<T>(`${BASE}${path}`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(body),
    });
  } catch (err: any) {
    if (err.message.startsWith('API ') || err.message === 'Session expired' || err.message === 'Password change required') throw err;
    throw new Error(`Network Error: ${err.message}`);
  }
}


async function put<T>(path: string, body: unknown): Promise<T> {
  return fetchWithAuth<T>(`${BASE}${path}`, {
    method: 'PUT',
    headers: headers(),
    body: JSON.stringify(body),
  });
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  return fetchWithAuth<T>(`${BASE}${path}`, {
    method: 'PATCH',
    headers: headers(),
    body: JSON.stringify(body),
  });
}

async function del<T>(path: string): Promise<T> {
  return fetchWithAuth<T>(`${BASE}${path}`, {
    method: 'DELETE',
    headers: headers(),
  });
}

async function postMultipart<T>(path: string, files: File[]): Promise<T> {
  // Don't set Content-Type — the browser injects the multipart boundary.
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f, f.name));
  const init: RequestInit = {
    method: 'POST',
    headers: _accessToken ? { Authorization: `Bearer ${_accessToken}` } : {},
    body: fd,
  };
  try {
    return await fetchWithAuth<T>(`${BASE}${path}`, init);
  } catch (err: any) {
    if (err.message.startsWith('API ') || err.message === 'Session expired' || err.message === 'Password change required') throw err;
    throw new Error(`Network Error: ${err.message}`);
  }
}

async function download(path: string, params?: Record<string, string | number | undefined>): Promise<void> {
  const url = new URL(path, BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), { headers: headers() });

  if (res.status === 401) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      const retryRes = await fetch(url.toString(), { headers: headers() });
      if (!retryRes.ok) throw new Error(`Download failed: ${retryRes.status}`);
      return processDownload(retryRes);
    }
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  return processDownload(res);
}

async function processDownload(res: Response): Promise<void> {
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
    velocity: {
      listSnapshots: (q?: SnapshotQuery) =>
        get<Paginated<VelocitySnapshot>>('/api/v1/airline/velocity/snapshots', q as Record<string, string | number | undefined>),
      getFilterMetadata: (tenant?: string) =>
        get<FilterMetadata[]>('/api/v1/airline/velocity/filter-metadata', tenant ? { tenant } : undefined),
      exportSnapshots: (q?: Record<string, string>) =>
        download('/api/v1/airline/velocity/export', q),
    },
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
    upload: (files: File[]) =>
      postMultipart<IngestionUploadResponse>('/api/v1/ingestion/upload', files),
    validate: (id: string) =>
      post<IngestionValidationResult>(`/api/v1/ingestion/jobs/${id}/validate`, {}),
    commit: (id: string, replaceExisting: boolean) =>
      post<IngestionCommitResult>(`/api/v1/ingestion/jobs/${id}/commit`, { replace_existing: replaceExisting }),
    cancel: (id: string) =>
      del<IngestionJob>(`/api/v1/ingestion/jobs/${id}`),
    getAudit: (id: string) =>
      get<IngestionAuditLog>(`/api/v1/ingestion/jobs/${id}/audit`),
    getPreview: (id: string) =>
      get<IngestionPreview>(`/api/v1/ingestion/jobs/${id}/preview`),
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

    // ── Phase 3 SFTP-driven ingestion admin (16 endpoints) ──
    sftpConnections: {
      list: (query?: SftpConnectionListQuery) => {
        const params: Record<string, string | number | undefined> = {};
        if (query?.page !== undefined) params.page = query.page;
        if (query?.page_size !== undefined) params.page_size = query.page_size;
        if (query?.tenant_code !== undefined) params.tenant_code = query.tenant_code;
        if (query?.is_active !== undefined) params.is_active = String(query.is_active);
        return get<Paginated<SftpConnection>>('/api/v1/admin/sftp-connections/', params);
      },
      get: (id: string) =>
        get<SftpConnection>(`/api/v1/admin/sftp-connections/${id}`),
      create: (body: SftpConnectionCreate) =>
        post<SftpConnection>('/api/v1/admin/sftp-connections/', body),
      update: (id: string, body: SftpConnectionUpdate) =>
        put<SftpConnection>(`/api/v1/admin/sftp-connections/${id}`, body),
      delete: (id: string) =>
        del<void>(`/api/v1/admin/sftp-connections/${id}`),
      test: (id: string) =>
        post<SftpConnectionTestResult>(`/api/v1/admin/sftp-connections/${id}/test`, {}),
    },
    ingestionSchedules: {
      list: (query?: IngestionScheduleListQuery) => {
        const params: Record<string, string | number | undefined> = {};
        if (query?.page !== undefined) params.page = query.page;
        if (query?.page_size !== undefined) params.page_size = query.page_size;
        if (query?.tenant_code !== undefined) params.tenant_code = query.tenant_code;
        if (query?.is_enabled !== undefined) params.is_enabled = String(query.is_enabled);
        if (query?.sftp_connection_id !== undefined) params.sftp_connection_id = query.sftp_connection_id;
        return get<Paginated<IngestionSchedule>>('/api/v1/admin/ingestion-schedules/', params);
      },
      get: (id: string) =>
        get<IngestionSchedule>(`/api/v1/admin/ingestion-schedules/${id}`),
      create: (body: IngestionScheduleCreate) =>
        post<IngestionSchedule>('/api/v1/admin/ingestion-schedules/', body),
      update: (id: string, body: IngestionScheduleUpdate) =>
        put<IngestionSchedule>(`/api/v1/admin/ingestion-schedules/${id}`, body),
      delete: (id: string) =>
        del<void>(`/api/v1/admin/ingestion-schedules/${id}`),
      enable: (id: string) =>
        post<IngestionSchedule>(`/api/v1/admin/ingestion-schedules/${id}/enable`, {}),
      disable: (id: string) =>
        post<IngestionSchedule>(`/api/v1/admin/ingestion-schedules/${id}/disable`, {}),
      runNow: (id: string) =>
        post<RunNowResult>(`/api/v1/admin/ingestion-schedules/${id}/run-now`, {}),
    },
    ingestionRuns: {
      list: (query?: IngestionRunListQuery) => {
        const params: Record<string, string | number | undefined> = {};
        if (query?.page !== undefined) params.page = query.page;
        if (query?.page_size !== undefined) params.page_size = query.page_size;
        if (query?.tenant_code !== undefined) params.tenant_code = query.tenant_code;
        if (query?.schedule_id !== undefined) params.schedule_id = query.schedule_id;
        if (query?.status !== undefined) params.status = query.status;
        if (query?.started_after !== undefined) params.started_after = query.started_after;
        if (query?.started_before !== undefined) params.started_before = query.started_before;
        return get<Paginated<IngestionRun>>('/api/v1/admin/ingestion-runs/', params);
      },
      get: (id: string) =>
        get<IngestionRunDetail>(`/api/v1/admin/ingestion-runs/${id}`),
    },
    passwordManagement: {
      listUsers: () => get<AdminUserListResponse>('/api/v1/admin/password-management/users'),
      listResetCodes: (limit?: number) =>
        get<AdminResetTokenListResponse>('/api/v1/admin/password-management/reset-codes', limit ? { limit } : undefined),
      generateCode: (email: string) =>
        post<AdminGenerateResetCodeResponse>('/api/v1/admin/password-management/generate-code', { email }),
      forceReset: (email: string, newPassword: string, forceChangeOnLogin: boolean) =>
        post<AdminForceResetResponse>('/api/v1/admin/password-management/force-reset', {
          email,
          new_password: newPassword,
          force_change_on_login: forceChangeOnLogin,
        }),
    },
    dashboard: {
      getHealth: () => get<PlatformHealthResponse>('/api/v1/admin/dashboard/health'),
      getTenantSummary: () => get<TenantSummaryResponse>('/api/v1/admin/dashboard/tenant-summary'),
    },
    settings: {
      smtp: {
        get: () => get<SmtpConfigRead | null>('/api/v1/admin/settings/smtp'),
        update: (body: SmtpConfigUpdate) =>
          put<SmtpConfigRead>('/api/v1/admin/settings/smtp', body),
        test: (body: SmtpTestRequest) =>
          post<SmtpTestResponse>('/api/v1/admin/settings/smtp/test', body),
        delete: () => del<void>('/api/v1/admin/settings/smtp'),
      },
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
    getGuestToken: (dashboardId: string, dateFilter?: DashboardDateFilter) => {
      const params: Record<string, string | number | undefined> = {
        dashboard_id: dashboardId,
      };
      if (dateFilter?.mode === 'single' && dateFilter.capDateEq) {
        params.cap_date_eq = dateFilter.capDateEq;
      } else if (dateFilter?.mode === 'range' && dateFilter.capDateFrom && dateFilter.capDateTo) {
        params.cap_date_from = dateFilter.capDateFrom;
        params.cap_date_to   = dateFilter.capDateTo;
      }
      return get<{
        token: string;
        dashboard_uuid: string;
        embedded_uuid: string;
        dashboard_title: string;
      }>(`/api/v1/superset/guest-token`, params);
    },
    getAvailableDates: (dashboardId: string) =>
      get<{ dashboard_id: string; dates: string[] }>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/available-dates`,
      ),
    getDashboardCharts: (dashboardId: string) =>
      get<DashboardChartsResponse>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/charts`,
      ),
  },
};
