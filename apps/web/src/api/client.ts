/**
 * Typed API client interface.
 * Every method returns a Promise; the mock implementation resolves in-memory.
 */
import type {
  Paginated, AirlineSnapshot, VelocitySnapshot, CflSnapshot, FilterMetadata,
  AlertRule, AlertEvent,
  TenantFeature, DataFreshness,
  SftpConnection, SftpConnectionCreate, SftpConnectionUpdate,
  SftpConnectionTestResult, SftpConnectionListQuery,
  IngestionSchedule, IngestionScheduleCreate, IngestionScheduleUpdate,
  IngestionScheduleListQuery, RunNowRequest, RunNowResult,
  IngestionRun, IngestionRunDetail, IngestionRunListQuery,
  AdminUserListResponse, AdminResetTokenListResponse,
  AdminGenerateResetCodeResponse, AdminForceResetResponse,
  PlatformHealthResponse, TenantSummaryResponse,
} from '../types';
import type {
  SmtpConfigRead, SmtpConfigUpdate, SmtpTestRequest, SmtpTestResponse,
} from '../types/smtpConfig';

// ── Superset chart manifest ────────────────
export interface DashboardChart {
  slice_id: number;
  slice_name: string;
  viz_type: string | null;
  description: string | null;
  is_kpi: boolean;
}

export interface DashboardChartsResponse {
  dashboard_id: number;
  dashboard_app_id: string;
  dashboard_title: string;
  charts: DashboardChart[];
}

// ── Query params ────────────────────────────
export interface JobQuery {
  page?: number;
  page_size?: number;
  domain?: string;
  status?: string;
  tenant_code?: string;
}

export interface SnapshotQuery {
  page?: number;
  page_size?: number;
  [key: string]: string | number | undefined;
}

/**
 * Date filter sent to /api/v1/superset/guest-token. The backend turns these
 * into an extra RLS clause on cap_date (single-day or BETWEEN).
 */
export interface DashboardDateFilter {
  mode: 'single' | 'range';
  capDateEq?: string;    // YYYY-MM-DD, set when mode === 'single'
  capDateFrom?: string;  // YYYY-MM-DD, set when mode === 'range'
  capDateTo?: string;    // YYYY-MM-DD, set when mode === 'range'
}

// ── KPI summary + detail (click-to-expand KPI row) ──
// Keys are per-airline. JY and PW each expose 5 keys; JY reuses PW's
// competitors_analyzed / routes_covered keys (JY-appropriate values, PW labels).
// competitors_avg_fare and dep_dates_monitored are shared. The backend returns
// only the subset registered for the requested airline_code.
export type KpiKey =
  // JY + PW (shared keys; JY supplies its own values/SQL)
  | 'competitors_analyzed'
  | 'routes_covered'
  // JY-specific
  | 'jy_avg_fare'
  // PW-specific
  | 'pw_avg_fare'
  // Shared (JY + PW + FJL)
  | 'competitors_avg_fare'
  | 'dep_dates_monitored'
  // FJL-specific (routes_covered / competitors_avg_fare / dep_dates_monitored are shared)
  | 'competitors_tracked'
  | 'fjl_avg_fare';

export interface KpiSummaryItem {
  // null when the underlying AVG (wrapped in NULLIF) had no non-zero rows
  // for the period — renderers show this as "—".
  value: number | null;
  label: string;
  subheader: string;
}

export interface KpiSummaryResponse {
  cap_date: string;
  airline_code: string;
  currency: string | null;   // null for JY/PW; "NOK" | "EUR" | "DKK" for FJL
  kpis: Record<KpiKey, KpiSummaryItem>;
}

export interface KpiDetailResponse {
  cap_date: string;
  airline_code: string;
  currency: string | null;
  kpi_key: KpiKey;
  columns: string[];
  // Cells are null when the per-group AVG/MIN (wrapped in NULLIF) had no
  // non-zero rows for that group; rendered as a blank cell.
  rows: Array<Record<string, string | number | null>>;
}



// ── Client interface ────────────────────────
export interface CpiApiClient {
  // Airline (tenant-aware: pass tenant='JY' or 'PW')
  airline: {
    listSnapshots(q?: SnapshotQuery): Promise<Paginated<AirlineSnapshot>>;
    getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
    exportSnapshots(q?: Record<string, string>): Promise<void>;
    velocity: {
      listSnapshots(q?: SnapshotQuery): Promise<Paginated<VelocitySnapshot>>;
      getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
      exportSnapshots(q?: Record<string, string>): Promise<void>;
    };
  };
  // CFL (tenant-aware: pass tenant='FJL')
  cfl: {
    listSnapshots(q?: SnapshotQuery): Promise<Paginated<CflSnapshot>>;
    getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
    exportSnapshots(q?: Record<string, string>): Promise<void>;
  };
  // Alerts
  alerts: {
    listRules(): Promise<AlertRule[]>;
    createRule(rule: Omit<AlertRule, 'id' | 'created_at'>): Promise<AlertRule>;
    listEvents(): Promise<AlertEvent[]>;
  };

  // Admin
  admin: {
    getTenantFeatures(): Promise<TenantFeature[]>;
    setTenantFeature(code: string, enabled: boolean): Promise<TenantFeature>;

    // ── Phase 3 SFTP-driven ingestion admin ──
    sftpConnections: {
      list(query?: SftpConnectionListQuery): Promise<Paginated<SftpConnection>>;
      get(id: string): Promise<SftpConnection>;
      create(body: SftpConnectionCreate): Promise<SftpConnection>;
      update(id: string, body: SftpConnectionUpdate): Promise<SftpConnection>;
      delete(id: string): Promise<void>;
      test(id: string): Promise<SftpConnectionTestResult>;
    };
    ingestionSchedules: {
      list(query?: IngestionScheduleListQuery): Promise<Paginated<IngestionSchedule>>;
      get(id: string): Promise<IngestionSchedule>;
      create(body: IngestionScheduleCreate): Promise<IngestionSchedule>;
      update(id: string, body: IngestionScheduleUpdate): Promise<IngestionSchedule>;
      delete(id: string): Promise<void>;
      enable(id: string): Promise<IngestionSchedule>;
      disable(id: string): Promise<IngestionSchedule>;
      runNow(id: string, body?: RunNowRequest): Promise<RunNowResult>;
    };
    ingestionRuns: {
      list(query?: IngestionRunListQuery): Promise<Paginated<IngestionRun>>;
      get(id: string): Promise<IngestionRunDetail>;
      cancel(id: string): Promise<IngestionRun>;
    };

    // ── Password Management ──
    passwordManagement: {
      listUsers(): Promise<AdminUserListResponse>;
      listResetCodes(limit?: number): Promise<AdminResetTokenListResponse>;
      generateCode(email: string): Promise<AdminGenerateResetCodeResponse>;
      forceReset(email: string, newPassword: string, forceChangeOnLogin: boolean): Promise<AdminForceResetResponse>;
    };

    // ── Admin Dashboard (Home page) ──
    dashboard: {
      getHealth(): Promise<PlatformHealthResponse>;
      getTenantSummary(): Promise<TenantSummaryResponse>;
    };

    // ── Platform Settings ──
    settings: {
      smtp: {
        // null when the smtp_config row hasn't been written yet.
        get(): Promise<SmtpConfigRead | null>;
        update(body: SmtpConfigUpdate): Promise<SmtpConfigRead>;
        test(body: SmtpTestRequest): Promise<SmtpTestResponse>;
        delete(): Promise<void>;
      };
    };
  };
  // Stats
  stats: {
    getFreshnessMetrics(): Promise<DataFreshness[]>;
  };
  // Tenant
  tenant: {
    getUserRoles(): Promise<{ roles: string[] }>;
    updateUserRoles(roles: string[], tenant_id: string): Promise<{ roles: string[] }>;
  };
  superset: {
    getGuestToken(
      dashboardId: string,
      dateFilter?: DashboardDateFilter,
    ): Promise<{
        token: string;
        dashboard_uuid: string;
        embedded_uuid: string;
        dashboard_title: string;
    }>;
    getAvailableDates(dashboardId: string): Promise<{
        dashboard_id: string;
        dates: string[];
    }>;
    getDashboardCharts(dashboardId: string): Promise<DashboardChartsResponse>;
    getChartFormDataKey(
      sliceId: number,
      dateFilter?: DashboardDateFilter,
    ): Promise<{ key: string }>;
  };
  kpi: {
    getSummary(airlineCode: string, capDate: string, currency?: string): Promise<KpiSummaryResponse>;
    getDetail(airlineCode: string, kpiKey: KpiKey, capDate: string, currency?: string): Promise<KpiDetailResponse>;
  };
  ingestion: {
    listJobs(q?: JobQuery): Promise<Paginated<IngestionJob>>;
    getJob(id: string): Promise<IngestionJob | null>;
    upload(files: File[]): Promise<IngestionUploadResponse>;
    validate(id: string): Promise<IngestionValidationResult>;
    commit(id: string, replaceExisting: boolean): Promise<IngestionCommitResult>;
    cancel(id: string): Promise<IngestionJob>;
    getAudit(id: string): Promise<IngestionAuditLog>;
    getPreview(id: string): Promise<IngestionPreview>;
  };
}

export type { CpiApiClient as default };
