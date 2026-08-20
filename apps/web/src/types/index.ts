// ──────── User & Session ────────
export type UserRole = 'TENANT_ADMIN' | 'TENANT_USER';
export type ModuleCode = 'airline_jy' | 'airline_pw' | 'airline_alt' | 'cfl_fjl' | 'airline_wm' | 'airline_da';
export type Capability = 'alerts' | 'exports' | 'saved_views';

export interface TenantSession {
  tenant_id: string;
  tenant_name: string;
  enabled_modules: ModuleCode[];
  enabled_capabilities: Capability[];
  // True for the RTS platform admin tenant. The backend equivalent is
  // is_platform_admin() in deps.py (identity-based, not role-based).
  is_super_admin?: boolean;
  user: { id: string; name: string; email: string; roles: UserRole[]; avatar_url?: string };
}

export interface NavItem {
  label: string;
  path: string;
  icon: string;
  requiredModules?: ModuleCode[];
  requiredCapabilities?: Capability[];
  requiredRoles?: UserRole[];
  // When true, only the RTS super-admin sees this item, regardless of role list.
  requireSuperAdmin?: boolean;
  hideForSuperAdmin?: boolean;
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
// Mirrors apps/api/app/schemas/airline.py AirlineSnapshotOut.
// All non-core fields are Optional in Pydantic — declared optional here so
// the UI can render '—' for missing values without TS complaints.
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

  // Reference outbound additions
  ref_dep_time?: string | null;
  ref_arr_time?: string | null;
  ref_stops?: number | null;
  ref_via?: string | null;
  ref_ff_code?: string | null;
  ref_cab_name?: string | null;
  ref_bkg_class?: string | null;
  ref_yr?: number | null;
  ref_anc_price?: number | null;
  ref_anc_type?: string | null;
  ref_equip_code?: string | null;
  ref_equip_name?: string | null;

  // Reference return leg
  ref_ret_flt_num?: string | null;
  ref_ret_dep_date?: string | null;
  ref_ret_dep_time?: string | null;
  ref_ret_arr_time?: string | null;
  ref_ret_stops?: number | null;
  ref_ret_via?: string | null;
  ref_ret_cab_name?: string | null;
  ref_ret_cab_code?: string | null;
  ref_ret_bkg_class?: string | null;
  ref_ret_seats?: number | null;
  ref_ret_equip_code?: string | null;

  // Competitor outbound additions
  comp_dep_time?: string | null;
  comp_arr_time?: string | null;
  comp_stops?: number | null;
  comp_via?: string | null;
  comp_ff_code?: string | null;
  comp_cab_name?: string | null;
  comp_bkg_class?: string | null;
  comp_yr?: number | null;
  comp_anc_price?: number | null;
  comp_anc_type?: string | null;
  comp_equip_code?: string | null;
  comp_equip_name?: string | null;

  // Competitor return leg
  comp_ret_flt_num?: string | null;
  comp_ret_dep_date?: string | null;
  comp_ret_dep_time?: string | null;
  comp_ret_arr_time?: string | null;
  comp_ret_stops?: number | null;
  comp_ret_via?: string | null;
  comp_ret_cab_name?: string | null;
  comp_ret_cab_code?: string | null;
  comp_ret_bkg_class?: string | null;
  comp_ret_seats?: number | null;
  comp_ret_equip_code?: string | null;

  // Provenance and dictionary additions
  path?: string | null;
  ref_pos?: string | null;
  ref_channel?: string | null;
  comp_pos?: string | null;
  comp_channel?: string | null;

  // Infra / metadata
  ref_curr?: string | null;
  comp_curr?: string | null;
  tenant_code?: string | null;
  report_date?: string | null;
  file_date?: string | null;
  source_file?: string | null;
  business_type?: string | null;
  ingested_at?: string | null;
  loaded_at?: string | null;
}

// ──────── JY velocity snapshot ────────
export interface VelocitySnapshot {
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
  airline_code: string;
}

// ──────── CFL snapshot ────────
export interface CflSnapshot {
  id: string;
  cap_date: string;
  cap_time: string;
  trip_type: string;
  source: string;
  org: string;
  dest: string;
  out_dep_date: string;
  out_dep_time: string;
  // Outbound Arrival (migration 024)
  out_arr_date: string | null;
  out_arr_time: string | null;
  prod_family: string;
  out_equip_name: string;
  out_cab_type: string;
  // Outbound Descriptions & Seats (migration 024)
  out_cabin_desc: string | null;
  out_seat_type: string | null;
  out_num_cabs: number | null;
  out_seat_fare: number | null;
  out_num_seats: number | null;
  total_fare: number;
  out_per_pax_fare: number;
  out_veh_fare: number;
  out_cab_fare: number;
  out_taxes: number;
  out_num_pax: number;
  veh_size: string;
  curr_code: string;
  out_avail: string;
  // Return Journey — Schedule & Product (migration 024)
  ret_dep_date: string | null;
  ret_dep_time: string | null;
  ret_arr_date: string | null;
  ret_arr_time: string | null;
  ret_equip_name: string | null;
  ret_cab_type: string | null;
  ret_cab_desc: string | null;
  ret_seat_type: string | null;
  ret_avail: string | null;
  // Return Journey — Fares (migration 024)
  ret_per_pax_fare: number | null;
  ret_num_pax: number | null;
  ret_veh_fare: number | null;
  ret_cab_fare: number | null;
  ret_num_cabs: number | null;
  ret_seat_fare: number | null;
  ret_num_seats: number | null;
  ret_taxes: number | null;
  // Total/Combined Fares (migration 024)
  tot_per_pax_fare: number | null;
  tot_num_pax: number | null;
  tot_veh_fare: number | null;
  tot_cab_fare: number | null;
  tot_num_cabs: number | null;
  tot_seat_fare: number | null;
  tot_num_seats: number | null;
  tot_taxes: number | null;
  // Duration (migration 024)
  duration: number | null;
}

// ──────── Alerts ────────
export interface AlertRule {
  id: string; name: string; domain: string;
  rule_type: 'threshold' | 'anomaly' | 'schedule';
  condition_json: string; is_active: boolean;
  created_at: string; owner: string;
}

export type AlertSeverity = 'info' | 'warning' | 'critical';

/** Structured facts behind an alert. Every field optional — a rule family that
 *  does not compute one simply omits it, and the row renderer skips it. */
export interface AlertPayload {
  route?: string;
  origin?: string;
  destination?: string;
  window?: string;
  competitor?: string;
  currency?: string;
  metric?: string;
  state?: 'undercut' | 'cheapest' | string;
  prev_value?: number;
  current_value?: number;
  delta_abs?: number;
  delta_pct?: number;
  direction?: 'up' | 'down';
  da_fare?: number;
  da_rank?: number;
  cheaper_competitors?: number;
  /** How many competitors we actually have on this route. Six of DreamAir's
   *  twelve routes carry exactly one, so "rank 1 of 2" needs this context. */
  competitor_count?: number;
  best_competitor?: string;
  best_competitor_fare?: number;
  observations?: number;
  prev_observations?: number;
  evaluated_at?: string;
  rule_key?: string;
  [key: string]: unknown;
}

export interface AlertEvent {
  id: string; rule_id: string; rule_name: string; triggered_at: string;
  severity: AlertSeverity;
  message: string; delivery_status: 'pending' | 'sent' | 'failed';

  // Added with the alerts engine (migration 040).
  rule_key: string;
  scope_key?: string | null;
  /** The capture date this fact is ABOUT, and the baseline it was compared
   *  against. Distinct from triggered_at, which is when we say it happened. */
  observed_at?: string | null;
  prev_observed_at?: string | null;
  /** 'backfill' marks an event computed retroactively from real historical
   *  captures rather than observed live. */
  evaluation_mode: 'live' | 'backfill' | 'manual' | 'preview' | string;
  payload: AlertPayload;
  /** Per-user, computed per request — two users of one tenant see the same
   *  events with different read state. */
  is_read: boolean;
}

export interface AlertSummary {
  unread_count: number;
  capped: boolean;
  recent: AlertEvent[];
  newest_triggered_at: string | null;
}

/** One control on the settings screen. Ranges and options come from the server
 *  so the client never hard-codes what a threshold may be. */
export interface AlertTunable {
  key: string;
  label: string;
  type: 'number' | 'enum' | 'bool' | 'multiselect';
  unit: 'percent' | 'currency' | 'places' | string | null;
  min: number | null;
  max: number | null;
  step: number | null;
  options: string[] | null;
  help: string | null;
}

export interface AlertPreset {
  id: string;
  rule_key: string;
  name: string;
  description: string | null;
  domain: string;
  rule_type: string;
  is_active: boolean;
  is_preset: boolean;
  severity_default: AlertSeverity;
  condition: Record<string, unknown>;
  tunables: AlertTunable[];
  /** Fields that must be filled before the rule may be switched on. */
  missing_requirements: string[];
  created_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AlertPresetUpdate {
  is_active?: boolean;
  condition?: Record<string, unknown>;
}

export interface AlertRunSummary {
  tenant_code: string;
  cap_date: string | null;
  prev_cap_date: string | null;
  cap_date_age_days: number | null;
  rules_evaluated: string[];
  groups_evaluated: number;
  events_created: number;
  events_suppressed_dedupe: number;
  groups_skipped_currency: number;
  captures_skipped_incomplete: number;
  duration_ms: number;
  mode: string;
  note: string | null;
}

export interface AlertPreview {
  rule_key: string;
  cap_date: string | null;
  prev_cap_date: string | null;
  would_fire: number;
  groups_evaluated: number;
  sample: { severity: AlertSeverity; message: string; payload: AlertPayload }[];
}

export interface AlertEventQuery {
  page?: number;
  page_size?: number;
  unread_only?: boolean;
  rule_key?: string;
  severity?: AlertSeverity;
  route?: string;
  competitor?: string;
  since?: string;
  until?: string;
  with_total?: boolean;
}

export interface MarkReadResult {
  updated: number;
  unread_count: number;
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
  /** cap_date the server actually queried — echoes the pinned date when the client sent none. */
  applied_file_date?: string | null;
  /** True when the server skipped count(*) because with_total=false was sent (total will be 0). */
  total_is_cached?: boolean;
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

// Date-scoped Run Now (see admin_ingestion_schedules.run_schedule_now).
//   'today'             — only files whose filename DDMMYY equals today (IST)
//   'all'               — no date filter (backfill)
//   'date:DDMMYY'       — only files matching the given date
// The DDMMYY narrowing is enforced server-side by the Pydantic validator.
export type RunNowScope = 'today' | 'all' | `date:${string}`;

export interface RunNowRequest {
  scope: RunNowScope;
}

export interface RunNowResult {
  task_id: string;
  run_id: string | null;
  // Echo of the scope the backend accepted; useful for toast messages.
  scope?: RunNowScope;
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

// ──────── Admin Password Management ────────
export interface AdminUserListItem {
  id: string;
  email: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
  is_active: boolean;
  is_locked: boolean;
  force_password_change: boolean;
  last_login: string | null;
  created_at: string;
}

export interface AdminUserListResponse {
  users: AdminUserListItem[];
  total: number;
}

export interface AdminResetTokenItem {
  id: string;
  email: string;
  code: string;
  status: 'pending' | 'used' | 'expired';
  created_at: string;
  expires_at: string;
  attempts: number;
}

export interface AdminResetTokenListResponse {
  tokens: AdminResetTokenItem[];
  total: number;
}

export interface AdminGenerateResetCodeResponse {
  success: boolean;
  message: string;
  code: string;
  expires_at: string;
}

export interface AdminForceResetResponse {
  success: boolean;
  message: string;
}

export interface AdminTenantOption {
  tenant_id: string;
  slug: string;
  name: string;
}

export interface AdminInviteUserResponse {
  user_id: string;
  email: string;
  invite_sent: boolean;
}

export interface AdminResendInviteResponse {
  success: boolean;
  invite_sent: boolean;
  message: string;
}

export interface AdminSendResetEmailResponse {
  sent: boolean;
  message: string;
}

export interface InviteVerifyResponse {
  valid: boolean;
  email?: string | null;
}

export interface InviteAcceptResponse {
  success: boolean;
  message: string;
}


// ──────── Data Ops (restored from 66b5965) ────────
export type IngestionStatus =
  | 'STAGED'
  | 'VALIDATING'
  | 'VALIDATED'
  | 'COMMITTING'
  | 'COMMITTED'
  | 'REJECTED'
  | 'REPLACED'
  | 'FAILED'
  | 'DELETED';

export type IngestionDomain = 'AIRLINE' | 'VELOCITY' | 'CFL';
export type IngestionMode = 'STRICT' | 'LENIENT';

export type IngestionAuditAction =
  | 'UPLOADED'
  | 'VALIDATED'
  | 'COMMITTED'
  | 'REJECTED'
  | 'REPLACED'
  | 'CANCELLED'
  | 'DELETED';

export interface IngestionJob {
  id: string;
  tenant_id: string;
  tenant_code: string;
  domain: IngestionDomain;
  filename: string;
  file_hash: string;
  file_size_bytes: number;
  file_date: string;
  status: IngestionStatus;
  mode: IngestionMode;
  row_count_total: number | null;
  row_count_valid: number | null;
  row_count_rejected: number | null;
  validation_summary: Record<string, unknown> | null;
  uploaded_by_user_id: string;
  uploaded_at: string;
  validated_at: string | null;
  committed_at: string | null;
  replaced_by_job_id: string | null;
  error_message: string | null;
  /** True only for a COMMITTED, manually-uploaded job whose inserted fact
   *  rows can be deleted from the Ingestion Jobs page. Computed by the API. */
  deletable?: boolean;
}

export type IngestionMode = 'STRICT' | 'LENIENT';

export type IngestionAuditAction =
  | 'UPLOADED'
  | 'VALIDATED'
  | 'COMMITTED'
  | 'REJECTED'
  | 'REPLACED'
  | 'CANCELLED'
  | 'DELETED';

export interface IngestionJob {
  id: string;
  tenant_id: string;
  tenant_code: string;
  domain: IngestionDomain;
  filename: string;
  file_hash: string;
  file_size_bytes: number;
  file_date: string;
  status: IngestionStatus;
  mode: IngestionMode;
  row_count_total: number | null;
  row_count_valid: number | null;
  row_count_rejected: number | null;
  validation_summary: Record<string, unknown> | null;
  uploaded_by_user_id: string;
  uploaded_at: string;
  validated_at: string | null;
  committed_at: string | null;
  replaced_by_job_id: string | null;
  error_message: string | null;
}

export type IngestionAuditAction =
  | 'UPLOADED'
  | 'VALIDATED'
  | 'COMMITTED'
  | 'REJECTED'
  | 'REPLACED'
  | 'CANCELLED'
  | 'DELETED';

export interface IngestionJob {
  id: string;
  tenant_id: string;
  tenant_code: string;
  domain: IngestionDomain;
  filename: string;
  file_hash: string;
  file_size_bytes: number;
  file_date: string;
  status: IngestionStatus;
  mode: IngestionMode;
  row_count_total: number | null;
  row_count_valid: number | null;
  row_count_rejected: number | null;
  validation_summary: Record<string, unknown> | null;
  uploaded_by_user_id: string;
  uploaded_at: string;
  validated_at: string | null;
  committed_at: string | null;
  replaced_by_job_id: string | null;
  error_message: string | null;
}

export interface IngestionJob {
  id: string;
  tenant_id: string;
  tenant_code: string;
  domain: IngestionDomain;
  filename: string;
  file_hash: string;
  file_size_bytes: number;
  file_date: string;
  status: IngestionStatus;
  mode: IngestionMode;
  row_count_total: number | null;
  row_count_valid: number | null;
  row_count_rejected: number | null;
  validation_summary: Record<string, unknown> | null;
  uploaded_by_user_id: string;
  uploaded_at: string;
  validated_at: string | null;
  committed_at: string | null;
  replaced_by_job_id: string | null;
  error_message: string | null;
}

export interface IngestionUploadFileResult {
  filename: string;
  job: IngestionJob | null;
  duplicate: boolean;
  conflict: boolean;
  existing_job_id: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface IngestionUploadSummary {
  accepted: number;
  duplicate: number;
  conflict: number;
  rejected: number;
}

export interface IngestionUploadResponse {
  files: IngestionUploadFileResult[];
  summary: IngestionUploadSummary;
}

export interface IngestionValidationResult {
  job: IngestionJob;
  row_count_total: number;
  row_count_valid: number;
  row_count_rejected: number;
  summary: Record<string, unknown>;
}

export interface IngestionCommitResult {
  job: IngestionJob;
  rows_inserted: number;
  replaced_job_id: string | null;
}

export interface IngestionDeleteDataResult {
  job: IngestionJob;
  rows_deleted: number;
}

export interface IngestionAuditEntry {
  id: string;
  job_id: string;
  actor_user_id: string;
  action: IngestionAuditAction;
  actor_ip: string | null;
  timestamp: string;
  details: Record<string, unknown> | null;
}

export interface IngestionAuditLog {
  job_id: string;
  entries: IngestionAuditEntry[];
}

export interface IngestionPreviewRow {
  row_num: number;
  data: Record<string, unknown>;
}

export interface IngestionPreviewRejection {
  row_num: number;
  reason: string;
}

export interface IngestionPreview {
  job_id: string;
  sample_valid: IngestionPreviewRow[];
  sample_rejected: IngestionPreviewRejection[];
}

export interface ImportBatch {
  id: string;
  import_job_id: string;
  batch_seq: number;
  record_count: number;
  completeness_score: number | null;
  warning_codes: string[];
  validation_results: {
    total_fields?: number;
    present_fields?: number;
    optional_missing?: string[];
    warnings?: Array<{ code: string; message: string }>;
  };
  created_at: string;
}

// ──────── Admin Dashboard (Home page) ────────
export type ServiceHealthStatus = 'healthy' | 'unhealthy' | 'unknown';

export interface ServiceHealthItem {
  name: string;
  status: ServiceHealthStatus;
  response_time_ms: number | null;
  details: string | null;
}

export interface PlatformHealthResponse {
  services: ServiceHealthItem[];
  checked_at: string;
}

export type TenantFreshnessStatus = 'fresh' | 'stale' | 'critical' | 'no_data';

export interface TenantDataSummary {
  tenant_id: string;
  tenant_name: string;
  tenant_type: 'airline' | 'cruise';
  airline_code: string;
  sftp_connected: boolean;
  sftp_last_pull: string | null;
  sftp_last_pull_status: string | null;
  latest_data_date: string | null;
  last_capture_at: string | null;
  freshness_status: TenantFreshnessStatus;
  total_records: number;
  next_scheduled_run: string | null;
  schedule_enabled: boolean;
  last_run_status: string | null;
  last_run_id: string | null;
  last_run_at: string | null;
}

export interface TenantSummaryResponse {
  tenants: TenantDataSummary[];
}
