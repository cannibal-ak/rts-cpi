import type { TenantSession } from '../types';

// Backed by the session preset's `is_super_admin` flag (true only for the
// RTS platform-admin preset). Mirrors the backend's identity-based
// is_platform_admin() check in deps.py — the prior length-=== 3 heuristic
// silently broke the moment admin's enabled_modules changed.
export function isSuperAdmin(session: TenantSession): boolean {
  return session.is_super_admin === true;
}
