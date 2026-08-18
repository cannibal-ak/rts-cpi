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
import { Box, CircularProgress, IconButton, Typography, Tooltip } from '@mui/material';
import { ChevronLeft, ChevronRight, InfoOutlined, WarningAmber } from '@mui/icons-material';
import { api } from '../../api';
import type {
  ChartFormDataKeyResponse, DashboardDateFilter, DashboardFilterSelections,
} from '../../api/client';

interface Props {
  sliceId: number;
  sliceName: string;
  supersetBaseUrl: string;
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  /** App dashboard id — the mint endpoint is scoped to it (tenant gate). */
  dashboardId: string;
  /** This dashboard is allow-listed for the chart-view filter overlay. */
  overlayEnabled?: boolean;
  dateFilter?: DashboardDateFilter;
  /** APPLIED selections, not pending. The backend drops out-of-scope entries. */
  selections?: DashboardFilterSelections;
  /** Bumped by Apply / Refresh / date change → re-mint and reload. */
  refreshKey?: number;
}

type Overlay =
  | { status: 'off' }
  | { status: 'minting' }
  | { status: 'ready'; res: ChartFormDataKeyResponse }
  | { status: 'failed' };

export default function SingleChartViewer({
  sliceId, sliceName, supersetBaseUrl, currentIndex, total, onPrev, onNext,
  dashboardId, overlayEnabled = false, dateFilter, selections, refreshKey = 0,
}: Props) {
  // Standalone explore mode strips Superset chrome (nav, menus) from the page.
  // The legacy `/superset/explore/` redirects (302) to this canonical path.
  const baseSrc = `${supersetBaseUrl}/explore/?slice_id=${sliceId}&standalone=1`;

  // ── Filter overlay ───────────────────────────────────────────────────────
  // This iframe loads anonymously, so neither the guest token's cap_date RLS nor
  // the dashboard's native filters reach it. The one channel the explore SPA
  // honours is a server-minted form_data_key, which the backend merges over the
  // slice's own saved config.
  const hasDate = dateFilter?.mode === 'single'
    ? !!dateFilter.capDateEq
    : !!(dateFilter?.capDateFrom && dateFilter?.capDateTo);
  const dateSig = dateFilter?.mode === 'single'
    ? `s:${dateFilter.capDateEq ?? ''}`
    : `r:${dateFilter?.capDateFrom ?? ''}:${dateFilter?.capDateTo ?? ''}`;
  // Order- and identity-independent, so a parent re-render that rebuilds the
  // object does not re-mint: {a:[2,1]} and {a:[1,2]} produce the same string.
  const selectionSig = React.useMemo(() => JSON.stringify(
    Object.entries(selections ?? {})
      .filter(([, v]) => v && v.length > 0)
      .map(([k, v]) => [k, [...v].sort()] as [string, string[]])
      .sort((a, b) => a[0].localeCompare(b[0])),
  ), [selections]);

  const wantOverlay = overlayEnabled && (hasDate || selectionSig !== '[]');
  const [overlay, setOverlay] = React.useState<Overlay>({ status: 'off' });

  React.useEffect(() => {
    if (!wantOverlay) { setOverlay({ status: 'off' }); return; }
    let cancelled = false;
    setOverlay({ status: 'minting' });
    api.superset.mintChartFormDataKey(dashboardId, sliceId, { dateFilter, selections })
      .then(res => { if (!cancelled) setOverlay({ status: 'ready', res }); })
      .catch(err => {
        if (cancelled) return;
        console.error('[ChartView] form-data-key mint failed:', err);
        setOverlay({ status: 'failed' });     // → plain URL + an explicit banner
      });
    return () => { cancelled = true; };
    // dateFilter / selections are read from the closure ON PURPOSE. Their object
    // identity changes on every parent render, while dateSig / selectionSig
    // change only when the VALUES do. Depending on the objects would re-mint on
    // every render — a Superset write and an iframe teardown per frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardId, sliceId, dateSig, selectionSig, refreshKey, wantOverlay]);

  const formDataKey = overlay.status === 'ready' ? overlay.res.key : null;
  const src = formDataKey
    ? `${baseSrc}&form_data_key=${encodeURIComponent(formDataKey)}`
    : baseSrc;

  // The old banner said "Dashboard filters don't apply in chart view". On an
  // overlay-enabled dashboard that is now a lie, and a silent fallback is worse
  // than a wrong banner — so derive it from what the SERVER actually put in the
  // key, never from what this component hoped for.
  const banner: { tone: 'info' | 'warning'; text: string } | null = (() => {
    if (!overlayEnabled) {
      return { tone: 'info', text: "Dashboard filters don't apply in chart view" };
    }
    if (overlay.status === 'failed') {
      return { tone: 'warning', text: 'Showing all data — filters could not be applied to this chart' };
    }
    if (overlay.status !== 'ready') return null;
    const { cap_date, applied, out_of_scope } = overlay.res;
    const parts = [
      ...(cap_date ? [`Cap date ${cap_date}`] : []),
      ...applied.map(a => `${a.label}: ${a.values.join(', ')}`),
    ];
    if (parts.length === 0 && out_of_scope.length === 0) return null;
    const skipped = out_of_scope.length
      ? `${parts.length ? ' · ' : ''}Not used by this chart: ${out_of_scope.map(f => f.label).join(', ')}`
      : '';
    return {
      tone: 'info',
      text: `${parts.length ? `Filtered — ${parts.join(' · ')}` : ''}${skipped}`,
    };
  })();

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

      {/* Compact status banner (replaces MUI Alert) — reports what the server
          actually applied, so it can never claim more than the chart shows. */}
      {banner && (
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
          {banner.tone === 'warning'
            ? <WarningAmber sx={{ fontSize: 14, color: 'warning.main', flexShrink: 0 }} />
            : <InfoOutlined sx={{ fontSize: 14, color: 'info.main', flexShrink: 0 }} />}
          <Box component="span">{banner.text}</Box>
        </Box>
      )}

      {/* Chart iframe — fills the remaining height of the pane exactly so the
          whole chart (canvas + axes + Superset's bottom range slider) fits in
          one frame; no outer scrollbar.  Superset re-lays out its canvas to
          whatever viewport it gets, so a shorter pane = smaller chart.
          While the form_data_key is being minted we show a brief spinner instead
          of loading the unfiltered URL first (avoids a flash of all-data). */}
      <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        {overlay.status === 'minting' ? (
          // Deliberately NOT the unfiltered URL first: that flashes all-data on
          // every Apply, which is worse than a brief spinner.
          <Box sx={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.5,
          }}>
            <CircularProgress size={20} />
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
              Applying filters…
            </Typography>
          </Box>
        ) : (
          <iframe
            // Key includes the resolved form_data_key so React tears the iframe
            // down rather than swapping src — no Superset state bleed between
            // chart switches or filter changes.
            key={`${sliceId}-${refreshKey}-${formDataKey ?? overlay.status}`}
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
