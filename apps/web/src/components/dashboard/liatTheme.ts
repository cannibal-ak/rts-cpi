/**
 * Palette for the Liat Air dashboard chrome — the third sibling of
 * bannerTheme.ts (WinAir) and dreamairTheme.ts.
 *
 * Same structure, same token names, same alpha values; only the hues differ.
 * Neither sibling is edited: both are live, and the tenants have to be able
 * to move apart.
 *
 * Anchored on the Liat Air logo's red — the A-mark gradient #E32228→#BC2026,
 * taken at its midpoint #D02127 — with the logo's remaining colours carrying
 * the rest of the chrome: the filter card sits on a light blue-grey drawn
 * from the swoosh/wordmark blues, and the chosen-state accent is a text-safe
 * step of the logo gold. Red is the BRAND ink (sidebar active items, Apply,
 * spinners, brand marks); gold is the CHOSEN state; blue is the SURFACE
 * family. Three logo families, one job each — see docs/liat-palette.md §0.
 *
 * Contrast, measured: white on brand red 5.35:1, white on pressed 8.10:1,
 * brand red on the chrome surface 4.53:1; card tokens on FILTER_BG — ink
 * 12.94:1, labels 7.69:1, muted 4.92:1, accent 4.78:1, error 6.52:1 — every
 * value clears the WinAir floor (10.17 / 5.89 / 3.86 / 4.53 / 6.11). Full
 * derivation and the CVD/contrast validator runs are in
 * docs/liat-palette.md — do not change a hex here without re-running it and
 * updating that document.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** Liat Air brand red — the A-mark gradient midpoint. */
export const BANNER_BG = '#D02127';

/**
 * Mode-aware brand ink for chrome OUTSIDE the fixed surfaces (sidebar rows,
 * spinners, chart controls): flat brand red on light surfaces, lightened on
 * dark paper (flat red is thin there — the same reason WinAir lightens).
 * Mirrors the WinAir/DreamAir brandInk contract exactly.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** The pressed state of red chrome — the gradient's dark end, one step on. */
export const BANNER_HEADER_BG = '#9C1B20';

// ── The LIGHT dashboard chrome ─────────────────────────────────
// A cool blue-grey surface (the logo's blues) and a deep gold accent (the
// logo's gold): on a red-branded page the chosen state must not be red, or
// selection would read as brand. Red appears on the card only for Apply,
// the one committing action.

/** The surface both cards sit on. */
export const FILTER_BG = '#E6EDF4';
/** Card edge — the surface alone is too close to a white page to bound it. */
export const FILTER_BORDER = 'rgba(18,38,63,0.13)';
/** Primary text: the "Filters" title, selected values, active labels. */
export const FILTER_INK = '#12263F';
/** Field labels and other supporting text. */
export const FILTER_LABEL_INK = '#2F4A6B';
/** Icons, placeholders, and idle readouts. */
export const FILTER_MUTED_INK = '#54677E';
/**
 * Deep gold accent for anything chosen — the selected tab pill, active field
 * borders, value chips, the "+N" pill, the active-count chip, the range
 * sliders. It is a UI accent only and never becomes a chart series colour;
 * the gold that does appear in charts is the brighter #C08A00.
 */
export const FILTER_ACCENT = '#8A5F00';
/** Selected-value chips inside a field. */
export const FILTER_CHIP_BG = 'rgba(138,95,0,0.14)';
/** Fill for fields and idle tab pills. One colour for both states — the
 *  border and the accent carry idle vs chosen. */
export const FILTER_FIELD_BG = '#ffffff';
export const FILTER_FIELD_LINE = 'rgba(18,38,63,0.45)';
/** Disabled Apply / Clear, and the hover wash behind Clear. */
export const FILTER_DISABLED_BG = 'rgba(18,38,63,0.10)';
export const FILTER_DISABLED_INK = 'rgba(18,38,63,0.38)';
export const FILTER_HOVER_BG = 'rgba(18,38,63,0.07)';
/** Loading skeletons — the field block and the label line above it. */
export const FILTER_SKELETON = 'rgba(18,38,63,0.11)';
export const FILTER_SKELETON_TEXT = 'rgba(18,38,63,0.08)';
/** "Filters unavailable", and the tab row's degraded-nav warning. The deep
 *  red #9A2A22, same as WinAir — and for the same reason now that the brand
 *  is red: brand red must never read as an error, and an error must never
 *  read as brand. 6.52:1 on FILTER_BG, and clearly darker than BANNER_BG. */
export const FILTER_ERROR_INK = '#9A2A22';
export const FILTER_ERROR_BG = 'rgba(154,42,34,0.09)';
/** Unfilled part of a range slider. */
export const FILTER_SLIDER_RAIL = 'rgba(18,38,63,0.28)';
