/**
 * Which tenant's dashboard chrome to paint with.
 *
 * WinAir was the only branded tenant, so its components imported the tokens
 * straight from bannerTheme.ts as module constants. DreamAir is a second one,
 * and a third is plausible, so the tokens are now looked up at render time
 * instead of bound at import time.
 *
 * The bundles are structurally identical by construction — TenantChrome is
 * derived from the WinAir module's shape, so adding a token to bannerTheme.ts
 * without adding it to dreamairTheme.ts is a compile error rather than a
 * DreamAir screen that silently renders a WinAir colour.
 *
 * Components consume this through `useTenantChrome()` and destructure the token
 * names they already used, so no usage site changed when this was introduced:
 *
 *     const { FILTER_BG, FILTER_ACCENT } = useTenantChrome();
 *
 * `getTenantChrome` is the non-hook form, for the few call sites outside a
 * component or where the tenant key is already in hand.
 */

import { useMemo } from 'react';
import { useSession } from '../../context/SessionContext';
import * as winair from './bannerTheme';
import * as dreamair from './dreamairTheme';
import * as liat from './liatTheme';

/**
 * The token bundle, with the hex literals widened to `string`.
 *
 * `typeof winair` on its own infers literal types (`'#CD1F25'`), which would
 * make dreamairTheme unassignable to it. Mapping over the keys keeps the shape
 * check — a token missing from either module is still a compile error — while
 * letting the two modules hold different values, which is the entire point.
 */
export type TenantChrome = {
  [K in keyof typeof winair]: (typeof winair)[K] extends string
    ? string
    : (typeof winair)[K];
};

/** WinAir red + teal grey. The default: an unbranded tenant gets no chrome. */
export const WINAIR_CHROME: TenantChrome = winair;
/** DreamAir azure + lilac grey. */
export const DREAMAIR_CHROME: TenantChrome = dreamair;
/** Liat Air brand red + blue grey, wordmark-blue chosen/scope accent. */
export const LIAT_CHROME: TenantChrome = liat;

/**
 * Tenant slugs that have their own chrome. A tenant absent from here is
 * unbranded and its callers fall back to the MUI theme, which is what
 * `isWmTenant ? BANNER_BG : undefined` used to express.
 */
const CHROME_BY_TENANT: Record<string, TenantChrome> = {
  wm: WINAIR_CHROME,
  da: DREAMAIR_CHROME,
  '5l': LIAT_CHROME,
};

/** The chrome for a tenant slug, or null if that tenant is unbranded. */
export function getTenantChrome(tenantKey: string | undefined | null): TenantChrome | null {
  if (!tenantKey) return null;
  return CHROME_BY_TENANT[tenantKey.toLowerCase()] ?? null;
}

/** True when the tenant has branded dashboard chrome at all. */
export function isBrandedTenant(tenantKey: string | undefined | null): boolean {
  return getTenantChrome(tenantKey) !== null;
}

/**
 * Tenant slug for the current session, derived the same way AppBar derives it:
 * a single enabled module identifies a tenant, anything else is the RTS
 * platform admin.
 */
export function tenantKeyFromModules(modules: readonly string[]): string {
  if (modules.length !== 1) return 'rts';
  const m = modules[0];
  return m.startsWith('airline_') ? m.slice('airline_'.length)
    : m.startsWith('cfl_') ? m.slice('cfl_'.length)
    : 'rts';
}

/**
 * The current tenant's chrome, or null when unbranded.
 *
 * Components that are only ever mounted for a branded tenant can assert with
 * `useTenantChrome() ?? WINAIR_CHROME`; the WinAir components do exactly that,
 * so their behaviour is unchanged for WinAir and correct for DreamAir.
 */
export function useTenantChrome(): TenantChrome | null {
  const { session } = useSession();
  const key = tenantKeyFromModules(session.enabled_modules);
  return useMemo(() => getTenantChrome(key), [key]);
}

/** As `useTenantChrome`, but never null — for components mounted only on a
 *  branded dashboard, where falling back to WinAir's tokens is the historical
 *  behaviour and safe. */
export function useBrandedChrome(): TenantChrome {
  return useTenantChrome() ?? WINAIR_CHROME;
}
