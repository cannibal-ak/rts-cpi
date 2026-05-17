/**
 * Isolated Superset chart embed for the dashboard "Chart view" mode.
 *
 * Renders a single Superset slice in an iframe via the standalone explore URL.
 * Auth note: Superset's Public role has all_datasource_access + read perms only
 * (see infra/SUPERSET_NOTES.md), so this works for unauthenticated tenant users.
 */
import React from 'react';
import { Box, IconButton, Typography, Tooltip } from '@mui/material';
import { ChevronLeft, ChevronRight, InfoOutlined } from '@mui/icons-material';

interface Props {
  sliceId: number;
  sliceName: string;
  supersetBaseUrl: string;
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}

export default function SingleChartViewer({
  sliceId, sliceName, supersetBaseUrl, currentIndex, total, onPrev, onNext,
}: Props) {
  // Standalone explore mode strips Superset chrome (nav, menus) from the page.
  // The legacy `/superset/explore/` redirects (302) to this canonical path.
  const src = `${supersetBaseUrl}/explore/?slice_id=${sliceId}&standalone=1`;

  const navBtnSx = {
    width: 28,
    height: 28,
    borderRadius: '6px',
    border: '1px solid',
    borderColor: 'divider',
    p: 0,
  };

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',      // fits exactly inside the chart pane — no outer scroll
      width: '100%',
      minWidth: 0,
      overflow: 'hidden',
    }}>
      {/* Header row */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 2,
        py: 1,
        borderBottom: '1px solid',
        borderColor: 'divider',
        gap: 2,
        minWidth: 0,
        flexShrink: 0,
      }}>
        <Typography
          sx={{
            fontSize: 14,
            fontWeight: 500,
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={sliceName}
        >
          {sliceName}
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
          <Tooltip title="Previous chart">
            <span>
              <IconButton size="small" onClick={onPrev} disabled={total <= 1} aria-label="Previous chart" sx={navBtnSx}>
                <ChevronLeft sx={{ fontSize: 18 }} />
              </IconButton>
            </span>
          </Tooltip>
          <Typography
            sx={{
              fontSize: 12,
              color: 'text.disabled',
              minWidth: 36,
              textAlign: 'center',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {currentIndex + 1} / {total}
          </Typography>
          <Tooltip title="Next chart">
            <span>
              <IconButton size="small" onClick={onNext} disabled={total <= 1} aria-label="Next chart" sx={navBtnSx}>
                <ChevronRight sx={{ fontSize: 18 }} />
              </IconButton>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* Compact info banner (replaces MUI Alert) */}
      <Box sx={(theme) => ({
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        px: 2,
        py: '4px',
        fontSize: 12,
        color: 'text.secondary',
        bgcolor: theme.palette.mode === 'dark' ? 'action.hover' : theme.palette.grey[50],
        borderBottom: '1px solid',
        borderColor: 'divider',
        flexShrink: 0,
      })}>
        <InfoOutlined sx={{ fontSize: 14, color: 'info.main', flexShrink: 0 }} />
        <Box component="span">Dashboard filters don't apply in chart view</Box>
      </Box>

      {/* Chart iframe — fills the remaining height of the pane exactly so the
          whole chart (canvas + axes + Superset's bottom range slider) fits in
          one frame; no outer scrollbar.  Superset re-lays out its canvas to
          whatever viewport it gets, so a shorter pane = smaller chart. */}
      <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        <iframe
          // Key on sliceId so React tears down the old iframe instead of just
          // updating src — avoids Superset state bleed between chart switches.
          key={sliceId}
          title={sliceName}
          src={src}
          style={{
            flex: 1,
            width: '100%',
            height: '100%',
            border: 'none',
            display: 'block',
          }}
        />
      </Box>
    </Box>
  );
}
