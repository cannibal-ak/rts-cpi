/**
 * Single source of truth for tenant display info.
 *
 * Keyed by the lowercase tenant slug (rts/jy/pw/fjl). The same map
 * drives the header avatar initials, profile-dropdown labels, and the
 * admin Home page tenant cards.
 */

export interface TenantConfigEntry {
  initials: string;
  displayName: string;
  orgName: string;
}

export const TENANT_CONFIG: Record<string, TenantConfigEntry> = {
  rts:     { initials: 'RTS', displayName: 'RTS Admin',    orgName: 'Revenue Technology Services' },
  jy:      { initials: 'JY', displayName: 'JY Airline',    orgName: 'interCaribbean Airways' },
  pw:      { initials: 'PW', displayName: 'PW Airline',    orgName: 'Precision Air' },
  fjl:     { initials: 'FL', displayName: 'FJL Cruise',    orgName: 'Fjord Line' },
  alt:     { initials: 'SA', displayName: 'Sky',           orgName: 'Sky Airways' },
  wm:      { initials: 'WA', displayName: 'WinAir',        orgName: 'WinAir' },
  da:      { initials: 'DA', displayName: 'DreamAir',      orgName: 'DreamAir' },
  '5l':    { initials: 'LA', displayName: 'Liat Air',      orgName: 'Liat Air' },
};

export const TENANT_FALLBACK: TenantConfigEntry = {
  initials: '??',
  displayName: 'User',
  orgName: 'Unknown',
};

/**
 * Resolve the canonical org name for a tenant by airline_code.
 *
 * Accepts uppercase codes from the API (e.g. 'JY', 'PW', 'FJL'). If the
 * code is not in TENANT_CONFIG, falls back to the provided `fallback`
 * (typically the API-supplied tenant_name) and emits a console.warn so
 * devs spot missing mappings during QA.
 */
export function getTenantDisplayName(airlineCode: string, fallback?: string): string {
  const key = (airlineCode ?? '').toLowerCase();
  const entry = TENANT_CONFIG[key];
  if (entry) return entry.orgName;
  console.warn(
    `[tenantConfig] No mapping for airline_code="${airlineCode}". ` +
    `Falling back to "${fallback ?? TENANT_FALLBACK.orgName}". ` +
    `Add this tenant to TENANT_CONFIG in utils/tenantConfig.ts.`
  );
  return fallback ?? TENANT_FALLBACK.orgName;
}
