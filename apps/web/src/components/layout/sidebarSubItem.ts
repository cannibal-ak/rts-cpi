/**
 * Shared styling for the sidebar's panel rows.
 *
 * Two different places render second-level rows - the static children in
 * navigation.ts (WinAir's Pricing / Velocity) and the async chart list under
 * Dashboards - and they must read as the same level of hierarchy, so the
 * styles live here rather than being duplicated in both.
 *
 * Both factories take an optional tenant `accent` (WinAir's brand red today).
 * With it, the active-row treatment uses that color instead of the app navy;
 * without it, the output is unchanged for every other tenant.
 */
import { alpha, lighten } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/**
 * The navy #1a5276 primary is too dim against the dark-mode paper, so active
 * rows switch to the lighter brand stop there. A tenant accent gets the same
 * treatment via lighten() since it has no palette stops of its own.
 */
const brandInk = (accent?: string) => (theme: Theme) =>
  accent
    ? (theme.palette.mode === 'dark' ? lighten(accent, 0.3) : accent)
    : (theme.palette.mode === 'dark' ? theme.palette.primary.light : theme.palette.primary.main);

/**
 * Active-row treatment shared by every panel row: brand-tinted background,
 * brand text, and a 3px square-cornered accent bar on the left edge. A solid
 * primary fill here would compete with the rail's filled active tile, so rows
 * stay light and let the bar carry the emphasis.
 */
export const selectedRowSx = (accent?: string) => ({
  '&.Mui-selected': {
    bgcolor: (theme: Theme) =>
      alpha(accent ?? theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.28 : 0.1),
    color: brandInk(accent),
    '& .MuiListItemIcon-root': { color: brandInk(accent) },
    '&:hover': {
      // The accent's light-mode hover tint stays at 0.12: the red ink has
      // less contrast headroom than the navy, and 0.16 drags it under AA.
      bgcolor: (theme: Theme) =>
        alpha(
          accent ?? theme.palette.primary.main,
          theme.palette.mode === 'dark' ? 0.36 : (accent ? 0.12 : 0.16),
        ),
    },
    '&::before': {
      content: '""',
      position: 'absolute',
      left: 0,
      top: 6,
      bottom: 6,
      width: 3,
      borderRadius: 0,
      bgcolor: brandInk(accent),
    },
  },
});

/** Indented row, same selected treatment as the top-level panel rows. */
export const subItemSx = (accent?: string) => ({
  mx: 1,
  pl: 4,
  pr: 1.5,
  borderRadius: 1,
  mb: 0.25,
  minHeight: 34,
  ...selectedRowSx(accent),
});

/**
 * Slightly smaller than a top-level label; wraps to at most two lines. The
 * clamp styles go through `sx` — as direct Typography props the -webkit-*
 * ones aren't system props and leak onto the DOM element (React warns).
 */
export const subItemTextProps = (selected: boolean) => ({
  sx: {
    fontSize: 12,
    fontWeight: selected ? 700 : 400,
    lineHeight: 1.3,
    overflow: 'hidden',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical' as const,
    wordBreak: 'break-word' as const,
  },
});
