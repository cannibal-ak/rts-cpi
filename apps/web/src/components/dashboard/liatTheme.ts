/**
 * Palette for the Liat Air dashboard chrome — the third sibling of
 * bannerTheme.ts (WinAir) and dreamairTheme.ts.
 *
 * Same structure, same token names, same alpha values; only the hues differ.
 * Neither sibling is edited: both are live, and the tenants have to be able
 * to move apart.
 *
 * The chrome speaks the two colours the logo writes with (client direction
 * 2026-08-26, superseding the gold chosen-state of the 2026-08-25 revision):
 * RED — the A-mark gradient #E32228→#BC2026 at its midpoint #D02127 — is the
 * BRAND and the committing action (sidebar active items, Apply, spinners,
 * brand marks); BLUE — the wordmark #275AA1 — is everything CHOSEN or SCOPED
 * (the selected tab pill, the date chips, active filter borders, value chips,
 * the sliders), with the same blue family seeding the light blue-grey card
 * surface. Gold no longer appears in the chrome at all; it survives only in
 * charts (#C08A00) and the sold-out marker amber — see docs/liat-palette.md
 * §0.
 *
 * Contrast, measured: white on brand red 5.35:1, white on pressed 8.10:1,
 * brand red on the chrome surface 4.53:1; white on the blue scope accent
 * 6.86:1, white on its pressed step 10.50:1; card tokens on FILTER_BG — ink
 * 12.94:1, labels 7.69:1, muted 4.92:1, accent 5.81:1, error 6.52:1 — every
 * value clears the WinAir floor (10.17 / 5.89 / 3.86 / 4.53 / 6.11). Full
 * derivation is in docs/liat-palette.md — do not change a hex here without
 * re-measuring and updating that document.
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

/**
 * The colour of "where you are" chrome — the selected section pill in the
 * tab row and the Latest data / Cap date scope chips. On the siblings this
 * IS the brand (their tokens alias BANNER_BG); Liat splits it out per the
 * 2026-08-26 red+blue direction: scope reads in the logo's wordmark blue,
 * and red keeps only brand marks and committing actions. The hex is also
 * Palette A slot 4 (the WM carrier line) — safe for the same scope reason
 * the brand red is: chrome is never a chart series, and Apply already
 * shares red with the 5L line below it. White text 6.86:1.
 */
export const SCOPE_ACCENT = '#275AA1';
/**
 * Its hover/pressed step. Not the swoosh gradient's dark end #245293 — that
 * is too close to SCOPE_ACCENT to read as a state change; this is the
 * wordmark blue darkened until the step shows. White text 10.50:1.
 */
export const SCOPE_ACCENT_PRESSED = '#1B3F72';

// ── The LIGHT dashboard chrome ─────────────────────────────────
// A cool blue-grey surface (the logo's blues) and the wordmark blue as the
// chosen-state accent: on a red-branded page the chosen state must not be
// red, or selection would read as brand. Red appears on the card only for
// Apply, the one committing action.

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
 * Wordmark-blue accent for anything chosen in the filter card — active field
 * borders, value chips, the "+N" pill, the active-count chip, the range
 * sliders. Same hex as SCOPE_ACCENT and the same scope note applies (the WM
 * carrier line shares it; chrome and chart series never meet in one plot).
 * 5.81:1 on FILTER_BG, 6.86:1 on the white fields — both above the gold it
 * replaced (4.78:1).
 */
export const FILTER_ACCENT = '#275AA1';
/** Selected-value chips inside a field. */
export const FILTER_CHIP_BG = 'rgba(39,90,161,0.14)';
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
