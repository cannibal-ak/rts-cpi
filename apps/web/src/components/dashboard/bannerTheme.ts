/**
 * Palette for the dashboard filter banner (WinAir today).
 *
 * A fixed dark surface rather than a theme-derived one, so it reads identically
 * in light and dark mode. Lives here, one level above winair/, because the
 * shared DateFilterToggle also needs it for its on-dark branch.
 */

/** Filter zone — WinAir brand teal. */
export const BANNER_BG = '#005973';
/** Header strip — one step darker, so the date + actions read as their own zone. */
export const BANNER_HEADER_BG = '#00485e';
/** Divider / edge line on the banner. */
export const HAIRLINE = 'rgba(255,255,255,0.14)';

// ── Controls on the banner ─────────────────────────────────
// Two states: idle, and holding a selection. The active state is brighter on
// both fill and border so applied filters are scannable without reading them.
export const FIELD_BG = 'rgba(255,255,255,0.06)';
export const FIELD_BG_ACTIVE = 'rgba(255,255,255,0.16)';
export const FIELD_LINE = 'rgba(255,255,255,0.22)';
export const FIELD_LINE_ACTIVE = 'rgba(255,255,255,0.55)';

/** Field labels and other supporting text on the banner. */
export const LABEL_INK = 'rgba(255,255,255,0.62)';
/** Icons and placeholder text. */
export const MUTED_INK = 'rgba(255,255,255,0.7)';
