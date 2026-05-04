// ──────── User & Session ────────
export type UserRole = 'TENANT_ADMIN';
export type ModuleCode = 'airline_jy' | 'airline_pw' | 'cfl_fjl';
export type Capability = 'alerts' | 'exports' | 'saved_views';

export interface TenantSession {
  tenant_id: string;
  tenant_name: string;
  enabled_modules: ModuleCode[];
  enabled_capabilities: Capability[];
  user: { id: string; name: string; email: string; roles: UserRole[]; avatar_url?: string };
}

export interface NavItem {
  label: string;
  path: string;
  icon: string;
  requiredModules?: ModuleCode[];
  requiredCapabilities?: Capability[];
  requiredRoles?: UserRole[];
  // When true, only the Skywave super-admin sees this item, regardless of role list.
  requireSuperAdmin?: boolean;
  children?: NavItem[];
  category?: string;
}

// ──────── Data freshness ────────
export interface DataFreshness {
  domain: string;
  report_date: string | null;
  last_capture_at: string;
  last_import_at: string;
  record_count: number;
  status: 'fresh' | 'stale' | 'unknown';
}

// ──────── Filter / View ────────
export interface FilterState { [key: string]: string | string[] | [string, string] | null }

export interface SavedView {
  id: string; name: string; domain: string; filters: FilterState;
  created_at: string; owner: string; visibility: 'private' | 'team' | 'public';
}

// ──────── Airline snapshot ────────
export interface AirlineSnapshot {
  id: string;
  cap_date: string;
  cap_time: string;
  trip_type: 'OW' | 'RT';
  ref_al: string;
  ref_flt_num: string;
  ref_org: string;
  ref_dst: string;
  ref_dep_date: string;
  ref_cab_code: string;
  ref_tot_fare: number;
  ref_base_fare: number;
  ref_tax: number;
  ref_yq: number;
  ref_seats: number;
  comp_al: string;
  comp_flt_num: string;
  comp_org: string;
  comp_dst: string;
  comp_dep_date: string;
  comp_cab_code: string;
  comp_tot_fare: number;
  comp_base_fare: number;
  comp_tax: number;
  comp_yq: number;
  comp_seats: number;
  pos: string;
  poa: string;
  fare_delta?: number;
  fare_delta_pct?: number;
}

// ──────── JY velocity snapshot ────────
export interface JyVelocitySnapshot {
  id: string;
  tenant_id: string;
  dep_date: string;
  dep_time: string;
  dep_code: string;
  city_pair: string;
  origin: string;
  destination: string;
  eqp: string;
  legseg_type: string;
  leg_seg_order: number;
  days_left: number;
  compartment: string;
  current_booking: number;
  capacity: number;
  actual_seat_factor: number;
  forecasted_seat_factor: number;
  seats_available: number;
  booking_pct: number;
  data_owner?: string;
  tenant_code?: string;
  business_type?: string;
  report_date?: string;
  file_date?: string;
  source_file?: string;
  loaded_at?: string;
  ingested_at?: string;
}

// ──────── CFL snapshot ────────
export interface CflSnapshot {
  id: string;
  cap_date: string;
  cap_time: string;
  trip_type: 'ONE_WAY' | 'ROUND_TRIP';
  source: string;
  org: string;
  dest: string;
  out_dep_date: string;
  out_dep_time: string;
  prod_family: string;
  out_equip_name: string;
  out_cab_type: string;
  total_fare: number;
  out_per_pax_fare: number;
  out_veh_fare: number;
  out_cab_fare: number;
  out_taxes: number;
  out_num_pax: number;
  veh_size: string;
  curr_code: string;
  out_avail: string;
}

// ──────── Alerts ────────
export interface AlertRule {
  id: string; name: string; domain: string;
  rule_type: 'threshold' | 'anomaly' | 'schedule';
  condition_json: string; is_active: boolean;
  created_at: string; owner: string;
}

export interface AlertEvent {
  id: string; rule_id: string; rule_name: string; triggered_at: string;
  severity: 'info' | 'warning' | 'critical';
  message: string; delivery_status: 'pending' | 'sent' | 'failed';
}



// ──────── Tenant features ────────
export interface TenantFeature {
  code: string;
  label: string;
  category: 'module' | 'capability' | 'analytics' | 'branding';
  enabled: boolean;
}

// ──────── Paginated response ────────
export interface PageInfo {
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface Paginated<T> {
  items: T[];
  page_info: PageInfo;
}

// ──────── Filter metadata ────────
export interface FilterMetadata {
  field: string;
  label: string;
  values: string[];
}

// ─── SFTP admin (Phase 4) ─────────────────────────────────
// IngestionDomain is the canonical YAML-declared domain enum
// (matches app/ingestion/filename_patterns.yaml on the server).
export type IngestionDomain = 'AIRLINE' | 'VELOCITY' | 'CFL';

export type SftpAuthMethod = 'password' | 'private_key';

// Read shape — what the API returns for a connection.
// Plaintext credentials are NEVER present; masked_credential
// is the operator-facing presence indicator.
export interface SftpConnection {
  id: string;
  tenant_code: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: SftpAuthMethod;
  remote_base_path: string;
  is_active: boolean;
  host_key_fingerprint: string | null;
  masked_credential: string;
  created_at: string;
  updated_at: string;
}

export interface SftpConnectionCreate {
  tenant_code: string;
  name: string;
  host: string;
  port?: number;
  username: string;
  auth_method: SftpAuthMethod;
  password?: string;
  private_key_pem?: string;
  remote_base_path: string;
  is_active?: boolean;
}

export interface SftpConnectionUpdate {
  name?: string;
  host?: string;
  port?: number;
  username?: string;
  auth_method?: SftpAuthMethod;
  password?: string;
  private_key_pem?: string;
  remote_base_path?: string;
  is_active?: boolean;
}

export interface IngestionSchedule {
  id: string;
  tenant_code: string;
  sftp_connection_id: string;
  cron_expression: string;
  timezone: string;
  is_enabled: boolean;
  domain: IngestionDomain;
  filename_regex: string;
  replace_existing: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  redbeat_registered: boolean;
  created_at: string;
  updated_at: string;
}

export interface IngestionScheduleCreate {
  tenant_code: string;
  sftp_connection_id: string;
  cron_expression: string;
  timezone?: string;
  is_enabled?: boolean;
  domain: IngestionDomain;
  filename_regex: string;
  replace_existing?: boolean;
}

export interface IngestionScheduleUpdate {
  sftp_connection_id?: string;
  cron_expression?: string;
  timezone?: string;
  is_enabled?: boolean;
  domain?: IngestionDomain;
  filename_regex?: string;
  replace_existing?: boolean;
}

export interface IngestionRun {
  id: string;
  schedule_id: string;
  tenant_code: string | null;
  started_at: string;
  finished_at: string | null;
  // The API returns string today: 'RUNNING' | 'SUCCESS' |
  // 'PARTIAL' | 'FAILED'. Kept open as `string` so a future
  // server-side enum extension doesn't break the type.
  status: string;
  files_seen: number;
  files_pulled: number;
  jobs_created: number;
  jobs_committed: number;
  triggered_by: string | null;
  // detail_log is a free-form JSONB observability field; the
  // current Phase 2 worker writes a list[dict] of per-file
  // outcomes, but the schema permits any shape. Treat as
  // opaque on the client.
  detail_log: unknown | null;
  error_summary: string | null;
}

export interface IngestionRunDetail extends IngestionRun {
  ingested_files: IngestedFile[];
}

export interface IngestedFile {
  id: string;
  run_id: string;
  schedule_id: string | null;
  remote_filename: string;
  sha256: string;
  remote_size_bytes: number;
  remote_mtime_utc: string | null;
  // 'COMMITTED' | 'DUPLICATE' | 'FAILED' | future variants —
  // see IngestionRun.status note for the rationale.
  outcome: string;
  ingestion_job_id: string | null;
  error_message: string | null;
  created_at: string;
}

// ── Operation results ──

export interface SftpConnectionTestResult {
  ok: boolean;
  detail: string;
}

export interface RunNowResult {
  task_id: string;
  run_id: string | null;
}

// ── List query shapes ──

export interface SftpConnectionListQuery {
  page?: number;
  page_size?: number;
  tenant_code?: string;
  is_active?: boolean;
}

export interface IngestionScheduleListQuery {
  page?: number;
  page_size?: number;
  tenant_code?: string;
  is_enabled?: boolean;
  sftp_connection_id?: string;
}

export interface IngestionRunListQuery {
  page?: number;
  page_size?: number;
  tenant_code?: string;
  schedule_id?: string;
  status?: string;
  started_after?: string;
  started_before?: string;
}
