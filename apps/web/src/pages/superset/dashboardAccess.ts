import type { TenantSession, ModuleCode } from '../../types';

export const DASHBOARD_MODULE_MAP: Record<string, ModuleCode> = {
  '1': 'airline_jy',
  '2': 'airline_pw',
  '3': 'cfl_fjl',
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
