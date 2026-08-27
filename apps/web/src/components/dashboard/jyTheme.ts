/**
 * Palette for the interCaribbean (JY) dashboard chrome — the fourth sibling
 * of bannerTheme.ts (WinAir), dreamairTheme.ts and liatTheme.ts.
 *
 * Same structure, same token names, same alpha values; only the hues differ.
 * No sibling is edited: all are live, and the tenants have to be able to
 * move apart.
 *
 * The chrome speaks the blues the brand already writes with. NAVY — the
 * dashboard sheet's own header gradient start #1E4A7A (dashboard 1 css,
 * `--jy-bg-header`), a close neighbour of the RTS platform navy #1a5276 —
 * is the BRAND and the committing action (sidebar active items, Apply,
 * spinners, brand marks). CERULEAN #0369A1 — the logo's ocean blue #049CFC
 * (ic_branded slot 1, the JY chart series) darkened until it reads on the
 * card — is everything CHOSEN (active field borders, value chips, the "+N"
 * pill, the sliders). The card surface is a sky tint of the same ocean blue.
 * Scope chrome aliases the brand, as on WinAir and DreamAir; only Liat
 * splits scope from brand. The logo's magenta #E4049C stays out of the
 * chrome entirely (it is carrier BW's series colour on JY charts); a
 * magenta-accent variant is recorded in docs/jy-palette.md as the fallback
 * if the two blues read as one in review.
 *
 * Brand and accent are both blues — they separate by lightness and
 * saturation (dark muted navy fill vs bright cerulean borders/chips), the
 * axis WinAir's teal-vs-red walks by hue. This is the known trade-off of
 * keeping the chrome inside the logo's blue system.
 *
 * Contrast, measured: white on brand navy 9.07:1, white on pressed 11.59:1,
 * brand navy on the chrome surface 7.57:1; card tokens on FILTER_BG — ink
 * 12.29:1, labels 7.69:1, muted 4.79:1, accent 4.95:1 (5.93:1 on the white
 * fields, and white on the accent itself 5.93:1), error 6.42:1 — every
 * value clears the WinAir floor (10.17 / 5.89 / 3.86 / 4.53 / 6.11). Full
 * derivation is in docs/jy-palette.md — do not change a hex here without
 * re-measuring and updating that document.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** interCaribbean brand navy — the JY dashboard sheet's header gradient start. */
export const BANNER_BG = '#1E4A7A';

/**
 * Mode-aware brand ink for chrome OUTSIDE the fixed surfaces (sidebar rows,
 * spinners, chart controls): flat brand navy on light surfaces, lightened on
 * dark paper (flat navy is thin there — the same reason WinAir lightens).
 * Mirrors the WinAir/DreamAir/Liat brandInk contract exactly.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** The pressed state of navy chrome — one step darker than brand. */
export const BANNER_HEADER_BG = '#163A61';

/**
 * The colour of "where you are" chrome — the selected section pill in the
 * tab row and the Latest data / Cap date scope chips. For JY this is the
 * brand navy itself, the WinAir/DreamAir pattern (only Liat paints scope in
 * a second hue): the tokens are aliases, not new hexes.
 */
export const SCOPE_ACCENT = BANNER_BG;
/** Its hover/pressed step. */
export const SCOPE_ACCENT_PRESSED = BANNER_HEADER_BG;
/** Mode-aware ink form of SCOPE_ACCENT — for JY simply brandInk. */
export const scopeInk = brandInk;

// ── The LIGHT dashboard chrome ─────────────────────────────────
// A sky tint of the logo's ocean blue as the surface, and that ocean blue
// darkened to cerulean as the chosen-state accent: on a navy-branded page
// the chosen state must be visibly brighter than the brand, or selection
// would read as brand. Navy appears on the card only for Apply, the one
// committing action.

/** The surface both cards sit on. */
export const FILTER_BG = '#DCEDF9';
/** Card edge — the surface alone is too close to a white page to bound it. */
export const FILTER_BORDER = 'rgba(15,42,64,0.13)';
/** Primary text: the "Filters" title, selected values, active labels. */
export const FILTER_INK = '#0F2A40';
/** Field labels and other supporting text. */
export const FILTER_LABEL_INK = '#2C4A66';
/** Icons, placeholders, and idle readouts. */
export const FILTER_MUTED_INK = '#4E6980';
/**
 * Cerulean accent for anything chosen in the filter card — active field
 * borders, value chips, the "+N" pill, the active-count chip, the range
 * sliders. The logo's ocean blue #049CFC itself only reaches 2.45:1 on this
 * surface, so it is darkened to read; the hue survives. 4.95:1 on
 * FILTER_BG, 5.93:1 on the white fields.
 */
export const FILTER_ACCENT = '#0369A1';
/** Selected-value chips inside a field. */
export const FILTER_CHIP_BG = 'rgba(3,105,161,0.14)';
/** Fill for fields and idle tab pills. One colour for both states — the
 *  border and the accent carry idle vs chosen. */
export const FILTER_FIELD_BG = '#ffffff';
export const FILTER_FIELD_LINE = 'rgba(15,42,64,0.45)';
/** Disabled Apply / Clear, and the hover wash behind Clear. */
export const FILTER_DISABLED_BG = 'rgba(15,42,64,0.10)';
export const FILTER_DISABLED_INK = 'rgba(15,42,64,0.38)';
export const FILTER_HOVER_BG = 'rgba(15,42,64,0.07)';
/** Loading skeletons — the field block and the label line above it. */
export const FILTER_SKELETON = 'rgba(15,42,64,0.11)';
export const FILTER_SKELETON_TEXT = 'rgba(15,42,64,0.08)';
/** "Filters unavailable", and the tab row's degraded-nav warning. The deep
 *  red #9A2A22, same as every sibling — on a blue-branded page it cannot be
 *  mistaken for brand, and it stays clear of the delta/status reds the grid
 *  pages use semantically. 6.42:1 on FILTER_BG. */
export const FILTER_ERROR_INK = '#9A2A22';
export const FILTER_ERROR_BG = 'rgba(154,42,34,0.09)';
/** Unfilled part of a range slider. */
export const FILTER_SLIDER_RAIL = 'rgba(15,42,64,0.28)';
