import { NavItem } from '../types';

export const navigationItems: NavItem[] = [
  {
    label: 'Home',
    path: '/',
    icon: 'Home',
    category: 'Overview',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
  },

  // ── Per-tenant CPI modules ───────────────────
  {
    label: 'Airline CPI \u2013 JY',
    path: '/cpi/airline/jy',
    icon: 'Flight',
    requiredModules: ['airline_jy'],
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Modules',
    hideForSuperAdmin: true,
  },
  {
    label: 'Airline CPI \u2013 PW',
    path: '/cpi/airline/pw',
    icon: 'Flight',
    requiredModules: ['airline_pw'],
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Modules',
    hideForSuperAdmin: true,
  },
  {
    label: 'Cruise/Ferry CPI \u2013 FJL',
    path: '/cpi/cruise/fjl',
    icon: 'DirectionsBoat',
    requiredModules: ['cfl_fjl'],
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Modules',
    hideForSuperAdmin: true,
  },

  // ── Analytics ─────────────────────────────
  {
    label: 'Dashboards',
    path: '/dashboards',
    icon: 'Dashboard',
    category: 'Analytics',
    hideForSuperAdmin: true,
    requiredRoles: ['TENANT_ADMIN'],
  },

  // ── Admin (Skywave platform admins only) ─────────────
  {
    label: 'SFTP Connections',
    path: '/admin/sftp-connections',
    icon: 'Storage',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Admin',
  },
  {
    label: 'Ingestion Schedules',
    path: '/admin/ingestion-schedules',
    icon: 'Schedule',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Admin',
  },
  {
    label: 'Ingestion Runs',
    path: '/admin/ingestion-runs',
    icon: 'History',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Admin',
  },
  {
    label: 'Password Management',
    path: '/admin/password-management',
    icon: 'VpnKey',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Admin',
  },
];
