/**
 * HTTP-based API client — talks to the real FastAPI backend.
 * Uses JWT Bearer tokens for authentication (Phase 2).
 */
import type { CpiApiClient, SnapshotQuery, JobQuery, ChartFormDataKeyResponse, DashboardChartsResponse, DashboardDateFilter, DashboardFilterConfigResponse, DashboardFilterSelections, DashboardPermalinkResponse, DashboardTabsResponse, KpiKey, KpiSummaryResponse, KpiDetailResponse, PriceHistoryQuery, PriceHistoryResponse, PricePointsQuery, PricePointsResponse } from './client';
import type {
  Paginated, AirlineSnapshot, VelocitySnapshot, CflSnapshot, FilterMetadata,
  AlertRule, AlertEvent, AlertSummary, AlertPreset, AlertPresetUpdate,
  AlertPreview, AlertRunSummary, AlertEventQuery, MarkReadResult,
  TenantFeature, DataFreshness,
  SftpConnection, SftpConnectionCreate, SftpConnectionUpdate,
  SftpConnectionTestResult, SftpConnectionListQuery,
  IngestionSchedule, IngestionScheduleCreate, IngestionScheduleUpdate,
  IngestionScheduleListQuery, RunNowRequest, RunNowResult,
  IngestionRun, IngestionRunDetail, IngestionRunListQuery,
  AdminUserListResponse, AdminResetTokenListResponse,
  AdminGenerateResetCodeResponse, AdminForceResetResponse,
  PlatformHealthResponse, TenantSummaryResponse,
  IngestionJob, IngestionUploadResponse, IngestionValidationResult, IngestionCommitResult, IngestionDeleteDataResult, IngestionAuditLog, IngestionPreview,
} from '../types';
import type {
  SmtpConfigRead, SmtpConfigUpdate, SmtpTestRequest, SmtpTestResponse,
} from '../types/smtpConfig';
import { authStorage } from '../utils/authStorage';
import { clearDatasetCache } from './datasetCache';
import type {
  AdminTenantOption, AdminInviteUserResponse, AdminResendInviteResponse,
  AdminSendResetEmailResponse, InviteVerifyResponse, InviteAcceptResponse,
} from '../types';

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

async function doRefresh(): Promise<boolean> {
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

// The grids fire several requests concurrently. When a token expires mid-flight
// they all see 401 at once, and each one used to launch its own
// POST /auth/refresh — a burst of identical refreshes racing each other.
// Collapse them onto a single in-flight promise; the rest await that result.
let _refreshInFlight: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  if (!_refreshInFlight) {
    _refreshInFlight = doRefresh().finally(() => { _refreshInFlight = null; });
  }
  return _refreshInFlight;
}

// Same problem on the failure path: a burst of failed refreshes each assigned
// window.location. Guard so only the first one navigates.
let _loggingOut = false;

function forceLogout(): never {
  if (!_loggingOut) {
    _loggingOut = true;
    authStorage.removeRefreshToken();
    _accessToken = null;
    // The location assignment reloads the page, which already drops the
    // in-memory dataset cache — this call is here so the invariant survives
    // if forceLogout ever becomes SPA navigation.
    clearDatasetCache();
    window.location.href = '/login';
  }
  throw new Error('Session expired');
}

/** Per-request options: caller-supplied abort signal and/or a timeout. */
export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

// Grid pages can legitimately take a while on a cold cache; 60s is a backstop
// against a request that hangs forever, not a latency target.
const DEFAULT_TIMEOUT_MS = 60_000;

/**
 * Compose a caller's abort signal with a timeout into one signal.
 * Written by hand rather than with AbortSignal.any(), which is too recent to
 * rely on across the browsers this app has to support.
 */
function withTimeout(opts?: RequestOptions): { signal: AbortSignal; dispose: () => void } {
  const ctrl = new AbortController();
  const timer = setTimeout(
    () => ctrl.abort(new DOMException('Request timed out', 'TimeoutError')),
    opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );
  const outer = opts?.signal;
  const onOuterAbort = () => ctrl.abort(outer?.reason);
  if (outer) {
    if (outer.aborted) ctrl.abort(outer.reason);
    else outer.addEventListener('abort', onOuterAbort, { once: true });
  }
  return {
    signal: ctrl.signal,
    dispose: () => {
      clearTimeout(timer);
      outer?.removeEventListener('abort', onOuterAbort);
    },
  };
}

/** True for a cancelled or timed-out request, so callers can ignore it. */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && (err.name === 'AbortError' || err.name === 'TimeoutError');
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

    // Handle forced MFA enrollment (Phase 4 gate — only fires when MFA_ENFORCED is on)
    if (res.status === 403 && errorCode === 'mfa_setup_required') {
      if (window.location.pathname !== '/setup-mfa') {
        window.location.href = '/setup-mfa?required=1';
      }
      throw new Error('MFA setup required');
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

async function fetchWithAuth<T>(url: string, init: RequestInit, opts?: RequestOptions): Promise<T> {
  const { signal, dispose } = withTimeout(opts);
  try {
    let res = await fetch(url, { ...init, signal });

    // On 401, attempt a single refresh then retry
    if (res.status === 401) {
      const refreshed = await attemptRefresh();
      if (!refreshed) forceLogout();
      // Retry with the newly refreshed token
      res = await fetch(url, { ...init, headers: { ...headers() }, signal });
    }

    return await handleResponse<T>(res);
  } finally {
    dispose();
  }
}

// Build a request URL that works for both absolute BASE
// (e.g. "http://192.168.101.10:8000" during local dev) and relative
// BASE (e.g. "/api" in production behind nginx). The native
// ``new URL(path, base)`` constructor REQUIRES an absolute base and
// throws "Invalid base URL" on a relative one — that's why this
// helper exists.
function buildUrl(path: string, base: string): string {
  if (/^https?:\/\//i.test(base)) {
    return new URL(path, base).toString();
  }
  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base;
  const normalizedPath = path.startsWith('/') ? path : '/' + path;
  return normalizedBase + normalizedPath;
}

// Serialise a flat param record into a "?k=v&k=v" suffix. Empty /
// undefined / null values are dropped, matching the previous
// URLSearchParams.set behaviour.
function buildQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return '';
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>, opts?: RequestOptions): Promise<T> {
  const url = buildUrl(path, BASE) + buildQuery(params);
  try {
    return await fetchWithAuth<T>(url, { headers: headers() }, opts);
  } catch (err: any) {
    // Cancellations and timeouts must reach the caller unwrapped, so it can
    // tell "this request was superseded" from "the backend is unreachable".
    if (isAbortError(err)) throw err;
    // err.message was read unguarded here; a non-Error rejection made
    // `.startsWith` throw a TypeError that masked the real failure.
    const msg = typeof err?.message === 'string' ? err.message : String(err);
    if (msg.startsWith('API ') || msg === 'Session expired' || msg === 'Password change required' || msg === 'MFA setup required') throw err;
    throw new Error(`Network Error: ${msg}. Is the backend at ${BASE} reachable?`);
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
    if (err.message.startsWith('API ') || err.message === 'Session expired' || err.message === 'Password change required' || err.message === 'MFA setup required') throw err;
    throw new Error(`Network Error: ${err.message}`);
  }
}

// Unauthenticated POST — no Authorization header, no 401-refresh/redirect
// interceptor. For public endpoints (e.g. accept-invite) reachable by
// logged-out users.
async function publicPost<T>(path: string, body: unknown): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return await handleResponse<T>(res);
  } catch (err: any) {
    if (err.message.startsWith('API ')) throw err;
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
    if (err.message.startsWith('API ') || err.message === 'Session expired' || err.message === 'Password change required' || err.message === 'MFA setup required') throw err;
    throw new Error(`Network Error: ${err.message}`);
  }
}

async function download(path: string, params?: Record<string, string | number | undefined>): Promise<void> {
  const url = buildUrl(path, BASE) + buildQuery(params);
  const res = await fetch(url, { headers: headers() });

  if (res.status === 401) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      const retryRes = await fetch(url, { headers: headers() });
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
    listSnapshots: (q?: SnapshotQuery, opts?: RequestOptions) =>
      get<Paginated<AirlineSnapshot>>('/api/v1/airline/snapshots', q as Record<string, string | number | undefined>, opts),
    getFilterMetadata: (tenant?: string) =>
      get<FilterMetadata[]>('/api/v1/airline/filter-metadata', tenant ? { tenant } : undefined),
    exportSnapshots: (q?: Record<string, string>) =>
      download('/api/v1/airline/export', q),
    listPricePoints: (q: PricePointsQuery, opts?: RequestOptions) =>
      get<PricePointsResponse>('/api/v1/airline/price-points', q as Record<string, string | number | undefined>, opts),
    getPriceHistory: (q: PriceHistoryQuery, opts?: RequestOptions) =>
      get<PriceHistoryResponse>('/api/v1/airline/price-points/history', q as Record<string, string | number | undefined>, opts),
    velocity: {
      listSnapshots: (q?: SnapshotQuery, opts?: RequestOptions) =>
        get<Paginated<VelocitySnapshot>>('/api/v1/airline/velocity/snapshots', q as Record<string, string | number | undefined>, opts),
      getFilterMetadata: (tenant?: string) =>
        get<FilterMetadata[]>('/api/v1/airline/velocity/filter-metadata', tenant ? { tenant } : undefined),
      exportSnapshots: (q?: Record<string, string>) =>
        download('/api/v1/airline/velocity/export', q),
    },
  },
  cfl: {
    listSnapshots: (q?: SnapshotQuery, opts?: RequestOptions) =>
      get<Paginated<CflSnapshot>>('/api/v1/cfl/snapshots', q as Record<string, string | number | undefined>, opts),
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
    deleteData: (id: string) =>
      del<IngestionDeleteDataResult>(`/api/v1/ingestion/jobs/${id}/data`),
    getAudit: (id: string) =>
      get<IngestionAuditLog>(`/api/v1/ingestion/jobs/${id}/audit`),
    getPreview: (id: string) =>
      get<IngestionPreview>(`/api/v1/ingestion/jobs/${id}/preview`),
  },
  alerts: {
    getSummary: (opts?: RequestOptions) =>
      get<AlertSummary>('/api/v1/alerts/summary', undefined, opts),

    listEvents: (q?: AlertEventQuery, opts?: RequestOptions) => {
      const params: Record<string, string | number | undefined> = {};
      if (q?.page !== undefined) params.page = q.page;
      if (q?.page_size !== undefined) params.page_size = q.page_size;
      if (q?.unread_only) params.unread_only = 'true';
      if (q?.rule_key) params.rule_key = q.rule_key;
      if (q?.severity) params.severity = q.severity;
      if (q?.route) params.route = q.route;
      if (q?.competitor) params.competitor = q.competitor;
      if (q?.since) params.since = q.since;
      if (q?.until) params.until = q.until;
      if (q?.with_total === false) params.with_total = 'false';
      return get<Paginated<AlertEvent>>('/api/v1/alerts/events', params, opts);
    },

    unreadCount: (opts?: RequestOptions) =>
      get<{ unread: number; capped: boolean }>('/api/v1/alerts/events/unread-count', undefined, opts),

    markRead: (eventIds: string[]) =>
      post<MarkReadResult>('/api/v1/alerts/events/read', { event_ids: eventIds }),
    markUnread: (eventIds: string[]) =>
      post<MarkReadResult>('/api/v1/alerts/events/unread', { event_ids: eventIds }),
    markAllRead: (before?: string) =>
      post<MarkReadResult>('/api/v1/alerts/events/read-all', { before: before ?? null }),

    listPresets: () => get<AlertPreset[]>('/api/v1/alerts/rules'),
    getPreset: (ruleKey: string) =>
      get<AlertPreset>(`/api/v1/alerts/rules/${encodeURIComponent(ruleKey)}`),
    updatePreset: (ruleKey: string, body: AlertPresetUpdate) =>
      patch<AlertPreset>(`/api/v1/alerts/rules/${encodeURIComponent(ruleKey)}`, body),
    previewPreset: (ruleKey: string, body: AlertPresetUpdate) =>
      post<AlertPreview>(`/api/v1/alerts/rules/${encodeURIComponent(ruleKey)}/preview`, body),
    run: (dryRun = false) =>
      post<AlertRunSummary>(`/api/v1/alerts/run?dry_run=${dryRun}`, {}),
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
      runNow: (id: string, body?: RunNowRequest) =>
        post<RunNowResult>(
          `/api/v1/admin/ingestion-schedules/${id}/run-now`,
          body ?? { scope: 'today' },
        ),
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
      cancel: (id: string) =>
        post<IngestionRun>(`/api/v1/admin/ingestion-runs/${id}/cancel`, {}),
      deleteFileData: (ingestedFileId: string) =>
        del<{ rows_deleted: number }>(`/api/v1/admin/ingestion-runs/files/${ingestedFileId}/data`),
      reingestFile: (ingestedFileId: string) =>
        post<RunNowResult>(`/api/v1/admin/ingestion-runs/files/${ingestedFileId}/reingest`, {}),
    },
    passwordManagement: {
      listUsers: () => get<AdminUserListResponse>('/api/v1/admin/password-management/users'),
      listTenants: () => get<AdminTenantOption[]>('/api/v1/admin/password-management/tenants'),
      inviteUser: (body: { email: string; display_name: string; tenant_id: string; role?: string }) =>
        post<AdminInviteUserResponse>('/api/v1/admin/password-management/invite-user', { role: 'TENANT_ADMIN', ...body }),
      resendInvite: (body: { email?: string; user_id?: string }) =>
        post<AdminResendInviteResponse>('/api/v1/admin/password-management/resend-invite', body),
      sendResetEmail: (body: { email: string }) =>
        post<AdminSendResetEmailResponse>('/api/v1/admin/password-management/send-reset-email', body),
      forceReset: (email: string, newPassword: string, forceChangeOnLogin: boolean) =>
        post<AdminForceResetResponse>('/api/v1/admin/password-management/force-reset', {
          email,
          new_password: newPassword,
          force_change_on_login: forceChangeOnLogin,
        }),
      // No request body; 204 No Content (handleResponse short-circuits it).
      deactivateUser: (userId: string) =>
        post<void>(`/api/v1/admin/password-management/users/${userId}/deactivate`, {}),
      reactivateUser: (userId: string) =>
        post<void>(`/api/v1/admin/password-management/users/${userId}/reactivate`, {}),
      // DELETE -> 204 No Content; handleResponse resolves void.
      deleteUser: (userId: string) =>
        del<void>(`/api/v1/admin/password-management/users/${userId}`),
      // Clears the user's enrolled authenticator + recovery codes (idempotent);
      // they re-enroll at next sign-in. Returns a small JSON body.
      resetMfa: (userId: string) =>
        post<{ user_id: string; email: string; mfa_reset: boolean }>(
          `/api/v1/admin/password-management/users/${userId}/reset-mfa`, {}),
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
  auth: {
    verifyInvite: (token: string) =>
      publicPost<InviteVerifyResponse>('/api/v1/auth/verify-invite', { token }),
    acceptInvite: (body: { token: string; new_password: string }) =>
      publicPost<InviteAcceptResponse>('/api/v1/auth/accept-invite', body),
  },
  stats: {
    getFreshnessMetrics: () => get<DataFreshness[]>('/api/v1/stats/freshness'),
  },
  tenant: {
    getUserRoles: () => get<{ roles: string[] }>('/api/v1/tenant/user-roles'),
    updateUserRoles: (roles, tenant_id) => post<{ roles: string[] }>('/api/v1/tenant/update-roles', { tenant_id, roles }),
  },
  superset: {
    getGuestToken: (dashboardId: string, dateFilter?: DashboardDateFilter, currency?: string) => {
      const params: Record<string, string | number | undefined> = {
        dashboard_id: dashboardId,
      };
      if (dateFilter?.mode === 'single' && dateFilter.capDateEq) {
        params.cap_date_eq = dateFilter.capDateEq;
      } else if (dateFilter?.mode === 'range' && dateFilter.capDateFrom && dateFilter.capDateTo) {
        params.cap_date_from = dateFilter.capDateFrom;
        params.cap_date_to   = dateFilter.capDateTo;
      }
      if (currency) {
        params.currency = currency;
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
    getDashboardTabs: (dashboardId: string) =>
      get<DashboardTabsResponse>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/tabs`,
      ),
    mintDashboardPermalink: (
      dashboardId: string,
      { activeTab, selections }: { activeTab?: string; selections?: DashboardFilterSelections },
    ) =>
      post<DashboardPermalinkResponse>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/permalink`,
        { active_tab: activeTab ?? null, selections: selections ?? {} },
      ),
    getFilterConfig: (dashboardId: string) =>
      get<DashboardFilterConfigResponse>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/filter-config`,
      ),
    buildFilterParams: (dashboardId: string, selections: DashboardFilterSelections) =>
      post<{ native_filters: string }>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/filter-params`,
        { selections },
      ),
    mintChartFormDataKey: (
      dashboardId: string,
      sliceId: number,
      { dateFilter, selections }: {
        dateFilter?: DashboardDateFilter; selections?: DashboardFilterSelections;
      },
    ) => {
      const payload: Record<string, unknown> = { selections: selections ?? {} };
      if (dateFilter?.mode === 'single' && dateFilter.capDateEq) {
        payload.cap_date_eq = dateFilter.capDateEq;
      } else if (dateFilter?.mode === 'range' && dateFilter.capDateFrom && dateFilter.capDateTo) {
        payload.cap_date_from = dateFilter.capDateFrom;
        payload.cap_date_to = dateFilter.capDateTo;
      }
      return post<ChartFormDataKeyResponse>(
        `/api/v1/superset/dashboards/${encodeURIComponent(dashboardId)}/charts/${sliceId}/form-data-key`,
        payload,
      );
    },
  },
  kpi: {
    getSummary: (airlineCode: string, capDate: string, currency?: string) =>
      get<KpiSummaryResponse>(
        `/api/v1/kpi/${encodeURIComponent(airlineCode)}/summary`,
        currency ? { cap_date: capDate, currency } : { cap_date: capDate },
      ),
    getDetail: (airlineCode: string, kpiKey: KpiKey, capDate: string, currency?: string) =>
      get<KpiDetailResponse>(
        `/api/v1/kpi/${encodeURIComponent(airlineCode)}/detail/${encodeURIComponent(kpiKey)}`,
        currency ? { cap_date: capDate, currency } : { cap_date: capDate },
      ),
  },
};
