import type { TenantSession, ModuleCode } from '../../types';

export const DASHBOARD_MODULE_MAP: Record<string, ModuleCode> = {
  '1': 'airline_jy',
  '2': 'airline_pw',
  '3': 'cfl_fjl',
  '5': 'airline_wm',
};

export function canAccessDashboard(
  session: TenantSession,
  dashboardId: string | undefined,
): boolean {
  if (!dashboardId) return false;
  const moduleCode = DASHBOARD_MODULE_MAP[dashboardId];
  if (!moduleCode) return false;
  return session.enabled_modules.includes(moduleCode);
}

// Reverse-lookup: returns the dashboard ID for a tenant with exactly one
// accessible dashboard. Returns null for admins (multiple matches),
// users with no enabled modules, or modules with no mapping.
export function getPrimaryDashboardId(session: TenantSession): string | null {
  const accessibleIds = Object.entries(DASHBOARD_MODULE_MAP)
    .filter(([, moduleCode]) => session.enabled_modules.includes(moduleCode))
    .map(([id]) => id);
  if (accessibleIds.length !== 1) return null;
  return accessibleIds[0];
}
