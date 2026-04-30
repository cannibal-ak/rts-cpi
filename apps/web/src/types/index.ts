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

// ──────── Ingestion ────────
export type JobStatus = 'queued' | 'validating' | 'committed' | 'failed';
export type ValidationMode = 'STRICT' | 'COMPAT';

export interface JobTimelineEntry {
  status: JobStatus;
  timestamp: string;
  message?: string;
}

export interface IngestionJob {
  id: string;
  source_name: string;
  domain: string;
  tenant_code?: string;
  status: JobStatus;
  validation_mode: ValidationMode;
  records_total: number;
  records_valid: number;
  records_rejected: number;
  started_at: string;
  completed_at?: string;
  timeline: JobTimelineEntry[];
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
