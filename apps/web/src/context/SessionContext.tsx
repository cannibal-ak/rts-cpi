import React, { createContext, useContext, useCallback, useMemo, ReactNode } from 'react';
import { TenantSession, UserRole, ModuleCode, Capability } from '../types';
import { mockSession } from '../mock/session';
import { RTS_SLUG, TENANT_MODULE_MAP, TENANT_NAME_MAP } from '../config/tenantConfig';
import { useAuth } from './AuthContext';

interface SessionContextType {
  session: TenantSession;
  hasRole: (roles: UserRole[]) => boolean;
  hasModule: (modules: ModuleCode[]) => boolean;
  hasCapability: (capabilities: Capability[]) => boolean;
  hasAccess: (opts: { roles?: UserRole[]; modules?: ModuleCode[]; capabilities?: Capability[] }) => boolean;
  isSyncing: boolean;
}

const SessionContext = createContext<SessionContextType | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  // Session is DERIVED synchronously from the authenticated (JWT-backed) user:
  // roles + tenantSlug come from AuthContext (/login + /me). No email->preset
  // matching, no async sync gap.
  //
  // CRITICAL: an authenticated user whose slug is unknown/unmapped resolves to
  // is_super_admin:false with NO modules — it must NEVER fall back to the
  // super-admin mockSession. mockSession is used ONLY for the pre-login
  // (unauthenticated) state.
  const session: TenantSession = useMemo(() => {
    if (!user) return mockSession;
    const slug = (user.tenantSlug || '').toLowerCase();
    const roles = user.roles as UserRole[];
    const moduleCode = TENANT_MODULE_MAP[slug];
    return {
      tenant_id: user.tenantId,
      tenant_name: TENANT_NAME_MAP[slug] ?? user.tenantSlug,
      enabled_modules: moduleCode ? [moduleCode] : [],
      enabled_capabilities: mockSession.enabled_capabilities,
      is_super_admin: slug === RTS_SLUG.toLowerCase() && roles.includes('TENANT_ADMIN'),
      user: {
        id: user.id,
        email: user.email,
        name: user.display_name,
        roles,
      },
    };
  }, [user]);

  // Derivation is synchronous, so the session is never stale relative to the
  // authenticated user — there is no syncing window to wait on.
  const isSyncing = false;

  const hasRole = useCallback((roles: UserRole[]) => {
    return roles.some(r => session.user.roles.includes(r));
  }, [session]);

  const hasModule = useCallback((modules: ModuleCode[]) => {
    return modules.some(m => session.enabled_modules.includes(m));
  }, [session]);

  const hasCapability = useCallback((capabilities: Capability[]) => {
    return capabilities.some(c => session.enabled_capabilities.includes(c));
  }, [session]);

  const hasAccess = useCallback((opts: { roles?: UserRole[]; modules?: ModuleCode[]; capabilities?: Capability[] }) => {
    if (opts.roles && !hasRole(opts.roles)) return false;
    if (opts.modules && !hasModule(opts.modules)) return false;
    if (opts.capabilities && !hasCapability(opts.capabilities)) return false;
    return true;
  }, [hasRole, hasModule, hasCapability]);

  const value = useMemo(() => ({
    session, hasRole, hasModule, hasCapability, hasAccess, isSyncing
  }), [session, hasRole, hasModule, hasCapability, hasAccess, isSyncing]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
