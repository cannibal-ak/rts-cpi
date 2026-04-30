import { TenantSession, DataFreshness, SavedView, SourceConfig } from '../types';

// Lightweight ingestion job type for home page display (no timeline needed)
interface HomeIngestionJob {
  id: string; source_name: string; domain: string;
  status: string; records_total: number; records_valid: number; records_rejected: number;
  started_at: string; completed_at?: string;
}

export const mockSession: TenantSession = {
  tenant_id: import.meta.env.VITE_TENANT_ID || 'a0000000-0000-0000-0000-000000000001',
  tenant_name: 'SkyWave Airlines Group',
  enabled_modules: ['airline_jy', 'airline_pw', 'cfl_fjl'],
  enabled_capabilities: ['alerts', 'exports', 'saved_views', 'contracts'],
  user: {
    id: 'user-001',
    name: 'Alex Rivera',
    email: 'alex.rivera@skywave.com',
    roles: ['TENANT_ADMIN'],
  },
};

export const mockRolePresets: Record<string, TenantSession> = {
  admin: { ...mockSession, user: { ...mockSession.user, roles: ['TENANT_ADMIN'] } },
  airline_jy: {
    ...mockSession,
    tenant_id: 'a0000000-0000-0000-0000-000000000001',
    tenant_name: 'Acme Airways - JY',
    enabled_modules: ['airline_jy'],
    user: { id: 'user-jy', name: 'Airline_JY', email: 'jy@airline.com', roles: ['TENANT_ADMIN'] },
  },
  airline_pw: {
    ...mockSession,
    tenant_id: 'bb000000-0000-0000-0000-000000000001',
    tenant_name: 'Skybound - PW',
    enabled_modules: ['airline_pw'],
    user: { id: 'user-pw', name: 'Airline_PW', email: 'pw@airline.com', roles: ['TENANT_ADMIN'] },
  },
  cruise_fjl: {
    ...mockSession,
    tenant_id: 'cc000000-0000-0000-0000-000000000001',
    tenant_name: 'Baltic Ferries - FJL',
    enabled_modules: ['cfl_fjl'],
    user: { id: 'user-fjl', name: 'Cruise_FJL', email: 'fjl@cruise.com', roles: ['TENANT_ADMIN'] },
  },
};

export const mockDataFreshness: DataFreshness[] = [
  { domain: 'Airline CPI', last_capture_at: '2026-03-05T08:30:00Z', last_import_at: '2026-03-05T09:15:00Z', record_count: 245890, status: 'fresh' },
  { domain: 'Cruise/Ferry CPI', last_capture_at: '2026-03-04T22:00:00Z', last_import_at: '2026-03-05T01:30:00Z', record_count: 18432, status: 'stale' },
];

export const mockIngestionJobs: HomeIngestionJob[] = [
  { id: 'job-001', source_name: 'SFTP - OAG Feed', domain: 'airline', status: 'committed', records_total: 15000, records_valid: 14985, records_rejected: 15, started_at: '2026-03-05T09:00:00Z', completed_at: '2026-03-05T09:12:00Z' },
  { id: 'job-002', source_name: 'API Push - FerryData', domain: 'cfl', status: 'validating', records_total: 3200, records_valid: 0, records_rejected: 0, started_at: '2026-03-05T09:30:00Z' },
  { id: 'job-003', source_name: 'Upload - Manual Comp', domain: 'airline', status: 'failed', records_total: 500, records_valid: 320, records_rejected: 180, started_at: '2026-03-05T08:45:00Z', completed_at: '2026-03-05T08:47:00Z' },
  { id: 'job-004', source_name: 'SFTP - CruiseLine A', domain: 'cfl', status: 'queued', records_total: 0, records_valid: 0, records_rejected: 0, started_at: '2026-03-05T09:45:00Z' },
];

// Validation errors, alert rules, and alert events are now served by the API client (see src/api/)
// Keeping references here only for backward compatibility of the Home page

export const mockSavedViews: SavedView[] = [
  { id: 'sv-001', name: 'LHR Hub - Economy Fares', domain: 'airline', filters: { ref_org: 'LHR', ref_cab_code: 'Y' }, created_at: '2026-02-28T10:00:00Z', owner: 'Alex Rivera', visibility: 'team' },
  { id: 'sv-002', name: 'Dover-Calais Vehicle Rates', domain: 'cfl', filters: { org: 'DVR', dest: 'CLS' }, created_at: '2026-03-01T14:00:00Z', owner: 'Sam Taylor', visibility: 'private' },
];

export const mockSourceConfigs: SourceConfig[] = [
  { id: 'src-001', name: 'OAG Airline Feed', type: 'sftp', domain: 'airline', status: 'active', last_poll_at: '2026-03-05T09:00:00Z', schedule: '0 */2 * * *' },
  { id: 'src-002', name: 'FerryData API', type: 'api_push', domain: 'cfl', status: 'active', last_poll_at: '2026-03-05T09:30:00Z' },
  { id: 'src-003', name: 'CruiseLine A SFTP', type: 'sftp', domain: 'cfl', status: 'error', last_poll_at: '2026-03-04T22:00:00Z', schedule: '0 0 * * *' },
  { id: 'src-004', name: 'Manual Upload Channel', type: 'upload', domain: 'airline', status: 'active' },
];
