import { Box, Tabs, Tab, Alert, Skeleton, CircularProgress } from '@mui/material';
import { ScatterPlot } from '@mui/icons-material';
import type { DashboardTab } from '../../../api/client';
import { BANNER_HEADER_BG, HAIRLINE, LABEL_INK } from '../bannerTheme';

/**
 * Reserved key for the CPI-rendered Latest Prices pane.
 *
 * Deliberately not a Superset layout id (those are all "TAB-*"), so it can
 * never be mistaken for one and sent to the permalink endpoint.
 */
export const PRICES_TAB = 'prices';

/**
 * Fallback entry shown when the section list is unavailable — embeds the
 * dashboard with no permalink, so Superset opens its own default section.
 * Also not a Superset layout id, for the same reason as PRICES_TAB.
 */
export const DASHBOARD_TAB = 'dashboard';

interface WinairTabBarProps {
  /** The dashboard's own sections. Empty while loading, or on failure. */
  tabs: DashboardTab[];
  value: string;
  onChange: (next: string) => void;
  loading: boolean;
  /** A Superset section is being minted/embedded — shown on the target tab. */
  switching: boolean;
  error: string | null;
}

/**
 * WinAir's one row of navigation: Latest Prices, then the dashboard's sections.
 *
 * Superset's own tab row is hidden inside the iframe (WM-EMBED-HIDE-TOPTABS
 * css block on dashboard 6 — Superset 3.1.0 ignores the uiConfig hideNav bit
 * the embed also sends), so this bar is the ONLY way to reach four fifths of
 * the dashboard. That is why it degrades loudly rather than quietly: a failed
 * tab fetch still leaves Latest Prices and a plain "Dashboard" entry
 * reachable. Once a Superset upgrade honours hideNav (sent only while a
 * section is pinned), the css block can go and that fallback view will get
 * Superset's own row back as its navigation.
 *
 * Presentational only — it does no fetching and knows nothing about the URL.
 */
export default function WinairTabBar({
  tabs, value, onChange, loading, switching, error,
}: WinairTabBarProps) {
  // With no usable section list, still offer a way into the embed. Superset
  // opens its own default section when no permalink pins one.
  const fallbackEntry: DashboardTab[] =
    !loading && tabs.length === 0 ? [{ id: DASHBOARD_TAB, label: 'Dashboard' }] : [];
  const entries = [...tabs, ...fallbackEntry];

  return (
    <Box
      sx={{
        bgcolor: BANNER_HEADER_BG,
        borderTopLeftRadius: 8,
        borderTopRightRadius: 8,
        borderBottom: `1px solid ${HAIRLINE}`,
        px: 1,
      }}
    >
      {loading ? (
        // Six entries: Latest Prices plus WinAir's five sections. A fixed
        // count keeps the bar from resizing when the real labels land.
        <Box sx={{ display: 'flex', gap: 2, py: 1.25, px: 1 }}>
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} variant="text" width={i === 0 ? 90 : 130} height={20}
                      sx={{ bgcolor: 'rgba(255,255,255,0.13)' }} />
          ))}
        </Box>
      ) : (
        <Tabs
          value={value}
          onChange={(_, next) => onChange(next)}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
          aria-label="WinAir dashboard sections"
          sx={{
            minHeight: 38,
            '& .MuiTabs-indicator': { height: 2, backgroundColor: '#ffffff' },
            '& .MuiTabs-scrollButtons.Mui-disabled': { opacity: 0.25 },
            '& .MuiTabs-scrollButtons': { color: LABEL_INK },
            '& .MuiTab-root': {
              minHeight: 38,
              py: 0.5,
              px: 1.5,
              fontSize: 12.5,
              fontWeight: 500,
              textTransform: 'none',
              color: LABEL_INK,
              gap: 0.75,
              '&.Mui-selected': { color: '#ffffff', fontWeight: 600 },
            },
          }}
        >
          <Tab
            value={PRICES_TAB}
            label="Latest Prices"
            icon={<ScatterPlot sx={{ fontSize: 15 }} />}
            iconPosition="start"
          />
          {entries.map(tab => (
            <Tab
              key={tab.id}
              value={tab.id}
              label={tab.label}
              // Progress sits on the tab being switched TO, so the wait is
              // attached to the thing the user just asked for.
              icon={
                switching && value === tab.id
                  ? <CircularProgress size={12} sx={{ color: LABEL_INK }} />
                  : undefined
              }
              iconPosition="start"
            />
          ))}
        </Tabs>
      )}

      {error && (
        <Alert
          severity="warning"
          sx={{
            py: 0,
            mb: 0.75,
            fontSize: 11.5,
            bgcolor: 'rgba(255,255,255,0.10)',
            color: '#ffd9d9',
            '& .MuiAlert-icon': { color: '#ffd9d9', py: 0.5 },
          }}
        >
          {error}
        </Alert>
      )}
    </Box>
  );
}
