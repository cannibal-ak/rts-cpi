import type {
  AirlineSnapshot, CflSnapshot, IngestionJob, ValidationError,
  AlertRule, AlertEvent, TenantFeature,
  FilterMetadata, JobTimelineEntry,
} from '../types';

// ── Helpers ─────────────────────────
const rand = (min: number, max: number) => Math.round((Math.random() * (max - min) + min) * 100) / 100;
const randInt = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = <T>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];
const uuid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const AIRLINES = ['BA', 'EK', 'SQ', 'LH', 'AF', 'QR', 'VS', 'AA', 'UA', 'DL', 'TK', 'NH'];
const AIRPORTS = ['LHR', 'JFK', 'DXB', 'SIN', 'CDG', 'FRA', 'IST', 'NRT', 'LAX', 'ORD', 'AMS', 'DOH'];
const CABINS = ['F', 'J', 'W', 'Y'];
const POS_CODES = ['GB', 'US', 'AE', 'SG', 'FR', 'DE'];

const FERRY_OPS = ['P&O Ferries', 'DFDS', 'Irish Ferries', 'Stena Line', 'Brittany Ferries', 'Viking Line'];
const PORTS = ['DVR', 'CLS', 'PLY', 'SBG', 'ROS', 'HEL', 'TLL', 'STO', 'CPH'];
const PROD_FAMILIES = ['Standard', 'Flexi', 'Premium', 'Economy Saver', 'Club'];
const EQUIP = ['Spirit of Britain', 'Cote dAlbatros', 'Stena Adventurer', 'MS Viking Grace', 'Pont-Aven'];
const VEH_SIZES = ['car', 'van', 'motorcycle', 'none', 'caravan'];
const CURRENCIES = ['USD'];

// ── Airline snapshots ───────────────
export function generateAirlineSnapshots(count: number = 60): AirlineSnapshot[] {
  const rows: AirlineSnapshot[] = [];
  for (let i = 0; i < count; i++) {
    const tripType = pick(['OW', 'RT'] as const);
    const refOrg = pick(AIRPORTS);
    let refDst = pick(AIRPORTS);
    while (refDst === refOrg) refDst = pick(AIRPORTS);
    const refAl = pick(AIRLINES);
    let compAl = pick(AIRLINES);
    while (compAl === refAl) compAl = pick(AIRLINES);
    const depOffset = randInt(1, 60);
    const depDate = new Date(Date.now() + depOffset * 86400000).toISOString().slice(0, 10);
    const capDate = new Date(Date.now() - randInt(0, 5) * 86400000).toISOString().slice(0, 10);
    const cabin = pick(CABINS);
    const refBase = rand(80, 1200);
    const refTax = rand(20, 180);
    const refYq = rand(0, 80);
    const compBase = refBase * rand(0.7, 1.35);
    const compTax = rand(20, 180);
    const compYq = rand(0, 80);
    rows.push({
      id: `air-${uuid()}`,
      cap_date: capDate,
      cap_time: `${String(randInt(0, 23)).padStart(2, '0')}:${String(randInt(0, 59)).padStart(2, '0')}:00`,
      trip_type: tripType,
      ref_al: refAl,
      ref_flt_num: `${refAl}${randInt(100, 999)}`,
      ref_org: refOrg,
      ref_dst: refDst,
      ref_dep_date: depDate,
      ref_cab_code: cabin,
      ref_tot_fare: Math.round((refBase + refTax + refYq) * 100) / 100,
      ref_base_fare: Math.round(refBase * 100) / 100,
      ref_tax: Math.round(refTax * 100) / 100,
      ref_yq: Math.round(refYq * 100) / 100,
      ref_seats: randInt(1, 9),
      comp_al: compAl,
      comp_flt_num: `${compAl}${randInt(100, 999)}`,
      comp_org: refOrg,
      comp_dst: refDst,
      comp_dep_date: depDate,
      comp_cab_code: cabin,
      comp_tot_fare: Math.round((compBase + compTax + compYq) * 100) / 100,
      comp_base_fare: Math.round(compBase * 100) / 100,
      comp_tax: Math.round(compTax * 100) / 100,
      comp_yq: Math.round(compYq * 100) / 100,
      comp_seats: randInt(1, 9),
      pos: pick(POS_CODES),
      poa: pick(POS_CODES),
    });
  }
  return rows;
}

// ── CFL snapshots ───────────────────
export function generateCflSnapshots(count: number = 40): CflSnapshot[] {
  const rows: CflSnapshot[] = [];
  for (let i = 0; i < count; i++) {
    const tripType = pick(['ONE_WAY', 'ROUND_TRIP'] as const);
    const org = pick(PORTS);
    let dest = pick(PORTS);
    while (dest === org) dest = pick(PORTS);
    const depOffset = randInt(1, 45);
    const depDate = new Date(Date.now() + depOffset * 86400000).toISOString().slice(0, 10);
    const capDate = new Date(Date.now() - randInt(0, 3) * 86400000).toISOString().slice(0, 10);
    const paxFare = rand(25, 220);
    const vehFare = rand(50, 350);
    const cabFare = rand(0, 180);
    const taxes = rand(5, 45);
    rows.push({
      id: `cfl-${uuid()}`,
      cap_date: capDate,
      cap_time: `${String(randInt(0, 23)).padStart(2, '0')}:${String(randInt(0, 59)).padStart(2, '0')}:00`,
      trip_type: tripType,
      source: pick(FERRY_OPS),
      org,
      dest,
      out_dep_date: depDate,
      out_dep_time: `${String(randInt(5, 22)).padStart(2, '0')}:${pick(['00', '15', '30', '45'])}`,
      prod_family: pick(PROD_FAMILIES),
      out_equip_name: pick(EQUIP),
      out_cab_type: pick(['Inside', 'Outside', 'Balcony', 'Suite', 'none']),
      total_fare: Math.round((paxFare + vehFare + cabFare + taxes) * 100) / 100,
      out_per_pax_fare: Math.round(paxFare * 100) / 100,
      out_veh_fare: Math.round(vehFare * 100) / 100,
      out_cab_fare: Math.round(cabFare * 100) / 100,
      out_taxes: Math.round(taxes * 100) / 100,
      out_num_pax: randInt(1, 6),
      veh_size: pick(VEH_SIZES),
      curr_code: pick(CURRENCIES),
      out_avail: pick(['Available', 'Limited', 'Sold Out']),
    });
  }
  return rows;
}

// ── Ingestion jobs ──────────────────
export function generateIngestionJobs(): IngestionJob[] {
  const statuses: Array<{ s: 'queued' | 'validating' | 'committed' | 'failed'; tl: (base: string) => JobTimelineEntry[] }> = [
    {
      s: 'committed', tl: (b) => [
        { status: 'queued', timestamp: b },
        { status: 'validating', timestamp: new Date(new Date(b).getTime() + 30000).toISOString() },
        { status: 'committed', timestamp: new Date(new Date(b).getTime() + 720000).toISOString(), message: 'All records committed successfully' },
      ]
    },
    {
      s: 'validating', tl: (b) => [
        { status: 'queued', timestamp: b },
        { status: 'validating', timestamp: new Date(new Date(b).getTime() + 15000).toISOString(), message: 'Validation in progress...' },
      ]
    },
    {
      s: 'failed', tl: (b) => [
        { status: 'queued', timestamp: b },
        { status: 'validating', timestamp: new Date(new Date(b).getTime() + 10000).toISOString() },
        { status: 'failed', timestamp: new Date(new Date(b).getTime() + 120000).toISOString(), message: '180 records rejected — exceeds failure threshold (36%)' },
      ]
    },
    {
      s: 'queued', tl: (b) => [
        { status: 'queued', timestamp: b, message: 'Waiting for worker slot' },
      ]
    },
  ];

  const sources = [
    { name: 'SFTP - OAG Feed (JY)', domain: 'airline', tenant_code: 'JY' },
    { name: 'API Push - FerryData (FJL)', domain: 'cfl', tenant_code: 'FJL' },
    { name: 'Upload - Manual Comp (JY)', domain: 'airline', tenant_code: 'JY' },
    { name: 'SFTP - CruiseLine A (FJL)', domain: 'cfl', tenant_code: 'FJL' },
    { name: 'SFTP - PW Airline Feed', domain: 'airline', tenant_code: 'PW' },
    { name: 'Daily CSV Ingest (JY)', domain: 'airline', tenant_code: 'JY' },
    { name: 'Daily CSV Ingest (PW)', domain: 'airline', tenant_code: 'PW' },
    { name: 'Daily CSV Ingest (FJL)', domain: 'cfl', tenant_code: 'FJL' },
  ];

  return sources.map((src, i) => {
    const st = statuses[i % statuses.length];
    const base = new Date(Date.now() - (i * 3600000 + randInt(0, 3600000))).toISOString();
    const total = randInt(500, 20000);
    const valid = st.s === 'committed' ? total - randInt(0, 20) : st.s === 'failed' ? Math.floor(total * 0.64) : 0;
    const rejected = st.s === 'committed' ? total - valid : st.s === 'failed' ? total - valid : 0;
    const timeline = st.tl(base);
    return {
      id: `job-${String(i + 1).padStart(3, '0')}`,
      source_name: src.name,
      domain: src.domain,
      tenant_code: src.tenant_code,
      status: st.s,
      validation_mode: pick(['STRICT', 'COMPAT'] as const),
      records_total: total,
      records_valid: valid,
      records_rejected: rejected,
      started_at: base,
      completed_at: st.s === 'committed' || st.s === 'failed' ? timeline[timeline.length - 1].timestamp : undefined,
      timeline,
    };
  });
}

// ── Validation errors ───────────────
export function generateValidationErrors(): ValidationError[] {
  const errorTemplates = [
    { field: 'RefTotFare', code: 'VAL_REQUIRED', msg: 'Required field RefTotFare is missing', sev: 'error' as const },
    { field: 'CompOrg', code: 'VAL_PATTERN_MISMATCH', msg: 'CompOrg must be a valid 3-letter IATA code', sev: 'error' as const },
    { field: 'TripType', code: 'VAL_INVALID_ENUM', msg: 'TripType must be OW or RT', sev: 'error' as const },
    { field: 'RefRetDepDate', code: 'VAL_CONDITIONAL_FORBIDDEN', msg: 'ReturnDepDate not allowed for TripType=OW', sev: 'warning' as const },
    { field: 'CompTotFare', code: 'VAL_RANGE_EXCEEDED', msg: 'CompTotFare exceeds maximum threshold (50000)', sev: 'error' as const },
    { field: 'RefDepDate', code: 'VAL_INVALID_FORMAT', msg: 'RefDepDate is not a valid ISO 8601 date', sev: 'error' as const },
    { field: 'CompCabCode', code: 'VAL_INVALID_ENUM', msg: 'CompCabCode value "Z" not in allowed set [F,J,W,Y]', sev: 'error' as const },
    { field: 'POS', code: 'VAL_PATTERN_MISMATCH', msg: 'POS must be a 2-letter ISO country code', sev: 'warning' as const },
    { field: 'RefSeats', code: 'VAL_RANGE_EXCEEDED', msg: 'RefSeats value -1 is below minimum (0)', sev: 'error' as const },
    { field: 'CompBaseFare', code: 'VAL_REQUIRED', msg: 'Required field CompBaseFare is missing', sev: 'error' as const },
    { field: 'CurrCode', code: 'VAL_PATTERN_MISMATCH', msg: 'CurrCode exceeds maxLength of 3', sev: 'error' as const },
    { field: 'RetDepDate', code: 'VAL_CONDITIONAL_REQUIRED', msg: 'RetDepDate required for TripType=ROUND_TRIP', sev: 'error' as const },
  ];
  const jobs = ['job-003', 'job-001', 'job-005', 'job-007'];
  const errors: ValidationError[] = [];
  for (let i = 0; i < 35; i++) {
    const tmpl = errorTemplates[i % errorTemplates.length];
    errors.push({
      id: `ve-${String(i + 1).padStart(3, '0')}`,
      job_id: pick(jobs),
      row_number: randInt(1, 15000),
      field: tmpl.field,
      error_code: tmpl.code,
      message: tmpl.msg,
      severity: tmpl.sev,
    });
  }
  return errors.sort((a, b) => a.job_id.localeCompare(b.job_id) || a.row_number - b.row_number);
}

// ── Alert rules ─────────────────────
export function generateAlertRules(): AlertRule[] {
  return [
    { id: 'ar-001', name: 'Fare Drop > 15% on Key Routes', domain: 'airline', rule_type: 'threshold', condition_json: '{"metric":"comp_tot_fare","operator":"decrease_pct","threshold":15,"routes":["LHR-DXB","LHR-JFK","CDG-SIN"]}', is_active: true, created_at: '2026-02-15T10:00:00Z', owner: 'Alex Rivera' },
    { id: 'ar-002', name: 'New Competitor on LHR-JFK', domain: 'airline', rule_type: 'anomaly', condition_json: '{"route":"LHR-JFK","event":"new_carrier"}', is_active: true, created_at: '2026-02-20T14:00:00Z', owner: 'Alex Rivera' },
    { id: 'ar-003', name: 'CFL Price Anomaly Detection', domain: 'cfl', rule_type: 'anomaly', condition_json: '{"metric":"total_fare","zscore_threshold":3}', is_active: false, created_at: '2026-01-10T08:00:00Z', owner: 'Sam Taylor' },
    { id: 'ar-004', name: 'Daily Import Health Check', domain: 'airline', rule_type: 'schedule', condition_json: '{"cron":"0 10 * * *","check":"import_freshness","max_age_hours":24}', is_active: true, created_at: '2026-02-01T09:00:00Z', owner: 'Jordan Chen' },
    { id: 'ar-005', name: 'DVR-CLS Vehicle Fare Spike', domain: 'cfl', rule_type: 'threshold', condition_json: '{"metric":"out_veh_fare","operator":"increase_pct","threshold":25,"route":"DVR-CLS"}', is_active: true, created_at: '2026-02-28T11:00:00Z', owner: 'Morgan Lee' },
  ];
}

// ── Alert events ────────────────────
export function generateAlertEvents(): AlertEvent[] {
  return [
    { id: 'ae-001', rule_id: 'ar-001', rule_name: 'Fare Drop > 15% on Key Routes', triggered_at: '2026-03-05T07:30:00Z', severity: 'critical', message: 'Fare dropped 22% on LHR-DXB (competitor: EK, was $820 now $640)', delivery_status: 'sent' },
    { id: 'ae-002', rule_id: 'ar-002', rule_name: 'New Competitor on LHR-JFK', triggered_at: '2026-03-04T18:00:00Z', severity: 'warning', message: 'New carrier detected on LHR-JFK route: Norse Atlantic (fare $289)', delivery_status: 'sent' },
    { id: 'ae-003', rule_id: 'ar-001', rule_name: 'Fare Drop > 15% on Key Routes', triggered_at: '2026-03-03T12:15:00Z', severity: 'info', message: 'Fare dropped 16% on CDG-SIN (competitor: SQ, was $1250 now $1050)', delivery_status: 'sent' },
    { id: 'ae-004', rule_id: 'ar-005', rule_name: 'DVR-CLS Vehicle Fare Spike', triggered_at: '2026-03-04T06:00:00Z', severity: 'warning', message: 'Vehicle fare increased 32% on DVR-CLS (P&O, was $180 now $238)', delivery_status: 'sent' },
    { id: 'ae-005', rule_id: 'ar-004', rule_name: 'Daily Import Health Check', triggered_at: '2026-03-05T10:00:00Z', severity: 'info', message: 'All airline imports within 24h freshness window', delivery_status: 'sent' },
    { id: 'ae-006', rule_id: 'ar-001', rule_name: 'Fare Drop > 15% on Key Routes', triggered_at: '2026-03-02T09:45:00Z', severity: 'critical', message: 'Fare dropped 28% on LHR-JFK (competitor: AA, was $650 now $468)', delivery_status: 'sent' },
    { id: 'ae-007', rule_id: 'ar-003', rule_name: 'CFL Price Anomaly Detection', triggered_at: '2026-03-01T14:30:00Z', severity: 'warning', message: 'Statistical anomaly on STO-TLL route (z-score 4.2, Stena Line)', delivery_status: 'failed' },
  ];
}





// ── Tenant features ─────────────────
export function generateTenantFeatures(): TenantFeature[] {
  return [
    { code: 'airline', label: 'Airline CPI Module', category: 'module', enabled: true },
    { code: 'cfl', label: 'Cruise / Ferry CPI Module', category: 'module', enabled: true },
    { code: 'alerts', label: 'Alerting Engine', category: 'capability', enabled: true },
    { code: 'exports', label: 'Data Exports', category: 'capability', enabled: true },
    { code: 'saved_views', label: 'Saved Views', category: 'capability', enabled: true },
    { code: 'superset_embed', label: 'Superset Embedded Dashboards', category: 'analytics', enabled: true },
    { code: 'cross_domain', label: 'Cross-Domain Harmonized Views', category: 'analytics', enabled: false },
    { code: 'co_branding', label: 'Tenant Co-Branding', category: 'branding', enabled: false },
  ];
}

// ── Filter metadata ─────────────────
export function airlineFilterMeta(): FilterMetadata[] {
  return [
    { field: 'file_date', label: 'File Date', values: ['2026-03-10', '2026-03-09', '2026-03-08'] },
    { field: 'airline', label: 'Airline', values: ['JY', 'PW'] },
  ];
}

export function cflFilterMeta(): FilterMetadata[] {
  return [
    { field: 'file_date', label: 'File Date', values: ['2026-03-10', '2026-03-09'] },
    { field: 'operator', label: 'Airline / Operator', values: ['FJL'] },
  ];
}

// ── Exported Constants ──────────────
export const mockAirlineSnapshots: AirlineSnapshot[] = [];
export const mockCflSnapshots: CflSnapshot[] = [];
export const mockIngestionJobs = generateIngestionJobs();
export const mockValidationErrors: ValidationError[] = [];
export const mockAlertRules = generateAlertRules();
export const mockAlertEvents = generateAlertEvents();


export const mockTenantFeatures = generateTenantFeatures();

export const mockFilterMetadata = {
  airline: airlineFilterMeta(),
  cfl: cflFilterMeta(),
};
