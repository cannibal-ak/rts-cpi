import type { TenantSession } from '../types';

// TEMPORARY: replace with a server-driven session.is_super_admin
// boolean once the auth payload exposes one. Today the Skywave
// super-admin is the only identity whose preset enables all three
// per-tenant CPI modules; tenant users have exactly one each.
export function isSuperAdmin(session: TenantSession): boolean {
  return session.enabled_modules.length === 3;
}
