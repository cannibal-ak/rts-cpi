/**
 * Palette for the Liat Air dashboard chrome — the third sibling of
 * bannerTheme.ts (WinAir) and dreamairTheme.ts.
 *
 * Same structure, same token names, same alpha values; only the hues differ.
 * Neither sibling is edited: both are live, and the tenants have to be able
 * to move apart.
 *
 * Anchored on the Liat Air logo's ocean blue #1B5FA8 (the swoosh), with a deep
 * gold chrome accent drawn from the logo's gold — so the filter card reads as
 * a chosen surface rather than an unstyled panel, the same reasoning behind
 * WinAir's teal and DreamAir's orchid, in Liat's hues. On a blue-branded page
 * a blue accent would not separate the chosen state from the brand itself;
 * gold does, and it is Liat's own second colour.
 *
 * Contrast, measured against FILTER_BG: ink 12.94:1, labels 7.69:1, muted
 * 4.92:1, accent 4.78:1, error 6.52:1 — every value clears the WinAir floor
 * (10.17 / 5.89 / 3.86 / 4.53 / 6.11). Full derivation and the CVD/contrast
 * validator runs are in docs/liat-palette.md — do not change a hex here
 * without re-running it and updating that document.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** Liat Air brand ocean blue, from the logo swoosh. */
export const BANNER_BG = '#1B5FA8';

/**
 * Mode-aware brand ink for chrome OUTSIDE the fixed surfaces (sidebar rows,
 * spinners, chart controls): flat ocean blue on light surfaces, lightened on
 * dark paper. Mirrors the WinAir/DreamAir brandInk contract exactly.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** The pressed state of ocean-blue chrome — one step darker than brand. */
export const BANNER_HEADER_BG = '#134878';

// ── The LIGHT dashboard chrome ─────────────────────────────────
// A cool blue-grey rather than a neutral grey, and a deep gold accent rather
// than the brand blue: blue stays for Apply, the one committing action in the
// card, and for brand marks.

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
/** "Filters unavailable", and the tab row's degraded-nav warning. Deep red,
 *  the same semantic value the siblings use — error is not a brand colour,
 *  and on Liat it does not collide with the brand at all. 6.52:1 on
 *  FILTER_BG. Distinct from the logo's red A-mark (#D64541 family), which is
 *  brand art, not a status colour. */
export const FILTER_ERROR_INK = '#9A2A22';
export const FILTER_ERROR_BG = 'rgba(154,42,34,0.09)';
/** Unfilled part of a range slider. */
export const FILTER_SLIDER_RAIL = 'rgba(18,38,63,0.28)';
