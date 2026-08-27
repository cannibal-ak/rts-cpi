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

/**
 * interCaribbean (JY): a straight mirror of dashboard 1's live label_colors,
 * which are the ic_branded scheme slots in carrier order (read from dev
 * superset.db 2026-08-27) — JY itself wears the logo's ocean blue. Without
 * this entry the WinAir table would paint JY's host line in WinAir's
 * `JY: '#2A78D6'`, disagreeing with the embedded charts beside it. Fallbacks
 * avoid every hue in the known set (S6 already holds slate #64748B).
 */
const JY_CARRIERS: CarrierColorTable = {
  known: {
    JY: '#049CFC',
    BW: '#E4049C',
    WM: '#8CD404',
    '9Q': '#04049C',
    '5L': '#F59E0B',
    PY: '#06B6D4',
    DO: '#8B5CF6',
    S6: '#64748B',
  },
  fallbacks: ['#A05A2C', '#0F766E'],
};

/**
 * Precision Air (PW): a straight mirror of dashboard 3's live label_colors
 * (the precisionAir scheme, read from dev superset.db 2026-08-27) — PW itself
 * wears the scheme's forest green. Aur/Coa/Fli are legacy name-style carrier
 * codes that appear only in historical captures; Exp is the late addition
 * bound by scripts/superset/pw_dash3_exp_keys.py (slate, no green/gold
 * collision — same reasoning as DA's Exp fix). Fallbacks avoid every hue in
 * the known set.
 */
const PW_CARRIERS: CarrierColorTable = {
  known: {
    PW: '#3C5414',
    TC: '#5C8226',
    KQ: '#4A6B1C',
    UI: '#80A83A',
    YS: '#A8C44E',
    CQ: '#C49714',
    Aur: '#FBC31C',
    Coa: '#6E9930',
    Fli: '#E0AD18',
    Exp: '#64748B',
  },
  fallbacks: ['#0F766E', '#7C3AED'],
};

/** Tenants with their own carrier tables. Absent tenants get WinAir's. */
const CARRIERS_BY_TENANT: Record<string, CarrierColorTable> = {
  '5l': LIAT_CARRIERS,
  jy: JY_CARRIERS,
  pw: PW_CARRIERS,
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
