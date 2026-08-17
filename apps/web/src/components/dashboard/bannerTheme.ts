/**
 * Palette for the dashboard filter banner (WinAir today).
 *
 * A fixed dark surface rather than a theme-derived one, so it reads identically
 * in light and dark mode. Lives here, one level above winair/, because the
 * shared DateFilterToggle also needs it for its on-dark branch.
 */

/** Filter zone — WinAir brand red, sampled from the WinAir logo. */
export const BANNER_BG = '#CD1F25';
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
// so the same alpha reads weaker on it — these sit where 0.62/0.7 sat on teal.
/** Field labels and other supporting text on the banner. */
export const LABEL_INK = 'rgba(255,255,255,0.78)';
/** Icons and placeholder text. */
export const MUTED_INK = 'rgba(255,255,255,0.85)';
