import React from 'react';
import { Navigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { UserRole, ModuleCode, Capability } from '../../types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRoles?: UserRole[];
  requiredModules?: ModuleCode[];
  requiredCapabilities?: Capability[];
}

export default function ProtectedRoute({ children, requiredRoles, requiredModules, requiredCapabilities }: ProtectedRouteProps) {
  const { hasAccess } = useSession();

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
