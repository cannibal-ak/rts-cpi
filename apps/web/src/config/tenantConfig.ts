import type { ModuleCode } from '../types';

/**
 * Tenant → module derivation, keyed by the REAL `tenant.slug` values.
 *
 * This is the single source the session derivation uses to decide which CPI
 * module (and therefore which dashboard / nav / branding) a tenant sees. It
 * REPLACES the old per-email `mockRolePresets`: onboarding a new tenant is now
 * one entry here (slug → ModuleCode) plus its dashboard id in
 * pages/superset/dashboardAccess.ts — no more email-keyed mock preset.
 *
 * NB: distinct from utils/tenantConfig.ts (which holds AppBar branding); this
 * file is purely the slug→module / slug→name lookup for SessionContext.
 */

// Real RTS platform-admin tenant slug (tenant table). is_super_admin keys off
// this — a non-RTS tenant is never a super admin.
export const RTS_SLUG = 'rts';

// slug (tenant.slug) → the tenant's single CPI ModuleCode.
// rts (platform admin) intentionally has NO module entry.
export const TENANT_MODULE_MAP: Record<string, ModuleCode> = {
  jy: 'airline_jy',
  pw: 'airline_pw',
  fjl: 'cfl_fjl',
  alt: 'airline_alt',
  wm: 'airline_wm',
  da: 'airline_da',
  '5l': 'airline_5l',
};

// slug → tenant_name. Reproduces the pre-3b mockRolePresets names EXACTLY
// (jy and wm intentionally differ from tenant.display_name). Display only —
// never used for gating; feeds session.tenant_name.
export const TENANT_NAME_MAP: Record<string, string> = {
  rts: 'Revenue Technology Services',
  jy: 'interCaribbean Airways',
  pw: 'Skybound - PW',
  fjl: 'Baltic Ferries - FJL',
  alt: 'Sky Airways',
  wm: 'WinAir',
  da: 'DreamAir',
  '5l': 'Liat Air',
};
