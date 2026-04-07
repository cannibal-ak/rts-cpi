import { useSession } from '../context/SessionContext';
import { UserRole, ModuleCode, Capability } from '../types';

export function useAccess() {
  const { hasRole, hasModule, hasCapability, hasAccess } = useSession();
  return { hasRole, hasModule, hasCapability, hasAccess };
}
