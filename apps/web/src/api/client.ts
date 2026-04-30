/**
 * Typed API client interface.
 * Every method returns a Promise; the mock implementation resolves in-memory.
 */
import type {
  Paginated, AirlineSnapshot, JyVelocitySnapshot, CflSnapshot, FilterMetadata,
  IngestionJob, ImportBatch,
  AlertRule, AlertEvent,
  TenantFeature, DataFreshness,
} from '../types';

// ── Query params ────────────────────────────
export interface SnapshotQuery {
  page?: number;
  page_size?: number;
  [key: string]: string | number | undefined;
}

export interface JobQuery {
  page?: number;
  page_size?: number;
  domain?: string;
  status?: string;
  tenant?: string;
}





// ── Client interface ────────────────────────
export interface CpiApiClient {
  // Airline (tenant-aware: pass tenant='JY' or 'PW')
  airline: {
    listSnapshots(q?: SnapshotQuery): Promise<Paginated<AirlineSnapshot>>;
    getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
    exportSnapshots(q?: Record<string, string>): Promise<void>;
    velocity: {
      listSnapshots(q?: SnapshotQuery): Promise<Paginated<JyVelocitySnapshot>>;
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
  // Ingestion
  ingestion: {
    listJobs(q?: JobQuery): Promise<Paginated<IngestionJob>>;
    getJob(id: string): Promise<IngestionJob | null>;
    listJobBatches(jobId: string): Promise<ImportBatch[]>;
    triggerIngest(tenant?: string, force?: boolean): Promise<{ message: string; results: any[] }>;
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
