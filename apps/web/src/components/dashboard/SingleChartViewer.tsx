/**
 * Isolated Superset chart embed for the dashboard "Chart view" mode.
 *
 * Renders a single Superset slice in an iframe via the standalone explore URL.
 * Auth note: Superset's Public role has all_datasource_access + read perms only
 * (see infra/SUPERSET_NOTES.md), so this works for unauthenticated tenant users.
 *
 * Date filter: on allowlisted dashboards (see CAP_DATE_CHARTVIEW_DASHBOARDS in
 * DashboardViewerPage) the dashboard's active cap_date filter is applied to the
 * standalone chart via a Superset `form_data_key` — a server-stored form_data
 * overlay carrying an `adhoc_filters` clause on cap_date (mirroring the backend
 * guest-token RLS: single day → cap_date == X; range → cap_date >= from AND
 * <= to, inclusive). We mint the key from our backend (which builds the overlay
 * server-side, incl. adhoc_filters_b for mixed_timeseries) and load
 * /explore/?slice_id=ID&standalone=1&form_data_key=KEY.
 *
 * Why a key and not raw `form_data` in the URL: the Superset explore SPA's
 * URL-param registry does NOT include raw `form_data` — it silently drops it and
 * renders the chart's saved (unfiltered) config. It DOES honor `form_data_key`.
 */
import React from 'react';
import { Box, IconButton, Typography, Tooltip, CircularProgress } from '@mui/material';
import { ChevronLeft, ChevronRight, InfoOutlined } from '@mui/icons-material';
import { api } from '../../api';
import type { DashboardDateFilter } from '../../api/client';

interface Props {
  sliceId: number;
  sliceName: string;
  supersetBaseUrl: string;
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  // ── Date-filter wiring (Chart view honors the dashboard's cap_date filter) ──
  dateFilter: DashboardDateFilter;
  capDateFilterEnabled: boolean; // dashboard is in the cap_date chart-view allowlist
  refreshKey: number;            // bumped on date-change / refresh → re-mints the key + reloads
}

// True once the active date filter carries usable values (so a key is mintable).
function dateFilterHasValues(df: DashboardDateFilter): boolean {
  if (df.mode === 'single') return !!df.capDateEq;
  return !!(df.capDateFrom && df.capDateTo);
}

export default function SingleChartViewer({
  sliceId, sliceName, supersetBaseUrl, currentIndex, total, onPrev, onNext,
  dateFilter, capDateFilterEnabled, refreshKey,
}: Props) {
  // Standalone explore mode strips Superset chrome (nav, menus) from the page.
  // The legacy `/superset/explore/` redirects (302) to this canonical path.
  const baseSrc = `${supersetBaseUrl}/explore/?slice_id=${sliceId}&standalone=1`;

  // Apply the dashboard's active cap_date filter ONLY on allowlisted dashboards,
  // and only once the filter carries date values.
  const wantFilter = capDateFilterEnabled && dateFilterHasValues(dateFilter);

  // Stable signature of the active date filter — drives the re-mint effect and
  // the iframe key without depending on the dateFilter object's identity.
  const dateSig = wantFilter
    ? (dateFilter.mode === 'single'
        ? `s:${dateFilter.capDateEq}`
        : `r:${dateFilter.capDateFrom}:${dateFilter.capDateTo}`)
    : 'none';

  // form_data_key minted by our backend for (sliceId, dateFilter). Re-minted
  // whenever the slice, the date filter, OR refreshKey changes (refreshKey keeps
  // the Refresh button honest — a fresh, non-expired key each time).
  const [formDataKey, setFormDataKey] = React.useState<string | null>(null);
  const [minting, setMinting] = React.useState(false);
  const [mintError, setMintError] = React.useState(false);

  React.useEffect(() => {
    if (!wantFilter) {
      setFormDataKey(null);
      setMinting(false);
      setMintError(false);
      return;
    }
    let cancelled = false;
    setMinting(true);
    setFormDataKey(null);
    setMintError(false);
    api.superset.getChartFormDataKey(sliceId, dateFilter)
      .then((res) => { if (!cancelled) setFormDataKey(res.key); })
      .catch(() => { if (!cancelled) setMintError(true); }) // fall back to plain (unfiltered) URL + notice
      .finally(() => { if (!cancelled) setMinting(false); });
    return () => { cancelled = true; };
    // dateSig captures the date values; dateFilter is read inside but intentionally
    // excluded from deps (its object identity changes on every parent render).
  }, [sliceId, dateSig, refreshKey, wantFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // While minting, show a brief loading state instead of flashing the unfiltered
  // chart. On mint error (formDataKey stays null after minting) we fall back to
  // the plain URL so the chart still renders.
  const showLoading = wantFilter && minting;
  const src = (wantFilter && formDataKey)
    ? `${baseSrc}&form_data_key=${encodeURIComponent(formDataKey)}`
    : baseSrc;

  // Reload the iframe when the slice, the refresh counter, the date filter, or
  // the resolved key changes (so the filtered URL takes effect once minted).
  const iframeKey = `${sliceId}-${refreshKey}-${dateSig}-${formDataKey ?? 'plain'}`;

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

      {/* Compact info banner (replaces MUI Alert).
          Only shown where the cap_date filter is NOT wired in (non-allowlisted
          dashboards) — there the dashboard's date filter genuinely doesn't reach
          chart view. On allowlisted dashboards the filter IS applied, so the
          banner is hidden to avoid lying to the user. */}
      {!capDateFilterEnabled && (
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
      )}

      {/* Allowlisted dashboard, but the form_data_key mint failed → the iframe
          falls back to the unfiltered (all-dates) URL. Surface that explicitly so
          the fallback is never silent. The normal filtered case stays banner-free. */}
      {capDateFilterEnabled && mintError && (
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
          <InfoOutlined sx={{ fontSize: 14, color: 'warning.main', flexShrink: 0 }} />
          <Box component="span">Showing all dates — date filter unavailable</Box>
        </Box>
      )}

      {/* Chart iframe — fills the remaining height of the pane exactly so the
          whole chart (canvas + axes + Superset's bottom range slider) fits in
          one frame; no outer scrollbar.  Superset re-lays out its canvas to
          whatever viewport it gets, so a shorter pane = smaller chart.
          While the form_data_key is being minted we show a brief spinner instead
          of loading the unfiltered URL first (avoids a flash of all-data). */}
      <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        {showLoading ? (
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CircularProgress size={28} />
          </Box>
        ) : (
          <iframe
            // Key on sliceId + refresh + date signature + resolved key so React
            // tears down the old iframe (instead of just updating src) on a chart
            // switch, a date-filter change, or once the key is minted — avoids
            // Superset state bleed and forces a reload with the new cap_date scope.
            key={iframeKey}
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
        )}
      </Box>
    </Box>
  );
}
