import { NavItem } from '../types';

export const navigationItems: NavItem[] = [
  {
    label: 'Home',
    path: '/',
    icon: 'Home',
    category: 'Overview',
    requiredRoles: ['TENANT_ADMIN'],
  },

  // ── Per-tenant CPI modules ───────────────────
  {
    label: 'Airline CPI \u2013 JY',
    path: '/cpi/airline/jy',
    icon: 'Flight',
    requiredModules: ['airline_jy'],
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Modules',
  },
  {
    label: 'Airline CPI \u2013 PW',
    path: '/cpi/airline/pw',
    icon: 'Flight',
    requiredModules: ['airline_pw'],
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Modules',
  },
  {
    label: 'Cruise/Ferry CPI \u2013 FJL',
    path: '/cpi/cruise/fjl',
    icon: 'DirectionsBoat',
    requiredModules: ['cfl_fjl'],
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Modules',
  },

  // ── Analytics & Data Ops ─────────────────────
  {
    label: 'Dashboards',
    path: '/dashboards',
    icon: 'Dashboard',
    category: 'Analytics',
    requiredRoles: ['TENANT_ADMIN'],
  },
  {
    label: 'Ingestion Jobs',
    path: '/ingestion',
    icon: 'CloudUpload',
    requiredRoles: ['TENANT_ADMIN'],
    category: 'Data Ops',
  },
];
