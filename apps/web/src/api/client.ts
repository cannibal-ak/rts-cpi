/**
 * Typed API client interface.
 * Every method returns a Promise; the mock implementation resolves in-memory.
 */
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
  IngestionJob, IngestionUploadResponse, IngestionValidationResult,
  IngestionCommitResult, IngestionDeleteDataResult, IngestionAuditLog, IngestionPreview,
} from '../types';
import type {
  SmtpConfigRead, SmtpConfigUpdate, SmtpTestRequest, SmtpTestResponse,
} from '../types/smtpConfig';
import type {
  AdminTenantOption, AdminInviteUserResponse, AdminResendInviteResponse,
  AdminSendResetEmailResponse, InviteVerifyResponse, InviteAcceptResponse,
} from '../types';

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

// ── Superset dashboard tabs, surfaced outside the iframe ────
// The dashboard's own top-level tab strip, read from its position_json. `id` is
// the layout component id ("TAB-wmNav2"), which is what a permalink's
// activeTabs expects. An empty list means the dashboard has no tabs.
export interface DashboardTab {
  id: string;
  label: string;
}

export interface DashboardTabsResponse {
  dashboard_id: number;
  dashboard_app_id: string;
  tabs: DashboardTab[];
  /**
   * Whether `tabs` really is the dashboard's navigation.
   *
   * The extractor takes the first tab strip it finds depth-first, which is
   * only the navigation on a dashboard actually built as a tabbed dashboard.
   * JY and SKY stack their sections directly in the grid, so what comes back
   * for them is the FIRST section's sub-tabs (Line / Bar / Table). Offering
   * those as extra links (the sidebar) is harmless; replacing Superset's own
   * tab row with them is not. Older responses omit the field — treat a
   * missing value as false rather than assuming navigation.
   */
  tabs_are_navigation?: boolean;
}

// A stored dashboard view (active tab + filter state). `key` is null when there
// was nothing to pin, in which case the caller should embed without the param.
export interface DashboardPermalinkResponse {
  key: string | null;
}

// ── Superset native filters, surfaced outside the iframe ────
// One entry per filter_select native filter on the dashboard, read from
// Superset's own native_filter_configuration. `id` is the NATIVE_FILTER-*
// key the dataMask must be keyed by when sending selections back.
export interface DashboardFilter {
  id: string;
  field: string;
  label: string;
  description: string | null;
  dataset_id: number;
  multi_select: boolean;
  values: string[];
  /**
   * Slice ids this filter applies to, straight from Superset's own
   * `chartsInScope`. `null` = the dashboard records no scope for it.
   */
  charts_in_scope: number[] | null;
}

export interface DashboardFilterConfigResponse {
  dashboard_id: string;
  filters: DashboardFilter[];
}

/**
 * Does this filter apply to the given slice?
 *
 * `null` (no scope recorded) and `undefined` (an older API that predates the
 * field) both mean "yes" — a filter must never disappear from the bar because
 * we failed to learn its scope. A null sliceId means "not scoped to one chart",
 * i.e. dashboard view, where everything applies.
 */
export function filterAppliesTo(f: DashboardFilter, sliceId: number | null): boolean {
  if (sliceId === null) return true;
  const scope = f.charts_in_scope;
  return scope == null ? true : scope.includes(sliceId);
}

/** Selected values keyed by native filter id. An absent/empty entry means "All". */
export type DashboardFilterSelections = Record<string, string[]>;

// ── Chart-view filter overlay ───────────────
// Chart view renders a standalone /explore/ iframe that no filter reaches, so
// selections are pushed through a server-minted Superset `form_data_key`.
export interface ChartOverlayApplied {
  id: string;
  label: string;
  column: string;
  values: string[];
}

export interface ChartFormDataKeyResponse {
  /** null when nothing was applicable — load the plain, unfiltered URL. */
  key: string | null;
  cap_date: string | null;
  applied: ChartOverlayApplied[];
  /** Selected, but scoped away from this chart by the dashboard's own config. */
  out_of_scope: { id: string; label: string }[];
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
 * Per-request controls for the snapshot list calls. `signal` lets a caller
 * cancel in-flight requests (e.g. the grid unmounting or the user switching
 * tabs mid-load); `timeoutMs` overrides the client default.
 */
export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
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
// Keys are per-airline. JY and PW each expose 5 keys; competitors_avg_fare and
// dep_dates_monitored are shared between them. The backend returns only the
// subset registered for the requested airline_code.
export type KpiKey =
  // JY-specific
  | 'airlines_analyzed'
  | 'markets_covered'
  | 'jy_avg_fare'
  // PW-specific
  | 'competitors_analyzed'
  | 'routes_covered'
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


// ── Price points (unaggregated fares for the Latest Prices chart) ──
// One object per OBSERVED FARE, not per stored row: the backend unpivots
// the reference/competitor pair so each airline's price is its own point.
// Fields therefore carry no ref_/comp_ prefix — `role` says which side it
// came from.

export interface PricePoint {
  airline: string;
  role: 'reference' | 'competitor';
  flt_num: string | null;

  /**
   * The reference market this fare was matched on, "ORG-DST". Group a
   * multi-route chart by THIS, never by origin/destination below — a
   * competitor row carries its own stations, which can differ from the
   * market it was compared in.
   */
  market: string;
  origin: string;
  destination: string;
  dep_date: string;          // YYYY-MM-DD
  // Feed clock strings, "HH:MM" (WinAir) or "HHMM" (JY/PW). Not every row
  // has them — WinAir carries times only where it flies the route itself.
  dep_time: string | null;
  arr_time: string | null;
  // Derived server-side from dep_time/arr_time; null when either is absent.
  duration_min: number | null;
  stops: number | null;
  via: string | null;

  cab_code: string | null;
  cab_name: string | null;
  bkg_class: string | null;
  ff_code: string | null;
  equip_code: string | null;
  // 9 is the ingest's stand-in for "the feed sent no seat count", not a real
  // availability of nine. WinAir's own fares never carry one; competitors' do.
  seats: number | null;

  curr: string | null;
  base_fare: number;
  tax: number;
  yq: number;
  yr: number;
  tot_fare: number;

  cap_date: string;
  cap_time: string | null;
  dbd: number | null;        // days before departure at capture time
}

// One entry per (market, airline, departure date) on which the airline
// offered NO purchasable fare all day. These are the days the fare lines
// skip; the chart marks them instead of drawing a dip to zero.
export interface NoFareDay {
  /** Same "ORG-DST" grouping key as PricePoint.market. */
  market: string;
  airline: string;
  dep_date: string;          // YYYY-MM-DD
  // 'sold_out' — fares were observed but every one was zero (seats gone);
  // 'not_on_sale' — the feed carried no bookable inventory for the day yet.
  status: 'sold_out' | 'not_on_sale';
  // Days before departure at capture time, computed server-side so the
  // Days Left filter can reach rows that carry no fare of their own.
  dbd: number;
}

export interface PricePointsResponse {
  cap_date: string | null;
  /** The markets actually queried, as "ORG-DST", in the order requested. */
  routes: string[];
  currency: string | null;   // null when the selection mixes currencies
  truncated: boolean;        // true when the per-market cap dropped points
  /** Which markets were cut, so a warning can name them. */
  truncated_routes: string[];
  points: PricePoint[];
  /**
   * Days with no purchasable fare at all, for the availability markers.
   * Present only when include_availability was requested; empty when the
   * server suppressed them (see availability_suppressed).
   */
  no_fare_days?: NoFareDay[];
  /**
   * True when a stops/flt_num filter made the server withhold no_fare_days:
   * a day with no fare carries no stops or flight number, so it cannot
   * honestly satisfy either filter.
   */
  availability_suppressed?: boolean;
}

export interface PricePointsQuery {
  /** Comma-separated ORG-DST pairs, e.g. "EIS-SXM,ANU-BGI". */
  routes?: string;
  /** Single-route form, kept for one-off and curl use. */
  origin?: string;
  destination?: string;
  tenant?: string;
  cap_date?: string;
  airlines?: string;         // comma-separated codes
  dep_from?: string;
  dep_to?: string;
  stops?: number;
  flt_num?: string;
  /** 1 asks the server to include no_fare_days; omitted = off (back-compat). */
  include_availability?: number;
  // Index signature so this is assignable to the query-param record the
  // HTTP client takes, matching SnapshotQuery above. The named fields keep
  // their types; origin and destination stay required.
  [key: string]: string | number | undefined;
}

export interface PriceHistoryPoint {
  cap_date: string;
  cap_time: string | null;
  tot_fare: number;
  seats: number | null;
  dbd: number | null;
}

export interface PriceHistoryResponse {
  airline: string;
  flt_num: string | null;
  origin: string;
  destination: string;
  dep_date: string;
  curr: string | null;
  points: PriceHistoryPoint[];
}

export interface PriceHistoryQuery {
  origin: string;
  destination: string;
  airline: string;
  dep_date: string;
  flt_num?: string;
  tenant?: string;
  [key: string]: string | number | undefined;
}


// ── Client interface ────────────────────────
export interface CpiApiClient {
  // Airline (tenant-aware: pass tenant='JY' or 'PW')
  airline: {
    listSnapshots(q?: SnapshotQuery, opts?: RequestOptions): Promise<Paginated<AirlineSnapshot>>;
    getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
    exportSnapshots(q?: Record<string, string>): Promise<void>;
    // Unaggregated fares for one route on one capture date — a single
    // bounded request, not a paged walk.
    listPricePoints(q: PricePointsQuery, opts?: RequestOptions): Promise<PricePointsResponse>;
    getPriceHistory(q: PriceHistoryQuery, opts?: RequestOptions): Promise<PriceHistoryResponse>;
    velocity: {
      listSnapshots(q?: SnapshotQuery, opts?: RequestOptions): Promise<Paginated<VelocitySnapshot>>;
      getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
      exportSnapshots(q?: Record<string, string>): Promise<void>;
    };
  };
  // CFL (tenant-aware: pass tenant='FJL')
  cfl: {
    listSnapshots(q?: SnapshotQuery, opts?: RequestOptions): Promise<Paginated<CflSnapshot>>;
    getFilterMetadata(tenant?: string): Promise<FilterMetadata[]>;
    exportSnapshots(q?: Record<string, string>): Promise<void>;
  };
  // Alerts
  alerts: {
    // Feed. getSummary is what the notification bell polls: one small request
    // that serves both the badge and the popover, so opening the popover costs
    // nothing and the two can never disagree.
    getSummary(opts?: RequestOptions): Promise<AlertSummary>;
    listEvents(q?: AlertEventQuery, opts?: RequestOptions): Promise<Paginated<AlertEvent>>;
    /** Options for the feed's Route dropdown, in the exact ORG-DST form the
     *  events filter matches on. Empty for tenants without alerts. */
    listRoutes(opts?: RequestOptions): Promise<string[]>;
    unreadCount(opts?: RequestOptions): Promise<{ unread: number; capped: boolean }>;
    markRead(eventIds: string[]): Promise<MarkReadResult>;
    markUnread(eventIds: string[]): Promise<MarkReadResult>;
    markAllRead(before?: string): Promise<MarkReadResult>;

    // Preset settings. Reads are open to any tenant user; writes need
    // TENANT_ADMIN and are enforced server-side.
    listPresets(): Promise<AlertPreset[]>;
    getPreset(ruleKey: string): Promise<AlertPreset>;
    updatePreset(ruleKey: string, body: AlertPresetUpdate): Promise<AlertPreset>;
    previewPreset(ruleKey: string, body: AlertPresetUpdate): Promise<AlertPreview>;
    run(dryRun?: boolean): Promise<AlertRunSummary>;
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
      deleteFileData(ingestedFileId: string): Promise<{ rows_deleted: number }>;
      reingestFile(ingestedFileId: string): Promise<RunNowResult>;
    };

    // ── Password Management ──
    passwordManagement: {
      listUsers(): Promise<AdminUserListResponse>;
      listTenants(): Promise<AdminTenantOption[]>;
      inviteUser(body: { email: string; display_name: string; tenant_id: string; role?: string }): Promise<AdminInviteUserResponse>;
      resendInvite(body: { email?: string; user_id?: string }): Promise<AdminResendInviteResponse>;
      sendResetEmail(body: { email: string }): Promise<AdminSendResetEmailResponse>;
      forceReset(email: string, newPassword: string, forceChangeOnLogin: boolean): Promise<AdminForceResetResponse>;
      deactivateUser(userId: string): Promise<void>;
      reactivateUser(userId: string): Promise<void>;
      deleteUser(userId: string): Promise<void>;
      resetMfa(userId: string): Promise<{ user_id: string; email: string; mfa_reset: boolean }>;
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
  // Public auth (invite acceptance — no JWT required)
  auth: {
    verifyInvite(token: string): Promise<InviteVerifyResponse>;
    acceptInvite(body: { token: string; new_password: string }): Promise<InviteAcceptResponse>;
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
      currency?: string,
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
    /** The dashboard's own top-level tabs, in render order. */
    getDashboardTabs(dashboardId: string): Promise<DashboardTabsResponse>;
    /**
     * Store a dashboard view and get the key that reopens it. The Embedded SDK
     * cannot set the active tab after mount, so the key is passed to Superset
     * as the `permalink_key` URL param instead. Tab and filters go in the SAME
     * permalink: a permalink_key next to a native_filters param would leave two
     * sources of truth for filter state racing on mount.
     */
    mintDashboardPermalink(
      dashboardId: string,
      opts: { activeTab?: string; selections?: DashboardFilterSelections },
    ): Promise<DashboardPermalinkResponse>;
    /** The dashboard's own native filters + their selectable values. */
    getFilterConfig(dashboardId: string): Promise<DashboardFilterConfigResponse>;
    /**
     * Turn selections into the rison `native_filters` URL param for the
     * Embedded SDK. Returns '' when nothing is selected, in which case the
     * caller should omit the param so the dashboard uses its own defaults.
     */
    buildFilterParams(
      dashboardId: string,
      selections: DashboardFilterSelections,
    ): Promise<{ native_filters: string }>;
    /**
     * Mint a Superset explore form_data_key carrying Chart view's cap_date and
     * native-filter selections for ONE slice. Scoped under the dashboard so the
     * backend can tenant-check it. Send ALL applied selections — the backend
     * drops the ones out of scope for this chart and reports them back.
     */
    mintChartFormDataKey(
      dashboardId: string,
      sliceId: number,
      opts: { dateFilter?: DashboardDateFilter; selections?: DashboardFilterSelections },
    ): Promise<ChartFormDataKeyResponse>;
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
    deleteData(id: string): Promise<IngestionDeleteDataResult>;
    getAudit(id: string): Promise<IngestionAuditLog>;
    getPreview(id: string): Promise<IngestionPreview>;
  };
}

export type { CpiApiClient as default };
