/**
 * In-memory mock API client — for offline demos without a backend.
 */
import type { CpiApiClient, SnapshotQuery, JobQuery, DashboardChartsResponse, DashboardFilterConfigResponse, DashboardFilterSelections, DashboardPermalinkResponse, DashboardTabsResponse, KpiKey, KpiSummaryResponse, KpiDetailResponse, PriceHistoryQuery, PricePointsQuery } from './client';
import type {
  Paginated,
  AlertRule,
  AlertEvent,
  AlertPreset,
  SftpConnection,
  SftpConnectionCreate,
  SftpConnectionUpdate,
  SftpConnectionTestResult,
  SftpConnectionListQuery,
  IngestionSchedule,
  IngestionScheduleCreate,
  IngestionScheduleUpdate,
  IngestionScheduleListQuery,
  RunNowRequest,
  RunNowResult,
  IngestionRun,
  IngestionRunDetail,
  IngestedFile,
  IngestionRunListQuery,
  IngestionJob, IngestionUploadResponse, IngestionValidationResult, IngestionCommitResult, IngestionDeleteDataResult, IngestionAuditLog, IngestionPreview,
  AdminUserListItem,
} from '../types';
import {
  mockAirlineSnapshots, mockCflSnapshots,
  mockAlertRules, mockAlertEvents, mockAlertPresets,
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

// Offline demo seed so deactivate/reactivate have state to flip in place.
const mockPwUsers: AdminUserListItem[] = [
  { id: 'mock-user-rts', email: 'admin@rts.com', tenant_name: 'RTS', tenant_slug: 'rts',
    role: 'TENANT_ADMIN', is_active: true, is_locked: false, force_password_change: false,
    last_login: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'mock-user-jy', email: 'jy@airline.com', tenant_name: 'JY Airways', tenant_slug: 'jy',
    role: 'TENANT_ADMIN', is_active: true, is_locked: false, force_password_change: false,
    last_login: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'mock-user-hist', email: 'analyst@airline.com', tenant_name: 'Skybound - PW', tenant_slug: 'pw',
    role: 'TENANT_ADMIN', is_active: true, is_locked: false, force_password_change: false,
    last_login: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'mock-user-del', email: 'temp@airline.com', tenant_name: 'Skybound - PW', tenant_slug: 'pw',
    role: 'TENANT_ADMIN', is_active: true, is_locked: false, force_password_change: false,
    last_login: null, created_at: '2026-01-01T00:00:00Z' },
];

// Mutable copies so mark-read actually flips state in mock mode — a frozen
// array cannot exercise the badge. Same pattern as mockTenantFeatures.
const _mockEvents: AlertEvent[] = mockAlertEvents.map(e => ({ ...e }));
const _mockPresets: AlertPreset[] = mockAlertPresets.map(p => ({ ...p }));

const _byNewest = (a: AlertEvent, b: AlertEvent) =>
  b.triggered_at.localeCompare(a.triggered_at);

export const mockClient: CpiApiClient = {
  airline: {
    listSnapshots: (q?: SnapshotQuery) =>
      delay(paginate(mockAirlineSnapshots, q?.page as number, q?.page_size as number)),
    getFilterMetadata: (_tenant?: string) => delay(mockFilterMetadata.airline),
    exportSnapshots: (_q?: Record<string, string>) => delay(undefined),
    // No fixture: the Latest Prices chart is WinAir-only and the mock
    // client has no WM session. An empty result renders the panel's
    // "pick a route" state rather than a broken chart.
    //
    // Note for anyone testing offline: the WinAir tab bar cannot be
    // exercised here either — mockClient's mintDashboardPermalink returns
    // {key: null} unconditionally, so no Superset section can be selected.
    listPricePoints: (q: PricePointsQuery) =>
      delay({
        cap_date: null,
        routes: (q.routes ?? '').split(',').filter(Boolean),
        currency: null,
        truncated: false,
        truncated_routes: [],
        points: [],
      }),
    getPriceHistory: (q: PriceHistoryQuery) =>
      delay({
        airline: q.airline,
        flt_num: q.flt_num ?? null,
        origin: q.origin,
        destination: q.destination,
        dep_date: q.dep_date,
        curr: null,
        points: [],
      }),
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
    deleteData: (_id: string) => Promise.reject(new Error('Mock client does not implement ingestion.deleteData')) as Promise<IngestionDeleteDataResult>,
    getAudit: (id: string) => delay({ job_id: id, entries: [] } as IngestionAuditLog),
    getPreview: (id: string) => delay({ job_id: id, sample_valid: [], sample_rejected: [] } as IngestionPreview),
  },
  alerts: {
    getSummary: () => {
      const unread = _mockEvents.filter(e => !e.is_read);
      return delay({
        unread_count: unread.length,
        capped: false,
        recent: [..._mockEvents].sort(_byNewest).slice(0, 5),
        newest_triggered_at: _mockEvents.length
          ? [..._mockEvents].sort(_byNewest)[0].triggered_at
          : null,
      });
    },

    listEvents: (q) => {
      let rows = [..._mockEvents].sort(_byNewest);
      if (q?.unread_only) rows = rows.filter(e => !e.is_read);
      if (q?.severity) rows = rows.filter(e => e.severity === q.severity);
      if (q?.rule_key) rows = rows.filter(e => e.rule_key === q.rule_key);
      if (q?.route) rows = rows.filter(e => e.payload?.route === q.route);
      if (q?.competitor) rows = rows.filter(e => e.payload?.competitor === q.competitor);
      if (q?.since) rows = rows.filter(e => (e.observed_at ?? '') >= q.since!);
      if (q?.until) rows = rows.filter(e => (e.observed_at ?? '') <= q.until!);
      const page = q?.page ?? 1;
      const pageSize = q?.page_size ?? 25;
      const start = (page - 1) * pageSize;
      const items = rows.slice(start, start + pageSize);
      return delay({
        items,
        page_info: {
          total: rows.length, page, page_size: pageSize,
          has_next: start + pageSize < rows.length,
        },
      });
    },

    unreadCount: () => delay({
      unread: _mockEvents.filter(e => !e.is_read).length, capped: false,
    }),

    markRead: (ids) => {
      let updated = 0;
      _mockEvents.forEach(e => {
        if (ids.includes(e.id) && !e.is_read) { e.is_read = true; updated++; }
      });
      return delay({ updated, unread_count: _mockEvents.filter(e => !e.is_read).length });
    },

    markUnread: (ids) => {
      let updated = 0;
      _mockEvents.forEach(e => {
        if (ids.includes(e.id) && e.is_read) { e.is_read = false; updated++; }
      });
      return delay({ updated, unread_count: _mockEvents.filter(e => !e.is_read).length });
    },

    markAllRead: () => {
      let updated = 0;
      _mockEvents.forEach(e => { if (!e.is_read) { e.is_read = true; updated++; } });
      return delay({ updated, unread_count: 0 });
    },

    // Distinct routes from the mock events — the real endpoint also folds in
    // the latest capture's routes, but the mock has no fare data to draw on.
    listRoutes: () => delay(
      [...new Set(_mockEvents.map(e => e.payload?.route).filter(Boolean))].sort() as string[],
    ),

    listPresets: () => delay(_mockPresets.map(p => ({ ...p }))),

    getPreset: (ruleKey) => {
      const p = _mockPresets.find(x => x.rule_key === ruleKey);
      return p ? delay({ ...p }) : Promise.reject(new Error(`no preset ${ruleKey}`));
    },

    updatePreset: (ruleKey, body) => {
      const p = _mockPresets.find(x => x.rule_key === ruleKey);
      if (!p) return Promise.reject(new Error(`no preset ${ruleKey}`));
      if (body.name !== undefined) {
        if (p.is_preset) return Promise.reject(new Error('built-in rules cannot be renamed'));
        p.name = body.name;
      }
      if (body.is_active !== undefined) p.is_active = body.is_active;
      if (body.condition) p.condition = { ...p.condition, ...body.condition };
      p.updated_at = new Date().toISOString();
      return delay({ ...p });
    },

    createRule: (body) => {
      const family = _mockPresets.find(
        x => x.is_preset && x.rule_key === body.preset_key);
      if (!family) return Promise.reject(new Error(`unknown rule type ${body.preset_key}`));
      const instance: AlertPreset = {
        ...family,
        id: `mock-rule-${_mockPresets.length + 1}`,
        rule_key: `${body.preset_key}__mock${_mockPresets.length + 1}`,
        preset_key: body.preset_key,
        is_preset: false,
        name: body.name,
        is_active: body.is_active ?? false,
        condition: { ...family.condition, ...(body.condition ?? {}) },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      _mockPresets.push(instance);
      return delay({ ...instance });
    },

    deleteRule: (ruleKey) => {
      const i = _mockPresets.findIndex(x => x.rule_key === ruleKey);
      if (i < 0) return Promise.reject(new Error(`no rule ${ruleKey}`));
      if (_mockPresets[i].is_preset) {
        return Promise.reject(new Error('built-in rules cannot be deleted'));
      }
      _mockPresets.splice(i, 1);
      return delay(undefined);
    },

    previewPreset: (ruleKey) => delay({
      rule_key: ruleKey,
      cap_date: '2026-08-12',
      prev_cap_date: '2026-08-10',
      would_fire: 3,
      groups_evaluated: 65,
      sample: _mockEvents.slice(0, 3).map(e => ({
        severity: e.severity, message: e.message, payload: e.payload,
      })),
    }),

    run: () => delay({
      tenant_code: 'DA',
      cap_date: '2026-08-12', prev_cap_date: '2026-08-10', cap_date_age_days: 8,
      rules_evaluated: ['undercut_position', 'comp_price_move',
                        'stops_disadvantage', 'service_gap'],
      groups_evaluated: 95, events_created: 0, events_suppressed_dedupe: 8,
      groups_skipped_currency: 0, captures_skipped_incomplete: 1,
      duration_ms: 42, mode: 'manual', note: null,
    }),
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
      runNow: (id: string, body?: RunNowRequest): Promise<RunNowResult> => {
        const row = mockIngestionSchedules.find(s => s.id === id);
        if (!row) return Promise.reject(new Error(`API 404: schedule ${id} not found`));
        const scope = body?.scope ?? 'today';
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
          // Mirror the worker's DATE_FILTER detail_log[0] event so the
          // mock runs page shows the same scope provenance as prod.
          detail_log: [
            {
              event: 'DATE_FILTER',
              scope,
              target_date: null,
              timezone: 'Asia/Kolkata',
              listed_total: 0,
              matched: 0,
              skipped_examples: [],
            },
          ],
          error_summary: null,
        };
        mockIngestionRuns.unshift(newRun);
        return delay({ task_id: mockUuid(), run_id: null, scope }, 300);
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
      cancel: (id: string): Promise<IngestionRun> => {
        const row = mockIngestionRuns.find(r => r.id === id);
        if (!row) return Promise.reject(new Error(`API 404: ingestion run ${id} not found`));
        if (row.status !== 'RUNNING') {
          return Promise.reject(new Error(
            `API 400: run is not cancellable: current status is '${row.status}'; only RUNNING runs can be cancelled`,
          ));
        }
        row.status = 'CANCELLING';
        // Simulate the worker noticing CANCELLING at its next checkpoint
        // and writing the terminal CANCELLED state. The page's 5s
        // auto-refresh picks this up.
        setTimeout(() => {
          if (row.status === 'CANCELLING') {
            row.status = 'CANCELLED';
            row.finished_at = new Date().toISOString();
          }
        }, 2000);
        return delay({ ...row });
      },
      deleteFileData: (_ingestedFileId: string): Promise<{ rows_deleted: number }> =>
        Promise.reject(new Error('Mock client does not implement ingestionRuns.deleteFileData')),
      reingestFile: (_ingestedFileId: string): Promise<RunNowResult> =>
        Promise.reject(new Error('Mock client does not implement ingestionRuns.reingestFile')),
    },
    // Password management isn't exercised offline; stubs keep the interface satisfied.
    passwordManagement: {
      listUsers: () => delay({ users: mockPwUsers.map(u => ({ ...u })), total: mockPwUsers.length }),
      listTenants: () => delay([]),
      inviteUser: (_body: { email: string; display_name: string; tenant_id: string; role?: string }) =>
        delay({ user_id: '00000000-0000-0000-0000-000000000000', email: _body.email, invite_sent: false }),
      resendInvite: (_body: { email?: string; user_id?: string }) =>
        delay({ success: false, invite_sent: false, message: 'Not available in mock mode' }),
      sendResetEmail: (_body: { email: string }) =>
        delay({ sent: false, message: 'Not available in mock mode' }),
      forceReset: (_email: string, _newPassword: string, _forceChangeOnLogin: boolean) =>
        delay({ success: false, message: 'Not available in mock mode' }),
      deactivateUser: (userId: string) => {
        if (userId === 'mock-user-jy') {
          return Promise.reject(Object.assign(
            new Error('jy@airline.com is the only active admin for Skywave - JY; add or reactivate another admin first.'),
            { status: 409, errorCode: 'last_active_admin', details: { tenant: 'Skywave - JY' } },
          ));
        }
        const u = mockPwUsers.find(x => x.id === userId);
        if (u) u.is_active = false;
        return delay(undefined as unknown as void);
      },
      reactivateUser: (userId: string) => {
        const u = mockPwUsers.find(x => x.id === userId);
        if (u) u.is_active = true;
        return delay(undefined as unknown as void);
      },
      // Offline sims of the backend 409 refusals for a couple of seed users.
      deleteUser: (userId: string) => {
        if (userId === 'mock-user-hist') {
          return Promise.reject(Object.assign(
            new Error('analyst@airline.com has activity history (audit / ingestion records) and cannot be deleted. Deactivate the account instead.'),
            { status: 409, errorCode: 'has_history', details: {} },
          ));
        }
        if (userId === 'mock-user-jy') {
          return Promise.reject(Object.assign(
            new Error('jy@airline.com is the only active admin for Skywave - JY; add or reactivate another admin first.'),
            { status: 409, errorCode: 'last_active_admin', details: { tenant: 'Skywave - JY' } },
          ));
        }
        const i = mockPwUsers.findIndex(x => x.id === userId);
        if (i >= 0) mockPwUsers.splice(i, 1);
        return delay(undefined as unknown as void);
      },
      // Offline sim: echo the looked-up email; the real endpoint is idempotent.
      resetMfa: (userId: string) => {
        const u = mockPwUsers.find(x => x.id === userId);
        return delay({ user_id: userId, email: u ? u.email : '', mfa_reset: true });
      },
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
  auth: {
    verifyInvite: (_token: string) => delay({ valid: false, email: null }),
    acceptInvite: (_body: { token: string; new_password: string }) =>
      delay({ success: false, message: 'Not available in mock mode' }),
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
    getChartFormDataKey: (sliceId: number, _dateFilter?: unknown): Promise<{ key: string }> =>
      delay({ key: `mock-form-data-key-${sliceId}` }),
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
    getDashboardTabs: (dashboardId: string): Promise<DashboardTabsResponse> => delay({
      dashboard_id: Number(dashboardId),
      dashboard_app_id: dashboardId,
      // Only the WinAir dashboard is tabbed; everything else reports no tabs,
      // which callers read as "not tab-navigable".
      tabs: dashboardId === '5'
        ? [
            { id: 'TAB-wmNav1', label: 'Avg_Fare' },
            { id: 'TAB-wmNav4', label: 'Min/Max_Fare' },
            { id: 'TAB-wmNav3', label: 'Competitor Breakdown' },
            { id: 'TAB-wmNav2', label: 'Pricing Recommendations' },
            { id: 'TAB-wmNav5', label: 'Velocity' },
          ]
        : [],
    }),
    // No Superset to store state in offline, so no key — the caller then embeds
    // without the param, same as the buildFilterParams '' contract below.
    mintDashboardPermalink: (
      _dashboardId: string,
      _opts: { activeTab?: string; selections?: DashboardFilterSelections },
    ): Promise<DashboardPermalinkResponse> => delay({ key: null }),
    getFilterConfig: (dashboardId: string): Promise<DashboardFilterConfigResponse> => delay({
      dashboard_id: dashboardId,
      filters: [
        // Scopes differ on purpose so chart view's per-chart filtering is
        // exercisable offline: Route reaches both charts, Days Left only one.
        { id: 'NATIVE_FILTER-Route',    field: 'route',     label: 'Route (O&D)', description: 'Origin → Destination',
          dataset_id: 32, multi_select: true, values: ['ANU → BGI', 'ANU → SLU', 'EIS → SXM'],
          charts_in_scope: [1, 2, 3] },
        { id: 'NATIVE_FILTER-DaysLeft', field: 'days_left', label: 'Days Left',   description: 'Days to departure',
          dataset_id: 34, multi_select: true, values: ['0', '7', '14', '30'],
          charts_in_scope: [3] },
      ],
    }),
    // The real endpoint rison-encodes a Superset dataMask. Mock mode has no
    // Superset to feed, so return '' — the caller then omits the URL param.
    buildFilterParams: (_dashboardId: string, _selections: DashboardFilterSelections) =>
      delay({ native_filters: '' }),
    // No Superset to mint against offline. A null key is the "nothing to
    // overlay" contract, so chart view falls back to the plain explore URL.
    mintChartFormDataKey: (_dashboardId: string, _sliceId: number) =>
      delay({ key: null, cap_date: null, applied: [], out_of_scope: [] }),
  },
  kpi: {
    getSummary: (airlineCode: string, capDate: string, currency?: string): Promise<KpiSummaryResponse> => delay({
      cap_date: capDate,
      airline_code: airlineCode.toUpperCase(),
      currency: airlineCode.toUpperCase() === 'FJL' ? (currency ?? 'NOK') : null,
      kpis: {
        airlines_analyzed:  { value: 7,      label: 'Airlines Analyzed',    subheader: 'Distinct competitors tracked' },
        markets_covered:    { value: 16,     label: 'Markets Covered',      subheader: 'Origin-destination pairs analyzed' },
        jy_avg_fare:        { value: 266.18, label: 'JY Avg Fare',          subheader: 'Average JY fare across all routes' },
        // PW
        competitors_analyzed: { value: 4,      label: 'Competitors Analyzed',   subheader: 'Distinct competitors tracked' },
        routes_covered:       { value: 7,      label: 'Routes Covered',          subheader: 'Origin-destination pairs analyzed' },
        pw_avg_fare:          { value: 179.10, label: 'PW Avg Fare',             subheader: 'Average PW fare across all routes' },
        competitors_avg_fare: { value: 410.01, label: 'Competitors Avg Fare',   subheader: 'Average competitor fare across all routes' },
        dep_dates_monitored:  { value: 30,     label: 'Dep Dates Monitored',    subheader: 'Future travel dates with pricing data' },
        competitors_tracked: { value: 3, label: 'Competitors Tracked', subheader: 'Competitor websites monitored' },
        fjl_avg_fare:        { value: 769.54, label: 'FJL Avg Fare', subheader: 'Average total fare across all routes' },
      },
    }),
    getDetail: (airlineCode: string, kpiKey: KpiKey, capDate: string, currency?: string): Promise<KpiDetailResponse> => {
      const tables: Record<KpiKey, { columns: string[]; rows: Array<Record<string, string | number>> }> = {
        airlines_analyzed: {
          columns: ['#', 'Competitor', 'Routes', 'Avg Fare'],
          rows: [
            { rank: 1, comp_al: 'BW', routes: 15, avg_fare: 324 },
            { rank: 2, comp_al: '5L', routes: 12, avg_fare: 73 },
          ],
        },
        markets_covered: {
          columns: ['#', 'Route', 'Competitors', 'JY avg fare'],
          rows: [{ rank: 1, route: 'ANU → EIS', competitors: 4, jy_avg: 341 }],
        },
        jy_avg_fare: {
          columns: ['#', 'Route', 'Competitor', 'JY Fare', 'Comp Fare', 'Difference'],
          rows: [{ rank: 1, route: 'BGI-ANU', comp_al: 'S6', jy_fare: 381, comp_fare: 0, difference: 381 }],
        },
        // PW
        competitors_analyzed: {
          columns: ['#', 'Competitor', 'Routes', 'Avg Fare', 'Fare Gap'],
          rows: [{ rank: 1, comp_al: 'CQ', routes: 3, avg_fare: 402, fare_gap: 326 }],
        },
        routes_covered: {
          columns: ['#', 'Route', 'Competitors', 'PW Avg Fare', 'Comp Avg Fare', 'Fare Gap'],
          rows: [{ rank: 1, route: 'DAR → ARK', competitors: 3, pw_avg: 30, comp_avg: 146, fare_gap: 116 }],
        },
        pw_avg_fare: {
          columns: ['#', 'Route', 'PW Avg Fare', 'Min Fare', 'Max Fare', 'Records'],
          rows: [{ rank: 1, route: 'DAR → NBO', avg_fare: 285, min_fare: 0, max_fare: 585, records: 1884 }],
        },
        competitors_avg_fare: {
          columns: ['#', 'Competitor', 'Avg Fare', 'Min Fare', 'Max Fare', 'Routes'],
          rows: [{ rank: 1, comp_al: 'KQ', avg_fare: 500, min_fare: 0, max_fare: 1867, routes: 3 }],
        },
        dep_dates_monitored: {
          columns: ['#', 'Dep Date', 'Records', 'Competitors', 'Routes'],
          rows: [{ rank: 1, ref_dep_date: '2026-06-23', records: 140, competitors: 4, routes: 7 }],
        },
        competitors_tracked: {
          columns: ['#', 'Competitor', 'Routes', 'Avg Total Fare', 'Avg Pax Fare', 'Records'],
          rows: [{ rank: 1, source: 'https://www.colorline.no/', routes: 6, avg_total: 1217.13, avg_pax: 197.33, records: 1805 }],
        },
        fjl_avg_fare: {
          columns: ['#', 'Route', 'Competitor', 'Total Fare', 'Pax Fare', 'Vehicle Fare', 'Cabin Fare'],
          rows: [{ rank: 1, route: 'Hirtshals → Larvik', source: 'https://www.colorline.no/', total_fare: 1289.03, pax_fare: 197.8, veh_fare: 1091.23, cab_fare: 0 }],
        },
      };
      return delay({
        cap_date: capDate,
        airline_code: airlineCode.toUpperCase(),
        currency: airlineCode.toUpperCase() === 'FJL' ? (currency ?? 'NOK') : null,
        kpi_key: kpiKey,
        columns: tables[kpiKey].columns,
        rows: tables[kpiKey].rows,
      });
    },
  },
};
