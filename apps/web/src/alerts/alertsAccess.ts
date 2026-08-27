/**
 * Who gets alerting, in one place.
 *
 * Gating is on module + role, deliberately NOT on capability. `SessionContext`
 * fills `enabled_capabilities` from `mock/session.ts` for every session, so
 * `hasCapability('alerts')` currently returns true for everyone — a guard that
 * reads as security and provides none, which is worse than no guard at all.
 * The backend enforces the real thing.
 *
 * When tenant_feature is properly plumbed into the session, add the capability
 * to the guards alongside the module and then drop the module: `hasAccess`
 * ANDs its clauses, so both can coexist during the transition.
 *
 * Widening to another tenant is one entry here plus CPI_ALERTS_TENANT_CODES on
 * the API.
 */
import type { ModuleCode, UserRole } from '../types';
import type { TenantSession } from '../types';

/** Tenants with the alerts UI switched on: DreamAir, Liat Air, WinAir, interCaribbean, Precision Air. */
export const ALERTS_MODULES: ModuleCode[] = ['airline_da', 'airline_5l', 'airline_wm', 'airline_jy', 'airline_pw'];

export const ALERTS_VIEW_ROLES: UserRole[] = ['TENANT_ADMIN', 'TENANT_USER'];
export const ALERTS_ADMIN_ROLES: UserRole[] = ['TENANT_ADMIN'];

/**
 * Whether this session sees alerting at all.
 *
 * The platform admin is excluded: it holds no tenant modules and alerts are
 * tenant-owned data, so a bell in the RTS header would always read zero.
 */
export function alertsEnabledFor(session: TenantSession): boolean {
  if (session.is_super_admin) return false;
  if (!ALERTS_MODULES.some(m => session.enabled_modules.includes(m))) return false;
  return session.user.roles.some(r => (ALERTS_VIEW_ROLES as string[]).includes(r));
}

/** Whether this session may change thresholds, not just read alerts. */
export function canEditAlertRules(session: TenantSession): boolean {
  return alertsEnabledFor(session)
    && session.user.roles.some(r => (ALERTS_ADMIN_ROLES as string[]).includes(r));
}
