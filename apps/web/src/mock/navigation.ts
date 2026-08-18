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
    requiredRoles: ['TENANT_ADMIN', 'TENANT_USER'],
    category: 'Modules',
    hideForSuperAdmin: true,
  },
  {
    label: 'Airline CPI \u2013 PW',
    path: '/cpi/airline/pw',
    icon: 'Flight',
    requiredModules: ['airline_pw'],
    requiredRoles: ['TENANT_ADMIN', 'TENANT_USER'],
    category: 'Modules',
    hideForSuperAdmin: true,
  },
  {
    label: 'Airline CPI \u2013 SKY',
    path: '/cpi/airline/alt',
    icon: 'Flight',
    requiredModules: ['airline_alt'],
    requiredRoles: ['TENANT_ADMIN', 'TENANT_USER'],
    category: 'Modules',
    hideForSuperAdmin: true,
  },
  {
    label: 'Airline CPI Data',
    path: '/cpi/airline/wm',
    icon: 'Flight',
    requiredModules: ['airline_wm'],
    requiredRoles: ['TENANT_ADMIN', 'TENANT_USER'],
    category: 'Modules',
    hideForSuperAdmin: true,
    // The page's two tabs, surfaced in the menu. Children inherit the parent's
    // gating: they only render if the parent survived the access filter.
    children: [
      { label: 'Pricing', path: '/cpi/airline/wm?tab=pricing', icon: 'PriceChange' },
      { label: 'Velocity', path: '/cpi/airline/wm?tab=velocity', icon: 'Speed' },
    ],
  },
  {
    label: 'Cruise/Ferry CPI \u2013 FJL',
    path: '/cpi/cruise/fjl',
    icon: 'DirectionsBoat',
    requiredModules: ['cfl_fjl'],
    requiredRoles: ['TENANT_ADMIN', 'TENANT_USER'],
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
    requiredRoles: ['TENANT_ADMIN', 'TENANT_USER'],
  },

  // ── Admin (RTS platform admins only) ─────────────
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
    icon: 'PlayCircleFilled',
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

  // ── Platform Settings (peer of ADMIN; renders as its own section) ─
  {
    label: 'Email',
    path: '/admin/settings/email',
    icon: 'Email',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Settings',
  },

  // ── Data Ops (manual fallback alongside SFTP automation) ─────
  {
    label: 'Ingestion Jobs',
    path: '/ingestion',
    icon: 'AssignmentTurnedIn',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Data Ops',
  },
  {
    label: 'Upload Files',
    path: '/ingestion/upload',
    icon: 'CloudUpload',
    requiredRoles: ['TENANT_ADMIN'],
    requireSuperAdmin: true,
    category: 'Data Ops',
  },
];
