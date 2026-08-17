/**
 * Shared styling for the sidebar's panel rows.
 *
 * Two different places render second-level rows - the static children in
 * navigation.ts (WinAir's Pricing / Velocity) and the async chart list under
 * Dashboards - and they must read as the same level of hierarchy, so the
 * styles live here rather than being duplicated in both.
 */
import { alpha } from '@mui/material/styles';
import type { Theme } from '@mui/material/styles';

/**
 * The navy #1a5276 primary is too dim against the dark-mode paper, so active
 * rows switch to the lighter brand stop there.
 */
const brandInk = (theme: Theme) =>
  theme.palette.mode === 'dark' ? theme.palette.primary.light : theme.palette.primary.main;

/**
 * Active-row treatment shared by every panel row: brand-tinted background,
 * brand text, and a 3px square-cornered accent bar on the left edge. A solid
 * primary fill here would compete with the rail's filled active tile, so rows
 * stay light and let the bar carry the emphasis.
 */
export const selectedRowSx = {
  '&.Mui-selected': {
    bgcolor: (theme: Theme) =>
      alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.28 : 0.1),
    color: brandInk,
    '& .MuiListItemIcon-root': { color: brandInk },
    '&:hover': {
      bgcolor: (theme: Theme) =>
        alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.36 : 0.16),
    },
    '&::before': {
      content: '""',
      position: 'absolute',
      left: 0,
      top: 6,
      bottom: 6,
      width: 3,
      borderRadius: 0,
      bgcolor: brandInk,
    },
  },
};

/** Indented row, same selected treatment as the top-level panel rows. */
export const subItemSx = {
  mx: 1,
  pl: 4,
  pr: 1.5,
  borderRadius: 1,
  mb: 0.25,
  minHeight: 34,
  ...selectedRowSx,
};

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
