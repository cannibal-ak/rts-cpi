/**
 * Isolated Superset chart embed for the dashboard "Chart view" mode.
 *
 * Renders a single Superset slice in an iframe via the standalone explore URL
 * (`/superset/explore/?slice_id=X&standalone=1`).  An info banner reminds the
 * user that dashboard filters do not apply in chart view.  Prev/Next buttons
 * cycle through the analytics chart list (wraps around at both ends).
 *
 * Auth note: standalone explore relies on the user's Superset session (admin
 * cookie).  For tenant users who don't have a Superset login, the iframe will
 * show Superset's own login page — by design, per spec.  Dashboard view (with
 * guest tokens) remains unaffected.
 */
import React from 'react';
import { Box, Paper, IconButton, Typography, Alert, Tooltip } from '@mui/material';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';

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
  const src = `${supersetBaseUrl}/superset/explore/?slice_id=${sliceId}&standalone=1`;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
      {/* Chart header: name + nav */}
      <Box sx={{
        display: 'flex', alignItems: 'center',
        px: 2, py: 1,
        borderBottom: '1px solid',
        borderColor: 'divider',
      }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, flexGrow: 1, mr: 2 }} noWrap>
          {sliceName}
        </Typography>

        <Tooltip title="Previous chart">
          <span>
            <IconButton size="small" onClick={onPrev} disabled={total <= 1} aria-label="Previous chart">
              <ChevronLeft />
            </IconButton>
          </span>
        </Tooltip>
        <Typography variant="caption" sx={{ mx: 1, color: 'text.secondary', minWidth: 40, textAlign: 'center' }}>
          {currentIndex + 1} / {total}
        </Typography>
        <Tooltip title="Next chart">
          <span>
            <IconButton size="small" onClick={onNext} disabled={total <= 1} aria-label="Next chart">
              <ChevronRight />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {/* Info banner */}
      <Alert
        severity="info"
        variant="outlined"
        sx={{
          mx: 2, mt: 1,
          py: 0,
          '& .MuiAlert-message': { py: 0.5, fontSize: '0.78rem' },
        }}
      >
        Dashboard filters don't apply in chart view.
      </Alert>

      {/* Chart iframe */}
      <Paper
        variant="outlined"
        sx={{
          flex: 1,
          m: 2,
          mt: 1,
          overflow: 'hidden',
          minHeight: 500,
        }}
      >
        <iframe
          // Key on sliceId so React tears down the old iframe instead of just
          // updating src — avoids Superset state bleed between chart switches.
          key={sliceId}
          title={sliceName}
          src={src}
          style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
        />
      </Paper>
    </Box>
  );
}
