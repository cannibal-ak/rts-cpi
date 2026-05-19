/**
 * In-memory mock API client — for offline demos without a backend.
 */
import type { CpiApiClient, SnapshotQuery, JobQuery, DashboardChartsResponse } from './client';
import type {
  Paginated,
  AlertRule,
  SftpConnection,
  SftpConnectionCreate,
  SftpConnectionUpdate,
  SftpConnectionTestResult,
  SftpConnectionListQuery,
  IngestionSchedule,
  IngestionScheduleCreate,
  IngestionScheduleUpdate,
  IngestionScheduleListQuery,
  RunNowResult,
  IngestionRun,
  IngestionRunDetail,
  IngestedFile,
  IngestionRunListQuery,
  IngestionJob, IngestionUploadResponse, IngestionValidationResult, IngestionCommitResult, IngestionAuditLog, IngestionPreview,
} from '../types';
import {
  mockAirlineSnapshots, mockCflSnapshots,
  mockAlertRules, mockAlertEvents,
  mockTenantFeatures,
  mockFilterMetadata,
} from './mockData';
import {
  mockSftpConnections,
  mockIngestionSchedules,
  mockIngestionRuns,
  mockIngestedFiles,
  makeQueryFilter,
  mockUuid,
} from '../mock/sftpAdminMock';

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

    // ── Phase 3 SFTP-driven ingestion admin (offline mocks) ──
    sftpConnections: {
      list: (query?: SftpConnectionListQuery) => {
        const result = makeQueryFilter<SftpConnection>(
          mockSftpConnections,
          {
            tenant_code: query?.tenant_code,
            is_active: query?.is_active,
          },
          query?.page ?? 1,
          query?.page_size ?? 20,
        );
        return delay<Paginated<SftpConnection>>({
          items: result.items,
          page_info: {
            total: result.total,
            page: result.page,
            page_size: result.page_size,
            has_next: result.has_next,
          },
        });
      },
      get: (id: string) => {
        const row = mockSftpConnections.find(c => c.id === id);
        if (!row) return Promise.reject(new Error(`API 404: SFTP connection ${id} not found`));
        return delay({ ...row });
      },
      create: (body: SftpConnectionCreate) => {
        const now = new Date().toISOString();
        const row: SftpConnection = {
          id: mockUuid(),
          tenant_code: body.tenant_code,
          name: body.name,
          host: body.host,
          port: body.port ?? 22,
          username: body.username,
          auth_method: body.auth_method,
          remote_base_path: body.remote_base_path,
          is_active: body.is_active ?? true,
          host_key_fingerprint: null,
          masked_credential: body.auth_method === 'password' ? '****' : 'pkey: <encrypted>',
          created_at: now,
          updated_at: now,
        };
        mockSftpConnections.push(row);
        return delay({ ...row });
      },
      update: (id: string, body: SftpConnectionUpdate) => {
        const row = mockSftpConnections.find(c => c.id === id);
        if (!row) return Promise.reject(new Error(`API 404: SFTP connection ${id} not found`));
        if (body.name !== undefined) row.name = body.name;
        if (body.host !== undefined) row.host = body.host;
        if (body.port !== undefined) row.port = body.port;
        if (body.username !== undefined) row.username = body.username;
        if (body.auth_method !== undefined) {
          row.auth_method = body.auth_method;
          row.masked_credential = body.auth_method === 'password' ? '****' : 'pkey: <encrypted>';
        }
        if (body.remote_base_path !== undefined) row.remote_base_path = body.remote_base_path;
        if (body.is_active !== undefined) row.is_active = body.is_active;
        row.updated_at = new Date().toISOString();
        return delay({ ...row });
      },
      delete: (id: string) => {
        const refs = mockIngestionSchedules.filter(s => s.sftp_connection_id === id).length;
        if (refs > 0) {
          return Promise.reject(
            new Error(
              `API 409: Cannot delete: ${refs} schedule(s) still reference this connection.`,
            ),
          );
        }
        const idx = mockSftpConnections.findIndex(c => c.id === id);
        if (idx >= 0) mockSftpConnections.splice(idx, 1);
        return delay<void>(undefined as void);
      },
      test: (_id: string): Promise<SftpConnectionTestResult> => {
        const ok = Math.random() < 0.5;
        const errors = [
          'connect_failed: Connection refused',
          'auth_failed: Authentication failed',
          'connect_failed: Host unreachable',
          'connect_failed: getaddrinfo ENOTFOUND',
        ];
        const detail = ok
          ? 'Connection successful — server banner: SSH-2.0-OpenSSH_8.4'
          : errors[Math.floor(Math.random() * errors.length)];
        return delay({ ok, detail });
      },
    },

    ingestionSchedules: {
      list: (query?: IngestionScheduleListQuery) => {
        const result = makeQueryFilter<IngestionSchedule>(
          mockIngestionSchedules,
          {
            tenant_code: query?.tenant_code,
            is_enabled: query?.is_enabled,
            sftp_connection_id: query?.sftp_connection_id,
          },
          query?.page ?? 1,
          query?.page_size ?? 20,
        );
        return delay<Paginated<IngestionSchedule>>({
          items: result.items,
          page_info: {
            total: result.total,
            page: result.page,
            page_size: result.page_size,
            has_next: result.has_next,
          },
        });
      },
      get: (id: string) => {
        const row = mockIngestionSchedules.find(s => s.id === id);
        if (!row) return Promise.reject(new Error(`API 404: schedule ${id} not found`));
        return delay({ ...row });
      },
      create: (body: IngestionScheduleCreate) => {
        const now = new Date().toISOString();
        const row: IngestionSchedule = {
          id: mockUuid(),
          tenant_code: body.tenant_code,
          sftp_connection_id: body.sftp_connection_id,
          cron_expression: body.cron_expression,
          timezone: body.timezone ?? 'UTC',
          is_enabled: body.is_enabled ?? true,
          domain: body.domain,
          filename_regex: body.filename_regex,
          replace_existing: body.replace_existing ?? false,
          last_run_at: null,
          next_run_at: null,
          redbeat_registered: body.is_enabled ?? true,
          created_at: now,
          updated_at: now,
        };
        mockIngestionSchedules.push(row);
        return delay({ ...row });
      },
      update: (id: string, body: IngestionScheduleUpdate) => {
        const row = mockIngestionSchedules.find(s => s.id === id);
        if (!row) return Promise.reject(new Error(`API 404: schedule ${id} not found`));
        if (body.sftp_connection_id !== undefined) row.sftp_connection_id = body.sftp_connection_id;
        if (body.cron_expression !== undefined) row.cron_expression = body.cron_expression;
        if (body.timezone !== undefined) row.timezone = body.timezone;
        if (body.is_enabled !== undefined) {
          row.is_enabled = body.is_enabled;
          row.redbeat_registered = body.is_enabled;
        }
        if (body.domain !== undefined) row.domain = body.domain;
        if (body.filename_regex !== undefined) row.filename_regex = body.filename_regex;
        if (body.replace_existing !== undefined) row.replace_existing = body.replace_existing;
        row.updated_at = new Date().toISOString();
        return delay({ ...row });
      },
      delete: (id: string) => {
        const idx = mockIngestionSchedules.findIndex(s => s.id === id);
        if (idx >= 0) mockIngestionSchedules.splice(idx, 1);
        // Cascade-simulate the migration-020 ON DELETE SET NULL on
        // ingestion_run.schedule_id and ingested_file.schedule_id.
        for (const r of mockIngestionRuns) {
          if (r.schedule_id === id) {
            (r as IngestionRun & { schedule_id: string | null }).schedule_id = null as unknown as string;
          }
        }
        for (const f of mockIngestedFiles) {
          if (f.schedule_id === id) f.schedule_id = null;
        }
        return delay<void>(undefined as void);
      },
      enable: (id: string) => {
        const row = mockIngestionSchedules.find(s => s.id === id);
        if (!row) return Promise.reject(new Error(`API 404: schedule ${id} not found`));
        row.is_enabled = true;
        row.redbeat_registered = true;
        row.updated_at = new Date().toISOString();
        return delay({ ...row });
      },
      disable: (id: string) => {
        const row = mockIngestionSchedules.find(s => s.id === id);
        if (!row) return Promise.reject(new Error(`API 404: schedule ${id} not found`));
        row.is_enabled = false;
        row.redbeat_registered = false;
        row.updated_at = new Date().toISOString();
        return delay({ ...row });
      },
      runNow: (id: string): Promise<RunNowResult> => {
        const row = mockIngestionSchedules.find(s => s.id === id);
        if (!row) return Promise.reject(new Error(`API 404: schedule ${id} not found`));
        // Side-effect: push a synthetic RUNNING run so the runs page
        // reflects the trigger. Real backend: worker creates this row
        // when it picks up the task.
        const newRun: IngestionRun = {
          id: mockUuid(),
          schedule_id: id,
          tenant_code: row.tenant_code,
          started_at: new Date().toISOString(),
          finished_at: null,
          status: 'RUNNING',
          files_seen: 0,
          files_pulled: 0,
          jobs_created: 0,
          jobs_committed: 0,
          triggered_by: 'MANUAL',
          detail_log: null,
          error_summary: null,
        };
        mockIngestionRuns.unshift(newRun);
        return delay({ task_id: mockUuid(), run_id: null }, 300);
      },
    },

    ingestionRuns: {
      list: (query?: IngestionRunListQuery) => {
        let rows: IngestionRun[] = [...mockIngestionRuns];
        if (query?.tenant_code !== undefined) rows = rows.filter(r => r.tenant_code === query.tenant_code);
        if (query?.schedule_id !== undefined) rows = rows.filter(r => r.schedule_id === query.schedule_id);
        if (query?.status !== undefined) rows = rows.filter(r => r.status === query.status);
        if (query?.started_after !== undefined) {
          const after = query.started_after;
          rows = rows.filter(r => r.started_at >= after);
        }
        if (query?.started_before !== undefined) {
          const before = query.started_before;
          rows = rows.filter(r => r.started_at < before);
        }
        rows.sort((a, b) => b.started_at.localeCompare(a.started_at));
        const page = query?.page ?? 1;
        const pageSize = query?.page_size ?? 20;
        const start = (page - 1) * pageSize;
        const slice = rows.slice(start, start + pageSize);
        return delay<Paginated<IngestionRun>>({
          items: slice,
          page_info: {
            total: rows.length,
            page,
            page_size: pageSize,
            has_next: start + pageSize < rows.length,
          },
        });
      },
      get: (id: string): Promise<IngestionRunDetail> => {
        const row = mockIngestionRuns.find(r => r.id === id);
        if (!row) return Promise.reject(new Error(`API 404: ingestion run ${id} not found`));
        const files: IngestedFile[] = mockIngestedFiles
          .filter(f => f.run_id === id)
          .sort((a, b) => a.created_at.localeCompare(b.created_at))
          .map(f => ({ ...f }));
        return delay({ ...row, ingested_files: files });
      },
    },
    // Password management isn't exercised offline; stubs keep the interface satisfied.
    passwordManagement: {
      listUsers: () => delay({ users: [], total: 0 }),
      listResetCodes: () => delay({ tokens: [], total: 0 }),
      generateCode: (_email: string) =>
        delay({ success: false, message: 'Not available in mock mode', code: '000000', expires_at: new Date().toISOString() }),
      forceReset: (_email: string, _newPassword: string, _forceChangeOnLogin: boolean) =>
        delay({ success: false, message: 'Not available in mock mode' }),
    },
    // SMTP settings aren't exercised offline; stubs keep the interface satisfied.
    settings: {
      smtp: {
        get: () => delay(null),
        update: (_body: unknown) => Promise.reject(new Error('API 503: SMTP config not available in mock mode')),
        test: (_body: unknown) => delay({
          success: false,
          message: 'Not available in mock mode',
          latency_ms: null,
        }),
        delete: () => delay(undefined as unknown as void),
      },
    },
    // Dashboard isn't exercised offline; mocks return plausible data so the UI renders.
    dashboard: {
      getHealth: () => delay({
        services: [
          { name: 'API', status: 'healthy' as const, response_time_ms: 0, details: null },
          { name: 'Database', status: 'healthy' as const, response_time_ms: 2, details: null },
          { name: 'Redis', status: 'healthy' as const, response_time_ms: 1, details: null },
          { name: 'RabbitMQ', status: 'healthy' as const, response_time_ms: 3, details: null },
          { name: 'Superset', status: 'healthy' as const, response_time_ms: 15, details: null },
          { name: 'SFTP', status: 'healthy' as const, response_time_ms: 2, details: '2 active connection(s)' },
        ],
        checked_at: new Date().toISOString(),
      }),
      getTenantSummary: () => delay({ tenants: [] }),
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
    getGuestToken: (dashboardId: string, _dateFilter?: unknown) => delay({
        token: `mock-token-${dashboardId}-${Date.now()}`,
        dashboard_uuid: `00000000-0000-0000-0000-00000000000${dashboardId}`,
        embedded_uuid: `11111111-1111-1111-1111-11111111111${dashboardId}`,
        dashboard_title: dashboardId === '1' ? 'Airline CPI JY Dashboard'
                       : dashboardId === '2' ? 'Airline CPI PW Dashboard'
                       : 'Cruise/Ferry CPI Dashboard',
    }),
    getAvailableDates: (dashboardId: string) => delay({
        dashboard_id: dashboardId,
        dates: [
          '2026-05-17','2026-05-14','2026-05-12','2026-05-10','2026-05-07','2026-05-05','2026-05-03',
        ],
    }),
    getDashboardCharts: (dashboardId: string): Promise<DashboardChartsResponse> => delay({
      dashboard_id: Number(dashboardId),
      dashboard_app_id: dashboardId,
      dashboard_title: dashboardId === '1' ? 'Airline CPI JY Dashboard'
                     : dashboardId === '2' ? 'Airline CPI PW Dashboard'
                     : 'Cruise/Ferry CPI Dashboard',
      charts: [
        { slice_id: 1, slice_name: 'Total Records',     viz_type: 'big_number_total',       description: null, is_kpi: true  },
        { slice_id: 2, slice_name: 'Trend by Date',     viz_type: 'echarts_timeseries_line', description: null, is_kpi: false },
        { slice_id: 3, slice_name: 'Breakdown by Type', viz_type: 'pie',                     description: null, is_kpi: false },
      ],
    }),
  },
};
