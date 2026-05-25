import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, Paper, IconButton, Typography, Fade, Chip, Tooltip,
  ToggleButton, ToggleButtonGroup, useMediaQuery,
} from '@mui/material';
import {
  ArrowBack, Flight, DirectionsBoat, CalendarMonth, Refresh,
  Dashboard as DashboardIcon, BarChart as BarChartIcon,
} from '@mui/icons-material';
import { keyframes } from '@mui/system';
import type { Theme } from '@mui/material/styles';
import { api } from '../../api';
import type { DashboardDateFilter } from '../../api/client';
import { useSession } from '../../context/SessionContext';
import { canAccessDashboard } from './dashboardAccess';
import { useDashboardCharts } from '../../hooks/useDashboardCharts';
import ChartSelectorPanel from '../../components/dashboard/ChartSelectorPanel';
import DateFilterToggle from '../../components/dashboard/DateFilterToggle';
import SingleChartViewer from '../../components/dashboard/SingleChartViewer';
import KPIRow from '../../components/dashboard/KPIRow';

/**
 * Superset base URL — used by the Embedded SDK to construct the iframe src.
 * The SDK creates:  {SUPERSET_URL}/embedded/{embedded_uuid}?uiConfig=...&show_filters=1&expand_filters=1
 * That endpoint renders the dashboard canvas only (no Superset nav/menu).
 */
const SUPERSET_URL = 'http://192.168.101.10:8088';

// Dashboard metadata (must match backend DASHBOARDS registry)
const DASHBOARD_META: Record<string, { title: string; tenant: string; isAirline: boolean; freshnessDomain: string }> = {
  '1': { title: 'JY Dashboard', tenant: 'JY', isAirline: true, freshnessDomain: 'Airline CPI \u2013 JY' },
  '2': { title: 'PW Dashboard', tenant: 'PW', isAirline: true, freshnessDomain: 'Airline CPI \u2013 PW' },
  '3': { title: 'FJL Dashboard', tenant: 'FJL', isAirline: false, freshnessDomain: 'Cruise/Ferry CPI \u2013 FJL' },
};

// Superset Embedded SDK type (UMD bundle loaded via CDN in index.html)
declare global {
  interface Window {
    supersetEmbeddedSdk: {
      embedDashboard: (config: {
        id: string;
        supersetDomain: string;
        mountPoint: HTMLElement;
        fetchGuestToken: () => Promise<string>;
        dashboardUiConfig?: {
          hideTitle?: boolean;
          hideChartControls?: boolean;
          hideTab?: boolean;
          filters?: { visible?: boolean; expanded?: boolean };
        };
      }) => Promise<{ unmount: () => void }>;
    };
  }
}

const pulse = keyframes`
  0% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(1); opacity: 0.8; }
`;

export default function DashboardViewerPage() {
  const { id } = useParams<{ id: string }>();
  const { session } = useSession();
  const navigate = useNavigate();
  const mountRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataDate, setDataDate] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // ── Date filter (drives RLS on chart queries via guest token) ──
  // Default to single-day mode; the actual day is filled in once
  // /available-dates resolves. We keep dateFilter in a ref so the
  // SDK's fetchGuestToken closure always reads the latest value
  // without having to re-bind the SDK callback on every change.
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [datesLoading, setDatesLoading] = useState(true);
  const [dateFilter, setDateFilter] = useState<DashboardDateFilter>({ mode: 'single' });
  const dateFilterRef = useRef<DashboardDateFilter>(dateFilter);
  useEffect(() => { dateFilterRef.current = dateFilter; }, [dateFilter]);

  const meta = id ? DASHBOARD_META[id] : undefined;

  // ── Slice & dice: chart selector + isolated chart view (additive) ──
  // viewMode toggles the right pane between the embedded dashboard SDK iframe
  // (existing) and a single-chart standalone iframe (new).  selectedSliceId
  // tracks which analytics chart the user picked.
  const [viewMode, setViewMode] = useState<'dashboard' | 'chart'>('dashboard');
  const [selectedSliceId, setSelectedSliceId] = useState<number | null>(null);

  const { analyticsCharts, loading: chartsLoading, error: chartsError, refetch: refetchCharts } =
    useDashboardCharts(id);

  // Narrow viewport → collapse selector into a horizontal chip rail
  const isNarrow = useMediaQuery((t: Theme) => t.breakpoints.down('md'));

  // When the chart list resolves (initial load OR dashboard switch), default
  // to the first chart.  If the current selection still exists in the new
  // list (e.g. an unrelated re-render), keep it — avoids snapping back to
  // chart 1 every time the manifest re-resolves.
  useEffect(() => {
    if (analyticsCharts.length === 0) {
      setSelectedSliceId(null);
      return;
    }
    setSelectedSliceId(prev =>
      prev !== null && analyticsCharts.some(c => c.slice_id === prev)
        ? prev
        : analyticsCharts[0].slice_id
    );
  }, [analyticsCharts]);

  // Returning to a different dashboard always starts in Dashboard mode.
  useEffect(() => {
    setViewMode('dashboard');
  }, [id]);

  // ── Load available cap_date values for this dashboard ──
  // Resets to default single-day mode whenever the dashboard changes, then
  // anchors on the most recent date once /available-dates resolves.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setDatesLoading(true);
    setAvailableDates([]);
    setDateFilter({ mode: 'single' });
    api.superset.getAvailableDates(id)
      .then(res => {
        if (cancelled) return;
        const dates = res.dates ?? [];
        setAvailableDates(dates);
        if (dates.length > 0) {
          setDateFilter({ mode: 'single', capDateEq: dates[0] });
        }
      })
      .catch(err => {
        if (!cancelled) console.error('[DateFilter] available-dates failed:', err);
      })
      .finally(() => { if (!cancelled) setDatesLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  const handleDateFilterChange = (next: DashboardDateFilter) => {
    setDateFilter(next);
    setRefreshKey(k => k + 1);   // bump → re-embed with new RLS-scoped guest token
  };

  // Effective selection — falls back to the first chart if state hasn't
  // settled yet.  Keeps the right pane non-blank in the brief window between
  // viewMode='chart' and the default-selection effect committing.
  const effectiveSliceId: number | null = selectedSliceId ?? analyticsCharts[0]?.slice_id ?? null;

  const selectedIndex = useMemo(
    () => analyticsCharts.findIndex(c => c.slice_id === effectiveSliceId),
    [analyticsCharts, effectiveSliceId],
  );

  const handleSelectChart = (sliceId: number) => {
    setSelectedSliceId(sliceId);
    setViewMode('chart');     // clicking a chart name auto-switches to chart view
  };

  const handlePrev = () => {
    if (analyticsCharts.length === 0) return;
    const idx = selectedIndex < 0 ? 0 : selectedIndex;
    const next = (idx - 1 + analyticsCharts.length) % analyticsCharts.length;
    setSelectedSliceId(analyticsCharts[next].slice_id);
  };

  const handleNext = () => {
    if (analyticsCharts.length === 0) return;
    const idx = selectedIndex < 0 ? 0 : selectedIndex;
    const next = (idx + 1) % analyticsCharts.length;
    setSelectedSliceId(analyticsCharts[next].slice_id);
  };

  useEffect(() => {
    if (!id || !mountRef.current || !meta) return;

    let unmount: (() => void) | undefined;

    const embed = async () => {
      try {
        // ── 1. Frontend access guard ──
        if (!canAccessDashboard(session, id)) {
          setError('Access Denied: You do not have permission to view this dashboard.');
          setIsLoading(false);
          return;
        }

        // ── 2. Wait for SDK (UMD bundle from CDN) ──
        let attempts = 0;
        while (!window.supersetEmbeddedSdk && attempts < 20) {
          await new Promise(r => setTimeout(r, 300));
          attempts++;
        }
        if (!window.supersetEmbeddedSdk) {
          throw new Error('Superset Embedded SDK did not load. Check the <script> tag in index.html.');
        }

        // ── 3. Fetch embedded_uuid + initial guest token from backend ──
        //   Pass the current date filter so the very first token carries
        //   the cap_date RLS clause — otherwise the iframe briefly loads
        //   unfiltered data before the SDK re-fetches.
        setIsLoading(true);
        const metadata = await api.superset.getGuestToken(id, dateFilterRef.current);

        // ── 3b. Fetch data freshness to get the report date ──
        try {
          const freshness = await api.stats.getFreshnessMetrics();
          const match = freshness.find(f => f.domain === meta.freshnessDomain);
          if (match?.report_date) {
            setDataDate(match.report_date);
          }
        } catch {
          // Non-critical — dashboard still works without the date
        }

        // ── 4. Embed the dashboard ──
        //   SDK creates an iframe to: {SUPERSET_URL}/embedded/{embedded_uuid}
        //   which is Superset's canvas-only view (no global nav, no chrome).
        //   The guest token is sent to the iframe via postMessage.
        const result = await window.supersetEmbeddedSdk.embedDashboard({
          id: metadata.embedded_uuid,
          supersetDomain: SUPERSET_URL,
          mountPoint: mountRef.current!,
          fetchGuestToken: async () => {
            const { token } = await api.superset.getGuestToken(id, dateFilterRef.current);
            return token;
          },
          dashboardUiConfig: {
            hideTitle: true,           // hide Superset's title bar (we show our own + data date)
            hideChartControls: true,   // hide chart-level three-dot menus
            hideTab: false,
            filters: {
              visible: true,
              expanded: true,   // start with filters visible (restyled as horizontal bar via dashboard CSS)
            },
          },
        });
        unmount = result.unmount;

        // Give Superset a moment to render inside the iframe
        setTimeout(() => setIsLoading(false), 1500);
      } catch (err: any) {
        console.error('Dashboard embed failed:', err);
        const msg = err?.message || 'Failed to load dashboard';
        setError(msg.startsWith('API ') || msg.startsWith('Network Error')
          ? `Backend error: ${msg}`
          : msg);
        setIsLoading(false);
      }
    };

    embed();

    return () => { unmount?.(); };
  }, [id, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const LoadingIcon = meta?.isAirline ? Flight : DirectionsBoat;
  const loadingLabel = meta?.isAirline ? 'Loading Airline Analytics...' : 'Preparing Maritime Insights...';

  // Format the data date for display
  const formattedDate = dataDate
    ? new Date(dataDate + 'T00:00:00').toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
      })
    : null;

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header bar */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0 }}>
        <Tooltip title="Back to dashboards">
          <IconButton onClick={() => navigate('/dashboards')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
        </Tooltip>
        <Typography variant="h5" component="h1" fontWeight={600}>
          {meta?.title ?? 'Dashboard'}
        </Typography>
        {formattedDate && (
          <Chip
            icon={<CalendarMonth sx={{ fontSize: 16 }} />}
            label={`Latest data: ${formattedDate}`}
            size="small"
            variant="outlined"
            color="primary"
            sx={{ ml: 2, fontWeight: 500 }}
          />
        )}
        <Box sx={{ flexGrow: 1 }} />

        {/* View mode toggle — segmented control */}
        <ToggleButtonGroup
          size="small"
          exclusive
          value={viewMode}
          onChange={(_, v) => {
            if (!v) return;
            // Defensive: if the user toggles into Chart view before the
            // default-selection effect has settled, pick the first chart now
            // so the right pane never renders blank.
            if (v === 'chart' && selectedSliceId === null && analyticsCharts.length > 0) {
              setSelectedSliceId(analyticsCharts[0].slice_id);
            }
            setViewMode(v);
          }}
          sx={{
            mr: 1,
            p: '3px',
            gap: '2px',
            bgcolor: 'action.hover',
            borderRadius: 1,                  // 8px container
            border: 0,
            '& .MuiToggleButton-root': {
              px: 1.5,
              py: '5px',
              fontSize: 12,
              fontWeight: 500,
              textTransform: 'none',
              border: 0,
              borderRadius: '6px',
              color: 'text.secondary',
              gap: 0.75,
              '&:hover': { bgcolor: 'transparent' },
              '&.Mui-selected': {
                bgcolor: 'background.paper',
                color: 'text.primary',
                border: '0.5px solid',
                borderColor: 'divider',
                '&:hover': { bgcolor: 'background.paper' },
              },
              '&.Mui-disabled': { border: 0 },
            },
          }}
        >
          <ToggleButton value="dashboard" aria-label="Full dashboard view">
            <DashboardIcon sx={{ fontSize: 14 }} />
            Dashboard
          </ToggleButton>
          <ToggleButton value="chart" aria-label="Single chart view" disabled={analyticsCharts.length === 0}>
            <BarChartIcon sx={{ fontSize: 14 }} />
            Chart view
          </ToggleButton>
        </ToggleButtonGroup>

        <Tooltip title="Refresh dashboard">
          <IconButton
            size="small"
            onClick={() => setRefreshKey(k => k + 1)}
            disabled={isLoading}
            aria-label="Refresh dashboard"
            sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}
          >
            <Refresh fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* ── Dashboard pane — kept mounted across mode toggles so the SDK
          iframe (and its guest-token / fetch lifecycle) survives a switch
          to Chart view and back without re-init.  In Chart view it is hidden
          via display:none, NOT unmounted. ──────────────────────────────── */}
      <Box sx={{
        display: viewMode === 'dashboard' ? 'flex' : 'none',
        flexDirection: 'column',
        flexGrow: 1,
        minHeight: 0,
      }}>
        {/* Date filter bar — drives cap_date RLS on every chart in this dashboard */}
        <Box sx={{ mb: 0.5 }}>
          <DateFilterToggle
            availableDates={availableDates}
            value={dateFilter}
            onChange={handleDateFilterChange}
            disabled={datesLoading || availableDates.length === 0}
          />
        </Box>

        {/* KPI row — CPI-rendered tiles + click-to-expand detail (JY + PW).
            These replace the Superset big-number tiles so the values and their
            drill-downs share a single source of truth and respond to the Cap
            Date picker above. The KPI set is per-airline (see KPIRow).
            cap_date: single-day uses the picked day; range uses the window's
            end (most recent) day, since the KPI queries are single-day. */}
        {(meta?.tenant === 'JY' || meta?.tenant === 'PW') && (
          <KPIRow
            airlineCode={meta.tenant}
            capDate={(dateFilter.mode === 'single' ? dateFilter.capDateEq : dateFilter.capDateTo) ?? ''}
          />
        )}

        {/* Dashboard container */}
        <Paper
          variant="outlined"
          sx={{
            flexGrow: 1,
            overflow: 'hidden',
            position: 'relative',
            bgcolor: 'background.paper',
            // Bleed past <main>'s p:3 horizontal padding so the embedded dashboard
            // gets the full available width — prevents right-edge clipping of the
            // last X-axis tick / legend items inside the iframe.
            mx: -3,
            borderRadius: 0,
            borderLeft: 'none',
            borderRight: 'none',
            // The SDK injects an <iframe> inside mountRef
            '& iframe': { width: '100%', height: '100%', border: 'none' },
          }}
        >
          {/* Loading overlay */}
          <Fade in={isLoading} unmountOnExit>
            <Box sx={{
              position: 'absolute', inset: 0, display: 'flex',
              flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              bgcolor: 'background.paper', zIndex: 10,
            }}>
              <LoadingIcon sx={{ fontSize: 56, color: 'primary.main', mb: 2, animation: `${pulse} 2s infinite ease-in-out` }} />
              <Typography variant="h6" color="text.secondary">{loadingLabel}</Typography>
            </Box>
          </Fade>

          {/* Error state */}
          {error && (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography color="error" variant="h6" gutterBottom>{error}</Typography>
              <Typography variant="body2" color="text.secondary">
                Check that Superset is running and the dashboard exists.
              </Typography>
            </Box>
          )}

          {/* SDK mount point — must stay in the DOM even while loading.
              Absolute-fill the (position:relative) Paper so the injected iframe
              exactly matches the flex-sized container. Avoids the brittle
              `calc(100vh - Npx)` that over-sized the iframe and let its bottom
              (the filter bar's APPLY FILTERS button) get clipped by the Paper's
              overflow:hidden. */}
          <Box
            ref={mountRef}
            sx={{
              position: 'absolute',
              inset: 0,
              visibility: isLoading ? 'hidden' : 'visible',
              '& > iframe': { width: '100%', height: '100% !important', border: 'none' },
            }}
          />
        </Paper>
      </Box>

      {/* ── Chart view pane — selector sidebar + isolated chart iframe.
          Conditionally rendered so the sidebar (and the flex row) do not
          exist in the DOM during Dashboard mode — the dashboard view is
          visually identical to the pre-feature state. ─────────────────── */}
      {viewMode === 'chart' && (
        <Box sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: isNarrow ? 'column' : 'row',
          minHeight: 0,
          minWidth: 0,
          // Match the dashboard Paper's edge-to-edge bleed past <main>'s p:3.
          mx: -3,
          // Clip any inner overflow so the page never shows a horizontal scrollbar.
          overflow: 'hidden',
          bgcolor: 'background.paper',
          borderTop: '1px solid',
          borderColor: 'divider',
        }}>
          <ChartSelectorPanel
            charts={analyticsCharts}
            selectedSliceId={effectiveSliceId}
            onSelectChart={handleSelectChart}
            loading={chartsLoading}
            error={chartsError}
            onRetry={refetchCharts}
            horizontal={isNarrow}
          />

          <Box sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0,
            // No vertical scroll on the chart pane — the iframe is sized to
            // fit the available height, and Superset re-renders the chart
            // smaller to keep everything visible in a single frame.
            overflow: 'hidden',
          }}>
            {effectiveSliceId !== null && analyticsCharts.length > 0 && (
              <SingleChartViewer
                sliceId={effectiveSliceId}
                sliceName={analyticsCharts[Math.max(0, selectedIndex)]?.slice_name ?? `Chart ${effectiveSliceId}`}
                supersetBaseUrl={SUPERSET_URL}
                currentIndex={Math.max(0, selectedIndex)}
                total={analyticsCharts.length}
                onPrev={handlePrev}
                onNext={handleNext}
              />
            )}
          </Box>
        </Box>
      )}
    </Box>
  );
}
