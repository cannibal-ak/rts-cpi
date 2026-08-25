/**
 * Which carrier-identity colours the native price charts use, per tenant.
 *
 * priceChartTheme.ts was written when WinAir was the only branded tenant, so
 * its KNOWN_AIRLINE_COLORS map is WinAir's Palette A — including
 * `'5L': '#1BAF7A'`, which is *Liat as WinAir's competitor*. On Liat's own
 * dashboard the host carrier must be the Liat brand red, so the table is now
 * looked up per tenant at render time, exactly the way tenantChrome.ts made
 * the chrome tokens tenant-pluggable.
 *
 * The default is the WinAir table, so WM (and DreamAir, which has no entry
 * yet) render byte-identically to before this file existed. DreamAir's
 * native panel currently hands its carriers WinAir fallbacks — a known,
 * pre-existing gap; when it is fixed, its table goes here, mirrored from
 * `CARRIER_COLORS` in scripts/superset_provision_dreamair.py.
 *
 * THE TABLE MUST AGREE WITH THE TENANT'S SUPERSET label_colors — the native
 * chart sits beside the embedded dashboard, and a carrier that changes
 * colour between the two panes reads as two different airlines. Liat's
 * competitor entries are therefore added only after
 * scripts/superset/liat_dash8_carrier_keys.py assigns slots from the
 * ingested data (docs/liat-palette.md §2): copy its printed assignment here.
 */
import { useMemo } from 'react';
import { useSession } from '../../context/SessionContext';
import { tenantKeyFromModules } from './tenantChrome';
import { WINAIR_CARRIER_TABLE } from './winair/priceChartTheme';
import type { CarrierColorTable } from './winair/priceChartTheme';

/**
 * Liat Air: 5L is always the brand red (liatTheme BANNER_BG). Competitor
 * slots were assigned by liat_dash8_carrier_keys.py on 2026-08-25 from the
 * first committed ingest, in descending row volume (docs/liat-palette.md
 * section 2 records the volumes) — so the three busiest carriers wear the
 * logo's own colours. This table and the dashboard's label_colors are the
 * same assignment in two mirrors; change them together or not at all.
 */
const LIAT_CARRIERS: CarrierColorTable = {
  known: {
    '5L': '#D02127',
    BW: '#0375B4',
    JY: '#C08A00',
    WM: '#275AA1',
    S6: '#2E7D32',
    PY: '#D6208F',
  },
  fallbacks: ['#64748B', '#0F766E'],
};

/** Tenants with their own carrier tables. Absent tenants get WinAir's. */
const CARRIERS_BY_TENANT: Record<string, CarrierColorTable> = {
  '5l': LIAT_CARRIERS,
};

/** The carrier table for a tenant slug; WinAir's when the tenant has none. */
export function getCarrierColorTable(tenantKey: string | undefined | null): CarrierColorTable {
  if (!tenantKey) return WINAIR_CARRIER_TABLE;
  return CARRIERS_BY_TENANT[tenantKey.toLowerCase()] ?? WINAIR_CARRIER_TABLE;
}

/** The current session tenant's carrier table. */
export function useCarrierColorTable(): CarrierColorTable {
  const { session } = useSession();
  const key = tenantKeyFromModules(session.enabled_modules);
  return useMemo(() => getCarrierColorTable(key), [key]);
}
