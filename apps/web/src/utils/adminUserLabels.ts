/**
 * Tenant and role labels shared by the admin user pages (Password Management,
 * Login Activity), so both tables read identically.
 */
import { getTenantDisplayName } from './tenantConfig';

// Slug for the RTS platform tenant — labelled "Admin" on the admin pages
// ("Admin - RTS" in the tables) rather than its full org name. It is left out
// of the invite dropdown: invites only create airline/cruise subtenants.
export const PLATFORM_TENANT_SLUG = 'rts';

interface UserLabelFields {
  email: string;
  role: string;
  tenant_slug: string;
  tenant_name: string;
}

// Tenant name shown on the admin pages: tenantConfig's canonical org name,
// except the platform tenant, which reads as "Admin".
export function pageTenantName(slug: string, fallback: string): string {
  if (slug.toLowerCase() === PLATFORM_TENANT_SLUG) return 'Admin';
  return getTenantDisplayName(slug, fallback);
}

export function formatTenantCell(user: UserLabelFields): string {
  return `${pageTenantName(user.tenant_slug, user.tenant_name)} - ${user.tenant_slug.toUpperCase()}`;
}

// Display-only role-label overrides for the admin user tables.
// These do NOT change the stored role (still TENANT_ADMIN), the API response,
// or any RBAC check — they only relabel the chip text for a few specific
// accounts. Keyed on lowercased email; anything not listed falls through to
// the real role value (TENANT_ADMIN).
export const ROLE_LABEL_OVERRIDES: Record<string, string> = {
  'admin@rts.com': 'RTS_SuperAdmin',
  'skyair@airline.com': 'Demo_Admin',
  'da@airline.com': 'Demo_Admin',
};

export function displayRole(user: UserLabelFields): string {
  const override = ROLE_LABEL_OVERRIDES[user.email.toLowerCase()];
  if (override) return override;
  if (user.role === 'TENANT_USER') return 'Subtenant';
  return user.role || '—';
}

// Subtenant chips use the info color to read as a distinct, lower-privilege
// role; email-overridden chips and TENANT_ADMIN keep the neutral chip.
export function roleChipColor(user: UserLabelFields): 'info' | 'default' {
  if (ROLE_LABEL_OVERRIDES[user.email.toLowerCase()]) return 'default';
  return user.role === 'TENANT_USER' ? 'info' : 'default';
}
