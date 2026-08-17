/**
 * Palette for the dashboard filter banner (WinAir today).
 *
 * A fixed dark surface rather than a theme-derived one, so it reads identically
 * in light and dark mode. Lives here, one level above winair/, because shared
 * dashboard chrome (CapDateChip's accent, DashboardViewerPage's WM branches)
 * imports it without reaching into a tenant directory.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** Filter zone — WinAir brand red, sampled from the WinAir logo. */
export const BANNER_BG = '#CD1F25';

/**
 * Mode-aware brand ink for WinAir chrome OUTSIDE the fixed banner (sidebar
 * rows, spinners, chart controls): flat red on light surfaces, lightened on
 * dark paper where flat #CD1F25 only reaches ~2.9:1. Usable directly as an
 * sx color value or called with a theme.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** Header strip — one step darker, so the date + actions read as their own zone. */
export const BANNER_HEADER_BG = '#A5181D';
/** Divider / edge line on the banner. */
export const HAIRLINE = 'rgba(255,255,255,0.14)';

// ── Controls on the banner ─────────────────────────────────
// Two states: idle, and holding a selection. The active state is brighter on
// both fill and border so applied filters are scannable without reading them.
export const FIELD_BG = 'rgba(255,255,255,0.06)';
export const FIELD_BG_ACTIVE = 'rgba(255,255,255,0.16)';
export const FIELD_LINE = 'rgba(255,255,255,0.22)';
export const FIELD_LINE_ACTIVE = 'rgba(255,255,255,0.55)';

// Ink alphas are tuned to the red surface: red is brighter than the old teal,
// so the same alpha reads weaker on it. 0.82/0.9 measure ~4.1:1 and ~4.6:1 on
// the red — the same contrast 0.62/0.7 delivered on the teal.
/** Field labels and other supporting text on the banner. */
export const LABEL_INK = 'rgba(255,255,255,0.82)';
/** Icons and placeholder text. */
export const MUTED_INK = 'rgba(255,255,255,0.9)';
