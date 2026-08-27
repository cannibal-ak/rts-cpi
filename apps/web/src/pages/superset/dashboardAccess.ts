import type { TenantSession, ModuleCode } from '../../types';

export const DASHBOARD_MODULE_MAP: Record<string, ModuleCode> = {
  '1': 'airline_jy',
  '2': 'airline_pw',
  '3': 'cfl_fjl',
  '4': 'airline_alt',
  '5': 'airline_wm',
  '6': 'airline_da',
  '7': 'airline_5l',
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

// Dashboards that do NOT offer the standalone Chart view. Their charts are
// only ever read inside the embedded dashboard, so nothing should link to a
// single slice - not the in-page selector, not the sidebar. '1' is
// interCaribbean (JY), '2' is Precision Air (PW), '5' is WinAir, '6' is
// DreamAir and '7' is Liat Air, whose charts are driven by their own top
// filter bar instead.
const NO_CHART_VIEW_DASHBOARDS = ['1', '2', '5', '6', '7'];

export function hasChartView(dashboardId: string | undefined | null): boolean {
  return !!dashboardId && !NO_CHART_VIEW_DASHBOARDS.includes(dashboardId);
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
