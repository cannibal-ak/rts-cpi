/**
 * Palette for the DreamAir dashboard chrome — the sibling of bannerTheme.ts.
 *
 * Same structure, same token names, same alpha values; only the hues differ.
 * bannerTheme.ts is deliberately NOT edited: WinAir imports it directly and is
 * live on production, so the two tenants have to be able to move apart.
 *
 * Anchored on the DreamAir logo azure #1268E3, with an orchid chrome accent so
 * the filter card reads as a chosen surface rather than an unstyled panel — the
 * same reasoning behind WinAir's teal grey, in DreamAir's hues.
 *
 * Every value here meets or beats its WinAir counterpart on contrast. Measured
 * against FILTER_BG: ink 12.91:1 (WinAir 10.17), labels 8.03:1 (5.89), muted
 * 4.60:1 (3.86), accent 4.95:1 (4.53). Full derivation and the CVD/contrast
 * validator runs are in docs/dreamair-palette.md — do not change a hex here
 * without re-running it and updating that document.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** DreamAir brand azure, sampled from the logo. */
export const BANNER_BG = '#1268E3';

/**
 * Mode-aware brand ink for chrome OUTSIDE the fixed surfaces (sidebar rows,
 * spinners, chart controls): flat azure on light surfaces, lightened on dark
 * paper. Mirrors WinAir's brandInk contract exactly.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** The pressed state of azure chrome — one step darker than brand. */
export const BANNER_HEADER_BG = '#0D4FB5';

// ── The LIGHT dashboard chrome ─────────────────────────────────
// Lilac grey rather than a neutral grey, and an orchid accent rather than the
// brand azure: on an azure-branded page an azure accent would not separate the
// chosen state from the brand itself. Azure stays for Apply, the one committing
// action in the card.

/** The surface both cards sit on. */
export const FILTER_BG = '#E7E3F3';
/** Card edge — the surface alone is too close to a white page to bound it. */
export const FILTER_BORDER = 'rgba(34,27,61,0.13)';
/** Primary text: the "Filters" title, selected values, active labels. */
export const FILTER_INK = '#221B3D';
/** Field labels and other supporting text. */
export const FILTER_LABEL_INK = '#463A6B';
/** Icons, placeholders, and idle readouts. */
export const FILTER_MUTED_INK = '#6A5F8C';
/**
 * Orchid accent for anything chosen — the selected tab pill, active field
 * borders, value chips, the "+N" pill, the active-count chip, the range
 * sliders. It is a UI accent only and never becomes a chart series colour;
 * the orchid that does appear in charts is the brighter #9B4FD8.
 */
export const FILTER_ACCENT = '#7A45B8';
/** Selected-value chips inside a field. */
export const FILTER_CHIP_BG = 'rgba(122,69,184,0.14)';
/** Fill for fields and idle tab pills. One colour for both states — the
 *  border and the accent carry idle vs chosen. */
export const FILTER_FIELD_BG = '#ffffff';
export const FILTER_FIELD_LINE = 'rgba(34,27,61,0.45)';
/** Disabled Apply / Clear, and the hover wash behind Clear. */
export const FILTER_DISABLED_BG = 'rgba(34,27,61,0.10)';
export const FILTER_DISABLED_INK = 'rgba(34,27,61,0.38)';
export const FILTER_HOVER_BG = 'rgba(34,27,61,0.07)';
/** Loading skeletons — the field block and the label line above it. */
export const FILTER_SKELETON = 'rgba(34,27,61,0.11)';
export const FILTER_SKELETON_TEXT = 'rgba(34,27,61,0.08)';
/** "Filters unavailable", and the tab row's degraded-nav warning. Deep red,
 *  the same semantic value WinAir uses — error is not a brand colour, and on
 *  DreamAir it does not collide with the brand at all. 6.11:1 on FILTER_BG. */
export const FILTER_ERROR_INK = '#9A2A22';
export const FILTER_ERROR_BG = 'rgba(154,42,34,0.09)';
/** Unfilled part of a range slider. */
export const FILTER_SLIDER_RAIL = 'rgba(34,27,61,0.28)';
