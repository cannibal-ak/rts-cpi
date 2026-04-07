import React, { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';
import { TenantSession, UserRole, ModuleCode, Capability } from '../types';
import { mockSession, mockRolePresets } from '../mock/session';
import { useAuth } from './AuthContext';

interface SessionContextType {
  session: TenantSession;
  hasRole: (roles: UserRole[]) => boolean;
  hasModule: (modules: ModuleCode[]) => boolean;
  hasCapability: (capabilities: Capability[]) => boolean;
  hasAccess: (opts: { roles?: UserRole[]; modules?: ModuleCode[]; capabilities?: Capability[] }) => boolean;
  updateFeatures: (modules: string[], capabilities: string[]) => void;
  updateRoles: (roles: UserRole[]) => void;
  isSyncing: boolean;
}

const SessionContext = createContext<SessionContextType | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [session, setSession] = useState<TenantSession>(mockSession);

  // Derive sync state: session is stale if emails don't match the current authenticated user
  const isSyncing = useMemo(() => {
    if (!user) return false;
    const userEmail = user.email.toLowerCase();
    const sessionEmail = session.user.email.toLowerCase();
    
    // If user exists but session belongs to a different email, we are syncing
    const matchingPreset = Object.values(mockRolePresets).find(p => p.user.email.toLowerCase() === userEmail);
    return !!matchingPreset && sessionEmail !== userEmail;
  }, [user, session.user.email]);

  // Sync session when auth user changes
  React.useEffect(() => {
    if (!user) {
      // Reset to default/Admin session on logout to prevent state leakage
      if (session.user.email !== mockSession.user.email) {
        setSession(mockSession);
      }
      return;
    }
    
    // Find matching preset by email
    const presetKey = Object.keys(mockRolePresets).find(key => 
      mockRolePresets[key].user.email.toLowerCase() === user.email.toLowerCase()
    );

    if (presetKey && mockRolePresets[presetKey].user.email.toLowerCase() !== session.user.email.toLowerCase()) {
      setSession(mockRolePresets[presetKey]);
    }
  }, [user, session.user.email]);

  const updateFeatures = useCallback((modules: string[], capabilities: string[]) => {
    setSession(prev => ({
      ...prev,
      enabled_modules: modules as ModuleCode[],
      enabled_capabilities: capabilities as Capability[],
    }));
  }, []);

  const updateRoles = useCallback((roles: UserRole[]) => {
    setSession(prev => ({
      ...prev,
      user: {
        ...prev.user,
        roles
      }
    }));
  }, []);

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
    session, hasRole, hasModule, hasCapability, hasAccess, updateFeatures, updateRoles, isSyncing
  }), [session, hasRole, hasModule, hasCapability, hasAccess, updateFeatures, updateRoles, isSyncing]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
