/**
 * In-memory seed data for the Phase 3 SFTP admin endpoints (offline mock).
 *
 * Mutating mock methods on mockClient mutate these arrays so the UI's
 * optimistic CRUD flows render meaningfully when VITE_API_BASE_URL is
 * empty. Seed values mirror the 5 known YAML-driven filename regexes
 * declared by Phase A's filename_parser.py.
 */
import type {
  SftpConnection,
  IngestionSchedule,
  IngestionRun,
  IngestedFile,
} from '../types';


// Stable UUIDs so the mock state survives in-session navigation
// without resetting between page loads.
const CONN_JY = '11111111-1111-1111-1111-111111111101';
const CONN_PW = '11111111-1111-1111-1111-111111111102';

const SCHED_JY_AIRLINE = '22222222-2222-2222-2222-222222222201';
const SCHED_JY_VELOCITY = '22222222-2222-2222-2222-222222222202';
const SCHED_PW_AIRLINE = '22222222-2222-2222-2222-222222222203';

// ── Regexes mirroring the Phase A YAML source-of-truth ──
export const KNOWN_REGEXES = {
  jy_airline: '^JY_(\\d{6})\\.xlsx$',
  jy_velocity: '^JYVelocityData_(\\d{2}\\.\\d{2}\\.\\d{4})\\.csv$',
  pw_airline: '^PW_(\\d{6})\\.csv$',
  pw_velocity: '^PWVelocityData_(\\d{2}\\.\\d{2}\\.\\d{4})\\.csv$',
  fjl_cfl: '^FJL_(\\d{6})\\.csv$',
} as const;


export const mockSftpConnections: SftpConnection[] = [
  {
    id: CONN_JY,
    tenant_code: 'jy',
    name: 'jy-airline-sftp',
    host: 'sftp.jy.test',
    port: 22,
    username: 'jy_pull',
    auth_method: 'password',
    remote_base_path: '/upload',
    is_active: true,
    host_key_fingerprint: null,
    masked_credential: '****',
    created_at: '2026-04-15T10:00:00Z',
    updated_at: '2026-04-15T10:00:00Z',
  },
  {
    id: CONN_PW,
    tenant_code: 'pw',
    name: 'pw-airline-sftp',
    host: 'sftp.pw.test',
    port: 22,
    username: 'pw_pull',
    auth_method: 'private_key',
    remote_base_path: '/inbound',
    is_active: true,
    host_key_fingerprint: 'sha256:AAAAB3NzaC1yc2EAAAADAQABAAABAQ',
    masked_credential: 'pkey: <encrypted>',
    created_at: '2026-04-15T10:05:00Z',
    updated_at: '2026-04-20T14:22:00Z',
  },
];


export const mockIngestionSchedules: IngestionSchedule[] = [
  {
    id: SCHED_JY_AIRLINE,
    tenant_code: 'jy',
    sftp_connection_id: CONN_JY,
    cron_expression: '0 3 * * *',
    timezone: 'UTC',
    is_enabled: true,
    domain: 'AIRLINE',
    filename_regex: KNOWN_REGEXES.jy_airline,
    replace_existing: false,
    last_run_at: '2026-05-04T03:00:12Z',
    next_run_at: '2026-05-05T03:00:00Z',
    redbeat_registered: true,
    created_at: '2026-04-15T10:30:00Z',
    updated_at: '2026-04-15T10:30:00Z',
  },
  {
    id: SCHED_JY_VELOCITY,
    tenant_code: 'jy',
    sftp_connection_id: CONN_JY,
    cron_expression: '0 4 * * *',
    timezone: 'UTC',
    is_enabled: true,
    domain: 'VELOCITY',
    filename_regex: KNOWN_REGEXES.jy_velocity,
    replace_existing: false,
    last_run_at: '2026-05-04T04:00:08Z',
    next_run_at: '2026-05-05T04:00:00Z',
    redbeat_registered: true,
    created_at: '2026-04-16T09:00:00Z',
    updated_at: '2026-04-16T09:00:00Z',
  },
  {
    id: SCHED_PW_AIRLINE,
    tenant_code: 'pw',
    sftp_connection_id: CONN_PW,
    cron_expression: '0 5 * * *',
    timezone: 'UTC',
    is_enabled: false,
    domain: 'AIRLINE',
    filename_regex: KNOWN_REGEXES.pw_airline,
    replace_existing: false,
    last_run_at: null,
    next_run_at: null,
    redbeat_registered: false,
    created_at: '2026-04-20T11:00:00Z',
    updated_at: '2026-04-25T16:30:00Z',
  },
];


// ── Runs (1 RUNNING, 2 SUCCESS, 1 PARTIAL, 1 FAILED) ──

const RUN_RUNNING = '33333333-3333-3333-3333-333333333301';
const RUN_SUCCESS_1 = '33333333-3333-3333-3333-333333333302';
const RUN_SUCCESS_2 = '33333333-3333-3333-3333-333333333303';
const RUN_PARTIAL = '33333333-3333-3333-3333-333333333304';
const RUN_FAILED = '33333333-3333-3333-3333-333333333305';

const ingestedFor = (
  runId: string,
  scheduleId: string,
  files: Array<{
    filename: string;
    sha: string;
    size: number;
    outcome: string;
    error?: string;
    minutesAgo: number;
  }>
): IngestedFile[] =>
  files.map((f, idx) => ({
    id: `${runId.slice(0, 8)}-file-${idx}`,
    run_id: runId,
    schedule_id: scheduleId,
    remote_filename: f.filename,
    sha256: f.sha,
    remote_size_bytes: f.size,
    remote_mtime_utc: new Date(Date.now() - f.minutesAgo * 60_000).toISOString(),
    outcome: f.outcome,
    ingestion_job_id: f.outcome === 'COMMITTED' ? `${runId.slice(0, 8)}-job-${idx}` : null,
    error_message: f.error ?? null,
    created_at: new Date(Date.now() - f.minutesAgo * 60_000).toISOString(),
  }));

const nowMinus = (mins: number) => new Date(Date.now() - mins * 60_000).toISOString();

export const mockIngestionRuns: IngestionRun[] = [
  // RUNNING — started 2 minutes ago, no progress yet
  {
    id: RUN_RUNNING,
    schedule_id: SCHED_JY_AIRLINE,
    tenant_code: 'jy',
    started_at: nowMinus(2),
    finished_at: null,
    status: 'RUNNING',
    files_seen: 0,
    files_pulled: 0,
    jobs_created: 0,
    jobs_committed: 0,
    triggered_by: 'SCHEDULED',
    detail_log: null,
    error_summary: null,
  },
  // SUCCESS — 2 files committed, 25 minutes ago
  {
    id: RUN_SUCCESS_1,
    schedule_id: SCHED_JY_AIRLINE,
    tenant_code: 'jy',
    started_at: nowMinus(30),
    finished_at: nowMinus(25),
    status: 'SUCCESS',
    files_seen: 2,
    files_pulled: 2,
    jobs_created: 2,
    jobs_committed: 2,
    triggered_by: 'SCHEDULED',
    detail_log: [
      { filename: 'JY_010426.xlsx', outcome: 'COMMITTED' },
      { filename: 'JY_020426.xlsx', outcome: 'COMMITTED' },
    ],
    error_summary: null,
  },
  // SUCCESS — 3 files committed, 90 minutes ago
  {
    id: RUN_SUCCESS_2,
    schedule_id: SCHED_JY_VELOCITY,
    tenant_code: 'jy',
    started_at: nowMinus(95),
    finished_at: nowMinus(90),
    status: 'SUCCESS',
    files_seen: 3,
    files_pulled: 3,
    jobs_created: 3,
    jobs_committed: 3,
    triggered_by: 'SCHEDULED',
    detail_log: [
      { filename: 'JYVelocityData_01.04.2026.csv', outcome: 'COMMITTED' },
      { filename: 'JYVelocityData_02.04.2026.csv', outcome: 'COMMITTED' },
      { filename: 'JYVelocityData_03.04.2026.csv', outcome: 'COMMITTED' },
    ],
    error_summary: null,
  },
  // PARTIAL — 2 committed, 1 failed
  {
    id: RUN_PARTIAL,
    schedule_id: SCHED_JY_AIRLINE,
    tenant_code: 'jy',
    started_at: nowMinus(45),
    finished_at: nowMinus(40),
    status: 'PARTIAL',
    files_seen: 3,
    files_pulled: 3,
    jobs_created: 3,
    jobs_committed: 2,
    triggered_by: 'SCHEDULED',
    detail_log: [
      { filename: 'JY_280426.xlsx', outcome: 'COMMITTED' },
      { filename: 'JY_290426.xlsx', outcome: 'COMMITTED' },
      { filename: 'JY_300426.xlsx', outcome: 'FAILED', error: 'header row missing' },
    ],
    error_summary: '1 of 3 files failed validation',
  },
  // FAILED — total failure 1h ago
  {
    id: RUN_FAILED,
    schedule_id: SCHED_JY_VELOCITY,
    tenant_code: 'jy',
    started_at: nowMinus(65),
    finished_at: nowMinus(63),
    status: 'FAILED',
    files_seen: 0,
    files_pulled: 0,
    jobs_created: 0,
    jobs_committed: 0,
    triggered_by: 'SCHEDULED',
    detail_log: null,
    error_summary: 'connect_failed: Connection refused on sftp.jy.test:22',
  },
];

export const mockIngestedFiles: IngestedFile[] = [
  ...ingestedFor(RUN_SUCCESS_1, SCHED_JY_AIRLINE, [
    { filename: 'JY_010426.xlsx', sha: 'a'.repeat(64), size: 245_120, outcome: 'COMMITTED', minutesAgo: 28 },
    { filename: 'JY_020426.xlsx', sha: 'b'.repeat(64), size: 248_990, outcome: 'COMMITTED', minutesAgo: 27 },
  ]),
  ...ingestedFor(RUN_SUCCESS_2, SCHED_JY_VELOCITY, [
    { filename: 'JYVelocityData_01.04.2026.csv', sha: 'c'.repeat(64), size: 1_234_500, outcome: 'COMMITTED', minutesAgo: 94 },
    { filename: 'JYVelocityData_02.04.2026.csv', sha: 'd'.repeat(64), size: 1_241_300, outcome: 'COMMITTED', minutesAgo: 93 },
    { filename: 'JYVelocityData_03.04.2026.csv', sha: 'e'.repeat(64), size: 1_252_780, outcome: 'COMMITTED', minutesAgo: 92 },
  ]),
  ...ingestedFor(RUN_PARTIAL, SCHED_JY_AIRLINE, [
    { filename: 'JY_280426.xlsx', sha: 'f'.repeat(64), size: 230_000, outcome: 'COMMITTED', minutesAgo: 44 },
    { filename: 'JY_290426.xlsx', sha: '1'.repeat(64), size: 232_500, outcome: 'COMMITTED', minutesAgo: 43 },
    {
      filename: 'JY_300426.xlsx',
      sha: '2'.repeat(64),
      size: 197_400,
      outcome: 'FAILED',
      error: 'header row missing',
      minutesAgo: 42,
    },
  ]),
];


// ── Helpers ──

/**
 * Apply scalar-equality filters and pagination over an in-memory array.
 * Used by all three list mocks so filter logic isn't duplicated.
 *
 * Each entry in ``filters`` is matched with strict ``===`` against the
 * corresponding row field; ``undefined`` entries are skipped (no filter).
 */
export function makeQueryFilter<T>(
  rows: T[],
  filters: Partial<Record<keyof T, unknown>>,
  page = 1,
  pageSize = 20,
): { items: T[]; total: number; page: number; page_size: number; has_next: boolean } {
  const filtered = rows.filter(r => {
    for (const k of Object.keys(filters) as Array<keyof T>) {
      const want = filters[k];
      if (want === undefined) continue;
      if ((r as any)[k] !== want) return false;
    }
    return true;
  });
  const start = (page - 1) * pageSize;
  const slice = filtered.slice(start, start + pageSize);
  return {
    items: slice,
    total: filtered.length,
    page,
    page_size: pageSize,
    has_next: start + pageSize < filtered.length,
  };
}


/** Generate a random-looking UUID for mock-created rows. */
export function mockUuid(): string {
  // Browser-only mocks; crypto.randomUUID is always available in Vite dev.
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for older runtimes.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
