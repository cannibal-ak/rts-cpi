/**
 * Palette for the Precision Air (PW) dashboard chrome — the fifth sibling
 * of bannerTheme.ts (WinAir), dreamairTheme.ts, liatTheme.ts and jyTheme.ts.
 *
 * Same structure, same token names, same alpha values; only the hues differ.
 * No sibling is edited: all are live, and the tenants have to be able to
 * move apart.
 *
 * The chrome speaks the brand's own forest green and gold. GREEN — the
 * dashboard sheet's own header gradient green #2B5329 (dashboard 3 css) —
 * is the BRAND and the committing action (sidebar active items, Apply,
 * spinners, brand marks). DARK GOLD #7A6000 — the brand gold #FBC31C
 * darkened until it reads on the card — is everything CHOSEN (active field
 * borders, value chips, the "+N" pill, the sliders). The card surface is a
 * green tint of the brand green. Scope chrome aliases the brand, as on
 * WinAir, DreamAir and JY; only Liat splits scope from brand. The raw brand
 * gold #FBC31C itself only reaches 1.62:1 on white — unusable as ink — and
 * the naive darkening #8A6D00 still FAILS the 4.53 accent floor at 4.18:1
 * on the surface, so the accent is taken further down to #7A6000.
 *
 * Brand and accent separate by hue (dark muted green fill vs dark gold
 * borders/chips), the axis WinAir's teal-vs-red walks; there is no
 * lightness-only trade-off here as on JY's two blues.
 *
 * Contrast, measured: white on brand green 8.85:1, white on pressed 12.07:1,
 * brand green on the chrome surface 7.53:1; card tokens on FILTER_BG — ink
 * 12.12:1, labels 8.35:1, muted 5.35:1, accent 5.10:1 (6.00:1 on the white
 * fields, and white on the accent itself 6.00:1), error 6.55:1 — every
 * value clears the WinAir floor (10.17 / 5.89 / 3.86 / 4.53 / 6.11). Full
 * derivation is in docs/pw-palette.md — do not change a hex here without
 * re-measuring and updating that document.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** Precision Air brand green — the PW dashboard sheet's header gradient green. */
export const BANNER_BG = '#2B5329';

/**
 * Mode-aware brand ink for chrome OUTSIDE the fixed surfaces (sidebar rows,
 * spinners, chart controls): flat brand green on light surfaces, lightened on
 * dark paper (flat green is thin there — the same reason WinAir lightens).
 * Mirrors the WinAir/DreamAir/Liat/JY brandInk contract exactly.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** The pressed state of green chrome — one step darker than brand. */
export const BANNER_HEADER_BG = '#1E3D1D';

/**
 * The colour of "where you are" chrome — the selected section pill in the
 * tab row and the Latest data / Cap date scope chips. For PW this is the
 * brand green itself, the WinAir/DreamAir/JY pattern (only Liat paints scope
 * in a second hue): the tokens are aliases, not new hexes.
 */
export const SCOPE_ACCENT = BANNER_BG;
/** Its hover/pressed step. */
export const SCOPE_ACCENT_PRESSED = BANNER_HEADER_BG;
/** Mode-aware ink form of SCOPE_ACCENT — for PW simply brandInk. */
export const scopeInk = brandInk;

// ── The LIGHT dashboard chrome ─────────────────────────────────
// A green tint of the brand green as the surface, and the brand gold
// darkened to read as the chosen-state accent: on a green-branded page the
// chosen state must be visibly a different hue than the brand, or selection
// would read as brand. Green appears on the card only for Apply, the one
// committing action.

/** The surface both cards sit on. */
export const FILTER_BG = '#E4F0E2';
/** Card edge — the surface alone is too close to a white page to bound it. */
export const FILTER_BORDER = 'rgba(23,48,26,0.13)';
/** Primary text: the "Filters" title, selected values, active labels. */
export const FILTER_INK = '#17301A';
/** Field labels and other supporting text. */
export const FILTER_LABEL_INK = '#2F4A2E';
/** Icons, placeholders, and idle readouts. */
export const FILTER_MUTED_INK = '#4E6650';
/**
 * Dark-gold accent for anything chosen in the filter card — active field
 * borders, value chips, the "+N" pill, the active-count chip, the range
 * sliders. The brand gold #FBC31C itself only reaches 1.62:1 on white, so
 * it is darkened to read; the hue survives. 5.10:1 on FILTER_BG, 6.00:1 on
 * the white fields.
 */
export const FILTER_ACCENT = '#7A6000';
/** Selected-value chips inside a field. */
export const FILTER_CHIP_BG = 'rgba(122,96,0,0.14)';
/** Fill for fields and idle tab pills. One colour for both states — the
 *  border and the accent carry idle vs chosen. */
export const FILTER_FIELD_BG = '#ffffff';
export const FILTER_FIELD_LINE = 'rgba(23,48,26,0.45)';
/** Disabled Apply / Clear, and the hover wash behind Clear. */
export const FILTER_DISABLED_BG = 'rgba(23,48,26,0.10)';
export const FILTER_DISABLED_INK = 'rgba(23,48,26,0.38)';
export const FILTER_HOVER_BG = 'rgba(23,48,26,0.07)';
/** Loading skeletons — the field block and the label line above it. */
export const FILTER_SKELETON = 'rgba(23,48,26,0.11)';
export const FILTER_SKELETON_TEXT = 'rgba(23,48,26,0.08)';
/** "Filters unavailable", and the tab row's degraded-nav warning. The deep
 *  red #9A2A22, same as every sibling — on a green-branded page it cannot be
 *  mistaken for brand, and it stays clear of the delta/status reds the grid
 *  pages use semantically. 6.55:1 on FILTER_BG. */
export const FILTER_ERROR_INK = '#9A2A22';
export const FILTER_ERROR_BG = 'rgba(154,42,34,0.09)';
/** Unfilled part of a range slider. */
export const FILTER_SLIDER_RAIL = 'rgba(23,48,26,0.28)';
