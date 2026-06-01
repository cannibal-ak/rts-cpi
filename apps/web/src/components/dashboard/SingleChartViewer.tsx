/**
 * Isolated Superset chart embed for the dashboard "Chart view" mode.
 *
 * Renders a single Superset slice in an iframe via the standalone explore URL.
 * Auth note: Superset's Public role has all_datasource_access + read perms only
 * (see infra/SUPERSET_NOTES.md), so this works for unauthenticated tenant users.
 *
 * Date filter: on allowlisted dashboards (see CAP_DATE_CHARTVIEW_DASHBOARDS in
 * DashboardViewerPage) the dashboard's active cap_date filter is injected into
 * the standalone explore URL via a `form_data` override carrying an
 * `adhoc_filters` clause on cap_date — mirroring the backend guest-token RLS
 * exactly (single day → cap_date == X; range → cap_date >= from AND <= to,
 * inclusive both ends). Superset's explore page merges this over the chart's
 * saved config, so Chart view is scoped to the same date(s) as Dashboard mode.
 */
import React from 'react';
import { Box, IconButton, Typography, Tooltip } from '@mui/material';
import { ChevronLeft, ChevronRight, InfoOutlined } from '@mui/icons-material';
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
  vizType: string | null;        // from the chart manifest; drives mixed_timeseries handling
  capDateFilterEnabled: boolean; // dashboard is in the cap_date chart-view allowlist
  refreshKey: number;            // bumped on date-change / refresh → reloads the iframe
}

// A Superset "SIMPLE" adhoc filter on the cap_date column.
type CapDateAdhocFilter = {
  clause: 'WHERE';
  expressionType: 'SIMPLE';
  subject: 'cap_date';
  operator: '==' | '>=' | '<=';
  comparator: string;
};

/**
 * Build the cap_date adhoc_filters array from the active date filter, mirroring
 * the backend RLS clause (superset.py) exactly:
 *   single → cap_date == capDateEq
 *   range  → cap_date >= capDateFrom AND cap_date <= capDateTo  (inclusive both ends)
 * Returns null when the filter has no usable values yet (so we emit the plain URL).
 */
function buildCapDateFilters(df: DashboardDateFilter): CapDateAdhocFilter[] | null {
  if (df.mode === 'single' && df.capDateEq) {
    return [{ clause: 'WHERE', expressionType: 'SIMPLE', subject: 'cap_date', operator: '==', comparator: df.capDateEq }];
  }
  if (df.mode === 'range' && df.capDateFrom && df.capDateTo) {
    return [
      { clause: 'WHERE', expressionType: 'SIMPLE', subject: 'cap_date', operator: '>=', comparator: df.capDateFrom },
      { clause: 'WHERE', expressionType: 'SIMPLE', subject: 'cap_date', operator: '<=', comparator: df.capDateTo },
    ];
  }
  return null;
}

export default function SingleChartViewer({
  sliceId, sliceName, supersetBaseUrl, currentIndex, total, onPrev, onNext,
  dateFilter, vizType, capDateFilterEnabled, refreshKey,
}: Props) {
  // Standalone explore mode strips Superset chrome (nav, menus) from the page.
  // The legacy `/superset/explore/` redirects (302) to this canonical path.
  const baseSrc = `${supersetBaseUrl}/explore/?slice_id=${sliceId}&standalone=1`;

  // Inject the dashboard's active cap_date filter ONLY on allowlisted dashboards,
  // and only once the filter actually carries date values. The override sets
  // `adhoc_filters` (and `adhoc_filters_b` for mixed_timeseries' second query)
  // and is merged by Superset's explore page over the chart's saved config.
  const capDateFilters = capDateFilterEnabled ? buildCapDateFilters(dateFilter) : null;
  const filterApplied = capDateFilters !== null;

  let src = baseSrc;
  if (capDateFilters) {
    const formDataOverride: Record<string, unknown> = { adhoc_filters: capDateFilters };
    if (vizType === 'mixed_timeseries') {
      // mixed_timeseries runs a second query whose filters live in adhoc_filters_b;
      // scope it to the same cap_date window so both series match.
      formDataOverride.adhoc_filters_b = capDateFilters;
    }
    src = `${baseSrc}&form_data=${encodeURIComponent(JSON.stringify(formDataOverride))}`;
  }

  // Reload the iframe when the slice, the date filter, or the refresh counter
  // changes. The date signature mirrors what actually drives the embed refresh.
  const dateSig = filterApplied
    ? (dateFilter.mode === 'single'
        ? `s:${dateFilter.capDateEq}`
        : `r:${dateFilter.capDateFrom}:${dateFilter.capDateTo}`)
    : 'none';
  const iframeKey = `${sliceId}-${refreshKey}-${dateSig}`;

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

      {/* Chart iframe — fills the remaining height of the pane exactly so the
          whole chart (canvas + axes + Superset's bottom range slider) fits in
          one frame; no outer scrollbar.  Superset re-lays out its canvas to
          whatever viewport it gets, so a shorter pane = smaller chart. */}
      <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        <iframe
          // Key on sliceId + refresh + date signature so React tears down the
          // old iframe (instead of just updating src) on a chart switch OR a
          // date-filter change — avoids Superset state bleed and forces a reload
          // with the new cap_date scope.
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
      </Box>
    </Box>
  );
}
