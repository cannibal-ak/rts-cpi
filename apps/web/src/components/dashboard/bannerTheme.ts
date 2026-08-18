/**
 * Palette for the dashboard chrome above the embed (WinAir today).
 *
 * Both cards — the tab row and the filter card — sit on one light teal grey
 * surface: a calm ground for controls, which are read and operated rather
 * than looked at. WinAir red survives as an accent on that ground (Apply, and
 * the brand chrome elsewhere in the app), not as a surface of its own.
 *
 * It is a fixed surface rather than a theme-derived one, so it reads
 * identically in light and dark mode. This lives one level above winair/
 * because shared dashboard chrome (CapDateChip's accent, DashboardViewerPage's
 * WM branches) imports it without reaching into a tenant directory.
 */

import { lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/** WinAir brand red, sampled from the WinAir logo. */
export const BANNER_BG = '#CD1F25';

/**
 * Mode-aware brand ink for WinAir chrome OUTSIDE the fixed surfaces (sidebar
 * rows, spinners, chart controls): flat red on light surfaces, lightened on
 * dark paper where flat #CD1F25 only reaches ~2.9:1. Usable directly as an
 * sx color value or called with a theme.
 */
export const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? lighten(BANNER_BG, 0.3) : BANNER_BG;
/** The pressed state of red chrome — one step darker than brand. */
export const BANNER_HEADER_BG = '#A5181D';

// ── The LIGHT dashboard chrome ─────────────────────────────────
// Teal grey rather than a neutral grey, so the chrome reads as a chosen
// colour rather than an unstyled panel; the ink is a teal-leaning slate for
// the same reason. FILTER_* is the whole vocabulary for both cards — the tab
// row and the filter card share it so a pill and a field say the same thing
// about being idle or holding a selection.
//
// Contrast against FILTER_BG, measured: ink 10.2:1, labels 5.9:1, muted 4.5:1
// on the white fields it is used inside. Field and pill borders reach 3.1:1
// against their own fill, which is what identifies the control — the fill
// difference between a white field and this surface is only 1.3:1 on its own.

/** The surface both cards sit on. */
export const FILTER_BG = '#D9E5E6';
/** Card edge — the surface alone is too close to a white page to bound it. */
export const FILTER_BORDER = 'rgba(30,52,56,0.13)';
/** Primary text: the "Filters" title, selected values, active labels. */
export const FILTER_INK = '#1E3438';
/** Field labels and other supporting text. */
export const FILTER_LABEL_INK = '#40585C';
/** Icons, placeholders, and idle readouts. */
export const FILTER_MUTED_INK = '#5C7478';
/**
 * Teal accent for anything chosen — the selected tab pill, active field
 * borders, value chips, the "+N" pill, the active-count chip, the range
 * sliders. Red is NOT used for these: on this surface it would read as an
 * error, and it is reserved for Apply, the one committing action in the card.
 */
export const FILTER_ACCENT = '#2F6E73';
/** Selected-value chips inside a field. */
export const FILTER_CHIP_BG = 'rgba(47,110,115,0.14)';
/** Fill for fields and idle tab pills. One colour for both states — the
 *  border and the accent carry idle vs chosen. */
export const FILTER_FIELD_BG = '#ffffff';
export const FILTER_FIELD_LINE = 'rgba(30,52,56,0.45)';
/** Disabled Apply / Clear, and the hover wash behind Clear. */
export const FILTER_DISABLED_BG = 'rgba(30,52,56,0.10)';
export const FILTER_DISABLED_INK = 'rgba(30,52,56,0.38)';
export const FILTER_HOVER_BG = 'rgba(30,52,56,0.07)';
/** Loading skeletons — the field block and the label line above it. */
export const FILTER_SKELETON = 'rgba(30,52,56,0.11)';
export const FILTER_SKELETON_TEXT = 'rgba(30,52,56,0.08)';
/** "Filters unavailable", and the tab row's degraded-nav warning — deep red,
 *  which the pale amber for red surfaces replaced and which works again now
 *  the ground is light. The tint is for the Alert that carries the warning;
 *  the ink alone is 6:1 on it. */
export const FILTER_ERROR_INK = '#9A2A22';
export const FILTER_ERROR_BG = 'rgba(154,42,34,0.09)';
/** Unfilled part of a range slider. */
export const FILTER_SLIDER_RAIL = 'rgba(30,52,56,0.28)';
