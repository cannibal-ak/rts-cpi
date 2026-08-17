/**
 * Shared styling for second-level sidebar rows.
 *
 * Two different places render them - the static children in navigation.ts
 * (WinAir's Pricing / Velocity) and the async chart list under Dashboards -
 * and they must read as the same level of hierarchy, so the styles live here
 * rather than being duplicated in both.
 */
import type { SxProps, Theme } from '@mui/material/styles';

/** Indented row, same selected treatment as the top-level items. */
export const subItemSx: SxProps<Theme> = {
  mx: 1,
  pl: 5,
  pr: 2,
  borderRadius: 1,
  mb: 0.25,
  minHeight: 34,
  '&.Mui-selected': {
    bgcolor: 'primary.main',
    color: 'primary.contrastText',
    '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
    '&:hover': { bgcolor: 'primary.dark' },
  },
};

/** Slightly smaller than a top-level label; wraps to at most two lines. */
export const subItemTextProps = (selected: boolean) => ({
  fontSize: 12,
  fontWeight: selected ? 700 : 400,
  lineHeight: 1.3,
  overflow: 'hidden',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical' as const,
  wordBreak: 'break-word' as const,
});
