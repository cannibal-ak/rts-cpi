import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Paper, IconButton, Typography, Fade, Chip, Tooltip } from '@mui/material';
import { ArrowBack, Flight, DirectionsBoat, CalendarMonth, Refresh } from '@mui/icons-material';
import { keyframes } from '@mui/system';
import { api } from '../../api';
import { useSession } from '../../context/SessionContext';
import { canAccessDashboard } from './dashboardAccess';

/**
 * Superset base URL — used by the Embedded SDK to construct the iframe src.
 * The SDK creates:  {SUPERSET_URL}/embedded/{embedded_uuid}?uiConfig=...&show_filters=1&expand_filters=1
 * That endpoint renders the dashboard canvas only (no Superset nav/menu).
 */
const SUPERSET_URL = 'http://192.168.101.10:8088';

// Dashboard metadata (must match backend DASHBOARDS registry)
const DASHBOARD_META: Record<string, { title: string; tenant: string; isAirline: boolean; freshnessDomain: string }> = {
  '1': { title: 'Airline CPI JY Dashboard', tenant: 'JY', isAirline: true, freshnessDomain: 'Airline CPI \u2013 JY' },
  '2': { title: 'Airline CPI PW Dashboard', tenant: 'PW', isAirline: true, freshnessDomain: 'Airline CPI \u2013 PW' },
  '3': { title: 'Cruise/Ferry CPI Dashboard', tenant: 'FJL', isAirline: false, freshnessDomain: 'Cruise/Ferry CPI \u2013 FJL' },
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

  const meta = id ? DASHBOARD_META[id] : undefined;

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
        setIsLoading(true);
        const metadata = await api.superset.getGuestToken(id);

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
            const { token } = await api.superset.getGuestToken(id);
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
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
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
            label={`Data as of ${formattedDate}`}
            size="small"
            variant="outlined"
            color="primary"
            sx={{ ml: 2, fontWeight: 500 }}
          />
        )}
        <Box sx={{ flexGrow: 1 }} />
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

      {/* Dashboard container */}
      <Paper
        variant="outlined"
        sx={{
          flexGrow: 1,
          overflow: 'hidden',
          position: 'relative',
          bgcolor: 'background.paper',
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

        {/* SDK mount point — must stay in the DOM even while loading */}
        <Box
          ref={mountRef}
          sx={{
            width: '100%',
            height: '100%',
            visibility: isLoading ? 'hidden' : 'visible',
            '& > iframe': { height: 'calc(100vh - 140px) !important' },
          }}
        />
      </Paper>
    </Box>
  );
}
