import React from 'react';
import { Navigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { UserRole, ModuleCode, Capability } from '../../types';
import { isSuperAdmin } from '../../utils/access';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRoles?: UserRole[];
  requiredModules?: ModuleCode[];
  requiredCapabilities?: Capability[];
  requireSuperAdmin?: boolean;
  // Hard-blocks the Skywave platform admin from a route. Used for tenant-only
  // surfaces (analytics dashboards) where the admin has no business being.
  denyForSuperAdmin?: boolean;
}

export default function ProtectedRoute({ children, requiredRoles, requiredModules, requiredCapabilities, requireSuperAdmin, denyForSuperAdmin }: ProtectedRouteProps) {
  const { hasAccess, session } = useSession();

  if (requireSuperAdmin && !isSuperAdmin(session)) {
    return <Navigate to="/not-authorized" replace />;
  }

  if (denyForSuperAdmin && isSuperAdmin(session)) {
    return <Navigate to="/" replace />;
  }

  const allowed = hasAccess({
    roles: requiredRoles,
    modules: requiredModules,
    capabilities: requiredCapabilities,
  });

  if (!allowed) {
    return <Navigate to="/not-authorized" replace />;
  }

  return <>{children}</>;
}
