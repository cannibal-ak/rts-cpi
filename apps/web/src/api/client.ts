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
  IngestionScheduleListQuery, RunNowResult,
  IngestionRun, IngestionRunDetail, IngestionRunListQuery,
  AdminUserListResponse, AdminResetTokenListResponse,
  AdminGenerateResetCodeResponse, AdminForceResetResponse,
} from '../types';

// ── Query params ────────────────────────────
export interface SnapshotQuery {
  page?: number;
  page_size?: number;
  [key: string]: string | number | undefined;
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
      runNow(id: string): Promise<RunNowResult>;
    };
    ingestionRuns: {
      list(query?: IngestionRunListQuery): Promise<Paginated<IngestionRun>>;
      get(id: string): Promise<IngestionRunDetail>;
    };

    // ── Password Management ──
    passwordManagement: {
      listUsers(): Promise<AdminUserListResponse>;
      listResetCodes(limit?: number): Promise<AdminResetTokenListResponse>;
      generateCode(email: string): Promise<AdminGenerateResetCodeResponse>;
      forceReset(email: string, newPassword: string, forceChangeOnLogin: boolean): Promise<AdminForceResetResponse>;
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
    getGuestToken(dashboardId: string): Promise<{
        token: string;
        dashboard_uuid: string;
        embedded_uuid: string;
        dashboard_title: string;
    }>;
  };
}

export type { CpiApiClient as default };
